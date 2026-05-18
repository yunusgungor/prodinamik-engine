# Troubleshooting Guide

This guide covers common errors, their root causes, and step-by-step solutions for the Prodinamik Engine. Errors are grouped by category. Each entry includes a CLI diagnostic command to help isolate the issue.

---

## Installation Errors

### Error: `ModuleNotFoundError: No module named 'prodinamik'`

**Cause:** The package is not installed, or the Python environment is misconfigured (wrong virtualenv, missing pip install).

**Solution:**
1. Verify installation: `pip show prodinamik-engine`
2. If not found, install: `pip install prodinamik-engine`
3. Ensure you are in the correct virtual environment: `which python`
4. If using a development clone, run: `pip install -e .` from the project root

**Diagnostic:** `python -c "import prodinamik; print(prodinamik.__version__)"`

---

### Error: `pkg_resources.VersionConflict: prodinamik-engine 1.2.0 required 1.3.0`

**Cause:** A dependency (e.g., `pydantic`, `click`, `orjson`) is outdated or incompatible with the installed engine version.

**Solution:**
1. Upgrade all dependencies: `pip install --upgrade prodinamik-engine`
2. If the conflict persists, create a fresh virtual environment and reinstall
3. Check `pip list | grep -E "pydantic|orjson|click"` for version mismatches

**Diagnostic:** `pip check`

---

### Error: `ERROR: Could not install packages due to an OSError: [Errno 28] No space left on device`

**Cause:** The filesystem is full; pip cannot write packages to site-packages.

**Solution:**
1. Free up disk space: `du -sh /tmp /var/cache/apt`
2. Clean pip cache: `pip cache purge`
3. Clean apt cache: `apt-get clean`
4. Remove old logs: `find /var/log -type f -name "*.gz" -delete`

**Diagnostic:** `df -h`

---

### Error: `fatal error: Python.h: No such file or directory`

**Cause:** Missing Python development headers required to compile C extensions.

**Solution:**
1. Install python3-dev (Debian/Ubuntu): `apt-get install python3-dev`
2. On RHEL/Fedora: `dnf install python3-devel`
3. Retry the installation

**Diagnostic:** `dpkg -l | grep python3-dev` (Debian) or `rpm -q python3-devel` (RHEL)

---

## Runtime Errors

### Error: `RuntimeError: WAL directory '/var/lib/prodinamik/wal' does not exist`

**Cause:** The WAL (Write-Ahead Log) directory has not been initialized, or the data path in the configuration is invalid.

**Solution:**
1. Create the directory: `mkdir -p /var/lib/prodinamik/wal`
2. Ensure write permissions: `chmod 755 /var/lib/prodinamik/wal`
3. Verify config path: `prodinamik config show | grep wal_dir`
4. If using a custom data directory, set it in the profile or via `--data-dir`

**Diagnostic:** `prodinamik config show | grep -E "wal_dir|data_dir"`

---

### Error: `EngineNotReadyError: Engine has not finished initialization`

**Cause:** The engine is still bootstrapping — loading state machines, connecting Raft, or rebuilding the WAL.

**Solution:**
1. Wait for initialization to complete (usually 2–10 seconds)
2. Check engine health: `prodinamik health status`
3. Inspect logs: `prodinamik logs --tail 50`
4. If stuck, check for Raft cluster issues (see Raft errors below)

**Diagnostic:** `prodinamik health status`

---

### Error: `TimeoutError: Run execution exceeded timeout of 3600s`

**Cause:** The state machine run exceeded its configured timeout, which is set per profile or at the run level.

**Solution:**
1. Increase the timeout: `prodinamik run inspect <run-id> | grep timeout`
2. Set a higher default in your profile: `prodinamik profile edit --timeout 7200`
3. For long-running workflows, break the state machine into smaller stages
4. Check if the run is stuck in a loop: `prodinamik run list --status running`

**Diagnostic:** `prodinamik run inspect <run-id> | grep -E "timeout|status|current_state"`

---

### Error: `FileNotFoundError: State machine definition not found at '/etc/prodinamik/sms/my_sm.yaml'`

**Cause:** The state machine YAML file path configured in the profile does not exist.

**Solution:**
1. Verify the file exists: `ls -la /etc/prodinamik/sms/my_sm.yaml`
2. List available state machines: `prodinamik sm list`
3. Update the profile with the correct path: `prodinamik profile edit --sm-path /path/to/sm.yaml`
4. If the file was deleted, restore from version control

**Diagnostic:** `prodinamik sm list --verbose`

---

## State Machine Errors

### Error: `InvalidTransitionError: Transition 'process' not allowed from state 'pending'`

**Cause:** The state machine YAML does not define the requested transition from the current state.

**Solution:**
1. Inspect the current state machine definition: `prodinamik sm show <sm-name>`
2. Verify allowed transitions: `cat <sm-file> | grep -A 5 "transitions:"`
3. Add the missing transition to the YAML, or correct the run's target action
4. Restart the run from a valid state: `prodinamik run rerun <run-id> --from-state pending`

