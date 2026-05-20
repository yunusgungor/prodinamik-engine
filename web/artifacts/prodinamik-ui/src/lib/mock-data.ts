import type {
  Run,
  RunDetail,
  Profile,
  AuditEntry,
  EngineMetrics,
  ApprovalTask,
  BudgetStatus,
  Alert,
} from "@workspace/api-client-react";

export const MOCK_PROFILES: Profile[] = [
  { id: "software", name: "Software", description: "Software development pipeline: spec → prototyping → iteration → review → release", state_count: 5, transition_count: 6, active_runs: 3 },
  { id: "content", name: "Content", description: "Content production pipeline: captured → decide_route → idea_review → brief_ready → drafting → verification → draft_review → approved → published → archived", state_count: 10, transition_count: 10, active_runs: 5 },
  { id: "haber", name: "Haber", description: "News verification pipeline: captured → fact_checking → cross_verified → published → correction_needed", state_count: 5, transition_count: 5, active_runs: 2 },
  { id: "devcycle", name: "DevCycle", description: "Development methodology pipeline: brief → prototyping → development → drift_resolution → review → blocked", state_count: 6, transition_count: 7, active_runs: 1 },
  { id: "research", name: "Research", description: "Research workflow: topic_selected → literature_review → hypothesis → experiment_design → paper_draft → peer_review", state_count: 6, transition_count: 7, active_runs: 2 },
  { id: "design", name: "Design", description: "Design pipeline: brief → research → sketch → wireframe → mockup → prototype → review", state_count: 7, transition_count: 8, active_runs: 1 },
];

export const MOCK_RUNS: Run[] = [
  { slug: "run-alpha-001", title: "Feature: auth module", profile: "software", state: "review", status: "active", created_at: new Date(Date.now() - 3600000 * 2).toISOString(), elapsed_seconds: 7200, iteration: 4 },
  { slug: "run-beta-042", title: "Q4 Release Notes", profile: "content", state: "draft", status: "active", created_at: new Date(Date.now() - 3600000 * 5).toISOString(), elapsed_seconds: 18000, iteration: 2 },
  { slug: "run-gamma-007", title: "LLM Benchmark Study", profile: "research", state: "analysis", status: "active", created_at: new Date(Date.now() - 3600000 * 8).toISOString(), elapsed_seconds: 28800, iteration: 6 },
  { slug: "run-delta-019", title: "Dashboard Redesign", profile: "design", state: "feedback", status: "active", created_at: new Date(Date.now() - 3600000 * 1).toISOString(), elapsed_seconds: 3600, iteration: 1 },
  { slug: "run-epsilon-003", title: "API Gateway Setup", profile: "software", state: "deploy", status: "active", created_at: new Date(Date.now() - 3600000 * 12).toISOString(), elapsed_seconds: 43200, iteration: 8 },
  { slug: "run-zeta-011", title: "Newsletter Campaign", profile: "content", state: "published", status: "completed", created_at: new Date(Date.now() - 3600000 * 24).toISOString(), elapsed_seconds: 86400, iteration: 3 },
  { slug: "run-eta-028", title: "Security Audit Report", profile: "research", state: "done", status: "completed", created_at: new Date(Date.now() - 3600000 * 48).toISOString(), elapsed_seconds: 172800, iteration: 5 },
  { slug: "run-theta-005", title: "Mobile App Mockups", profile: "design", state: "error", status: "error", created_at: new Date(Date.now() - 3600000 * 3).toISOString(), elapsed_seconds: 10800, iteration: 2 },
  { slug: "run-iota-034", title: "CI/CD Pipeline Fix", profile: "software", state: "initial", status: "active", created_at: new Date(Date.now() - 1800000).toISOString(), elapsed_seconds: 1800, iteration: 0 },
  { slug: "run-kappa-016", title: "Blog Post Series", profile: "content", state: "review", status: "active", created_at: new Date(Date.now() - 3600000 * 6).toISOString(), elapsed_seconds: 21600, iteration: 3 },
];

