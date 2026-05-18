"""Prodinamik Engine v1.1 — Health Dashboard

ASCII/ANSI dashboard for terminal use. Shows:
- Thermal map of engine health
- Run status matrix
- Degradation timeline
- Cost summary
- Alert log

Usage:
    from engine.dashboard import Dashboard
    dash = Dashboard(engine)
    print(dash.render())
"""

import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from .log import get_logger


class Dashboard:
    """Terminal health dashboard for Prodinamik Engine"""

    # ANSI color codes
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    CYAN = "\033[36m"
    BLUE = "\033[34m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

    # Thermal map thresholds
    THERMAL = {
        "critical": (0.8, RED),
        "warning": (0.5, YELLOW),
        "healthy": (0.0, GREEN),
    }

    def __init__(self, engine=None):
        self.engine = engine
        self._alert_log: List[Dict[str, Any]] = []
        self._last_poll: Dict[str, Any] = {}

    def attach(self, engine):
        """Attach to engine"""
        self.engine = engine

    def log_alert(self, level: str, message: str, source: str = "dashboard"):
        """Add alert to rolling log"""
        self._alert_log.append({
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message,
            "source": source,
        })
        # Keep last 100
        if len(self._alert_log) > 100:
            self._alert_log = self._alert_log[-100:]

    # ──────────────────────────────────────
    # Render
    # ──────────────────────────────────────

    def render(self) -> str:
        """Render full dashboard"""
        parts = [
            self._header(),
            self._thermal_map(),
            self._run_matrix(),
            self._degradation_timeline(),
            self._cost_summary(),
            self._alert_section(),
        ]
        return "\n\n".join(parts)

    def render_compact(self) -> str:
        """Compact single-line status"""
        health = self._get_health()
        deg = health.get("degradation", "?")
        deg_color = self._deg_color(deg)
        deg_badge = f"{deg_color}{deg}{self.RESET}"
        active = health.get("active_runs", 0)
        score = health.get("health_score", 0)
        score_color = self._score_color(score)
        return (f"{self.CYAN}Prodinamik{self.RESET} "
                f"Deg:{deg_badge} "
                f"Score:{score_color}{score:.0f}{self.RESET} "
                f"Runs:{self.BOLD}{active}{self.RESET}")

    # ──────────────────────────────────────
    # Sections
    # ──────────────────────────────────────

    def _header(self) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return (
            f"{self.BOLD}{self.CYAN}╔══════════════════════════════════════╗{self.RESET}\n"
            f"{self.BOLD}{self.CYAN}║{self.RESET}  Prodinamik Engine Health Dashboard  {self.BOLD}{self.CYAN}║{self.RESET}\n"
            f"{self.BOLD}{self.CYAN}║{self.RESET}  {self.DIM}{now}{self.RESET}                   {self.BOLD}{self.CYAN}║{self.RESET}\n"
            f"{self.BOLD}{self.CYAN}╚══════════════════════════════════════╝{self.RESET}"
        )

    def _thermal_map(self) -> str:
        """ASCII thermal bar for key metrics"""
        health = self._get_health()
        lines = [f"{self.BOLD}Thermal Map{self.RESET}"]

        metrics = [
            ("Health Score", health.get("health_score", 0) / 100.0),
            ("Degradation", self._deg_normalized(health.get("degradation", "FULL"))),
            ("Budget Used", min(1.0, health.get("total_cost", 0) / 1.0)),
        ]

        for label, value in metrics:
            value = min(1.0, max(0.0, value))
            bar = self._thermal_bar(value)
            color = self._thermal_color(value)
            pct = f"{value * 100:.0f}%"
            lines.append(f"  {self.DIM}{label}:{self.RESET} {color}{bar}{self.RESET} {pct}")

        # Profile list
        profiles = health.get("profiles", [])
        if profiles:
            lines.append(f"  {self.DIM}Profiles:{self.RESET} {', '.join(profiles)}")

        return "\n".join(lines)

    def _run_matrix(self) -> str:
        """Run status matrix"""
        if not self.engine:
            return f"{self.DIM}Run matrix: engine not attached{self.RESET}"

        try:
            runs = self.engine.list_runs(include_archived=False)
        except Exception as e:
            get_logger().warning("Dashboard run matrix unavailable: %s", e)
            return f"{self.DIM}Run matrix unavailable{self.RESET}"

        if not runs:
            return f"{self.DIM}No active runs{self.RESET}"

        lines = [f"{self.BOLD}Run Matrix ({len(runs)} active){self.RESET}"]

        # Group by profile
        by_profile: Dict[str, list] = {}
        for r in runs:
            by_profile.setdefault(r.profile, []).append(r)

        for profile, profile_runs in sorted(by_profile.items()):
            lines.append(f"  {self.CYAN}{profile}{self.RESET}:")
            for r in profile_runs:
                elapsed = ""
                try:
                    secs = self.engine.run_manager.get_state_elapsed(r.slug)
                    if secs is not None:
                        elapsed = f" [{secs:.0f}s]"
                except Exception as e:
                    get_logger().debug("Dashboard elapsed time error for %s: %s", r.slug, e)

                state_color = self._state_color(r.state)
                status_icon = "🔄" if r.status == "active" else "📦"
                lines.append(
                    f"    {status_icon} {self.BOLD}{r.slug}{self.RESET}"
                    f" → {state_color}{r.state}{self.RESET}{self.DIM}{elapsed}{self.RESET}"
                )

        return "\n".join(lines)

    def _degradation_timeline(self) -> str:
        """ASCII timeline of degradation levels"""
        health = self._get_health()
        deg = health.get("degradation", "FULL")

        levels = ["FULL", "DEGRADED", "SURVIVAL"]
        idx = levels.index(deg) if deg in levels else 0

        bar_chars = ["━", "━", "━"]
        for i in range(3):
            if i < idx:
                bar_chars[i] = self.RED + "●" + self.RESET
            elif i == idx:
                bar_chars[i] = self.YELLOW + "●" + self.RESET if i > 0 else self.GREEN + "●" + self.RESET
            else:
                bar_chars[i] = self.DIM + "○" + self.RESET

        return (
            f"{self.BOLD}Degradation State{self.RESET}\n"
            f"  {self.GREEN}FULL{self.RESET} {bar_chars[0]}  "
            f"{self.YELLOW}DEGRADED{self.RESET} {bar_chars[1]}  "
            f"{self.RED}SURVIVAL{self.RESET} {bar_chars[2]}"
        )

    def _cost_summary(self) -> str:
        """Cost summary section"""
        health = self._get_health()
        total = health.get("total_cost", 0)
        active = health.get("active_runs", 0)

        # Estimate daily cost if engine available
        daily_est = 0.0
        if self.engine:
            try:
                runs = self.engine.list_runs(include_archived=True)
                if len(runs) > 0:
                    # Estimate: count events as proxy
                    event_count = sum(
                        len(self.engine._get_event_store(r.slug).get_all())
                        for r in runs[:10]  # sample
                        if hasattr(self.engine, '_get_event_store')
                    )
                    daily_est = total / max(1, len(runs)) * 0.05  # rough heuristic
            except Exception as e:
                get_logger().debug("Dashboard cost summary error: %s", e)
                pass

        return (
            f"{self.BOLD}Cost Summary{self.RESET}\n"
            f"  {self.DIM}Total:{self.RESET}   ${total:.4f}\n"
            f"  {self.DIM}Active:{self.RESET}  {active} runs\n"
            f"  {self.DIM}Est.Daily:{self.RESET} ${daily_est:.4f}"
        )

    def _alert_section(self) -> str:
        """Recent alerts"""
        if not self._alert_log:
            return f"{self.DIM}No alerts logged{self.RESET}"

        recent = self._alert_log[-5:]
        lines = [f"{self.BOLD}Recent Alerts{self.RESET}"]
        for alert in recent:
            lvl_color = {
                "error": self.RED,
                "warning": self.YELLOW,
                "info": self.GREEN,
            }.get(alert["level"], self.DIM)
            lines.append(
                f"  {lvl_color}{alert['level'][0].upper()}{self.RESET} "
                f"{self.DIM}{alert['timestamp'][11:19]}{self.RESET} "
                f"{alert['message']}"
            )
        return "\n".join(lines)

    # ──────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────

    def _get_health(self) -> dict:
        if self.engine:
            try:
                return self.engine.health_snapshot
            except Exception as e:
                get_logger().debug("Dashboard health snapshot error: %s", e)
                pass
        return {}

    def _thermal_bar(self, value: float, width: int = 20) -> str:
        """Render a thermal bar █████░░░░░"""
        filled = min(width, max(0, int(value * width)))
        empty = width - filled
        color = self._thermal_color(value)
        bar = "█" * filled + "░" * empty
        return f"{color}{bar}{self.RESET}"

    def _thermal_color(self, value: float) -> str:
        if value >= 0.8:
            return self.RED
        elif value >= 0.5:
            return self.YELLOW
        return self.GREEN

    def _deg_color(self, deg: str) -> str:
        return {
            "FULL": self.GREEN,
            "DEGRADED": self.YELLOW,
            "SURVIVAL": self.RED,
        }.get(deg, self.DIM)

    def _deg_normalized(self, deg: str) -> float:
        return {"FULL": 0.0, "DEGRADED": 0.5, "SURVIVAL": 1.0}.get(deg, 0.0)

    def _score_color(self, score: float) -> str:
        if score >= 80:
            return self.GREEN
        elif score >= 50:
            return self.YELLOW
        return self.RED

    def _state_color(self, state: str) -> str:
        terminal = {"done", "released", "completed", "archived", "cancelled"}
        error = {"error", "failed", "cancelled"}
        if state in error:
            return self.RED
        elif state in terminal:
            return self.GREEN
        else:
            return self.YELLOW


