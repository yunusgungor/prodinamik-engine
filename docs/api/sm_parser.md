# State Machine Parser

Prodinamik Engine v1.1 — StateMachine YAML Parser

Parses formal state machine definitions from YAML.

**Module:** `engine.sm_parser.py`

## Classes

### `StateMachineParser`

YAML state machine tanımını Python nesnelerine çevirir

**Methods:**

- `parse_file(cls, path)`
  — YAML dosyasını parse et
- `parse_string(cls, yaml_str)`
  — YAML string'ini parse et
- `_parse_dict(cls, raw)`