export const MOCK_RUN_DETAIL: RunDetail = {
  slug: "run-alpha-001",
  title: "Feature: auth module",
  profile: "software",
  state: "review",
  status: "active",
  created_at: new Date(Date.now() - 3600000 * 2).toISOString(),
  elapsed_seconds: 7200,
  iteration: 4,
  context: {
    repository: "github.com/acme/platform",
    branch: "feat/auth-module",
    commit: "a3f8c2d",
    assignee: "dev-team",
    priority: "high",
    labels: ["auth", "backend", "security"],
  },
  events: [
    { event_type: "run.created", timestamp: new Date(Date.now() - 3600000 * 2).toISOString(), data: { profile: "software", title: "Feature: auth module" } },
    { event_type: "state.transition", timestamp: new Date(Date.now() - 3600000 * 1.8).toISOString(), data: { from: "initial", to: "development", trigger: "auto" } },
    { event_type: "validator.t1.passed", timestamp: new Date(Date.now() - 3600000 * 1.5).toISOString(), data: { checks: 12, passed: 12 } },
    { event_type: "state.transition", timestamp: new Date(Date.now() - 3600000 * 1.2).toISOString(), data: { from: "development", to: "testing", trigger: "manual" } },
    { event_type: "validator.t2.passed", timestamp: new Date(Date.now() - 3600000 * 0.8).toISOString(), data: { checks: 8, passed: 7, warnings: 1 } },
    { event_type: "state.transition", timestamp: new Date(Date.now() - 3600000 * 0.5).toISOString(), data: { from: "testing", to: "review", trigger: "auto" } },
    { event_type: "human.approval.requested", timestamp: new Date(Date.now() - 3600000 * 0.3).toISOString(), data: { reviewer: "tech-lead", task_id: "task-review-001" } },
  ],
  validation_results: [
    { tier: "T1", passed: true, errors: [], warnings: [] },
    { tier: "T2", passed: true, errors: [], warnings: ["Complexity score approaching threshold: 8.2/10"] },
    { tier: "T3", passed: false, errors: ["Security scan: 1 medium severity finding in auth token handling"], warnings: ["Missing rate limiting on /auth/refresh endpoint"] },
  ],
  possible_transitions: ["approve", "reject", "pause", "escalate"],
  state_history: [
    { state: "initial", entered_at: new Date(Date.now() - 3600000 * 2).toISOString(), exited_at: new Date(Date.now() - 3600000 * 1.8).toISOString(), duration_seconds: 720 },
    { state: "development", entered_at: new Date(Date.now() - 3600000 * 1.8).toISOString(), exited_at: new Date(Date.now() - 3600000 * 1.2).toISOString(), duration_seconds: 2160 },
    { state: "testing", entered_at: new Date(Date.now() - 3600000 * 1.2).toISOString(), exited_at: new Date(Date.now() - 3600000 * 0.5).toISOString(), duration_seconds: 2520 },
    { state: "review", entered_at: new Date(Date.now() - 3600000 * 0.5).toISOString(), exited_at: null, duration_seconds: null },
  ],
};

export const MOCK_ALERTS: Alert[] = [
  { level: "warning", message: "High memory usage on worker-node-03 (87%)", timestamp: new Date(Date.now() - 600000).toISOString(), id: "alert-001" },
  { level: "error", message: "LLM provider timeout: openai-gpt4 (3 consecutive failures)", timestamp: new Date(Date.now() - 1800000).toISOString(), id: "alert-002" },
  { level: "info", message: "Degradation level changed: FULL → DEGRADED", timestamp: new Date(Date.now() - 3600000).toISOString(), id: "alert-003" },
  { level: "warning", message: "Budget usage at 78% of soft limit ($780/$1000)", timestamp: new Date(Date.now() - 5400000).toISOString(), id: "alert-004" },
  { level: "info", message: "Plugin 'slack-notifier' v2.1.0 installed successfully", timestamp: new Date(Date.now() - 7200000).toISOString(), id: "alert-005" },
];

