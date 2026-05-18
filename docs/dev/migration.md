# Migration Guide

This guide covers upgrading from older versions of the Prodinamik Engine. Each section details breaking changes, new features, migration steps, and CLI commands.

---

## v0.5 → v1.0: Core Engine & State Machine API

### What Changed

- **State machine definitions migrated from Python DSL to YAML.** The old `StateMachine` class hierarchy (`class MyMachine(StateMachine)`) was removed in favor of declarative YAML files.
- **Validator system replaced with 3-tier pipeline.** The single `validate()` method was split into `validate_t1()`, `validate_t2()`, `validate_t3()`.
- **Event store introduced.** Previously events were logged to stderr or discarded; now all transitions are written to the WAL-backed event store.
- **Removed API:** `StateMachine.run()`, `ValidatorRegistry`, `StateMachine.serialize()`.
- **New API:** `engine.Engine.execute()`, `engine.Profile`, `engine.RunManager`.

### What Broke

```python
# Old (v0.5) — removed
from engine import StateMachine

class MyMachine(StateMachine):
    initial = "draft"
    states = ["draft", "review", "published"]
    transitions = [
        {"trigger": "submit", "source": "draft", "dest": "review"}
    ]

sm = MyMachine()
sm.submit()  # Trigger method
```

```python
# Old (v0.5) — custom validators
class MyValidator:
    def validate(self, state, transition, context):
        return True
```

### How to Fix

```yaml
# New (v1.0) — YAML state machine definition
# save as: machines/publishing.yaml
states:
  - name: draft
    type: initial
  - name: review
    type: intermediate
  - name: published
    type: terminal
transitions:
  - name: submit
    source: draft
    dest: review
    type: REVERSIBLE
  - name: approve
    source: review
    dest: published
    type: IRREVERSIBLE
```

```python
# New (v1.0) — loading a state machine
from engine import Engine

engine = Engine()
engine.load_state_machine("publishing", "machines/publishing.yaml")
result = engine.execute("publishing", "submit")
```

```python
# New (v1.0) — 3-tier validator
from engine.validators import T1Validator, T2Validator, T3Validator

class SchemaValidator(T1Validator):
    def validate_t1(self, state, context):
        return "title" in context.inputs

class RubricValidator(T2Validator):
    def validate_t2(self, state, context):
        return self.score_rubric(context.inputs) > 0.7
```

### Migration CLI Commands

```bash
# Validate old DSL files against new YAML schema
prodinamik validate-migration --from dsl --input old_machines/

# Auto-convert old DSL to YAML
prodinamik migrate dsl-to-yaml --input old_machines.py --output machines/

# Test that converted YAML produces equivalent state machines
prodinamik test equivalence --old old_machines/ --new machines/
```

### Rollback

```bash
prodinamik migrate rollback --version 0.5
```

---

## v1.0 → v1.1: Async Runtime & Profile Changes

### What Changed

- **Synchronous engine replaced with async runtime.** `Engine` was wrapped in `AsyncEngine` with lifecycle hooks. The `engine.execute()` API is now async.
- **Introducation of profiles** — `content`, `software`, `research`, `design` — with predefined scaling and budget settings.
- **HTTP server added** for REST API access.
- **Raft consensus split** from monolithic `raft.py` into 3 modules (`types`, `consensus`, `cluster`).
- **State machine core split** from monolithic `state_machine.py` into 3 modules (`types`, `parser`, `runtime`).
- **New API:** `AsyncEngine`, `engine.Profile`, `engine.serve()`, `engine.RaftCluster`.
- **Removed API:** `Engine.run_forever()`, direct `StateMachine` instantiation.

### What Broke

```python
# Old (v1.0) — sync API removed
from engine import Engine

engine = Engine()
result = engine.execute("publishing", "submit")
print(result.status)
```

```bash
# Old (v1.0) — profile was a dict, not a typed object
PROFILE = {
    "max_concurrent_runs": 5,
    "budget_per_run": 0.50
}
```

### How to Fix

```python
# New (v1.1) — async API
import asyncio
from engine import AsyncEngine

async def main():
    engine = AsyncEngine()
    await engine.start()
    result = await engine.execute("publishing", "submit")
    print(result.status)
    await engine.stop()

asyncio.run(main())
```

```python
# New (v1.1) — typed profiles
from engine.profile import Profile

profile = Profile(
    name="content",
    max_concurrent_runs=10,
    budget_per_run=0.50,
    degradation_strategy="auto",
)
engine.load_profile(profile)
```

```bash
# New (v1.1) — profile selection via CLI
prodinamik run --profile content --sm publishing --transition submit
```

### Migration CLI Commands

