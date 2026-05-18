"""Prodinamik Engine v1.3 — Configuration

Config dataclass + YAML/config file parsing.
Environment variable override support.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any
import os
import yaml

from .llm_base import LLMProviderConfig


# ──────────────────────────────────────────────
# Config Dataclass
# ──────────────────────────────────────────────

@dataclass
class DegradationConfig:
    disk_usage_max_pct: float = 95.0
    disk_usage_warn_pct: float = 80.0
    consecutive_llm_failures: int = 3
    consecutive_adapter_failures: int = 3


@dataclass
class BudgetDefaults:
    soft_limit_usd: float = 1.0
    hard_limit_usd: float = 5.0
    max_llm_calls_per_run: int = 20
    max_storage_mb: int = 100
    timeout_per_state: int = 3600


@dataclass
class EventStoreConfig:
    retention_days: int = 90
    compaction_batch: int = 10
    max_events_per_run: int = 10000


@dataclass
class StateMachineConfig:
    max_steps: int = 100
    default_timeout: int = 86400


@dataclass
class LLMConfig:
    """LLM provider configuration"""
    enabled: bool = False
    default_provider: str = ""
    providers: Dict[str, LLMProviderConfig] = field(default_factory=dict)
    max_retries: int = 3
    fallback_enabled: bool = True


@dataclass
class LoggingConfig:
    level: str = "INFO"
    format: str = "json"  # "json" | "text"
    file: Optional[str] = None


@dataclass
class ProdinamikConfig:
    """Root configuration"""
    data_dir: str = ".hermes"
    log: LoggingConfig = field(default_factory=LoggingConfig)
    degradation: DegradationConfig = field(default_factory=DegradationConfig)
    budget: BudgetDefaults = field(default_factory=BudgetDefaults)
    event_store: EventStoreConfig = field(default_factory=EventStoreConfig)
    state_machine: StateMachineConfig = field(default_factory=StateMachineConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    profiles: List[str] = field(default_factory=lambda: [
        "content", "software", "research", "design",
    ])

    @classmethod
    def load(cls, path: Optional[str] = None) -> "ProdinamikConfig":
        """Load config from YAML file, then apply env overrides"""
        cfg = cls()

        if path:
            p = Path(path)
            if p.exists():
                data = yaml.safe_load(p.read_text(encoding="utf-8"))
                if data:
                    cfg = cls._merge(cfg, data)

        # Env overrides
        cfg = cls._apply_env(cfg)

        return cfg

    @staticmethod
    def _merge(cfg: "ProdinamikConfig", data: dict) -> "ProdinamikConfig":
        """Merge YAML data into config, preserving defaults"""
        if "data_dir" in data:
            cfg.data_dir = data["data_dir"]
        if "log" in data:
            log = data["log"]
            if "level" in log:
                cfg.log.level = log["level"].upper()
            if "format" in log:
                cfg.log.format = log["format"]
            if "file" in log:
                cfg.log.file = log["file"]
        if "degradation" in data:
            d = data["degradation"]
            if "disk_usage_max_pct" in d:
                cfg.degradation.disk_usage_max_pct = d["disk_usage_max_pct"]
            if "consecutive_llm_failures" in d:
                cfg.degradation.consecutive_llm_failures = d["consecutive_llm_failures"]
            if "consecutive_adapter_failures" in d:
                cfg.degradation.consecutive_adapter_failures = d["consecutive_adapter_failures"]
        if "budget" in data:
            b = data["budget"]
            if "soft_limit_usd" in b:
                cfg.budget.soft_limit_usd = b["soft_limit_usd"]
            if "hard_limit_usd" in b:
                cfg.budget.hard_limit_usd = b["hard_limit_usd"]
            if "max_llm_calls_per_run" in b:
                cfg.budget.max_llm_calls_per_run = b["max_llm_calls_per_run"]
            if "max_storage_mb" in b:
                cfg.budget.max_storage_mb = b["max_storage_mb"]
        if "event_store" in data:
            es = data["event_store"]
            if "retention_days" in es:
                cfg.event_store.retention_days = es["retention_days"]
            if "compaction_batch" in es:
                cfg.event_store.compaction_batch = es["compaction_batch"]
        if "profiles" in data:
            cfg.profiles = data["profiles"]
        if "llm" in data:
            llm = data["llm"]
            if "enabled" in llm:
                cfg.llm.enabled = llm["enabled"]
            if "default_provider" in llm:
                cfg.llm.default_provider = llm["default_provider"]
            if "max_retries" in llm:
                cfg.llm.max_retries = llm["max_retries"]
            if "fallback_enabled" in llm:
                cfg.llm.fallback_enabled = llm["fallback_enabled"]
            if "providers" in llm:
                for pid, pcfg in llm["providers"].items():
                    cfg.llm.providers[pid] = LLMProviderConfig(
                        api_key=pcfg.get("api_key", ""),
                        base_url=pcfg.get("base_url", ""),
                        model=pcfg.get("model", ""),
                        temperature=pcfg.get("temperature", 0.7),
                        max_tokens=pcfg.get("max_tokens", 2048),
                        timeout=pcfg.get("timeout", 60),
                        extra=pcfg.get("extra", {}),
                    )
        return cfg

    @staticmethod
    def _apply_env(cfg: "ProdinamikConfig") -> "ProdinamikConfig":
        """Apply environment variable overrides"""
        env_map = {
            "PRODINAMIK_LOG_LEVEL": ("log", "level"),
            "PRODINAMIK_DATA_DIR": ("data_dir",),
            "PRODINAMIK_BUDGET_SOFT": ("budget", "soft_limit_usd"),
            "PRODINAMIK_BUDGET_HARD": ("budget", "hard_limit_usd"),
        }
        for env_key, attrs in env_map.items():
            value = os.environ.get(env_key)
            if value is not None:
                target = cfg
                for attr in attrs[:-1]:
                    target = getattr(target, attr)
                try:
                    current = getattr(target, attrs[-1])
                    if isinstance(current, str):
                        setattr(target, attrs[-1], value)
                    else:
                        setattr(target, attrs[-1], type(current)(value))
                except (ValueError, TypeError, AttributeError):
                    pass
        return cfg

    def to_dict(self) -> dict:
        return {
            "data_dir": self.data_dir,
            "log": {
                "level": self.log.level,
                "format": self.log.format,
                "file": self.log.file,
            },
            "degradation": {
                "disk_usage_max_pct": self.degradation.disk_usage_max_pct,
                "consecutive_llm_failures": self.degradation.consecutive_llm_failures,
                "consecutive_adapter_failures": self.degradation.consecutive_adapter_failures,
            },
            "budget": {
                "soft_limit_usd": self.budget.soft_limit_usd,
                "hard_limit_usd": self.budget.hard_limit_usd,
                "max_llm_calls_per_run": self.budget.max_llm_calls_per_run,
                "max_storage_mb": self.budget.max_storage_mb,
            },
            "event_store": {
                "retention_days": self.event_store.retention_days,
                "compaction_batch": self.event_store.compaction_batch,
            },
            "llm": {
                "enabled": self.llm.enabled,
                "default_provider": self.llm.default_provider,
                "max_retries": self.llm.max_retries,
                "fallback_enabled": self.llm.fallback_enabled,
                "providers": {
                    pid: {
                        "base_url": p.base_url,
                        "model": p.model,
                        "temperature": p.temperature,
                        "max_tokens": p.max_tokens,
                        "timeout": p.timeout,
                    }
                    for pid, p in self.llm.providers.items()
                },
            },
            "profiles": self.profiles,
        }
