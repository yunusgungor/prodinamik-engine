# Auto-Remediation

Prodinamik Engine v1.3 — Auto-Remediation

Automated recovery actions for common failure patterns.
Matches failure signatures to remediation strategies and
executes fixes automatically.

Architecture:
    FailurePatterns DB → FailureMatcher → RemediationEngine
                            ↓
                    Execute Action (auto/manual)

Pattern types:
    - Transient: retry, backoff
    - State: rollback, state fix
    - Resource: cleanup, eviction
    - Config: reset, reload

**Module:** `engine.autofix.py`

## Classes

### `FailureClass`(str, Enum)

### `RemediationType`(str, Enum)

### `AutoRemediationStatus`(str, Enum)

### `FailureSignature`

Signature of a failure pattern

**Methods:**

- `matches(error_message)`
  — Check if an error message matches this signature

### `RemediationAction`

A remediation action to take

**Methods:**

- `async execute(context)`
  — Execute the remediation action

### `RemediationPlan`

A complete remediation plan for a failure

**Methods:**

- `has_auto_remediation()`
- `to_dict()`

### `RemediationResult`

Result of a remediation execution

**Methods:**

- `to_dict()`

### `FailureMatcher`

Matches error messages to known failure patterns

**Methods:**

- `__init__(patterns)`
- `match(error_message)`
  — Match an error message to known patterns
- `best_match(error_message)`
  — Get the single best match for an error
- `classify(error_message)`
  — Classify an error into a failure class
- `add_pattern(pattern)`
  — Add a custom failure pattern
- `add_pattern_from(name, failure_class, match_patterns, description)`
  — Create and add a failure pattern

### `AutoRemediator`

Executes automated remediation for known failure patterns

Usage:
    remediator = AutoRemediator()
    plan = remediator.create_plan(error_message)
    result = await remediator.execute(plan, context)

**Methods:**

- `__init__(matcher)`
- `create_plan(error_message, run_context)`
  — Create a remediation plan for an error
- `_generate_actions(signature)`
  — Generate appropriate actions for a failure signature
- `_estimate_timeout(signature)`
  — Estimate timeout for a remediation plan
- `async execute(plan, context)`
  — Execute a remediation plan
- `async remediate(error_message, context)`
  — One-shot: match error → create plan → execute
- `get_stats()`
  — Get remediation statistics
- `recent_results(limit)`

## Functions

### `create_default_patterns()`

Create default failure patterns for the engine