```bash
# Upgrade profile files to v1.1 format
prodinamik migrate profiles --input profiles/ --output profiles_v1.1/

# Generate async wrapper for existing sync code
prodinamik scaffold async-wrapper --input my_engine.py --output my_engine_async.py

# Validate new profile schema
prodinamik validate profile --file profiles/content.yaml

# Auto-upgrade mkdocs config to v1.1 nav format
prodinamik migrate mkdocs --config mkdocs.yml
```

### Breaking Changes Checklist

- [ ] Replace all `Engine` with `AsyncEngine` and add `await engine.start()`/`await engine.stop()`
- [ ] Update profile dicts to typed `Profile` objects
- [ ] Move state machine loading to before `await engine.start()`
- [ ] Update CLI scripts to use `--profile` flag

---

## v1.1 → v1.2: Plugin Ecosystem & Auth System

### What Changed

- **Plugin system introduced.** Four new modules: `plugin.py`, `plugin_registry.py`, `hermes_bridge.py`, `plugin_repo.py`. CLI gained 10 plugin commands.
- **Authentication system added.** API key authentication with RBAC (admin/user/readonly roles). Rate limiter per key.
- **Registry became a singleton** — `Registry()` auto-discovers profiles and plugins.
- **New API:** `PluginBase`, `PluginRegistry`, `HermesPluginBridge`, `AuthManager`, `RateLimiter`.
- **Removed API:** `Registry(discover=True)`, manual key management.

### What Broke

```python
# Old (v1.1) — Registry was instantiated fresh
from engine.registry import Registry

reg = Registry(discover=True)
profile = reg.load_profile("content")
```

```bash
# Old (v1.1) — no auth in HTTP server
prodinamik serve --port 8080
```

### How to Fix

```python
# New (v1.2) — singleton registry
from engine.registry import Registry

reg = Registry()  # Now a singleton — auto-discovery is always on
profile = reg.get_profile("content")
```

```python
# New (v1.2) — plugin authoring
from engine.plugin import PluginBase

class SlackNotifier(PluginBase):
    name = "slack-notifier"
    version = "1.0.0"
    dependencies = ["requests>=2.0"]

    def on_load(self):
        self.webhook_url = self.config["webhook_url"]

    async def on_event(self, event, context):
        if event["type"] == "transition.failed":
            await self.post_to_slack(event)
```

```bash
# New (v1.2) — enable authentication
prodinamik serve --port 8080 --auth --api-key-file keys.json

# New (v1.2) — plugin management
prodinamik plugin install slack-notifier --source repo
prodinamik plugin enable slack-notifier
prodinamik plugin list
```

```python
# New (v1.2) — API key management
from engine.auth import AuthManager

auth = AuthManager()
auth.create_key("deploy-bot", role="admin")
auth.create_key("readonly-monitor", role="readonly")
```

### Migration CLI Commands

```bash
# Migrate existing registry cache to singleton format
prodinamik migrate registry --cache-file .registry_cache.pkl

# Generate API keys from existing config
prodinamik auth init --admin-key my-admin-key --output keys.json

# Convert old plugin stubs to PluginBase format
prodinamik scaffold plugin --name my-plugin --output plugins/

# Validate plugin compatibility
prodinamik plugin validate --path plugins/my-plugin/
```

### Plugin Migration Notes

- Old hook-based extensions (function callbacks) still work but won't get lifecycle management. Migrate to `PluginBase` to use `on_load`/`on_unload`/`on_event`.
- Plugins are auto-discovered from `~/.prodinamik/plugins/` and `./plugins/`.
- If your plugin reads engine internals directly, switch to `HermesPluginBridge` for a stable API surface.

---

## v1.2 → v1.3: AI-Native Features

### What Changed

- **5 new AI modules** added: `aidetect.py` (drift detection), `predict.py` (predictive degradation), `skillforge.py` (skill emergence), `recommend.py` (run recommender), `autofix.py` (auto-remediation).
- **4 new AI CLI commands:** `ai detect`, `ai predict`, `ai recommend`, `ai status`.
- **Plugin system upgraded** with dependency resolution and repository management.
- **Auto-remediation engine** — automatic failure detection and recovery with configurable escalation policies.
- **New API:** `AIDriftDetector`, `PredictiveDegrader`, `SkillForge`, `RunRecommender`, `AutoFixEngine`.
- **Configuration changes:** AI features require explicit enabling in the engine config or profile.

### What Broke

```python
# Old (v1.2) — engine config had no AI section
config = {
    "profile": "content",
    "max_runs": 10,
}
```

```bash
# Old (v1.2) — no AI CLI commands
# `prodinamik ai` was an unknown command
```

```python
# Old (v1.2) — plugin loading without dependency resolution
plugin_registry.load("my-plugin")
```

### How to Fix