**Diagnostic:** `prodinamik sm validate <sm-file>`

---

### Error: `ValidationError: Required field 'output_path' not set in context`

**Cause:** A transition validator requires a context field that was not provided by the run.

**Solution:**
1. Check the validators attached to the transition: `prodinamik sm show <sm-name> --transitions`
2. Review the run context: `prodinamik run inspect <run-id> --context`
3. Provide the missing field: `prodinamik run update <run-id> --context '{"output_path": "/tmp/out"}'`
4. Alternatively, make the validator optional in the state machine definition

**Diagnostic:** `prodinamik sm validate <sm-file> --context '{"output_path": "test"}'`

---

### Error: `CycleDetectedError: State machine contains a cycle: draft -> review -> draft -> review`

**Cause:** The state machine YAML defines a loop without an exit condition, which the parser detects as an infinite cycle.

**Solution:**
1. Re-examine the state machine topology: `prodinamik sm visualize <sm-name>`
2. Add a terminal state (e.g., `approved` or `rejected`) that breaks the loop
3. Ensure transitions from the cycle state lead to distinct downstream states
4. Re-validate: `prodinamik sm validate <sm-file>`

**Diagnostic:** `prodinamik sm validate --strict <sm-file>`

---

### Error: `UnknownStateError: Target state 'archived' is not defined in state machine 'default'`

**Cause:** The state machine does not include a state named `archived` in its state list.

**Solution:**
1. List defined states: `prodinamik sm show <sm-name> | grep -A 50 "states:"`
2. Add the missing state to the YAML under the `states:` section
3. Ensure the transition to the new state is also defined
4. Re-validate the state machine

**Diagnostic:** `prodinamik sm show <sm-name> --states`

---

## Plugin Errors

### Error: `PluginLoadError: Plugin 's3-upload' failed to load: ImportError: No module named 'boto3'`

**Cause:** The plugin requires a Python package that is not installed.

**Solution:**
1. Install the required dependency: `pip install boto3`
2. Verify the plugin manifest for additional requirements: `cat ~/.prodinamik/plugins/s3-upload/manifest.json`
3. Restart the engine: `prodinamik restart`
4. Check plugin registration: `prodinamik plugin list`

**Diagnostic:** `prodinamik plugin inspect s3-upload`

---

### Error: `PluginVersionError: Plugin 'notifier' v0.3.0 is incompatible with engine >=1.4.0`

**Cause:** The plugin specifies an `engine_version` constraint in its manifest that does not match the installed engine version.

**Solution:**
1. Check engine version: `prodinamik --version`
2. Check plugin requirements: `cat ~/.prodinamik/plugins/notifier/manifest.json | grep engine_version`
3. Upgrade the plugin: `prodinamik plugin install notifier --upgrade`
4. Or downgrade the engine if the plugin is critical

**Diagnostic:** `prodinamik plugin list --verbose`

---

### Error: `PluginHookError: Plugin 'audit-log' raised exception in after_transition hook`

**Cause:** A plugin hook (e.g., `before_transition`, `after_run`) encountered an unhandled exception.

**Solution:**
1. Examine the full traceback in logs: `prodinamik logs --plugin audit-log`
2. Check the plugin source for file I/O or network assumptions
3. Temporarily disable the plugin: `prodinamik plugin disable audit-log`
4. Report the issue to the plugin maintainer or fix the hook logic

**Diagnostic:** `prodinamik logs --level DEBUG --tail 100`

---

## Authentication & Authorization Errors

### Error: `AuthError: Invalid API key: 'pdmk_abc...'`

**Cause:** The API key is malformed, revoked, or does not exist in the key store.

**Solution:**
1. Generate a new key: `prodinamik auth create-key --role user --name my-key`
2. Verify existing keys: `prodinamik auth list-keys`
3. Check if the key was revoked: `prodinamik auth inspect-key <key-id>`
4. Ensure the key format matches `pdmk_<48-hex-chars>`

**Diagnostic:** `prodinamik auth list-keys --show-hashes`

---

### Error: `PermissionDeniedError: User 'ci-bot' does not have 'admin' role for this operation`

**Cause:** The RBAC role assigned to the API key lacks sufficient permissions for the requested operation.

**Solution:**
1. Check the key's role: `prodinamik auth inspect-key <key-id>`
2. Create a new key with the required role: `prodinamik auth create-key --role admin`
3. Or elevate the existing key's role (requires admin): `prodinamik auth update-key <key-id> --role admin`
4. Limited operations can use `readonly` or `user` roles; only cluster management requires `admin`

**Diagnostic:** `prodinamik auth list-keys --verbose`

---

### Error: `RateLimitExceeded: API key 'deploy-bot' exceeded 100 requests/minute`

**Cause:** The rate limiter has throttled the key based on the configured per-key limit.

