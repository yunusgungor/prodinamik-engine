# Scaffolding

Prodinamik Engine v1.1 — Scaffolding Generator

Generates new profile modules and project scaffolds for the Prodinamik Engine.
This module provides template-based code generation to quickly bootstrap
custom profiles (state machines, validators, adapters) and full project
directories with configuration, README, and run storage.

Usage:
    from engine.scaffold import generate_profile, generate_project, list_profiles
    from pathlib import Path

    # Generate a single profile module
    profile_path = generate_profile("my_workflow", Path("./profiles"))

    # Generate a full project scaffold
    project_dir = generate_project("my_project", Path("./projects"))

    # List available profiles
    profiles = list_profiles(Path("./profiles"))

CLI equivalent:
    prodinamik new profile <name>     # → calls generate_profile()
    prodinamik new project <name>     # → calls generate_project()

**Module:** `engine/scaffold.py` (289 lines, 0 classes, 3 functions)

---

## Templates

The module ships four embedded string templates used by the generator
functions. Each is a Python `str` with `{name}` / `{name_camel}` format
placeholders.

### `PROFILE_TEMPLATE`

Generated output when `generate_profile()` is called. Produces a complete,
runnable Python module containing:

- Module docstring with profile name and generation notice
- Imports for `ProductProfile` and `StateMachineParser`
- An inline YAML constant (`{name_camel}STATES_YAML`) defining the state
  machine with 5 default states and 6 transitions

  | State      | Type         | Description                  |
  |------------|--------------|------------------------------|
  | backlog    | initial      | Ideas waiting to be processed|
  | active     | intermediate | Work in progress             |
  | review     | intermediate | Pending review               |
  | done       | terminal     | Completed successfully       |
  | cancelled  | error        | Abandoned or rejected        |

  Transitions:
  - backlog → active   (Start working)
  - active  → review   (Submit for review, condition: work_complete)
  - review  → active   (Revise after review, condition: changes_requested)
  - review  → done     (Mark complete, condition: approved)
  - review  → cancelled(Abandon, condition: rejected)
  - active  → cancelled(Abandon mid-work, condition: abandoned)

- A `{name_camel}Profile` class extending `ProductProfile` with:
  - `name`, `version`, `description` class attributes
  - `state_machine_yaml` pointing to the inline YAML constant
  - `__init__()` setting `_initialized = False`
  - `initialize()` parsing the YAML via `StateMachineParser.parse_string()`
  - Properties for `validators`, `adapters`, and `budget` (default budget:
    soft_limit=$0.50, hard_limit=$1.00, hard_warn_frac=0.8)
  - `__repr__()` returning `<ClassName name=... v=...>`

### `PROJECT_TEMPLATE`

Generated output when `generate_project()` produces `profile.py` inside the
new project directory. Contains:

- Module docstring
- `sys.path` manipulation to ensure the engine package is importable from
  the project root
- Imports for `ProductProfile` and `StateMachineParser`
- An inline YAML constant `PROFILE_YAML` defining a simple state machine:

  | State | Type         | Description     |
  |-------|--------------|-----------------|
  | todo  | initial      | Queued items    |
  | doing | intermediate | In progress     |
  | done  | terminal     | Completed       |

  Transitions:
  - todo  → doing (Start item)
  - doing → done  (Complete item, condition: verified)

- A `__main__` block that loads the engine config, creates an `AsyncEngine`,
  and prints a startup banner with instructions for `prodinamik shell`

### `INIT_TEMPLATE`

Minimal `__init__.py` for the profiles package:
```python
"""Prodinamik profiles"""
```

Created automatically in the output directory if no `__init__.py` exists yet.

### `README_TEMPLATE`

Standard project-level README.md with:
- Project title and description
- Quick start commands: install, shell, run, list, benchmark
- File structure diagram showing profile.py, prodinamik.yaml, runs/

---

## Functions

### `generate_profile(name, output_dir) -> Path`

Generate a new profile module file.

**Parameters:**

| Parameter    | Type   | Description                                        |
|------------- |--------|----------------------------------------------------|
| `name`       | `str`  | Profile name. Hyphens and underscores are converted to CamelCase for the class name. Example: `"my-workflow"` → class `MyWorkflowProfile`. |
| `output_dir` | `Path` | Directory where the profile file will be written. Created (including parents) if it does not exist. |

**Returns:**

| Type   | Description                             |
|--------|-----------------------------------------|
| `Path` | Path to the newly created `.py` file.   |

**Raises:**

| Exception         | Condition                                                     |
|-------------------|---------------------------------------------------------------|
| `FileExistsError` | If `{output_dir}/{name}.py` already exists. Does NOT overwrite. |

**Behavior:**