# ──────────────────────────────────────────────
# HTML Dashboard Export
# ──────────────────────────────────────────────

def render_html_dashboard(engine, metrics_snapshot: dict = None) -> str:
    """Generate a simple HTML dashboard page"""
    health = {}
    if engine:
        try:
            health = engine.health_snapshot
        except Exception as e:
            get_logger().warning("HTML dashboard health snapshot error: %s", e)
            pass

    deg = health.get("degradation", "FULL")
    score = health.get("health_score", 0)
    active = health.get("active_runs", 0)
    profiles = health.get("profiles", [])

    deg_pct = {"FULL": 0, "DEGRADED": 50, "SURVIVAL": 100}.get(deg, 0)

    runs_html = ""
    if engine:
        try:
            runs = engine.list_runs(include_archived=False)
            for r in runs:
                runs_html += f"""<tr>
                    <td>{r.slug}</td>
                    <td>{r.profile}</td>
                    <td><span class="state-{r.state}">{r.state}</span></td>
                    <td>{r.status}</td>
                </tr>\n"""
        except Exception as e:
            get_logger().warning("HTML dashboard runs list error: %s", e)
            runs_html = "<tr><td colspan='4'>N/A</td></tr>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Prodinamik Engine Dashboard</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #0d1117; color: #c9d1d9; padding: 2rem; }}
  h1 {{ color: #58a6ff; margin-bottom: 1.5rem; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
          gap: 1rem; margin-bottom: 2rem; }}
  .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1.25rem; }}
  .card h2 {{ font-size: 0.85rem; color: #8b949e; text-transform: uppercase; margin-bottom: 0.5rem; }}
  .card .value {{ font-size: 2rem; font-weight: 700; }}
  .green {{ color: #3fb950; }}
  .yellow {{ color: #d29922; }}
  .red {{ color: #f85149; }}
  .bar {{ height: 8px; background: #21262d; border-radius: 4px; margin-top: 0.5rem; }}
  .bar-fill {{ height: 100%; border-radius: 4px; transition: width 1s; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ text-align: left; padding: 0.5rem 0.75rem; border-bottom: 1px solid #21262d; }}
  th {{ color: #8b949e; font-size: 0.8rem; text-transform: uppercase; }}
  .state-done, .state-completed {{ color: #3fb950; }}
  .state-active {{ color: #d29922; }}
  .state-error {{ color: #f85149; }}
  pre {{ background: #161b22; padding: 1rem; border-radius: 6px; overflow-x: auto; font-size: 0.85rem; }}
</style>
</head>
<body>
  <h1>🔍 Prodinamik Engine</h1>

  <div class="grid">
    <div class="card">
      <h2>Health Score</h2>
      <div class="value {'green' if score >= 80 else 'yellow' if score >= 50 else 'red'}">{score:.1f}</div>
      <div class="bar"><div class="bar-fill" style="width:{score}%;background:{'#3fb950' if score >= 80 else '#d29922' if score >= 50 else '#f85149'}"></div></div>
    </div>
    <div class="card">
      <h2>Degradation</h2>
      <div class="value {'green' if deg == 'FULL' else 'yellow' if deg == 'DEGRADED' else 'red'}">{deg}</div>
      <div class="bar"><div class="bar-fill" style="width:{deg_pct}%;background:{'#3fb950' if deg == 'FULL' else '#d29922' if deg == 'DEGRADED' else '#f85149'}"></div></div>
    </div>
    <div class="card">
      <h2>Active Runs</h2>
      <div class="value">{active}</div>
    </div>
    <div class="card">
      <h2>Profiles</h2>
      <div class="value">{len(profiles)}</div>
      <div style="color:#8b949e;font-size:0.85rem">{', '.join(profiles) if profiles else 'none'}</div>
    </div>
  </div>

  <div class="card" style="margin-bottom:1rem">
    <h2>Active Runs</h2>
    <table>
      <thead><tr><th>Slug</th><th>Profile</th><th>State</th><th>Status</th></tr></thead>
      <tbody>{runs_html}</tbody>
    </table>
  </div>

  <div class="card">
    <h2>Metrics Snapshot</h2>
    <pre>{__import__('json').dumps(metrics_snapshot if metrics_snapshot else {}, indent=2, default=str)[:2000]}</pre>
  </div>
</body>
</html>"""
