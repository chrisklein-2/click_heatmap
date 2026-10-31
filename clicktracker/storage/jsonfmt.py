"""JSON helpers: compact layout (one flat object per line) and atomic writes."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _is_flat(value: Any) -> bool:
    """True for scalars and for dicts/lists that contain no nested dicts/lists."""
    if isinstance(value, dict):
        return not any(isinstance(v, (dict, list)) for v in value.values())
    if isinstance(value, list):
        return not any(isinstance(v, (dict, list)) for v in value)
    return True


def dumps_compact(obj: Any, indent: int = 2) -> str:
    """Pretty-print JSON, but keep every flat object/array on a single line."""
    return _encode(obj, indent, 0)


def _encode(obj: Any, indent: int, level: int) -> str:
    if _is_flat(obj):
        return json.dumps(obj, ensure_ascii=False)
    inner = " " * (indent * (level + 1))
    outer = " " * (indent * level)
    if isinstance(obj, dict):
        lines = [f"{inner}{json.dumps(str(k), ensure_ascii=False)}: {_encode(v, indent, level + 1)}"
                 for k, v in obj.items()]
        return "{\n" + ",\n".join(lines) + "\n" + outer + "}"
    lines = [inner + _encode(v, indent, level + 1) for v in obj]
    return "[\n" + ",\n".join(lines) + "\n" + outer + "]"


def write_json_atomic(path: Path, obj: Any, indent: int = 2) -> None:
    """Write to a temp file then swap it in, so the file is never half-written."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(dumps_compact(obj, indent) + "\n", encoding="utf-8")
    os.replace(tmp, path)