1. Creates `output_dir` (and parents) via `Path.mkdir(parents=True, exist_ok=True)`.
2. Derives `name_camel` by splitting on `-` and `_`, capitalizing each segment, and joining. Example: `"flux-release"` → `"FluxRelease"`, `"my_profile"` → `"MyProfile"`.
3. Constructs the full output path: `{output_dir}/{name}.py`.
4. Checks for pre-existing file; raises `FileExistsError` if found.
5. Formats `PROFILE_TEMPLATE` with `name=name` and `name_camel=name_camel`.
6. Writes the formatted content to the target file.
7. Checks if `{output_dir}/__init__.py` exists; if not, creates it with `INIT_TEMPLATE`.
8. Returns the `Path` to the newly created file.

**Example:**

```python
from engine.scaffold import generate_profile
from pathlib import Path

path = generate_profile("content-pipeline", Path("profiles"))
print(path)  # profiles/content-pipeline.py
```

### `generate_project(name, output_dir) -> Path`

Generate a new project scaffold with profile, config, and README.

**Parameters:**

| Parameter    | Type   | Description                                            |
|------------- |--------|--------------------------------------------------------|
| `name`       | `str`  | Project name. Used as directory name and profile name.  |
| `output_dir` | `Path` | Parent directory where the project folder will be created. |

**Returns:**

| Type   | Description                                  |
|--------|----------------------------------------------|
| `Path` | Path to the newly created project directory. |

**Raises:**

| Exception         | Condition                                                       |
|-------------------|-----------------------------------------------------------------|
| `FileExistsError` | If the project directory `{output_dir}/{name}` already exists.   |

**Behavior:**

1. Constructs the project directory path: `{output_dir}/{name}`.
2. Checks for pre-existing directory; raises `FileExistsError` if found.
3. Creates the project directory (including parents).
4. Writes `profile.py` inside the project directory using `PROJECT_TEMPLATE` formatted with `name=name`.
5. Writes `prodinamik.yaml` — a default engine configuration file containing:

   ```yaml
   data_dir: "./runs"
   log:
     level: INFO
     format: text
   runtime:
     poll_interval: 5
     health_check_interval: 60
     max_shutdown_wait: 10
     auto_recover: true
     enable_timeout_watcher: true
   ```

6. Writes `README.md` using `README_TEMPLATE` formatted with `name=name`.
7. Creates the `runs/` directory (for run data storage) with a `.gitkeep` file.
8. Returns the `Path` to the new project directory.

**Example:**

```python
from engine.scaffold import generate_project
from pathlib import Path

project_dir = generate_project("flux-release", Path("projects"))
print(project_dir)  # projects/flux-release
```

**Generated project structure:**

```
{name}/
├── profile.py            # Profile module (PROJECT_TEMPLATE)
├── prodinamik.yaml       # Engine configuration
├── README.md             # Project README
└── runs/
    └── .gitkeep          # Placeholder for run data
```

### `list_profiles(profile_dir: Optional[Path] = None) -> list`

List available profile modules in a given directory.

**Parameters:**

| Parameter     | Type          | Description                                                                   |
|-------------- |---------------|-------------------------------------------------------------------------------|
| `profile_dir` | `Optional[Path]` | Directory to scan for profile `.py` files. If `None`, the path is resolved automatically from the CLI config's `data_dir` by going up one level to a `profiles/` directory. |

**Returns:**

| Type   | Description                                                  |
|--------|--------------------------------------------------------------|
| `list` | A sorted list of profile module names (file stems). Empty list if the directory does not exist or contains no profile files. |

**Behavior:**

1. If `profile_dir` is `None`, imports `get_config()` from `.cli` to obtain the configured `data_dir`, then derives the profiles directory as `Path(cfg.data_dir).parent / "profiles"`.
2. If the directory does not exist, returns `[]`.
3. Iterates over all `*.py` files in the directory, sorted alphabetically.
4. Skips `__init__.py`.
5. Collects and returns the file `stem` (filename without extension) for each remaining file.

**Example:**

```python
from engine.scaffold import list_profiles
from pathlib import Path

names = list_profiles(Path("profiles"))
print(names)  # ['content-pipeline', 'my_workflow', 'software']
```

---

## Notes

- **Idempotency:** `generate_profile()` and `generate_project()` refuse to
  overwrite existing files/directories. The caller must handle
  `FileExistsError` (e.g., by prompting the user or choosing a different
  name).
- **Imports:** Both generated files assume the `engine` package is
  importable. The project template inserts `sys.path` manipulation to
  support running `python profile.py` directly from the project root.
- **State machines:** The default state machines in the templates are meant
  as starting points. Users should edit the YAML constants to match their
  domain-specific workflow.
- **Budget:** The default budget is conservative ($0.50 soft / $1.00 hard).
  Adjust `budget` property in the generated profile for production use.
- **CLI integration:** These functions are called by `prodinamik new profile`
  and `prodinamik new project` CLI commands.
