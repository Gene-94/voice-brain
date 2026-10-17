"""Tiny {{placeholder}} template renderer (no Jinja dependency)."""

from __future__ import annotations

import re
from typing import Mapping

_VAR = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def render(template: str, mapping: Mapping[str, object]) -> str:
    """Replace {{var}} placeholders. Unknown keys render as empty string."""

    def sub(match: re.Match) -> str:
        key = match.group(1)
        value = mapping.get(key, "")
        if value is None:
            return ""
        if isinstance(value, (list, tuple)):
            return _render_list(value)
        return str(value)

    return _VAR.sub(sub, template)


def _render_list(items: list | tuple) -> str:
    lines = []
    for item in items:
        if isinstance(item, str):
            lines.append(f"  - {item}")
        else:
            lines.append(f"  - {item}")
    return "\n".join(lines)


def yaml_list(items: list | tuple) -> str:
    """Render a list for YAML frontmatter (used for themes/tags)."""
    if not items:
        return "[]"
    return "\n" + "\n".join(f"  - {i}" for i in items)
