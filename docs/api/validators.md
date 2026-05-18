# Validator Pipeline

Prodinamik Engine v0.5 — 3-Tier Validation System

The validator pipeline is the core quality gate of the Prodinamik Engine. Every artifact (run output, state transition payload, or product deliverable) passes through a configurable chain of validators that enforce correctness, quality, and safety.

**Module:** `engine.validators.py` (627 lines, 9 classes, 19 functions)

---

## Overview

The validation system is built on a **3-tier architecture**:

| Tier | Name | Execution | Timing | Characteristics |
|------|------|-----------|--------|----------------|
| T1 | Fail-fast | Sequential | <50ms | Regex/rule-based, deterministic, no LLM |
| T2 | Semantic | Parallel | 10-60s | LLM-based, independent checks |
| T3 | Formal | Sequential | 30-300s | Depends on T2 results, deep verification |

Each validator is wrapped with:

- **Content-addressable caching** — results are keyed by SHA-256 of the input content
- **Per-validator timeout management** — each validator has a configurable deadline
- **Degradation-aware cache policy** — cache behavior changes under system stress

---

## CachePolicy

```python
class CachePolicy(Enum):
    FULL = "full"        # All caches valid
    DEGRADED = "degraded"  # Only T1 caches valid
    SURVIVAL = "survival"  # No caches valid
```

Controls how the `ContentAddressableCache` behaves under different system health levels:

- **FULL** — All cached results (T1, T2, T3) are returned from cache when available
- **DEGRADED** — Only T1 (fail-fast) cached results are used; T2/T3 caches are bypassed to force fresh evaluation
- **SURVIVAL** — All caching is bypassed; every validation runs from scratch

---

## ContentAddressableCache

Keys validator results by SHA-256 of the input content, so identical artifacts never trigger redundant validation.

```python
cache = ContentAddressableCache(cache_dir=".cache/verification/")
```

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `get` | `(content, validator_name, tier, cache_policy) -> Optional[ValidationResult]` | Read from cache; respects degradation policy |
| `set` | `(content, validator_name, result, tier, ttl=3600)` | Write result to memory + disk cache |
| `invalidate` | `(validator_name=None)` | Clear cache for one validator or all |
| `hit_rate` | *property* `-> float` | Cache hit ratio (0.0–1.0) |
| `stats` | *property* `-> dict` | hit_count, miss_count, hit_rate, memory_entries |

### Degradation-Aware Lookup Logic

```python
def _is_valid(entry, tier, policy):
    if datetime.now() > entry.expires_at:
        return False
    if policy == CachePolicy.DEGRADED and tier in (2, 3):
        return False
    return True
```

### Example

```python
cache = ContentAddressableCache()
result = cache.get(content, "SlopScanT1", ValidatorTier.T1, CachePolicy.FULL)
if result:
    print(f"Cache hit: {result}")
else:
    # ... run validation ...
    cache.set(content, "SlopScanT1", result, ValidatorTier.T1, ttl=3600)

print(f"Hit rate: {cache.hit_rate:.1%}")
print(f"Stats: {cache.stats}")
```

---

## CacheEntry

```python
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
```

---

## ValidatorTimeoutManager

Prevents runaway validators by enforcing per-validator deadlines. Timed-out validators are marked as `skipped` rather than `failed`.

### Default Timeouts

| Validator Name | Timeout (s) |
|----------------|-------------|
| SlopScanT1 | 10 |
| FormatCheck | 5 |
| SchemaValidator | 10 |
| CompileCheck | 120 |
| SyntaxCheck | 5 |
| BuildValidator | 300 |
| SmokeTestValidator | 60 |
| TestCoverageValidator | 60 |
| SecurityAudit | 30 |

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `get_timeout` | `(validator_name, default=30) -> int` | Lookup timeout for a validator |
| `run_with_timeout` | `async (validator, artifact) -> ValidationResult` | Execute with timeout wrapping |

### Example

```python
timeout = ValidatorTimeoutManager.get_timeout("SlopScanT1")  # 10s
result = await ValidatorTimeoutManager.run_with_timeout(my_validator, artifact)
if result.skipped:
    print(f"⏱️ Validator timed out: {result.message}")
```

---

## RegexValidator

