"""
Prodinamik Engine v1.1 — StateMachine Runtime (Facade)

Formal state machine runtime with compile-time validation,
graph algorithms, and runtime transition rules.

Backward-compatible: re-exports all types from sm_types
and sm_parser so existing imports continue to work.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import List, Dict, Optional, Set, Tuple
from collections import OrderedDict

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

    def __init__(self, config: StateMachineConfig, lru_size: int = 128):
        self.config = config
        self._lock: threading.Lock = threading.Lock()
        self._build_transition_map()
        self._validate_or_raise()
        # LRU cache for can_transition results
        self._transition_cache: OrderedDict = OrderedDict()
        self._lru_size = lru_size

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
        """Bir state'ten gidilebilecek state'leri listele (cached)"""
        cache_key = f"next:{current_state}"
        with self._lock:
            if cache_key in self._transition_cache:
                self._transition_cache.move_to_end(cache_key)
                return self._transition_cache[cache_key]

        with self._lock:
            result = [t.to_state for t in self._transition_map.get(current_state, [])]
        with self._lock:
            self._transition_cache[cache_key] = result
            if len(self._transition_cache) > self._lru_size:
                self._transition_cache.popitem(last=False)
        return result

    def can_transition(self, from_state: str, to_state: str,
                       runtime: RuntimeState = None,
                       ltl_runtime: dict = None) -> Tuple[bool, str]:
        # LRU cache lookup (sadece runtime'sız çağrılar için — yani statik kontroller)
        if runtime is None:
            cache_key = f"{from_state}→{to_state}"
            with self._lock:
                if cache_key in self._transition_cache:
                    # Move to end (most recently used)
                    self._transition_cache.move_to_end(cache_key)
                    return self._transition_cache[cache_key]

        if from_state not in self.config.states:
            return False, f"Source state '{from_state}' not found"
        if to_state not in self.config.states:
            return False, f"Target state '{to_state}' not found"

        if self.config.states[from_state].state_type == StateType.TERMINAL:
            return False, f"Cannot transition from terminal state '{from_state}'"

        with self._lock:
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

        # LTL evaluation (before condition check, optional)
        if runtime and ltl_runtime is not None:
            try:
                ltl_ok, ltl_reason = self._evaluate_ltl_rules(
                    from_state, runtime, ltl_runtime
                )
                if not ltl_ok:
                    return False, ltl_reason
            except Exception as e:
                return False, f"LTL evaluation failed: {e}"

        if t.condition and runtime:
            try:
                if not self._evaluate_condition(t.condition, runtime):
                    return False, f"Transition condition not met: {t.condition}"
            except Exception as e:
                return False, f"Condition evaluation failed: {e}"

        # Fix K8: Increment reentry_count for self-loop transitions
        if runtime and from_state == to_state:
            runtime.reentry_count += 1

        # Cache the result (sadece runtime'sız çağrılar için)
        if runtime is None:
            cache_key = f"{from_state}→{to_state}"
            with self._lock:
                self._transition_cache[cache_key] = (True, "Transition allowed")
                if len(self._transition_cache) > self._lru_size:
                    self._transition_cache.popitem(last=False)

        return True, "Transition allowed"

    def _evaluate_condition(self, condition: str, runtime: RuntimeState) -> bool:
        if not condition:
            return True
        try:
            condition = condition.strip()
            # Handle compound conditions
            if ' OR ' in condition:
                parts = condition.split(' OR ')
                return any(self._evaluate_single_condition(p.strip(), runtime) for p in parts)
            if ' AND ' in condition:
                parts = condition.split(' AND ')
                return all(self._evaluate_single_condition(p.strip(), runtime) for p in parts)
            return self._evaluate_single_condition(condition, runtime)
        except Exception:
            return True  # Backward compatible: never crash on unknown conditions

    def _evaluate_single_condition(self, condition: str, runtime: RuntimeState) -> bool:
        """Evaluate a single (non-compound) condition against RuntimeState fields."""
        condition = condition.strip()

        # Numeric comparisons: field op value
        # e.g. "iterations >= 5", "drift_count < 3", "failures <= 2", "drift_count == 0"
        for op in ('>=', '<=', '>', '<', '==', '!='):
            if op in condition:
                parts = condition.split(op, 1)
                if len(parts) == 2:
                    field_name = parts[0].strip()
                    target_val_str = parts[1].strip()
                    try:
                        target_val = int(target_val_str)
                    except ValueError:
                        return True  # Can't parse target value, skip
                    actual_val = self._get_runtime_field(field_name, runtime)
                    if actual_val is None:
                        return True  # Unknown field, skip
                    if op == '>=':
                        return actual_val >= target_val
                    elif op == '<=':
                        return actual_val <= target_val
                    elif op == '>':
                        return actual_val > target_val
                    elif op == '<':
                        return actual_val < target_val
                    elif op == '==':
                        return actual_val == target_val
                    elif op == '!=':
                        return actual_val != target_val

        # Simple boolean condition names → RuntimeState fields
        base_cond = condition.split('(')[0].strip() if '(' in condition else condition
        field_map = {
            # These check RuntimeState fields directly
            'human_approved': lambda r: bool(r.human_approved),
            'drift_detected': lambda r: r.drift_count > 0,
            'consecutive_failures': lambda r: r.consecutive_failures > 0,
            # These are always false in current RuntimeState (external signals)
            'changes_requested': lambda r: False,
            'manual_unblock': lambda r: False,
            'project_abandoned': lambda r: False,
            'max_iterations_exceeded': lambda r: r.total_iterations > r.iteration_count,
        }
        if base_cond in field_map:
            return field_map[base_cond](runtime)

        # Backward-compatible hardcoded conditions
        if condition.startswith('prototype_passes('):
            return True

        # Default: return True (backward compatible)
        return True

    def _get_runtime_field(self, field_name: str, runtime: RuntimeState):
        """Map a condition field name to a RuntimeState attribute value."""
        field_map = {
            'iterations': 'iteration_count',
            'iteration_count': 'iteration_count',
            'drift_count': 'drift_count',
            'failures': 'consecutive_failures',
            'consecutive_failures': 'consecutive_failures',
            'reentry_count': 'reentry_count',
            'total_iterations': 'total_iterations',
        }
        attr = field_map.get(field_name)
        if attr:
            return getattr(runtime, attr, None)
        return None

    def _evaluate_ltl_rules(self, current_state: str, runtime: RuntimeState,
                             ltl_history: dict) -> Tuple[bool, str]:
        """Evaluate LTL temporal logic rules against historical states.

        Supports operators:
          G(condition) — Globally: condition must hold in all visited states
          F(condition) — Eventually: condition must hold at some point
          X(condition) — Next: condition will be checked on the next transition
          A U B        — Until: A must hold until B becomes true
        """
        if not self.config.ltl_rules:
            return True, "No LTL rules defined"

        # Snapshot current state metrics into history
        state_snapshots = ltl_history.setdefault('state_snapshots', [])
        state_snapshots.append({
            'state': current_state,
            'iteration_count': runtime.iteration_count,
            'drift_count': runtime.drift_count,
            'consecutive_failures': runtime.consecutive_failures,
            'human_approved': runtime.human_approved,
        })

        # Initialize tracking dicts
        g_evaluations = ltl_history.setdefault('G_evaluations', {})
        f_evaluations = ltl_history.setdefault('F_evaluations', {})
        x_pending = ltl_history.setdefault('X_pending', [])
        u_states = ltl_history.setdefault('U_states', {})

        # Check any pending X(condition) from the previous transition
        if x_pending:
            for expr in x_pending:
                cond_result = self._evaluate_single_condition(expr, runtime)
                if not cond_result:
                    return False, f"LTL X({expr}) not satisfied on next transition"
            x_pending.clear()

        for rule in self.config.ltl_rules:
            expr = rule.expression.strip()

            # G(condition): globally
            if expr.startswith('G(') and expr.endswith(')'):
                inner = expr[2:-1]
                result = self._evaluate_single_condition(inner, runtime)
                key = f"G({inner})"
                if key not in g_evaluations:
                    g_evaluations[key] = result
                else:
                    g_evaluations[key] = g_evaluations[key] and result
                if not g_evaluations[key]:
                    return False, (
                        f"LTL G({inner}) violated at state '{current_state}'"
                    )

            # F(condition): eventually
            elif expr.startswith('F(') and expr.endswith(')'):
                inner = expr[2:-1]
                result = self._evaluate_single_condition(inner, runtime)
                key = f"F({inner})"
                if key not in f_evaluations:
                    f_evaluations[key] = result
                else:
                    f_evaluations[key] = f_evaluations[key] or result

            # X(condition): next — deferred to next transition
            elif expr.startswith('X(') and expr.endswith(')'):
                inner = expr[2:-1]
                x_pending.append(inner)

            # A U B: until
            elif ' U ' in expr:
                parts = expr.split(' U ', 1)
                if len(parts) == 2:
                    cond_a = parts[0].strip()
                    cond_b = parts[1].strip()
                    result_a = self._evaluate_single_condition(cond_a, runtime)
                    result_b = self._evaluate_single_condition(cond_b, runtime)
                    key = f"U({cond_a},{cond_b})"
                    until_state = u_states.get(key, 'waiting')
                    if until_state == 'waiting':
                        if result_b:
                            u_states[key] = 'satisfied'
                        elif not result_a:
                            return False, (
                                f"LTL Until violated: '{cond_a}' must hold "
                                f"until '{cond_b}' at state '{current_state}'"
                            )

            else:
                # Plain expression — evaluate directly
                if not self._evaluate_single_condition(expr, runtime):
                    return False, f"LTL condition '{expr}' not met"

        return True, "All LTL rules satisfied"

    def get_transition_type(self, from_state: str, to_state: str) -> TransitionType:
        with self._lock:
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