```yaml
# New (v1.3) — engine config with AI section
# save as: config.yaml or profile override
engine:
  profile: content
  max_runs: 10
  ai:
    enabled: true
    drift_detection: true
    predictive_degradation: true
    auto_remediation: true
    skill_emergence: true
    run_recommender: true
```

```python
# New (v1.3) — using AI modules
from engine import AsyncEngine
from engine.aidetect import AIDriftDetector
from engine.predict import PredictiveDegrader
from engine.autofix import AutoFixEngine

engine = AsyncEngine()
await engine.start()

# Drift detection
detector = AIDriftDetector(engine)
drift_report = await detector.analyze()
print(f"Drift score: {drift_report.score}")

# Predictive degradation
predictor = PredictiveDegrader(engine)
forecast = await predictor.forecast("next_4_hours")
if forecast.threshold_breach_probability > 0.7:
    print("Warning: High chance of degradation")

# Auto-remediation
autofix = AutoFixEngine(engine)
await autofix.register_handler(
    pattern="validator.timeout",
    action="retry_max_3",
    cooldown=60,
)
```

```bash
# New (v1.3) — AI CLI commands
prodinamik ai detect --window 24h
prodinamik ai predict --horizon 4h
prodinamik ai recommend --sm publishing
prodinamik ai status
```

```python
# New (v1.3) — plugin dependency resolution
from engine.plugin_registry import PluginRegistry

reg = PluginRegistry()
reg.install("my-plugin", source="./plugins/", resolve_deps=True)
```

### Migration CLI Commands

```bash
# Upgrade config to v1.3 format with AI defaults
prodinamik migrate config --input config.yaml --output config.v1.3.yaml

# Enable AI features on existing profile
prodinamik profile edit content --ai-enabled

# Initialize auto-remediation rules
prodinamik scaffold autofix --rules-dir autofix-rules/

# Check AI feature readiness
prodinamik ai check-system

# Train initial drift detection baseline
prodinamik ai detect --baseline --output baseline.json

# Migrate plugin repository index
prodinamik plugin migrate-repo --index plugin_index.json
```

### Breaking Changes Checklist

- [ ] Add `ai: { enabled: true }` to engine config or profile YAML
- [ ] Update CI/CD to use `prodinamik ai check-system` as a pre-deployment gate
- [ ] Review auto-remediation escalation policies for production safety
- [ ] Train drift detection baseline before enabling in production
- [ ] Test that all existing plugins load with new dependency resolution

### Feature Flags

Each AI feature can be independently toggled:

```yaml
ai:
  enabled: true
  drift_detection: true      # ADR-009: trend/anomaly/emergence detection
  predictive_degradation: false  # ADR-009: forecasting (opt-in on high-traffic)
  auto_remediation: true     # ADR-009: self-healing (default on)
  skill_emergence: false     # ADR-009: auto SKILL.md gen (opt-in)
  run_recommender: true      # ADR-009: transition scoring
```

---

## Appendices

### Quick Reference: CLI Command Changes

| v0.5 | v1.0 | v1.1 | v1.2 | v1.3 |
|------|------|------|------|------|
| `run` | `run` | `run --profile` | `run --profile` | `run --profile` |
| — | `validate-migration` | — | — | — |
| — | `migrate dsl-to-yaml` | `migrate profiles` | `migrate registry` | `migrate config` |
| — | — | `serve` | `serve --auth` | `serve --auth` |
| — | — | — | `plugin install` | `plugin install --resolve-deps` |
| — | — | — | — | `ai detect` |
| — | — | — | — | `ai predict` |
| — | — | — | — | `ai recommend` |
| — | — | — | — | `ai status` |

### Version Compatibility Matrix

| From → To | Config Auto-Migrate | YAML State Machine | Python Validators | Plugin Files | Profile Files |
|-----------|-------------------|--------------------|----------------------|--------------|---------------|
| v0.5 → v1.0 | ❌ (manual) | ✅ (CLI tool) | ⚠️ (rewrite) | N/A | N/A |
| v1.0 → v1.1 | ✅ | ✅ | ✅ | N/A | ✅ (CLI tool) |
| v1.1 → v1.2 | ✅ | ✅ | ✅ | ✅ (CLI tool) | ✅ |
| v1.2 → v1.3 | ✅ (CLI tool) | ✅ | ✅ | ✅ (with deps) | ✅ (ai opt-in) |

### Need Help?

```bash
prodinamik migrate --help        # Show all migration commands
prodinamik version               # Check current engine version
prodinamik doctor                # System check for migration readiness
```

For breaking issues, see [troubleshooting.md](../troubleshooting.md) or open an issue at <https://github.com/yunusgungor/prodinamik-engine/issues>.