Pattern-based validation using regular expressions. Scans content for forbidden patterns, promotional language, clickbait, and vague attributions.

**Tier:** T1 (fail-fast, deterministic, <50ms)

```python
patterns = [
    ("filler_phrases", r"(aslında|sırf|sadece|bence|şahsen)", "warning"),
    ("promo_language", r"(harika|mükemmel|inanılmaz)", "error"),
    ("vague_attribution", r"(uzmanlar|kaynaklar\s+söylüyor)", "error"),
    ("clickbait", r"(gözlerden kaçan|kimsenin bilmediği)", "error"),
    ("overclaim", r"(devrim|çığır|dönüm noktası)", "warning"),
]

validator = RegexValidator(
    ValidatorDef(name="SlopScanT1", tier=ValidatorTier.T1, critical=True),
    patterns,
)

result = await validator.validate(content)
```

### Parameters

| Param | Type | Description |
|-------|------|-------------|
| `defn` | `ValidatorDef` | Validator definition with name, tier, critical flag |
| `patterns` | `List[Tuple[str, str, str]]` | `[(pattern_name, regex, severity), ...]` where severity is `"error"`, `"warning"`, or `"info"` |

### Methods

| Method | Description |
|--------|-------------|
| `validate(artifact)` | Run all regex patterns; fails on any `"error"` match |
| `_get_content(artifact)` | Extract string content from artifact (string, `.content`, `.text`, or `str()`) |
| `_format_message(errors, warnings)` | Build human-readable result message |

### Validation Logic

- Scans content with all compiled regex patterns
- Collects up to 5 matches per pattern
- **FAIL** if any `"error"`-severity pattern matches
- Returns warnings and info findings in `details`

---

## LengthValidator

Enforces minimum and maximum content length.

**Tier:** T1

```python
validator = LengthValidator(
    ValidatorDef(name="LengthCheck", tier=ValidatorTier.T1, critical=False),
    min_chars=10,
    max_chars=10000,
)
result = await validator.validate(content)
```

### Parameters

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `defn` | `ValidatorDef` | required | Validator definition |
| `min_chars` | `int` | 0 | Minimum character count |
| `max_chars` | `int` | `None` | Maximum character count (`None` = no limit) |

---

## SchemaValidator

Validates that content is well-formed YAML or JSON.

**Tier:** T1

```python
yaml_validator = SchemaValidator(
    ValidatorDef(name="SchemaCheck", tier=ValidatorTier.T1),
    schema_type="yaml",
)
json_validator = SchemaValidator(
    ValidatorDef(name="JSONSchemaCheck", tier=ValidatorTier.T1),
    schema_type="json",
)
```

### Parameters

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `defn` | `ValidatorDef` | required | Validator definition |
| `schema_type` | `str` | `"yaml"` | `"yaml"` or `"json"` |

---

## ValidatorPipeline

Orchestrates the 3-tier validation flow. T1 runs first (sequential, fail-fast), then T2 (parallel), then T3 (sequential, dependent on T2).

```python
pipeline = ValidatorPipeline(
    cache=ContentAddressableCache(),
    cache_policy=CachePolicy.FULL,
)

result = await pipeline.run(
    artifact=content,
    tier1=[regex_validator, length_validator],
    tier2=[llm_semantic_validator],
    tier3=[formal_verification_validator],
)
```

### Pipeline Flow

```
       ┌─────────────┐
       │   Artifact   │
       └──────┬──────┘
              ▼
    ┌─────────────────┐
    │  T1: Sequential  │  <── fail-fast
    │  (regex, schema, │      if any critical fails → STOP
    │   length, ...)   │
    └────────┬────────┘
             │ (all passed)
             ▼
    ┌─────────────────┐
    │  T2: Parallel    │  <── independent LLM checks
    │  (semantic,      │      all run concurrently
    │   safety, ...)   │
    └────────┬────────┘
             │ (all finished)
             ▼
    ┌─────────────────┐
    │  T3: Sequential  │  <── depends on T2 results
    │  (formal, deep   │      skipped if dependency failed
    │   verification)  │
    └────────┬────────┘
             ▼
    ┌─────────────────┐
    │ PipelineResult   │
    │ passed / failed  │
    └─────────────────┘
```

### Methods

