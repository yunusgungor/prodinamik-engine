"""
Prodinamik Engine v0.5 — Product Profile Base Class

Her ürün tipi (Content, Software, Research, ...) bir ProductProfile olarak
tanımlanır. Profile, state machine, validator set'i, adapter listesi,
store şeması, template'ler ve budget tanımını içerir.

Kullanım:
    class SoftwareProfile(ProductProfile):
        name = "software"
        version = "1.0"
        ...
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Type, Any, Callable
from pathlib import Path
from enum import Enum

from engine.state_machine import (
    StateMachine, StateMachineConfig, StateMachineParser,
    StateDefinition, TransitionDefinition, RuntimeState,
    TransitionType, StateType,
)
from engine.sm_types import HITLConfig, AskDirective, ConditionalAsk


# ──────────────────────────────────────────────
# Budget
# ──────────────────────────────────────────────

@dataclass
class Budget:
    """Per-profile resource budget"""
    max_concurrent_validators: int = 2
    max_llm_calls_per_run: int = 20
    max_storage_mb: int = 100
    timeout_per_state: int = 3600
    max_wal_entries: int = 1000
    soft_limit_usd: float = 1.0
    hard_limit_usd: float = 5.0


# ──────────────────────────────────────────────
# Validator Definition
# ──────────────────────────────────────────────

class ValidatorTier(Enum):
    T1 = 1  # Fail-fast (deterministic, <50ms)
    T2 = 2  # Parallel (independent, LLM)
    T3 = 3  # Sequential (depends on T2)


@dataclass
class ValidatorDef:
    """Validator tanımı (profile YAML'de kullanılır)"""
    name: str
    tier: ValidatorTier
    critical: bool = False
    timeout_seconds: int = 120
    depends_on: List[str] = field(default_factory=list)
    cache_ttl: int = 3600
    model: Optional[str] = None          # T2/T3 için LLM model
    runner: Optional[str] = None         # T1 için CLI runner


# ──────────────────────────────────────────────
# Adapter Definition
# ──────────────────────────────────────────────

@dataclass
class AdapterDef:
    """Adapter tanımı"""
    name: str
    type: str  # "buffer" | "crates_io" | "github" | "file" | "docker"
    config: dict = field(default_factory=dict)
    fallback_mode: str = "file"  # "file" | "queue" | "skip"
    max_retries: int = 3
    circuit_breaker_threshold: int = 3


# ──────────────────────────────────────────────
# Store Schema
# ──────────────────────────────────────────────

@dataclass
class StoreDef:
    """Store tipi tanımı"""
    name: str
    type: str  # "markdown" | "json" | "yaml" | "toml" | "binary"
    path: str  # Relative to run dir
    required: bool = False


# ──────────────────────────────────────────────
# Template
# ──────────────────────────────────────────────

@dataclass
class TemplateDef:
    """Template tanımı"""
    name: str
    path: str  # Relative to profile dir
    description: str = ""


# ──────────────────────────────────────────────
# Validator Base Class
# ──────────────────────────────────────────────

class Validator(ABC):
    """Base validator sınıfı. Her ValidatorDef için bir instance."""

    def __init__(self, defn: ValidatorDef):
        self.defn = defn
        self.name = defn.name
        self.tier = defn.tier
        self.critical = defn.critical

    @abstractmethod
    async def validate(self, artifact: Any) -> "ValidationResult":
        ...

    async def auto_fix(self, artifact: Any) -> Any:
        """Opsiyonel: otomatik düzeltme"""
        return artifact

    def explain(self, result: "ValidationResult") -> str:
        """Validasyon sonucunu açıkla"""
        if result.passed:
            return f"✅ {self.name}: passed"
        return f"❌ {self.name}: {result.message}"


@dataclass
class ValidationResult:
    """Validator çıktısı"""
    passed: bool
    message: str = ""
    details: dict = field(default_factory=dict)
    skipped: bool = False
    cost_usd: float = 0.0


# ──────────────────────────────────────────────
# Adapter Base Class
# ──────────────────────────────────────────────

class Adapter(ABC):
    """Base adapter sınıfı. Circuit breaker + fallback içerir."""

    def __init__(self, defn: AdapterDef):
        self.defn = defn
        self.name = defn.name
        self.failure_count = 0
        self.circuit_open = False
        self.last_failure_time = None

    @abstractmethod
    async def _send(self, artifact: Any) -> "AdapterResult":
        """Gerçek gönderme işlemi (alt sınıflar override eder)"""
        ...

    async def send(self, artifact: Any) -> "AdapterResult":
        """Circuit breaker + retry + fallback ile send"""
        if self.circuit_open:
            return await self._fallback(artifact)

        for attempt in range(self.defn.max_retries):
            try:
                result = await self._send(artifact)
                self.failure_count = 0
                return result
            except TransientError:
                import asyncio
                backoff = [1, 5, 30]
                if attempt < len(backoff):
                    await asyncio.sleep(backoff[attempt])
                    continue
                self._record_failure()
                return await self._fallback(artifact)
            except PermanentError:
                self._record_failure()
                return await self._fallback(artifact)

        return await self._fallback(artifact)

    def _record_failure(self):
        self.failure_count += 1
        self.last_failure_time = __import__('datetime').datetime.now()
        if self.failure_count >= self.defn.circuit_breaker_threshold:
            self.circuit_open = True

    async def _fallback(self, artifact: Any) -> "AdapterResult":
        """Varsayılan fallback: artifact'i dosyaya yaz"""
        from pathlib import Path
        from datetime import datetime

        fallback_dir = Path(f".fallback/{self.name}")
        fallback_dir.mkdir(parents=True, exist_ok=True)
        path = fallback_dir / f"{datetime.now().isoformat()}.json"

        if hasattr(artifact, 'json'):
            content = artifact.json()
        else:
            content = str(artifact)

        path.write_text(content, encoding="utf-8")

        return AdapterResult(
            success=True,
            message=f"Adapter {self.name} failed. Saved to {path}",
            fallback=True,
        )


class TransientError(Exception):
    """Geçici hata (retry yapılabilir)"""
    pass


class PermanentError(Exception):
    """Kalıcı hata (retry yapılamaz)"""
    pass


@dataclass
class AdapterResult:
    """Adapter çıktısı"""
    success: bool
    message: str = ""
    fallback: bool = False
    url: Optional[str] = None
    cost_usd: float = 0.0


# ──────────────────────────────────────────────
# Product Profile — Abstract
# ──────────────────────────────────────────────

class ProductProfile(ABC):
    """
    Bir ürün tipini tanımlar.

    Alt sınıflar şunları TANIMLAMALIDIR:
    - name: str
    - version: str
    - _state_machine_yaml: str (inline YAML veya path)

    Alt sınıflar ŞUNLARI OVERRIDE EDEBİLİR:
    - setup_validators()
    - setup_adapters()
    - setup_stores()
    - setup_templates()
    - setup_budget()
    """

    name: str = "unnamed"
    version: str = "0.0.0"
    description: str = ""

    # YAML state machine tanımı (inline string veya file path)
    state_machine_yaml: str = ""

    def __init__(self):
        self._state_machine: Optional[StateMachine] = None
        self._validators: List[ValidatorDef] = []
        self._adapters: List[AdapterDef] = []
        self._stores: List[StoreDef] = []
        self._templates: List[TemplateDef] = []
        self._budget: Budget = Budget()
        self._initialized = False

    def initialize(self):
        """Profile'i başlat. State machine'i yükle, validator'ları setup et."""
        if self._initialized:
            return

        # State machine
        if self.state_machine_yaml:
            config = StateMachineParser.parse_string(self.state_machine_yaml)
            self._state_machine = StateMachine(config)

        # Setup hooks
        self.setup_validators()
        self.setup_adapters()
        self.setup_stores()
        self.setup_templates()
        self.setup_budget()

        self._initialized = True

    @property
    def state_machine(self) -> Optional[StateMachine]:
        if not self._initialized:
            self.initialize()
        return self._state_machine

    # ──────────────────────────────────────
    # Setup Hooks (override edilebilir)
    # ──────────────────────────────────────

    def setup_validators(self):
        """Validator'ları tanımla"""
        pass

    def setup_adapters(self):
        """Adapter'ları tanımla"""
        pass

    def setup_stores(self):
        """Store şemasını tanımla"""
        pass

    def setup_templates(self):
        """Template'leri tanımla"""
        pass

    def setup_budget(self):
        """Budget'ı yapılandır"""
        pass

    # ──────────────────────────────────────
    # Profile Metadata
    # ──────────────────────────────────────

    @property
    def validators(self) -> List[ValidatorDef]:
        return list(self._validators)

    @property
    def tier1_validators(self) -> List[ValidatorDef]:
        return [v for v in self._validators if v.tier == ValidatorTier.T1]

    @property
    def tier2_validators(self) -> List[ValidatorDef]:
        return [v for v in self._validators if v.tier == ValidatorTier.T2]

    @property
    def tier3_validators(self) -> List[ValidatorDef]:
        return [v for v in self._validators if v.tier == ValidatorTier.T3]

    @property
    def adapters(self) -> List[AdapterDef]:
        return list(self._adapters)

    @property
    def stores(self) -> List[StoreDef]:
        return list(self._stores)

    @property
    def templates(self) -> List[TemplateDef]:
        return list(self._templates)

    @property
    def budget(self) -> Budget:
        return self._budget

    def add_validator(self, defn: ValidatorDef):
        self._validators.append(defn)

    def add_adapter(self, defn: AdapterDef):
        self._adapters.append(defn)

    def add_store(self, defn: StoreDef):
        self._stores.append(defn)

    def add_template(self, defn: TemplateDef):
        self._templates.append(defn)

    # ──────────────────────────────────────
    # Display
    # ──────────────────────────────────────

    def summary(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "state_machine": repr(self._state_machine) if self._state_machine else "none",
            "validators": f"{len(self.tier1_validators)}T1 + {len(self.tier2_validators)}T2 + {len(self.tier3_validators)}T3",
            "adapters": [a.name for a in self._adapters],
            "stores": [s.name for s in self._stores],
            "budget": {
                "soft_limit": self._budget.soft_limit_usd,
                "hard_limit": self._budget.hard_limit_usd,
            },
        }

    def __repr__(self):
        return (f"ProductProfile(name={self.name}, v{self.version}, "
                f"validators={len(self._validators)}, "
                f"adapters={len(self._adapters)})")
