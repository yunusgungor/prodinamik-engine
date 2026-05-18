"""
Prodinamik Engine v1.1 — StateMachine Runtime (Facade)

Formal state machine runtime with compile-time validation,
graph algorithms, and runtime transition rules.

Backward-compatible: re-exports all types from sm_types
and sm_parser so existing imports continue to work.
"""

from datetime import datetime
from typing import List, Dict, Optional, Set, Tuple

from .sm_parser import StateMachineParser

from .sm_types import (
    StateType, TransitionType, StateDefinition, TransitionDefinition,
    LTLRule, StateMachineConfig, ValidationError, RuntimeState,
    StateMachineValidationError, TransitionError,
)


class StateMachine:
    """
    Formal state machine runtime.
    - YAML'den yüklenir (via StateMachineParser)
    - Compile-time validate edilir
    - Runtime'da transition kurallarını uygular
    """

    def __init__(self, config: StateMachineConfig):
        self.config = config
        self._build_transition_map()
        self._validate_or_raise()

    def _build_transition_map(self):
        """Transition'ları from_state bazında grupla (hızlı lookup için)"""
        self._transition_map: Dict[str, List[TransitionDefinition]] = {}
        for t in self.config.transitions:
            self._transition_map.setdefault(t.from_state, []).append(t)

    # ──────────────────────────────────────
    # Compile-Time Validation
    # ──────────────────────────────────────

    def validate(self) -> List[ValidationError]:
        errors = []
        errors.extend(self._validate_initial_states())
        errors.extend(self._validate_intermediate_states())
        errors.extend(self._validate_terminal_states())
        errors.extend(self._validate_cycle_exits())
        errors.extend(self._validate_reachability())
        errors.extend(self._validate_max_reentries())
        errors.extend(self._validate_transition_targets())
        return errors

    def _validate_initial_states(self) -> List[ValidationError]:
        errors = []
        for s in self.config.initial_states:
            outgoing = self._transition_map.get(s.name, [])
            if not outgoing:
                errors.append(ValidationError(
                    field=f"states.{s.name}",
                    message=f"Initial state '{s.name}' has no outgoing transitions"
                ))
        return errors

    def _validate_intermediate_states(self) -> List[ValidationError]:
        errors = []
        for s in self.config.intermediate_states:
            outgoing = self._transition_map.get(s.name, [])
            if not outgoing:
                errors.append(ValidationError(
                    field=f"states.{s.name}",
                    message=f"Intermediate state '{s.name}' has no exit transitions"
                ))
        return errors

    def _validate_terminal_states(self) -> List[ValidationError]:
        errors = []
        for s in self.config.terminal_states:
            outgoing = self._transition_map.get(s.name, [])
            if outgoing:
                errors.append(ValidationError(
                    field=f"states.{s.name}",
                    message=f"Terminal state '{s.name}' should have no outgoing transitions"
                ))
            if s.max_reentries != 0:
                errors.append(ValidationError(
                    field=f"states.{s.name}.max_reentries",
                    message=f"Terminal state '{s.name}' must have max_reentries=0"
                ))
        return errors

    def _validate_cycle_exits(self) -> List[ValidationError]:
        cycles = self._find_cycles()
        cycles = [c for c in cycles if len(c) > 1]
        errors = []
        for cycle in sorted(cycles, key=len):
            cycle_set = set(cycle)
            has_exit = any(
                any(t.to_state not in cycle_set
                    for t in self._transition_map.get(node, []))
                for node in cycle
            )
            if not has_exit:
                errors.append(ValidationError(
                    field="transitions",
                    message=f"Dead-end cycle detected: {' → '.join(cycle)}. "
                            f"All transitions in cycle point back into the cycle."
                ))
        return errors

    def _validate_reachability(self) -> List[ValidationError]:
        reachable = self._find_reachable_states()
        errors = []
        for name, state in self.config.states.items():
            if name not in reachable and state.state_type != StateType.INITIAL:
                errors.append(ValidationError(
                    field=f"states.{name}",
                    message=f"Unreachable state: '{name}'. No path from any initial state."
                ))
        return errors

    def _validate_max_reentries(self) -> List[ValidationError]:
        errors = []
        for name, state in self.config.states.items():
            if state.max_reentries is None and state.state_type not in (StateType.TERMINAL, StateType.ERROR):
                errors.append(ValidationError(
                    field=f"states.{name}.max_reentries",
                    message=f"State '{name}' missing max_reentries",
                    severity="WARNING"
                ))
        return errors

    def _validate_transition_targets(self) -> List[ValidationError]:
        errors = []
        for t in self.config.transitions:
            if t.to_state not in self.config.states:
                errors.append(ValidationError(
                    field=f"transitions.{t.from_state}→{t.to_state}",
                    message=f"Transition target '{t.to_state}' not found in state definitions"
                ))
            if t.from_state not in self.config.states:
                errors.append(ValidationError(
                    field=f"transitions.{t.from_state}→{t.to_state}",
                    message=f"Transition source '{t.from_state}' not found in state definitions"
                ))
        return errors

    def _validate_or_raise(self):
        errors = self.validate()
        critical = [e for e in errors if e.severity == "ERROR"]
        if critical:
            raise StateMachineValidationError(
                f"StateMachine validation failed with {len(critical)} error(s):\n"
                + "\n".join(f"  • {e.field}: {e.message}" for e in critical)
            )

    # ──────────────────────────────────────
    # Graph Algorithms
    # ──────────────────────────────────────

    def _find_cycles(self) -> List[List[str]]:
        cycles = []
        visited = set()
        path = []
        path_set = set()

        def dfs(node, start):
            nonlocal path, path_set
            if node in path_set:
                cycle_start = path.index(node)
                cycle = path[cycle_start:]
                canonical = min(
                    cycle[i:] + cycle[:i]
                    for i in range(len(cycle))
                )
                if canonical not in [c[:len(canonical)] for c in cycles]:
                    cycles.append(canonical)
                return
            if node in visited:
                return
            visited.add(node)
            path.append(node)
            path_set.add(node)
            for t in self._transition_map.get(node, []):
                dfs(t.to_state, node)
            path.pop()
            path_set.discard(node)

        for state_name in self.config.states:
            dfs(state_name, state_name)
        return cycles

    def _find_reachable_states(self) -> Set[str]:
        reachable = set()
        queue = list(self.config.initial_states.keys() if hasattr(
            self.config.initial_states, 'keys')
                     else [s.name for s in self.config.initial_states])
        while queue:
            current = queue.pop(0)
            if current in reachable:
                continue
            reachable.add(current)
            for t in self._transition_map.get(current, []):
                if t.to_state not in reachable:
                    queue.append(t.to_state)
        return reachable

    # ──────────────────────────────────────
    # Runtime Operations
    # ──────────────────────────────────────

    def get_next_states(self, current_state: str) -> List[str]:
        return [t.to_state for t in self._transition_map.get(current_state, [])]

    def can_transition(self, from_state: str, to_state: str,
                       runtime: RuntimeState = None) -> Tuple[bool, str]:
        if from_state not in self.config.states:
            return False, f"Source state '{from_state}' not found"
        if to_state not in self.config.states:
            return False, f"Target state '{to_state}' not found"

        if self.config.states[from_state].state_type == StateType.TERMINAL:
            return False, f"Cannot transition from terminal state '{from_state}'"

        matching = [t for t in self._transition_map.get(from_state, [])
                    if t.to_state == to_state]
        if not matching:
            return False, f"No transition from '{from_state}' to '{to_state}'"

        t = matching[0]
        if t.requires_human:
            return False, f"Transition requires human approval"

        if runtime:
            state_def = self.config.states[to_state]
            if state_def.max_reentries is not None:
                if from_state == to_state and runtime.reentry_count >= state_def.max_reentries:
                    return False, (
                        f"Max reentries ({state_def.max_reentries}) "
                        f"exceeded for state '{to_state}'"
                    )

        if t.condition and runtime:
            try:
                if not self._evaluate_condition(t.condition, runtime):
                    return False, f"Transition condition not met: {t.condition}"
            except Exception as e:
                return False, f"Condition evaluation failed: {e}"

        return True, "Transition allowed"

    def _evaluate_condition(self, condition: str, runtime: RuntimeState) -> bool:
        if condition == "drift_detected":
            return True
        if condition.startswith("iterations"):
            parts = condition.replace("iterations ", "").split()
            if len(parts) >= 2:
                op = parts[0]
                val = int(parts[1])
                if op == ">=":
                    return runtime.iteration_count >= val
                elif op == ">":
                    return runtime.iteration_count > val
                elif op == "<":
                    return runtime.iteration_count < val
        if condition.startswith("consecutive_failures"):
            return False
        if condition == "prototype_passes(spec)":
            return True
        if condition in ("human_approved", "changes_requested",
                         "manual_unblock", "project_abandoned"):
            return False
        if condition.startswith("max_iterations"):
            return False
        return True

    def get_transition_type(self, from_state: str, to_state: str) -> TransitionType:
        for t in self._transition_map.get(from_state, []):
            if t.to_state == to_state:
                return t.transition_type
        return TransitionType.REVERSIBLE

    def create_runtime(self, initial_state: str = None) -> RuntimeState:
        if not initial_state:
            initials = self.config.initial_states
            if not initials:
                raise ValueError("No initial state defined")
            initial_state = list(initials.keys())[0] if hasattr(initials, 'keys') else initials[0].name
        return RuntimeState(
            current_state=initial_state,
            entered_at=datetime.now()
        )

    def snapshot(self) -> dict:
        return {
            "profile": self.config.profile,
            "name": self.config.name,
            "version": self.config.version,
            "states": list(self.config.states.keys()),
            "transitions": [
                f"{t.from_state}→{t.to_state} ({t.transition_type.value})"
                for t in self.config.transitions
            ],
            "ltl_rules": [r.expression for r in self.config.ltl_rules],
        }

    def __repr__(self):
        return (f"StateMachine(profile={self.config.profile}, "
                f"name={self.config.name}, "
                f"states={len(self.config.states)}, "
                f"transitions={len(self.config.transitions)})")