**Solution:**
1. Wait for the rate limit window to reset (default: 60 seconds)
2. Increase the rate limit for the key: `prodinamik auth update-key <key-id> --rate-limit 500`
3. Or adjust the global default in the profile: `prodinamik profile edit --rate-limit 500`
4. Implement exponential backoff in your client

**Diagnostic:** `prodinamik auth rate-limit-status <key-id>`

---

## Chaos Engineering Errors

### Error: `ChaosScenarioError: Scenario 'disk-full' is marked as dangerous. Use --force to confirm.`

**Cause:** Dangerous chaos scenarios require explicit confirmation before execution.

**Solution:**
1. Confirm the scenario: `prodinamik chaos run disk-full --force`
2. Review which scenarios are dangerous: `prodinamik chaos list`
3. Run in a sandbox environment first: `prodinamik chaos run disk-full --sandbox`
4. Monitor safety constraints: `prodinamik chaos status`

**Diagnostic:** `prodinamik chaos list --verbose`

---

### Error: `ChaosSafetyError: Memory pressure would exceed safety limit of 80% (current: 78%, request: +15%)`

**Cause:** The chaos scenario's resource demand combined with current utilization would breach the safety threshold.

**Solution:**
1. Check current system resources: `free -m`
2. Reduce the scenario's resource parameters: `prodinamik chaos run memory-pressure --params '{"mb": 100}'`
3. Adjust safety limits in the profile: `prodinamik profile edit --chaos-memory-limit 90`
4. Run during low-utilization periods

**Diagnostic:** `prodinamik chaos dry-run memory-pressure`

---

### Error: `RecoveryTimeoutError: System did not recover within 60s after 'network-partition' scenario`

**Cause:** The system's self-healing mechanism failed to restore normal operation within the expected window.

**Solution:**
1. Check if iptables rules were cleaned up: `iptables -L -n`
2. Manually restore connectivity: `prodinamik chaos cleanup network-partition`
3. Increase the recovery timeout: `prodinamik chaos run network-partition --recovery-timeout 120`
4. Inspect the engine status: `prodinamik health status --verbose`

**Diagnostic:** `prodinamik chaos history --scenario network-partition`

---

## Raft Consensus Errors

### Error: `RaftNotConnected: Node is not connected to the Raft cluster`

**Cause:** The Raft node could not join or has been disconnected from the cluster.

**Solution:**
1. Check cluster members: `prodinamik raft list`
2. Verify network connectivity between nodes: `prodinamik raft ping <node-id>`
3. Restart the Raft service: `prodinamik raft restart`
4. If the cluster was reset, re-initialize: `prodinamik raft init --bootstrap`

**Diagnostic:** `prodinamik raft status`

---

### Error: `RaftLeaderElectionTimeout: No leader elected after 5s`

**Cause:** The Raft cluster cannot reach a quorum — likely because fewer than a majority of nodes are online.

**Solution:**
1. Count cluster members: `prodinamik raft list | wc -l`
2. Ensure at least `(N/2)+1` nodes are running
3. Check node logs: `prodinamik logs --component raft`
4. For a 3-node cluster, at least 2 must be online. If a node is permanently down, reconfigure the cluster: `prodinamik raft remove-node <dead-node-id>`

**Diagnostic:** `prodinamik raft status --verbose`

---

### Error: `RaftLogInconsistency: Log index 1427 diverges from leader's log`

**Cause:** A follower node's WAL is out of sync with the leader, possibly due to a previous network partition or storage corruption.

**Solution:**
1. The engine will automatically trigger log compaction and re-sync
2. Monitor recovery: `prodinamik raft status --watch`
3. If stuck, force a full snapshot sync: `prodinamik raft sync --full`
4. As a last resort, remove and re-add the node: `prodinamik raft remove-node <node-id> && prodinamik raft add-node <node-id>`

**Diagnostic:** `prodinamik raft log --tail 20`

---

### Error: `RaftPersistenceError: Failed to write Raft log entry at index 5123: disk full`

**Cause:** The Raft log storage directory is on a full disk.

**Solution:**
1. Check disk usage: `df -h $(prodinamik config show | grep raft_dir)`
2. Trigger log compaction: `prodinamik raft compact`
3. Reduce the Raft log retention period: `prodinamik profile edit --raft-log-retention 24h`
4. Move the Raft directory to a larger volume

**Diagnostic:** `prodinamik raft stats | grep -E "log_size|last_index"`

---

## General Diagnostics

### Gathering Diagnostic Information

Run this comprehensive diagnostic command when troubleshooting:

```bash
prodinamik health status          # Engine health
prodinamik raft status            # Raft cluster state
prodinamik sm list                # Loaded state machines
prodinamik plugin list            # Registered plugins
prodinamik run list --limit 10    # Recent runs
prodinamik config show            # Active configuration
prodinamik logs --level DEBUG --tail 100  # Recent debug logs
```

To export a full diagnostic bundle:

```bash
prodinamik diag bundle --output /tmp/prodinamik-diag.tar.gz
```

This creates a tarball containing configuration, recent logs, health snapshots, and system info for support requests.
