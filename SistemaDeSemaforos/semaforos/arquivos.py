"""Publicação atômica de arquivos lidos durante uma execução."""
import json
import os
import uuid
import time
from pathlib import Path


def write_json(path, value):
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2, default=str))


def write_text(path, value):
    path = Path(path)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(value, encoding="utf-8")
        for attempt in range(8):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 7:
                    raise
                time.sleep(0.01)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
