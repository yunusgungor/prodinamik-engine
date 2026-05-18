#!/usr/bin/env python3
"""
Prodinamik Engine — Auto-Generate API Reference Docs

Scans engine/ modules and generates MkDocs-compatible markdown
for each public class and function.

Usage:
    python scripts/gen_api_docs.py          # Generate all API docs
    python scripts/gen_api_docs.py --watch  # Watch mode (not implemented)
"""

import os
import re
import ast
import sys
from pathlib import Path
from typing import List, Optional


DOCS_DIR = Path(__file__).resolve().parent.parent / "docs" / "api"
ENGINE_DIR = Path(__file__).resolve().parent.parent / "engine"

# Modules to document (in order)
API_MODULES = [
    ("engine", "Engine Core"),
    ("state_machine", "State Machine Runtime"),
    ("sm_types", "State Machine Types"),
    ("sm_parser", "State Machine Parser"),
    ("profile", "Product Profile"),
    ("run_manager", "Run Manager"),
    ("validators", "Validator Pipeline"),
    ("event_store", "Event Store"),
    ("degradation", "Degradation Manager"),
    ("cost", "Cost Tracking"),
    ("budget", "Budget Enforcement"),
    ("safety", "Safety Monitor"),
    ("migration", "Migration"),
    ("runtime", "Async Runtime"),
    ("hooks", "Lifecycle Hooks"),
    ("shell", "Interactive Shell"),
    ("scaffold", "Scaffolding"),
    ("bench", "Benchmarks"),
    ("registry", "Profile Registry"),
    ("metrics", "Metrics Pipeline"),
    ("dashboard", "Health Dashboard"),
    ("audit", "Audit Log"),
    ("auth", "Authentication"),
    ("ratelimit", "Rate Limiter"),
    ("server", "HTTP Server"),
    ("raft_types", "Raft Types"),
    ("raft_consensus", "Raft Consensus"),
    ("raft_cluster", "Raft Cluster"),
    ("chaos", "Chaos Engine"),
    ("alert", "Alert Manager"),
    ("config", "Configuration"),
    ("log", "Logging"),
    ("cli", "CLI Entry Point"),
]


def extract_docstring(node: ast.AST) -> Optional[str]:
    """Extract docstring from an AST node"""
    if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module))
            and ast.get_docstring(node)):
        return ast.get_docstring(node)
    return None


def extract_class_info(tree: ast.Module, module_name: str) -> List[dict]:
    """Extract class definitions and their signatures"""
    classes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = []
            for base in node.bases:
                if isinstance(base, ast.Name):
                    bases.append(base.id)
                elif isinstance(base, ast.Attribute):
                    bases.append(f"{base.value.id}.{base.attr}")

            methods = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    args = []
                    for arg in item.args.args:
                        if arg.arg != 'self':
                            args.append(arg.arg)
                    methods.append({
                        "name": item.name,
                        "args": args,
                        "docstring": extract_docstring(item),
                        "async": isinstance(item, ast.AsyncFunctionDef),
                    })

            classes.append({
                "name": node.name,
                "bases": bases,
                "docstring": extract_docstring(node),
                "methods": methods,
            })
    return classes


def extract_functions(tree: ast.Module) -> List[dict]:
    """Extract top-level functions"""
    functions = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith('_') or node.name == '__init__':
                args = []
                for arg in node.args.args:
                    if arg.arg != 'self':
                        args.append(arg.arg)
                functions.append({
                    "name": node.name,
                    "args": args,
                    "docstring": extract_docstring(node),
                    "async": isinstance(node, ast.AsyncFunctionDef),
                })
    return functions


def generate_module_doc(module_name: str, friendly_name: str) -> str:
    """Generate MkDocs markdown for a module"""
    path = ENGINE_DIR / f"{module_name}.py"
    if not path.exists():
        return f"# {friendly_name}\n\nModule `{module_name}` not found.\n"

    with open(path) as f:
        try:
            tree = ast.parse(f.read())
        except SyntaxError:
            return f"# {friendly_name}\n\nModule parse error.\n"

    module_doc = extract_docstring(tree)
    classes = extract_class_info(tree, module_name)
    functions = extract_functions(tree)

    lines = [f"# {friendly_name}"]
    if module_doc:
        lines.append(f"\n{module_doc}\n")

    lines.append(f"**Module:** `engine.{module_name}.py`\n")

    # Classes
    if classes:
        lines.append("## Classes\n")
        for cls in classes:
            base_str = f"({', '.join(cls['bases'])})" if cls['bases'] else ""
            lines.append(f"### `{cls['name']}`{base_str}\n")
            if cls['docstring']:
                lines.append(f"{cls['docstring']}\n")

            if cls['methods']:
                lines.append("**Methods:**\n")
                for m in cls['methods']:
                    prefix = "async " if m['async'] else ""
                    args_str = ", ".join(m['args'])
                    sig = f"{prefix}{m['name']}({args_str})"
                    lines.append(f"- `{sig}`")
                    if m['docstring']:
                        # Only include first line
                        first_line = m['docstring'].split('\n')[0]
                        if first_line:
                            lines.append(f"  — {first_line}")
                lines.append("")

    # Functions
    if functions:
        lines.append("## Functions\n")
        for fn in functions:
            prefix = "async " if fn['async'] else ""
            args_str = ", ".join(fn['args'])
            sig = f"{prefix}{fn['name']}({args_str})"
            lines.append(f"### `{sig}`\n")
            if fn['docstring']:
                lines.append(f"{fn['docstring']}\n")

    return "\n".join(lines)


def generate_all():
    """Generate all API docs"""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    # Generate overview
    overview_lines = ["# API Reference\n",
                      "Auto-generated API documentation for all engine modules.\n",
                      "| Module | Description | File |",
                      "|--------|-------------|------|"]

    for module_name, friendly_name in API_MODULES:
        path = ENGINE_DIR / f"{module_name}.py"
        if path.exists():
            lines_of_code = len(path.read_text().splitlines())
            overview_lines.append(f"| [{friendly_name}]({module_name}.md) | `engine.{module_name}.py` | {lines_of_code} lines |")
            doc = generate_module_doc(module_name, friendly_name)
            (DOCS_DIR / f"{module_name}.md").write_text(doc)
            print(f"  ✅ {module_name}.md ({lines_of_code} lines)")
        else:
            overview_lines.append(f"| {friendly_name} | `engine.{module_name}.py` | ❌ Not found |")
            print(f"  ⚠️  {module_name}.py not found, skipping")

    overview_lines.append("")
    (DOCS_DIR / "engine.md").write_text("\n".join(overview_lines))
    print(f"\n✅ Generated {len(API_MODULES)} API docs in {DOCS_DIR}")


if __name__ == "__main__":
    generate_all()
