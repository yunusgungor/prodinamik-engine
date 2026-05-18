"""
Prodinamik Engine v0.5 — StateMachine YAML Parser

Formal state machine tanımını YAML'den parse eder.
Compile-time validation: hatalı tanım engine'i başlatmaz.
LTL temporal constraints, transition types, runtime invariants.
"""

import re
import yaml
from enum import Enum
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set, Tuple, Callable
from dataclasses import dataclass, field
from pathlib import Path


# ──────────────────────────────────────────────
# Transition Types
# ──────────────────────────────────────────────

class TransitionType(Enum):
    REVERSIBLE = "reversible"      # Önceki state'e direkt dönülebilir
    COMPENSABLE = "compensable"    # Farklı bir aksiyonla telafi edilebilir
    IRREVERSIBLE = "irreversible"  # Geri alınamaz (yayınlanmış tweet, released crate)


class StateType(Enum):
    INITIAL = "initial"
    INTERMEDIATE = "intermediate"
    TERMINAL = "terminal"
    ERROR = "error"


# ──────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────

@dataclass
class StateDefinition:
    """Tek bir state'in formal tanımı"""
    name: str
    state_type: StateType
    max_reentries: Optional[int] = None     # None = sınırsız
    timeout_seconds: Optional[int] = None   # None = timeout yok
    entry_hooks: List[str] = field(default_factory=list)
    exit_hooks: List[str] = field(default_factory=list)
    validators: List[str] = field(default_factory=list)
    temporal_max_duration: Optional[int] = None
    temporal_on_timeout: Optional[str] = None
    reminders: List[dict] = field(default_factory=list)
    requires_manual: bool = False

    def __post_init__(self):
        if self.state_type == StateType.TERMINAL and self.max_reentries is not None:
            assert self.max_reentries == 0, \
                f"Terminal state '{self.name}' must have max_reentries=0"
        if self.state_type == StateType.INITIAL and self.max_reentries is not None:
            assert self.max_reentries <= 1, \
                f"Initial state '{self.name}' cannot have max_reentries > 1"


@dataclass
class TransitionDefinition:
    """İki state arasındaki geçişin formal tanımı"""
    from_state: str
    to_state: str
    transition_type: TransitionType = TransitionType.REVERSIBLE
    condition: Optional[str] = None       # Python expression string
    action: Optional[str] = None          # Action hook name
    requires_human: bool = False


@dataclass
class LTLRule:
    """Linear Temporal Logic constraint"""
    expression: str  # "G(drafting → F(verification OR cancelled))"
    within_seconds: Optional[int] = None  # "WITHIN 86400"


@dataclass
class StateMachineConfig:
    """Complete state machine configuration from YAML"""
    profile: str
    name: str
    version: str
    states: Dict[str, StateDefinition]          # name → StateDefinition
    transitions: List[TransitionDefinition]
    ltl_rules: List[LTLRule]
    max_steps: int = 100

    @property
    def initial_states(self) -> List[StateDefinition]:
        return [s for s in self.states.values() if s.state_type == StateType.INITIAL]

    @property
    def terminal_states(self) -> List[StateDefinition]:
        return [s for s in self.states.values() if s.state_type == StateType.TERMINAL]

    @property
    def intermediate_states(self) -> List[StateDefinition]:
        return [s for s in self.states.values() if s.state_type == StateType.INTERMEDIATE]


# ──────────────────────────────────────────────
# Validation Errors
# ──────────────────────────────────────────────

@dataclass
class ValidationError:
    field: str
    message: str
    severity: str = "ERROR"  # ERROR | WARNING


# ──────────────────────────────────────────────
# State Machine Runtime
# ──────────────────────────────────────────────

@dataclass
class RuntimeState:
    """Bir run'ın anlık state bilgisi"""
    current_state: str
    previous_state: Optional[str] = None
    reentry_count: int = 0           # Bu state'e kaç kere girildi
    iteration_count: int = 0         # Toplam iterasyon sayısı
    entered_at: datetime = field(default_factory=datetime.now)
    last_transition_at: datetime = field(default_factory=datetime.now)
    version: int = 0                 # Optimistic locking için