export const MOCK_METRICS: EngineMetrics = {
  active_runs: 8,
  total_runs: 247,
  total_transitions: 1893,
  total_events: 12456,
  degradation_level: "DEGRADED",
  uptime_seconds: 432000,
  health_score: 74,
  runs_by_state: {
    initial: 2,
    development: 3,
    testing: 4,
    review: 5,
    deploy: 1,
    done: 180,
    error: 8,
    paused: 3,
    cancelled: 41,
  },
  runs_by_profile: {
    software: 89,
    content: 72,
    research: 51,
    design: 35,
  },
  transition_latency_p50: 145,
  transition_latency_p95: 892,
  transition_latency_p99: 2341,
  throughput_per_minute: 3.2,
  total_cost_usd: 783.42,
  budget_usage_ratio: 0.78,
  alerts: MOCK_ALERTS,
};

export const MOCK_BUDGET: BudgetStatus = {
  total_cost_usd: 783.42,
  budget_usage_ratio: 0.78,
  soft_limit_usd: 1000,
  hard_limit_usd: 1500,
  llm_calls: 4821,
  tool_calls: 12093,
  hourly_cost_usd: 4.23,
  daily_cost_usd: 101.5,
  cost_by_category: {
    llm: 512.30,
    compute: 198.45,
    storage: 48.22,
    network: 24.45,
  },
};

export const MOCK_APPROVALS: ApprovalTask[] = [
  { task_id: "task-review-001", description: "Review and approve auth module implementation before deployment", created_at: new Date(Date.now() - 3600000 * 0.3).toISOString(), run_slug: "run-alpha-001", priority: "high", data: { reviewer: "tech-lead", branch: "feat/auth-module" } },
  { task_id: "task-budget-002", description: "Budget limit approaching — approve 20% increase for Q4 LLM usage", created_at: new Date(Date.now() - 7200000).toISOString(), run_slug: null, priority: "medium", data: { current_spend: 783.42, requested_increase: 200 } },
  { task_id: "task-deploy-003", description: "Approve production deployment: API Gateway v3.2.1", created_at: new Date(Date.now() - 1800000).toISOString(), run_slug: "run-epsilon-003", priority: "critical", data: { version: "3.2.1", environment: "production" } },
];

export const MOCK_AUDIT_ENTRIES: AuditEntry[] = [
  { id: "ae-001", event_type: "run.created", timestamp: new Date(Date.now() - 300000).toISOString(), data: { slug: "run-iota-034", profile: "software" }, summary: "New run created: run-iota-034", actor: "api-key:pdmk_admin" },
  { id: "ae-002", event_type: "state.transition", timestamp: new Date(Date.now() - 900000).toISOString(), data: { slug: "run-alpha-001", from: "testing", to: "review" }, summary: "State transition: testing → review", actor: "system" },
  { id: "ae-003", event_type: "human.approved", timestamp: new Date(Date.now() - 1800000).toISOString(), data: { task_id: "task-old-001", feedback: "LGTM" }, summary: "Approval: task-old-001 approved", actor: "api-key:pdmk_user_1" },
  { id: "ae-004", event_type: "plugin.enabled", timestamp: new Date(Date.now() - 3600000).toISOString(), data: { plugin_id: "slack-notifier", version: "2.1.0" }, summary: "Plugin enabled: slack-notifier", actor: "api-key:pdmk_admin" },
  { id: "ae-005", event_type: "budget.warning", timestamp: new Date(Date.now() - 5400000).toISOString(), data: { usage_ratio: 0.78, cost: 783.42 }, summary: "Budget warning: 78% utilization", actor: "system" },
  { id: "ae-006", event_type: "run.archived", timestamp: new Date(Date.now() - 7200000).toISOString(), data: { slug: "run-old-099", reason: "manual" }, summary: "Run archived: run-old-099", actor: "api-key:pdmk_admin" },
  { id: "ae-007", event_type: "auth.login", timestamp: new Date(Date.now() - 10800000).toISOString(), data: { role: "admin", source: "api" }, summary: "Authentication: admin login", actor: "api-key:pdmk_admin" },
  { id: "ae-008", event_type: "run.error", timestamp: new Date(Date.now() - 14400000).toISOString(), data: { slug: "run-theta-005", error: "LLM timeout after 3 retries" }, summary: "Run error: run-theta-005", actor: "system" },
  { id: "ae-009", event_type: "config.updated", timestamp: new Date(Date.now() - 18000000).toISOString(), data: { section: "budget", field: "soft_limit_usd", old: 800, new: 1000 }, summary: "Config updated: budget.soft_limit_usd", actor: "api-key:pdmk_admin" },
  { id: "ae-010", event_type: "state.transition", timestamp: new Date(Date.now() - 21600000).toISOString(), data: { slug: "run-zeta-011", from: "review", to: "published" }, summary: "State transition: review → published", actor: "system" },
];

