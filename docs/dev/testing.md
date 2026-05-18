# Testing

## Running Tests

```bash
# Run all tests
make test
# or
python -m pytest tests/ -v

# Run specific phase
python -m pytest tests/test_phase10.py -v

# Run with coverage
make test-coverage
```

## Test Structure

| File | Tests | Covers |
|------|-------|--------|
| `test_integration.py` | 7 | Core engine fundamentals |
| `test_phase2.py` | 8 | EventStore, Degradation, Safety, Cache |
| `test_phase3.py` | 6 | Cost, Budget, Raft, CRDT |
| `test_phase4.py` | 6 | DebugCLI, Registry, HealthDashboard |
| `test_phase5.py` | 6 | Profiles, Migration, Cross-Profile |
| `test_phase6.py` | 8 | AsyncEngine, Hooks, Timeout, Shutdown |
| `test_phase7.py` | 27 | Shell, Scaffold, Benchmarks, CLI |
| `test_phase8.py` | 31 | Metrics, Dashboard, Audit, CLI |
| `test_phase9.py` | 35 | Auth, Rate Limiter, Server, Raft, CLI |
| `test_phase10.py` | 53 | Chaos + Monitoring + Alert |
| **Total** | **177** | **All features** |

## Writing Tests

```python
import pytest
from engine.state_machine import StateMachine, StateMachineParser

def test_my_feature():
    yaml = """
    profile: test
    name: my-test
    version: 1.0
    states:
        created: {type: initial, max_reentries: 1}
        done: {type: terminal, max_reentries: 0}
    transitions:
        created -> done: {}
    """
    config = StateMachineParser.parse_string(yaml)
    sm = StateMachine(config)
    rt = sm.create_runtime("created")
    assert rt.current_state == "created"
    assert sm.can_transition("created", "done", rt) == (True, "Transition allowed")
```

## Test Fixtures

Common fixtures in `conftest.py`:

```python
@pytest.fixture
def sm():
    """Shared state machine fixture"""
    yaml = "..."
    return StateMachine(StateMachineParser.parse_string(yaml))

@pytest.fixture
def chaos_engine(tmp_path):
    """Chaos engine with temp directory"""
    return ChaosEngine(base_path=str(tmp_path))
```
