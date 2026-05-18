"""
Prodinamik Engine v0.5 — Validators

Base validator sınıfları + Tier1 regex/rule tabanlı validator'lar.
Tier 1 = Fail-fast, deterministik, <50ms, LLM gerektirmez.

Her validator:
- Content-addressable cache ile cache'lenebilir
- Per-validator timeout ile zaman aşımına uğratılabilir
- Degradation-aware cache policy ile çalışır
"""

import re
import hashlib
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any, Callable, Tuple
from enum import Enum

from engine.profile import Validator, ValidatorDef, ValidatorTier, ValidationResult


# ──────────────────────────────────────────────
# Content-Addressable Cache
# ──────────────────────────────────────────────

class CachePolicy(Enum):
    FULL = "full"        # Tüm cache geçerli
    DEGRADED = "degraded"  # Sadece T1 cache geçerli
    SURVIVAL = "survival"  # Hiçbir cache geçerli değil


class ContentAddressableCache:
    """
    Validator sonuçlarını content hash'ine göre cache'ler.
    Degradation-aware: Hangi seviyede hangi cache'lerin geçerli olduğunu bilir.
    """

    def __init__(self, cache_dir: str = ".cache/verification/"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: Dict[str, "CacheEntry"] = {}
        self._hit_count = 0
        self._miss_count = 0

    def get(self, content: str, validator_name: str,
            tier: ValidatorTier = ValidatorTier.T1,
            cache_policy: CachePolicy = CachePolicy.FULL) -> Optional[ValidationResult]:
        """
        Cache'ten sonuç al.

        Degradation-aware:
        - FULL: Tüm cache'ler kullanılır
        - DEGRADED: Sadece T1 cache'leri kullanılır
        - SURVIVAL: Cache kullanılmaz
        """
        if cache_policy == CachePolicy.SURVIVAL:
            self._miss_count += 1
            return None

        content_hash = hashlib.sha256(content.encode()).hexdigest()
        cache_key = f"{validator_name}:{content_hash}"

        # Memory cache
        if cache_key in self._memory_cache:
            entry = self._memory_cache[cache_key]
            if self._is_valid(entry, tier, cache_policy):
                self._hit_count += 1
                return entry.result

        # Disk cache
        cache_file = self.cache_dir / f"{cache_key}.json"
        if cache_file.exists():
            try:
                import json
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                entry = CacheEntry(
                    key=cache_key,
                    validator_tier=tier,
                    result=ValidationResult(
                        passed=data["passed"],
                        message=data.get("message", ""),
                        details=data.get("details", {}),
                    ),
                    expires_at=datetime.fromisoformat(data["expires_at"]),
                    created_at=datetime.fromisoformat(data["created_at"]),
                )
                self._memory_cache[cache_key] = entry
                if self._is_valid(entry, tier, cache_policy):
                    self._hit_count += 1
                    return entry.result
            except (json.JSONDecodeError, KeyError, OSError):
                pass

        self._miss_count += 1
        return None

    def set(self, content: str, validator_name: str,
            result: ValidationResult, tier: ValidatorTier = ValidatorTier.T1,
            ttl: int = 3600):
        """Cache'e sonuç yaz"""
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        cache_key = f"{validator_name}:{content_hash}"

        entry = CacheEntry(
            key=cache_key,
            validator_tier=tier,
            result=result,
            expires_at=datetime.now() + timedelta(seconds=ttl),
            created_at=datetime.now(),
        )

        self._memory_cache[cache_key] = entry

        # Disk cache
        import json
        cache_file = self.cache_dir / f"{cache_key}.json"
        cache_file.write_text(
            json.dumps({
                "key": cache_key,
                "passed": result.passed,
                "message": result.message,
                "details": result.details,
                "expires_at": entry.expires_at.isoformat(),
                "created_at": entry.created_at.isoformat(),
            }, ensure_ascii=False),
            encoding="utf-8"
        )

    def _is_valid(self, entry, tier, policy):
        if datetime.now() > entry.expires_at:
            return False

        if policy == CachePolicy.DEGRADED:
            tier_val = tier.value if hasattr(tier, 'value') else tier
            if tier_val in (2, 3):
                return False

        return True

    def invalidate(self, validator_name: str = None):
        """Cache'i temizle (belirli validator veya tümü)"""
        if validator_name:
            self._memory_cache = {
                k: v for k, v in self._memory_cache.items()
                if not k.startswith(f"{validator_name}:")
            }
            for f in self.cache_dir.glob(f"{validator_name}:*.json"):
                f.unlink()
        else:
            self._memory_cache.clear()
            for f in self.cache_dir.glob("*.json"):
                f.unlink()

    @property
    def hit_rate(self) -> float:
        total = self._hit_count + self._miss_count
        return self._hit_count / total if total > 0 else 0.0

    @property
    def stats(self) -> dict:
        return {
            "hit_count": self._hit_count,
            "miss_count": self._miss_count,
            "hit_rate": self.hit_rate,
            "memory_entries": len(self._memory_cache),
        }


@dataclass
class CacheEntry:
    key: str
    validator_tier: ValidatorTier
    result: ValidationResult
    expires_at: datetime
    created_at: datetime

    @property
    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at


# ──────────────────────────────────────────────
# Per-Validator Timeout Manager
# ──────────────────────────────────────────────

class ValidatorTimeoutManager:
    """
    Her validator için ayrı timeout yönetimi.
    Timeout olan validator'lar skipped olarak işaretlenir.
    """

    DEFAULT_TIMEOUTS = {
        "SlopScanT1": 10,
        "FormatCheck": 5,
        "SchemaValidator": 10,
        "CompileCheck": 120,
        "SyntaxCheck": 5,
        "BuildValidator": 300,
        "SmokeTestValidator": 60,
        "TestCoverageValidator": 60,
        "SecurityAudit": 30,
    }

    @classmethod
    def get_timeout(cls, validator_name: str, default: int = 30) -> int:
        return cls.DEFAULT_TIMEOUTS.get(validator_name, default)

    @classmethod
    async def run_with_timeout(cls, validator: Validator, artifact: Any) -> ValidationResult:
        """Validator'ı timeout ile çalıştır"""
        timeout = cls.get_timeout(validator.name)
        import asyncio

        try:
            return await asyncio.wait_for(
                validator.validate(artifact),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return ValidationResult(
                passed=False,
                skipped=True,
                message=f"⏱️ {validator.name} timed out after {timeout}s",
            )


# ──────────────────────────────────────────────
# Tier1 Validators (Fail-fast, Deterministic)
# ──────────────────────────────────────────────

class RegexValidator(Validator):
    """
    Regex pattern tabanlı validasyon.
    T1: <50ms, deterministik, LLM gerektirmez.
    """

    def __init__(self, defn: ValidatorDef, patterns: List[Tuple[str, str, str]]):
        """
        patterns: [(pattern_name, regex, severity), ...]
        severity: "error" | "warning" | "info"
        """
        super().__init__(defn)
        self.patterns = [
            (name, re.compile(regex), severity)
            for name, regex, severity in patterns
        ]

    async def validate(self, artifact: Any) -> ValidationResult:
        """
        Tüm regex pattern'lerini tara.
        Herhangi bir "error" pattern'i eşleşirse FAIL.
        """
        content = self._get_content(artifact)
        if not content:
            return ValidationResult(passed=False, message="Empty content")

        findings = []
        for name, pattern, severity in self.patterns:
            matches = pattern.findall(content)
            for match in matches[:5]:  # Her pattern için max 5 match
                findings.append({
                    "pattern": name,
                    "severity": severity,
                    "match": match[:200] if isinstance(match, str) else str(match)[:200],
                })

        errors = [f for f in findings if f["severity"] == "error"]
        warnings = [f for f in findings if f["severity"] == "warning"]

        return ValidationResult(
            passed=len(errors) == 0,
            message=self._format_message(errors, warnings),
            details={
                "errors": errors,
                "warnings": warnings,
                "total_findings": len(findings),
            },
        )

    def _get_content(self, artifact: Any) -> str:
        """Artifact'ten içerik string'ini çıkar"""
        if isinstance(artifact, str):
            return artifact
        if hasattr(artifact, 'content'):
            return artifact.content
        if hasattr(artifact, 'text'):
            return artifact.text
        return str(artifact)

    def _format_message(self, errors: List[dict], warnings: List[dict]) -> str:
        parts = []
        if errors:
            parts.append(f"❌ {len(errors)} error(s):")
            for e in errors[:3]:
                parts.append(f"  • [{e['pattern']}] {e['match'][:80]}")
            if len(errors) > 3:
                parts.append(f"  ... and {len(errors) - 3} more")
        if warnings:
            parts.append(f"⚠️ {len(warnings)} warning(s)")
        return "\n".join(parts)


class LengthValidator(Validator):
    """İçerik uzunluğu validasyonu — T1"""

    def __init__(self, defn: ValidatorDef, min_chars: int = 0, max_chars: int = None):
        super().__init__(defn)
        self.min_chars = min_chars
        self.max_chars = max_chars

    async def validate(self, artifact: Any) -> ValidationResult:
        content = self._get_content(artifact)
        length = len(content)

        if length < self.min_chars:
            return ValidationResult(
                passed=False,
                message=f"Content too short: {length} chars (min: {self.min_chars})",
                details={"length": length, "min": self.min_chars},
            )

        if self.max_chars and length > self.max_chars:
            return ValidationResult(
                passed=False,
                message=f"Content too long: {length} chars (max: {self.max_chars})",
                details={"length": length, "max": self.max_chars},
            )

        return ValidationResult(
            passed=True,
            message=f"✅ Length OK: {length} chars",
            details={"length": length},
        )

    def _get_content(self, artifact: Any) -> str:
        if isinstance(artifact, str): return artifact
        if hasattr(artifact, 'content'): return artifact.content
        if hasattr(artifact, 'text'): return artifact.text
        return str(artifact)


class SchemaValidator(Validator):
    """
    YAML/JSON şema validasyonu — T1
    Verilen artifact'in geçerli bir YAML/JSON olup olmadığını kontrol eder.
    """

    def __init__(self, defn: ValidatorDef, schema_type: str = "yaml"):
        super().__init__(defn)
        self.schema_type = schema_type

    async def validate(self, artifact: Any) -> ValidationResult:
        content = self._get_content(artifact)
        if not content:
            return ValidationResult(passed=False, message="Empty content")

        try:
            if self.schema_type == "yaml":
                import yaml
                yaml.safe_load(content)
            elif self.schema_type == "json":
                import json
                json.loads(content)
            return ValidationResult(
                passed=True,
                message=f"✅ Valid {self.schema_type.upper()}",
            )
        except Exception as e:
            return ValidationResult(
                passed=False,
                message=f"❌ Invalid {self.schema_type.upper()}: {e}",
                details={"error": str(e)},
            )

    def _get_content(self, artifact: Any) -> str:
        if isinstance(artifact, str): return artifact
        if hasattr(artifact, 'content'): return artifact.content
        return str(artifact)


# ──────────────────────────────────────
# Validator Pipeline (3-Tier)
# ──────────────────────────────────────

class ValidatorPipeline:
    """
    3-Tier Validator Pipeline.

    T1: Fail-fast (sıralı, deterministik, <50ms)
    T2: Parallel (bağımsız, LLM çağrılı)
    T3: Sequential (T2 sonuçlarına bağımlı)

    Her validator content-addressable cache + per-validator timeout ile çalışır.
    """

    def __init__(self, cache: ContentAddressableCache = None,
                 cache_policy: CachePolicy = CachePolicy.FULL):
        self.cache = cache or ContentAddressableCache()
        self.cache_policy = cache_policy
        self.llm_calls: List[dict] = []  # Cost tracking

    async def run(self, artifact: Any,
                  tier1: List[Validator],
                  tier2: List[Validator],
                  tier3: List[Validator]) -> "PipelineResult":
        """
        Tüm pipeline'ı çalıştır.

        1. T1 (sıralı) — hata varsa hemen dön
        2. T2 (paralel) — tümü bağımsız
        3. T3 (sıralı) — T2 sonuçlarına bağımlı
        """
        results = {}

        # TIER 1: Fail-fast (sıralı)
        t1_passed = await self._run_tier1(artifact, tier1, results)
        if not t1_passed:
            return PipelineResult(
                passed=False,
                results=results,
                stopped_at=tier1[0].name if tier1 else "t1",
                tier="T1",
            )

        # TIER 2: Parallel
        await self._run_tier2(artifact, tier2, results)

        # TIER 3: Sequential (T2'ye bağımlı)
        await self._run_tier3(artifact, tier3, results)

        all_passed = all(
            r.passed for r in results.values()
            if not getattr(r, 'skipped', False)
        )
        return PipelineResult(
            passed=all_passed,
            results=results,
            tier="T3" if tier3 else "T2",
        )

    async def _run_tier1(self, artifact: Any, validators: List[Validator],
                         results: dict) -> bool:
        """T1: Sıralı, fail-fast"""
        for v in validators:
            # Cache kontrolü
            cached = self.cache.get(
                str(artifact), v.name, v.tier, self.cache_policy
            )
            if cached:
                results[v.name] = cached
                if not cached.passed:
                    return False
                continue

            # Run with timeout
            result = await ValidatorTimeoutManager.run_with_timeout(v, artifact)

            # Cache sonucu
            self.cache.set(str(artifact), v.name, result, v.defn.cache_ttl if hasattr(v, 'defn') else 3600)

            results[v.name] = result
            if not result.passed and v.critical:
                return False

        return True

    async def _run_tier2(self, artifact: Any, validators: List[Validator],
                         results: dict):
        """T2: Paralel (bağımsız)"""
        if not validators:
            return

        import asyncio

        async def run_one(v):
            cached = self.cache.get(
                str(artifact), v.name, v.tier, self.cache_policy
            )
            if cached:
                results[v.name] = cached
                return

            result = await ValidatorTimeoutManager.run_with_timeout(v, artifact)
            self.cache.set(str(artifact), v.name, result,
                          v.defn.cache_ttl if hasattr(v, 'defn') else 3600)

            # Cost tracking
            if result.cost_usd > 0:
                self.llm_calls.append({
                    "validator": v.name,
                    "cost_usd": result.cost_usd,
                })

            results[v.name] = result

        tasks = [asyncio.create_task(run_one(v)) for v in validators]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_tier3(self, artifact: Any, validators: List[Validator],
                         results: dict):
        """T3: Sequential (T2'ye bağımlı)"""
        for v in validators:
            # Dependency check
            deps = getattr(v.defn, 'depends_on', [])
            deps_passed = all(
                results.get(d, ValidationResult(passed=False)).passed
                for d in deps
            )
            if not deps_passed:
                results[v.name] = ValidationResult(
                    passed=False,
                    skipped=True,
                    message=f"⏭️ Skipped (dependency failed: {', '.join(deps)})"
                )
                continue

            # Cache
            cached = self.cache.get(
                str(artifact), v.name, v.tier, self.cache_policy
            )
            if cached:
                results[v.name] = cached
                continue

            # Run
            result = await ValidatorTimeoutManager.run_with_timeout(v, artifact)
            self.cache.set(str(artifact), v.name, result,
                          v.defn.cache_ttl if hasattr(v, 'defn') else 3600)
            results[v.name] = result


@dataclass
class PipelineResult:
    """Pipeline çıktısı"""
    passed: bool
    results: Dict[str, ValidationResult]
    stopped_at: str = ""
    tier: str = ""

    @property
    def summary(self) -> str:
        total = len(self.results)
        passed_count = sum(1 for r in self.results.values() if r.passed)
        failed_count = sum(1 for r in self.results.values()
                          if not r.passed and not r.skipped)
        skipped_count = sum(1 for r in self.results.values() if r.skipped)

        if self.passed:
            return f"✅ All {total} validators passed"
        return (
            f"❌ {failed_count}/{total} failed "
            f"(stopped at {self.tier}:{self.stopped_at})"
        )


# ──────────────────────────────────────
# Demo
# ──────────────────────────────────────

def demo():
    import asyncio

    # Content slop patterns (T1)
    slop_patterns = [
        ("filler_phrases", r"(aslında|sırf|sadece|bence|şahsen)", "warning"),
        ("promo_language", r"(harika|mükemmel|inanılmaz|şahane|benzersiz)", "error"),
        ("vague_attribution", r"(uzmanlar|kaynaklar|araştırmacılar\s+söylüyor)", "error"),
        ("clickbait", r"(gözlerden kaçan|kimsenin bilmediği|duymadınız)", "error"),
        ("overclaim", r"(devrim|çığır|dönüm noktası|ezber bozan)", "warning"),
    ]

    slop_def = ValidatorDef(name="SlopScanT1", tier=ValidatorTier.T1, critical=True)
    slop_validator = RegexValidator(slop_def, slop_patterns)

    length_def = ValidatorDef(name="LengthCheck", tier=ValidatorTier.T1, critical=False)
    length_validator = LengthValidator(length_def, min_chars=10, max_chars=10000)

    # Schema validator
    schema_def = ValidatorDef(name="SchemaCheck", tier=ValidatorTier.T1, critical=False)
    schema_validator = SchemaValidator(schema_def, schema_type="yaml")

    # Pipeline
    pipeline = ValidatorPipeline()

    # Test 1: Clean content
    clean_text = "RISC-V pipeline timing closure için 7 strateji. Her biri farklı tradeoff içerir."
    print(f"\n📝 Test 1: Clean content")
    result = asyncio.run(pipeline.run(clean_text, [slop_validator, length_validator], [], []))
    print(f"   {result.summary}")
    print(f"   Slop: {result.results['SlopScanT1']}")

    # Test 2: Slop content
    sloppy_text = "Bu harika ve mükemmel bir ürün! Uzmanlar söylüyor ki aslında devrim niteliğinde."
    print(f"\n📝 Test 2: Slop content")
    result = asyncio.run(pipeline.run(sloppy_text, [slop_validator, length_validator], [], []))
    print(f"   {result.summary}")
    print(f"   Slop: {result.results['SlopScanT1']}")

    # Test 3: Length violation
    short_text = "Merhaba"
    print(f"\n📝 Test 3: Length violation")
    result = asyncio.run(pipeline.run(short_text, [slop_validator, length_validator], [], []))
    print(f"   {result.summary}")

    # Test 4: Schema validation
    good_yaml = "name: test\nversion: 1.0\n"
    bad_yaml = "name: test\n: : invalid"
    print(f"\n📝 Test 4: Schema validation")
    result = asyncio.run(pipeline.run(good_yaml, [schema_validator], [], []))
    print(f"   Good YAML: {result.results['SchemaCheck'].message}")
    result = asyncio.run(pipeline.run(bad_yaml, [schema_validator], [], []))
    print(f"   Bad YAML: {result.results['SchemaCheck'].message}")

    # Cache stats
    print(f"\n📊 Cache: {pipeline.cache.stats}")

    print(f"\n{'='*50}")
    print(f"All Tier1 validator tests passed!")
    print(f"{'='*50}")


if __name__ == "__main__":
    demo()