| Method | Description |
|--------|-------------|
| `run(artifact, tier1, tier2, tier3)` | Full pipeline execution |
| `_run_tier1(artifact, validators, results)` | Sequential T1 with cache + timeout |
| `_run_tier2(artifact, validators, results)` | Parallel T2 via `asyncio.gather` |
| `_run_tier3(artifact, validators, results)` | Sequential T3 with dependency checks |

### Dependency Resolution (T3)

T3 validators declare `depends_on` in their `ValidatorDef`. If any dependency failed, the T3 validator is automatically skipped:

```python
result = await pipeline.run(artifact, tier1, tier2, [deep_check])
if result.results["DeepCheck"].skipped:
    print("DeepCheck skipped: dependency failed")
```

---

## PipelineResult

```python
@dataclass
class PipelineResult:
    passed: bool
    results: Dict[str, ValidationResult]
    stopped_at: str = ""
    tier: str = ""

    @property
    def summary(self) -> str:
        ...
```

### Example Output

```python
result = await pipeline.run(...)
print(result.summary)
# "✅ All 5 validators passed"
# or
# "❌ 2/5 failed (stopped at T1:SlopScanT1)"
```

---

## CrossValidator (Planned)

Validates consistency between related artifacts. For example, verifying that a Rust `Cargo.toml` and `Cargo.lock` are in sync, or that a YAML spec matches its output.

*Not yet implemented in v0.5 — reserved for T3 usage.*

---

## Usage Examples

### Complete Pipeline with Cache

```python
import asyncio
from engine.profile import ValidatorDef, ValidatorTier, ValidationResult
from engine.validators import (
    RegexValidator, LengthValidator, SchemaValidator,
    ValidatorPipeline, ContentAddressableCache, CachePolicy,
)

async def validate_content(content: str) -> bool:
    # T1: Slop scan
    slop_patterns = [
        ("promo_language", r"(harika|mükemmel|inanılmaz)", "error"),
        ("clickbait", r"(gözlerden kaçan|duymadınız)", "error"),
    ]
    slop = RegexValidator(
        ValidatorDef("SlopScanT1", ValidatorTier.T1, critical=True),
        slop_patterns,
    )
    length = LengthValidator(
        ValidatorDef("LengthCheck", ValidatorTier.T1),
        min_chars=10, max_chars=50000,
    )

    pipeline = ValidatorPipeline(cache_policy=CachePolicy.FULL)
    result = await pipeline.run(content, [slop, length], [], [])

    print(result.summary)
    for name, r in result.results.items():
        status = "✅" if r.passed else ("⏭️" if r.skipped else "❌")
        print(f"  {status} {name}: {r.message}")

    return result.passed

asyncio.run(validate_content("RISC-V pipeline timing closure için 7 strateji."))
```

### Cache Statistics

```python
pipeline = ValidatorPipeline()
# ... run validations ...
stats = pipeline.cache.stats
print(f"Cache hit rate: {stats['hit_rate']:.1%}")
print(f"Memory entries: {stats['memory_entries']}")
```

### Invalidating Cache

```python
# Invalidate specific validator
pipeline.cache.invalidate("SlopScanT1")

# Invalidate all
pipeline.cache.invalidate()

# After invalidation, hit rate resets
print(pipeline.cache.hit_rate)  # 0.0
```

---

## Reference: Complete Class Hierarchy

```
Validator (ABC, from engine.profile)
├── RegexValidator       # T1: regex pattern matching
├── LengthValidator      # T1: content length bounds
├── SchemaValidator      # T1: YAML/JSON structure check
└── [T2/T3 custom]       # user-implemented

ContentAddressableCache   # SHA-256 keyed cache
ValidatorTimeoutManager   # per-validator deadlines
ValidatorPipeline         # 3-tier orchestrator

CachePolicy (Enum)        # FULL | DEGRADED | SURVIVAL
CacheEntry (dataclass)    # cache item with expiry
PipelineResult (dataclass)# pipeline output
```

---

## Reference: Key Functions

| Function | Source | Description |
|----------|--------|-------------|
| `demo()` | `validators.py:564` | Runs T1 validation demo with slop/length/schema checks |

Related modules: `engine.profile.py` (Validator base class, ValidationResult), `engine.degradation.py` (degradation levels), `engine.chaos.py` (degraded-mode fault injection).