export const MOCK_PLUGINS = [
  { id: "slack-notifier", name: "Slack Notifier", version: "2.1.0", type: "INTEGRATION", status: "enabled", description: "Send run notifications to Slack channels", author: "prodinamik-team", dependencies: [] },
  { id: "openai-llm", name: "OpenAI LLM Provider", version: "1.5.2", type: "LLM_PROVIDER", status: "enabled", description: "OpenAI GPT-4 and GPT-3.5 LLM provider", author: "prodinamik-team", dependencies: [] },
  { id: "code-validator", name: "Code Quality Validator", version: "3.0.1", type: "VALIDATOR", status: "enabled", description: "Validates code quality metrics (complexity, coverage, style)", author: "prodinamik-team", dependencies: ["git-adapter"] },
  { id: "git-adapter", name: "Git Adapter", version: "1.2.0", type: "ADAPTER", status: "enabled", description: "Git repository integration for software pipelines", author: "prodinamik-team", dependencies: [] },
  { id: "webhook-hook", name: "Webhook Hook", version: "1.0.3", type: "HOOK", status: "enabled", description: "Fire webhooks on state transitions and events", author: "community", dependencies: [] },
  { id: "anthropic-llm", name: "Anthropic Claude", version: "1.1.0", type: "LLM_PROVIDER", status: "disabled", description: "Claude-3 Sonnet and Claude-3 Haiku LLM provider", author: "prodinamik-team", dependencies: [] },
  { id: "postgres-store", name: "PostgreSQL Event Store", version: "2.0.0", type: "STORE", status: "enabled", description: "PostgreSQL-backed event store for run persistence", author: "prodinamik-team", dependencies: [] },
  { id: "research-profile", name: "Research Profile", version: "1.3.0", type: "PROFILE", status: "enabled", description: "Specialized state machine for research workflows", author: "prodinamik-team", dependencies: [] },
  { id: "drift-detector", name: "Drift Detector", version: "0.9.1", type: "AGENT", status: "error", description: "ML-based pattern drift detection agent", author: "prodinamik-labs", dependencies: ["openai-llm"] },
  { id: "telegram-notifier", name: "Telegram Notifier", version: "1.0.0", type: "INTEGRATION", status: "disabled", description: "Send run notifications via Telegram bot", author: "community", dependencies: [] },
];

