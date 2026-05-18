# Logging

Prodinamik Engine v1.0 — Logging

Standard logging module with structured output support.

**Module:** `engine.log.py`

## Classes

### `StructuredFormatter`(logging.Formatter)

Simple JSON-like structured formatter for machine parsing

**Methods:**

- `format(record)`

## Functions

### `setup(config)`

Configure and return the root logger

### `get_logger()`

Get the configured logger, or a default one if not yet setup

### `debug(msg)`

### `info(msg)`

### `warn(msg)`

### `error(msg)`