class StateMachine:
    """
    Formal state machine runtime.
    - YAML'den yüklenir
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
        """Tüm validation kurallarını çalıştır. Hata yoksa boş liste döner."""
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
        """
        Tüm cycle'ların bir exit condition'ı olmalı.

        Bir cycle'da en az bir node, cycle dışına transition'a sahip olmalıdır.
        (Self-loop'lar cycle sayılmaz — onlar zaten max_reentries ile kontrol edilir)
        """
        cycles = self._find_cycles()
        # Self-loop'ları filtrele (sadece aynı state'e dönen cycle'lar)
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
        """Dead state yok (ulaşılamayan state)"""
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
        """Validation hatası varsa hemen fırlat"""
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
        """
        DFS ile cycle tespiti (Johnson's algorithm basitleştirilmiş)

        Her cycle 1 kere sayılır, canonical form (döndürülmüş) ile dedup.
        """
        cycles = []
        visited = set()
        path = []
        path_set = set()

        def dfs(node, start):
            nonlocal path, path_set

            if node in path_set:
                # Cycle bulundu — canonical forma çevir
                cycle_start = path.index(node)
                cycle = path[cycle_start:]
                # Canonical form: en küçük string temsili
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
        """BFS ile ulaşılabilir state'leri bul"""
        reachable = set()
        queue = list(self.config.initial_states.keys() if hasattr(self.config.initial_states, 'keys')
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
        """Bir state'ten gidilebilecek state'leri listele"""
        return [t.to_state for t in self._transition_map.get(current_state, [])]

    def can_transition(self, from_state: str, to_state: str,
                       runtime: RuntimeState = None) -> Tuple[bool, str]:
        """
        Transition'ın geçerli olup olmadığını kontrol eder.

        Returns: (allowed, reason)
        """
        # State var mı?
        if from_state not in self.config.states:
            return False, f"Source state '{from_state}' not found"
        if to_state not in self.config.states:
            return False, f"Target state '{to_state}' not found"

        # Terminal state'den çıkış yasak
        if self.config.states[from_state].state_type == StateType.TERMINAL:
            return False, f"Cannot transition from terminal state '{from_state}'"

        # Transition tanımlı mı?
        matching = [t for t in self._transition_map.get(from_state, [])
                    if t.to_state == to_state]
        if not matching:
            return False, f"No transition from '{from_state}' to '{to_state}'"

        t = matching[0]

        # Human approval gerekli mi?
        if t.requires_human:
            return False, f"Transition requires human approval"

        # max_reentries kontrolü (sadece re-entry'ler için, ilk giriş için değil)
        if runtime:
            state_def = self.config.states[to_state]
            if state_def.max_reentries is not None:
                # Eğer hedef state, mevcut state'ten farklıysa → yeni state'e ilk giriş
                # Reentry sadece aynı state'e dönüldüğünde sayılır
                if from_state == to_state and runtime.reentry_count >= state_def.max_reentries:
                    return False, (
                        f"Max reentries ({state_def.max_reentries}) "
                        f"exceeded for state '{to_state}'"
                    )

        # Condition kontrolü
        if t.condition and runtime:
            try:
                # Condition bir Python expression — runtimedaki değerlere göre
                if not self._evaluate_condition(t.condition, runtime):
                    return False, f"Transition condition not met: {t.condition}"
            except Exception as e:
                return False, f"Condition evaluation failed: {e}"

        return True, "Transition allowed"

    def _evaluate_condition(self, condition: str, runtime: RuntimeState) -> bool:
        """
        Condition string'ini değerlendir.
        Desteklenen değişkenler: iteration_count, reentry_count, ...
        """
        # Simple built-in conditions
        if condition == "drift_detected":
            return True  # Dışarıdan kontrol edilir
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
            return False  # Dışarıdan set edilir
        if condition == "prototype_passes(spec)":
            return True  # Dışarıdan kontrol edilir
        if condition == "human_approved":
            return False  # Varsayılan: insan onayı gerekli
        if condition == "changes_requested":
            return False
        if condition == "manual_unblock":
            return False
        if condition == "project_abandoned":
            return False
        if condition.startswith("max_iterations"):
            return False

        return True  # Bilinmeyen condition → pas geç

    def get_transition_type(self, from_state: str, to_state: str) -> TransitionType:
        """Transition'ın tipini döndür"""
        for t in self._transition_map.get(from_state, []):
            if t.to_state == to_state:
                return t.transition_type
        return TransitionType.REVERSIBLE

    def create_runtime(self, initial_state: str = None) -> RuntimeState:
        """Yeni bir runtime state oluştur (yeni run için)"""
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
        """State machine'in anlık görüntüsü (debug/persistence için)"""
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


# ──────────────────────────────────────────────
# YAML Parser
# ──────────────────────────────────────────────

class StateMachineParser:
    """YAML state machine tanımını Python nesnelerine çevirir"""

    STATE_TYPE_MAP = {
        "initial": StateType.INITIAL,
        "intermediate": StateType.INTERMEDIATE,
        "terminal": StateType.TERMINAL,
        "error": StateType.ERROR,
    }

    TRANSITION_TYPE_MAP = {
        "REVERSIBLE": TransitionType.REVERSIBLE,
        "COMPENSABLE": TransitionType.COMPENSABLE,
        "IRREVERSIBLE": TransitionType.IRREVERSIBLE,
    }

    @classmethod
    def parse_file(cls, path: str) -> StateMachineConfig:
        """YAML dosyasını parse et"""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"StateMachine YAML not found: {path}")

        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls._parse_dict(raw)

    @classmethod
    def parse_string(cls, yaml_str: str) -> StateMachineConfig:
        """YAML string'ini parse et"""
        raw = yaml.safe_load(yaml_str)
        return cls._parse_dict(raw)

    @classmethod
    def _parse_dict(cls, raw: dict) -> StateMachineConfig:
        if not raw:
            raise ValueError("Empty YAML")

        # Parse states
        states = {}
        for name, s in raw.get("states", {}).items():
            state_type = cls.STATE_TYPE_MAP.get(s.get("type", "intermediate"))
            if state_type is None:
                raise ValueError(f"Invalid state type for '{name}': {s.get('type')}")

            states[name] = StateDefinition(
                name=name,
                state_type=state_type,
                max_reentries=s.get("max_reentries"),
                timeout_seconds=s.get("timeout"),
                entry_hooks=s.get("entry", []),
                exit_hooks=s.get("exit", []),
                validators=s.get("validators", []),
                temporal_max_duration=s.get("temporal", {}).get("max_duration"),
                temporal_on_timeout=s.get("temporal", {}).get("on_timeout"),
                reminders=s.get("temporal", {}).get("reminders", []),
                requires_manual=s.get("requires_manual", False),
            )

        # Parse transitions
        transitions = []
        for raw_t in raw.get("transitions", []):
            from_state, to_state = raw_t.split(" -> ") if " -> " in raw_t else \
                                    raw_t.split("→")

            # Transition metadata (inline dict)
            meta = {}
            if isinstance(raw.get("transitions"), dict):
                meta = raw["transitions"].get(raw_t, {})

            transitions.append(TransitionDefinition(
                from_state=from_state.strip(),
                to_state=to_state.strip(),
                transition_type=cls.TRANSITION_TYPE_MAP.get(
                    meta.get("type", "REVERSIBLE")
                ),
                condition=meta.get("condition"),
                action=meta.get("action"),
                requires_human=meta.get("requires_human", False),
            ))

        # Parse LTL rules
        ltl_rules = []
        for rule_def in raw.get("temporal_constraints", []):
            if isinstance(rule_def, str):
                ltl_rules.append(LTLRule(expression=rule_def))
            elif isinstance(rule_def, dict):
                expr = rule_def.get("rule", "")
                within = rule_def.get("within")
                ltl_rules.append(LTLRule(
                    expression=expr,
                    within_seconds=within,
                ))

        # Formal properties
        formal = raw.get("formal_properties", {})
        max_steps = formal.get("termination", {}).get("max_steps", 100)

        return StateMachineConfig(
            profile=raw.get("profile", "unknown"),
            name=raw.get("name", "unnamed"),
            version=raw.get("version", "0.0.0"),
            states=states,
            transitions=transitions,
            ltl_rules=ltl_rules,
            max_steps=max_steps,
        )


# ──────────────────────────────────────────────
# Exceptions
# ──────────────────────────────────────────────

class StateMachineValidationError(Exception):
    """State machine validation hatası — compile-time"""
    pass

class TransitionError(Exception):
    """Geçersiz transition — runtime"""
    pass


# ──────────────────────────────────────────────
# CLI Quick Test
# ──────────────────────────────────────────────

def demo():
    """Örnek bir state machine yükle ve test et"""
    yaml_str = """
profile: software
name: dev-cycle
version: 1.0

formal_properties:
  termination:
    max_steps: 100

states:
  spec:
    type: initial
    max_reentries: 1
    timeout: 3600
    validators: ["SchemaValidator"]

  prototyping:
    type: intermediate
    max_reentries: 5
    timeout: 7200
    validators: ["BuildValidator"]

  iteration:
    type: intermediate
    max_reentries: 10
    timeout: 86400
    validators: ["TestCoverageValidator", "LintValidator"]

  review:
    type: intermediate
    timeout: 2592000

  release:
    type: terminal
    max_reentries: 0

  blocked:
    type: error
    requires_manual: true

  cancelled:
    type: terminal
    max_reentries: 0

transitions:
  spec -> prototyping: {type: REVERSIBLE}
  prototyping -> iteration: {type: REVERSIBLE, condition: "prototype_passes(spec)"}
  iteration -> iteration: {type: REVERSIBLE, condition: "drift_detected", action: "log_drift"}
  iteration -> review: {type: REVERSIBLE, condition: "iterations >= 4"}
  iteration -> blocked: {type: REVERSIBLE, condition: "consecutive_failures >= 3"}
  iteration -> cancelled: {type: REVERSIBLE, condition: "max_iterations_exceeded"}
  review -> release: {type: COMPENSABLE, condition: "human_approved"}
  review -> iteration: {type: REVERSIBLE, condition: "changes_requested"}
  review -> cancelled: {type: REVERSIBLE, condition: "project_abandoned"}
  blocked -> iteration: {type: REVERSIBLE, condition: "manual_unblock"}
"""

    config = StateMachineParser.parse_string(yaml_str)
    sm = StateMachine(config)

    print(f"✅ StateMachine loaded: {sm}")
    print(f"   States: {len(config.states)}")
    print(f"   Transitions: {len(config.transitions)}")
    print(f"   Initial: {[s.name for s in config.initial_states]}")
    print(f"   Terminal: {[s.name for s in config.terminal_states]}")

    # Test transitions
    rt = sm.create_runtime("spec")
    print(f"\n📌 Current: {rt.current_state}")
    print(f"   Next: {sm.get_next_states('spec')}")

    allowed, reason = sm.can_transition("spec", "prototyping", rt)
    print(f"   spec → prototyping: {'✅' if allowed else '❌'} ({reason})")

    allowed, reason = sm.can_transition("release", "iteration", rt)
    print(f"   release → iteration: {'✅' if allowed else '❌'} ({reason})")

    # Test terminal state restrictions
    state_def = config.states["release"]
    print(f"\n📌 Terminal state check: release.max_reentries={state_def.max_reentries}")

    # Snapshot
    print(f"\n📸 Snapshot: {sm.snapshot()}")

    return sm


if __name__ == "__main__":
    sm = demo()