export const MOCK_MARKETPLACE_PLUGINS = [
  { id: "jira-adapter", name: "Jira Adapter", version: "2.3.0", type: "ADAPTER", rating: 4.7, downloads: 1247, description: "Jira issue tracking integration for software pipelines" },
  { id: "github-actions-hook", name: "GitHub Actions Hook", version: "1.1.0", type: "HOOK", rating: 4.5, downloads: 893, description: "Trigger GitHub Actions workflows on state transitions" },
  { id: "llama-llm", name: "Ollama LLM Provider", version: "0.8.0", type: "LLM_PROVIDER", rating: 4.2, downloads: 421, description: "Local Ollama model provider (Llama, Mistral, CodeLlama)" },
  { id: "s3-store", name: "S3 Artifact Store", version: "1.0.2", type: "STORE", rating: 4.8, downloads: 2156, description: "AWS S3 storage backend for run artifacts" },
  { id: "datadog-metrics", name: "Datadog Metrics", version: "1.5.1", type: "INTEGRATION", rating: 4.6, downloads: 734, description: "Export engine metrics to Datadog dashboards" },
  { id: "ml-validator", name: "ML Output Validator", version: "0.5.0", type: "VALIDATOR", rating: 3.9, downloads: 187, description: "Validate LLM outputs against quality benchmarks" },
];

export const MOCK_LATENCY_DATA = Array.from({ length: 24 }, (_, i) => ({
  time: `${String(i).padStart(2, "0")}:00`,
  p50: Math.round(100 + Math.random() * 200),
  p95: Math.round(500 + Math.random() * 800),
  p99: Math.round(1500 + Math.random() * 2000),
}));

export const MOCK_THROUGHPUT_DATA = Array.from({ length: 24 }, (_, i) => ({
  time: `${String(i).padStart(2, "0")}:00`,
  value: parseFloat((1 + Math.random() * 6).toFixed(2)),
}));

export const MOCK_DRIFT_DATA = Array.from({ length: 40 }, (_, i) => ({
  x: i,
  y: parseFloat((Math.random() * 100).toFixed(1)),
  type: ["semantic", "behavioral", "temporal", "structural"][Math.floor(Math.random() * 4)],
  run: `run-${String(Math.floor(Math.random() * 50)).padStart(3, "0")}`,
}));

export const MOCK_RAFT_NODES = [
  { id: "node-01", address: "10.0.1.10:7001", state: "leader", lastSeen: new Date(Date.now() - 1000).toISOString(), logIndex: 18432, term: 7 },
  { id: "node-02", address: "10.0.1.11:7001", state: "follower", lastSeen: new Date(Date.now() - 2000).toISOString(), logIndex: 18430, term: 7 },
  { id: "node-03", address: "10.0.1.12:7001", state: "follower", lastSeen: new Date(Date.now() - 1500).toISOString(), logIndex: 18432, term: 7 },
];

export const STATE_MACHINE_NODES = [
  { id: "initial", type: "initial", label: "initial", x: 80, y: 200 },
  { id: "planning", type: "intermediate", label: "planning", x: 240, y: 100 },
  { id: "development", type: "intermediate", label: "development", x: 400, y: 100 },
  { id: "testing", type: "intermediate", label: "testing", x: 560, y: 100 },
  { id: "review", type: "intermediate", label: "review", x: 560, y: 260 },
  { id: "deploy", type: "intermediate", label: "deploy", x: 400, y: 260 },
  { id: "done", type: "terminal", label: "done", x: 240, y: 260 },
  { id: "error", type: "error", label: "error", x: 400, y: 380 },
  { id: "paused", type: "pause", label: "paused", x: 240, y: 380 },
];

export const STATE_MACHINE_EDGES = [
  { id: "e1", from: "initial", to: "planning", label: "start" },
  { id: "e2", from: "planning", to: "development", label: "plan_ready" },
  { id: "e3", from: "development", to: "testing", label: "code_ready" },
  { id: "e4", from: "testing", to: "review", label: "tests_pass" },
  { id: "e5", from: "review", to: "deploy", label: "approved" },
  { id: "e6", from: "deploy", to: "done", label: "deployed" },
  { id: "e7", from: "testing", to: "error", label: "tests_fail" },
  { id: "e8", from: "development", to: "error", label: "build_fail" },
  { id: "e9", from: "error", to: "development", label: "retry" },
  { id: "e10", from: "review", to: "development", label: "changes_required" },
  { id: "e11", from: "development", to: "paused", label: "pause" },
  { id: "e12", from: "paused", to: "development", label: "resume" },
];
