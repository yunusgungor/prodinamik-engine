# Run Recommender

Prodinamik Engine v1.3 — Intelligent Run Recommender

Suggests optimal state transitions, next actions, and
profile configurations based on historical run data.

Architecture:
    HistoricalRunData → TransitionMatrix → SuccessPredictor
                              ↓
                      NextBestAction Recommender

Key features:
    - Transition success probability (based on history)
    - Optimal next state suggestion
    - Profile-specific recommendations
    - Bottleneck detection

**Module:** `engine.recommend.py`

## Classes

### `TransitionRecord`

Record of a state transition

### `TransitionStats`

Statistics for a specific transition

**Methods:**

- `success_rate()`
- `reliability()`
- `to_dict()`

### `Recommendation`

A recommended action for a run

**Methods:**

- `to_dict()`

### `TransitionHistory`

Collects and analyzes transition records

**Methods:**

- `__init__(max_records)`
- `record(run_id, profile, from_state, to_state, duration_seconds, success, error)`
  — Record a transition
- `get_transitions(from_state, profile, since, limit)`
  — Query transitions with filters
- `total_count()`
- `total_successful()`
- `success_rate()`

### `TransitionAnalyzer`

Analyzes transition patterns and computes statistics

**Methods:**

- `__init__(history)`
- `analyze(from_state, profile)`
  — Analyze transitions, optionally filtered
- `get_possible_transitions(state)`
  — Get all states reachable from a given state
- `get_most_common(limit)`
  — Get the most frequently attempted transitions
- `get_bottlenecks()`
  — Find problematic transitions (low success, high duration)

### `RunRecommender`

Recommends optimal next state for a run

Scoring factors:
- Historical success rate of the transition
- Frequency of use (popularity)
- Recency (last used)
- Profile compatibility

**Methods:**

- `__init__(history, analyzer)`
- `recommend(run_id, current_state, profile, top_n)`
  — Get the best next state recommendations for a run
- `_get_valid_targets(current_state, profile)`
  — Get valid next states from history and state machine
- `_score_transition(from_state, to_state, profile)`
  — Score a possible transition (0.0 - 1.0)
- `_generate_reasoning(from_state, to_state, profile)`
  — Generate human-readable reasoning for recommendation
- `_estimate_duration(from_state, to_state)`
  — Estimate transition duration in seconds
- `_get_warnings(from_state, to_state)`
  — Get warnings for a transition

### `AIRecommender`

Facade for intelligent recommendation capabilities

Usage:
    recommender = AIRecommender()
    recommender.record_transition(...)
    rec = recommender.get_recommendation(run_id, current_state)
    bottlenecks = recommender.find_bottlenecks()

**Methods:**

- `__init__()`
- `record_transition(run_id, profile, from_state, to_state, duration_seconds, success, error)`
  — Record a state transition for learning
- `get_recommendation(run_id, current_state, profile, top_n)`
  — Get the best next state recommendation
- `find_bottlenecks()`
  — Find problematic transitions
- `get_most_common_transitions(limit)`
  — Get most common transitions
- `get_transition_stats(from_state, profile)`
  — Get detailed transition statistics
- `generate_report()`
  — Generate comprehensive recommendation report
- `metrics()`
