"""Pydantic modelleri — OpenAPI şemasını otomatik oluşturur."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Health ──

class HealthStatus(BaseModel):
    status: str = "ok"
    version: str = "1.3.0"
    uptime: float = 0.0
    degradation: str = "FULL"
    health_score: float = 100.0


# ── Run ──

class Run(BaseModel):
    slug: str
    title: Optional[str] = None
    profile: str
    state: str
    status: str = "active"
    created_at: str
    updated_at: Optional[str] = None
    elapsed_seconds: Optional[float] = None
    iteration: Optional[int] = None


class RunEvent(BaseModel):
    event_type: str
    timestamp: str
    data: Optional[dict] = None
    id: Optional[str] = None


class ValidationResult(BaseModel):
    tier: str
    passed: bool
    errors: list[str] = []
    warnings: list[str] = []


class StateHistoryEntry(BaseModel):
    state: str
    entered_at: str
    exited_at: Optional[str] = None
    duration_seconds: Optional[float] = None


class RunDetail(Run):
    context: Optional[dict] = None
    events: list[RunEvent] = []
    validation_results: list[ValidationResult] = []
    possible_transitions: list[str] = []
    state_history: list[StateHistoryEntry] = []


class RunInput(BaseModel):
    profile: str
    title: Optional[str] = None
    context: Optional[dict] = None


class RunInputData(BaseModel):
    data: RunInput


class TransitionInput(BaseModel):
    transition: str
    reason: Optional[str] = None
    data: Optional[dict] = None


# ── Profile ──

class Profile(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    state_count: Optional[int] = None
    transition_count: Optional[int] = None
    active_runs: Optional[int] = None


class ProfileState(BaseModel):
    name: str
    type: str = "intermediate"  # initial, intermediate, terminal, pause
    description: Optional[str] = None


class ProfileTransition(BaseModel):
    from_state: str
    to_state: str
    label: Optional[str] = None
    condition: Optional[str] = None


class ProfileDetail(Profile):
    states: list[ProfileState] = []
    transitions: list[ProfileTransition] = []


# ── Audit ──

class AuditEntry(BaseModel):
    id: Optional[str] = None
    event_type: str
    timestamp: str
    data: Optional[dict] = None
    summary: Optional[str] = None
    actor: Optional[str] = None


# ── Alert ──

class Alert(BaseModel):
    level: str  # info, warning, error
    message: str
    timestamp: str
    id: Optional[str] = None


# ── Metrics ──

class EngineMetrics(BaseModel):
    active_runs: int = 0
    total_runs: int = 0
    total_transitions: int = 0
    total_events: int = 0
    degradation_level: str = "FULL"
    uptime_seconds: float = 0.0
    health_score: float = 100.0
    runs_by_state: Optional[dict[str, int]] = None
    runs_by_profile: Optional[dict[str, int]] = None
    transition_latency_p50: Optional[float] = None
    transition_latency_p95: Optional[float] = None
    transition_latency_p99: Optional[float] = None
    throughput_per_minute: Optional[float] = None
    total_cost_usd: Optional[float] = None
    budget_usage_ratio: Optional[float] = None
    alerts: list[Alert] = []


# ── Human Loop ──

class ApprovalTask(BaseModel):
    task_id: str
    description: str
    created_at: str
    run_slug: Optional[str] = None
    priority: Optional[str] = "medium"
    data: Optional[dict] = None


class ApprovalAction(BaseModel):
    task_id: str
    feedback: Optional[str] = None


class PauseInput(BaseModel):
    task_id: str
    reason: str = "human_review"


class ActionResult(BaseModel):
    success: bool = True
    message: str = ""


class BudgetStatus(BaseModel):
    total_cost_usd: float = 0.0
    budget_usage_ratio: float = 0.0
    soft_limit_usd: float = 1000.0
    hard_limit_usd: float = 1500.0
    llm_calls: int = 0
    tool_calls: int = 0
    hourly_cost_usd: float = 0.0
    daily_cost_usd: float = 0.0
    cost_by_category: Optional[dict[str, float]] = None


class HumanDashboard(BaseModel):
    pending_approvals: int = 0
    active_runs_human: int = 0
    budget_status: Optional[BudgetStatus] = None
    recent_audit: list[AuditEntry] = []


# ── HITL (Prodinamik Engine spesifik) ──

class HITLQuestion(BaseModel):
    question: str
    type: str = "yes_no"  # yes_no, multiple_choice
    choices: list[str] = []
    timeout: Optional[int] = None


class TransitionResult(BaseModel):
    slug: str
    state: str
    awaiting_input: bool = False
    questions: list[HITLQuestion] = []
    timeout: Optional[int] = None
    _hitl: bool = False
    _instruction: Optional[str] = None


# ── AI Grid ──

class DriftEvent(BaseModel):
    id: str
    type: str  # semantic, behavioral, temporal, structural
    severity: str  # low, medium, high, critical
    description: str
    timestamp: str
    run_slug: Optional[str] = None
    confidence: Optional[float] = None


class EmergenceCandidate(BaseModel):
    id: str
    type: str
    description: str
    occurrences: int
    affected_runs: int
    confidence: float
    suggested_name: Optional[str] = None


class AgentTask(BaseModel):
    task_id: str
    task_type: str
    interval_seconds: int
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    run_count: int = 0
    status: str = "idle"  # idle, running, completed, failed


class AgentStatus(BaseModel):
    is_running: bool
    uptime: float
    active_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    success_rate: float = 1.0


# ── Raft ──

class RaftNode(BaseModel):
    id: str
    address: str
    state: str  # leader, follower, candidate
    last_seen: Optional[str] = None
    log_index: int = 0
    term: int = 0


# ── API Key ──

class APIKeyInfo(BaseModel):
    id: str
    name: str
    role: str
    created_at: str
    expires_at: Optional[str] = None
    last_used: Optional[str] = None
    enabled: bool = True


class APIKeyCreate(BaseModel):
    name: str
    role: str = "user"
    expires_in_days: int = 365


class APIKeyCreated(BaseModel):
    id: str
    name: str
    role: str
    key: str  # only shown once at creation
    created_at: str
    expires_at: Optional[str] = None


# ── Plugin ──

class Plugin(BaseModel):
    id: str
    name: str
    version: str
    type: str
    status: str  # enabled, disabled, error
    description: Optional[str] = None
    author: Optional[str] = None
    dependencies: list[str] = []


class MarketplacePlugin(BaseModel):
    id: str
    name: str
    version: str
    type: str
    rating: float = 0.0
    downloads: int = 0
    description: Optional[str] = None


# ── Chaos ──

class ChaosScenario(BaseModel):
    id: str
    name: str
    description: str
    severity: str
    duration: int = 30


class ChaosResult(BaseModel):
    scenario: str
    outcome: str  # success, failure
    recovery_time_sec: Optional[float] = None
    metrics_before: Optional[dict] = None
    metrics_after: Optional[dict] = None
