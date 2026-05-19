"""
Prodinamik Engine v1.1 — StateMachine YAML Parser

Parses formal state machine definitions from YAML.
"""

import yaml
from pathlib import Path
from typing import Dict, List, Optional

from .sm_types import (
    StateType, TransitionType, StateDefinition, TransitionDefinition,
    LTLRule, StateMachineConfig, HITLConfig, AskDirective, ConditionalAsk,
)


class StateMachineParser:
    """YAML state machine tanımını Python nesnelerine çevirir"""

    STATE_TYPE_MAP = {
        "initial": StateType.INITIAL,
        "intermediate": StateType.INTERMEDIATE,
        "terminal": StateType.TERMINAL,
        "error": StateType.ERROR,
        "pause": StateType.PAUSE,
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
                hitl=cls._parse_hitl(s.get("hitl", {})),
            )

        transitions = []
        for raw_t in raw.get("transitions", []):
            from_state, to_state = raw_t.split(" -> ") if " -> " in raw_t else \
                                    raw_t.split("→")
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

        ltl_rules = []
        for rule_def in raw.get("temporal_constraints", []):
            if isinstance(rule_def, str):
                ltl_rules.append(LTLRule(expression=rule_def))
            elif isinstance(rule_def, dict):
                expr = rule_def.get("rule", "")
                within = rule_def.get("within")
                ltl_rules.append(LTLRule(expression=expr, within_seconds=within))

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

    @classmethod
    def _parse_hitl(cls, hitl_raw: dict) -> Optional[HITLConfig]:
        """Parse HITL config from YAML dict"""
        if not hitl_raw:
            return None

        ask_user = []
        for au in hitl_raw.get("ask_user", []):
            if isinstance(au, str):
                ask_user.append(AskDirective(question=au))
            elif isinstance(au, dict):
                ask_user.append(AskDirective(
                    question=au.get("question", ""),
                    type=au.get("type", "open"),
                    choices=au.get("choices", []),
                    required=au.get("required", True),
                    timeout_seconds=au.get("timeout", 300),
                ))

        ask_if = []
        for ai in hitl_raw.get("ask_if", []):
            if isinstance(ai, dict):
                ask_if.append(ConditionalAsk(
                    condition=ai.get("condition", ""),
                    question=ai.get("question", ""),
                    type=ai.get("type", "yes_no"),
                    choices=ai.get("choices", []),
                    on_timeout=ai.get("on_timeout", "proceed"),
                ))

        return HITLConfig(
            pause=hitl_raw.get("pause", False),
            ask_user=ask_user,
            ask_if=ask_if,
            on_timeout=hitl_raw.get("on_timeout", "proceed"),
            resume_transitions=hitl_raw.get("resume_transitions", {}),
        )
