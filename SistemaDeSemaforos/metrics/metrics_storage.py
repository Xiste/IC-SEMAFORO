"""Normaliza métricas e grava os resultados de um episódio.

Entrada: dicionários de valores escalares, entidades e contexto da execução.
Saída: JSON tipado e manifesto de arquivos; usado pelo runner após a coleta.
"""

import hashlib
import gzip
import json
import math
from pathlib import Path
import re
from tempfile import NamedTemporaryFile

from .metric_presentation import describe_metric, presentation_sort_key


def write_json(path: Path, contents: dict) -> None:
    """Publica um JSON completo; uma interrupção não deixa metade do arquivo."""
    temporary = None
    try:
        with NamedTemporaryFile(dir=path.parent, prefix=".json-", delete=False) as temporary_file:
            temporary = Path(temporary_file.name)
        compressed = path.suffix == ".gz"
        opener = gzip.open if compressed else open
        with opener(temporary, "wt", encoding="utf-8") as stream:
            json.dump(contents, stream, ensure_ascii=False, allow_nan=False,
                      indent=None if compressed else 2)
            stream.write("\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def file_info(path: Path) -> dict:
    """Identifica o conteúdo de uma entrada ou saída sem carregá-lo todo na RAM."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def metric_records(values: dict) -> list[dict]:
    """Converte escalares para o contrato metric_name/data_type/value."""
    records = []
    types = {bool: "bool", int: "int", float: "float", str: "string"}
    for name, value in sorted(values.items()):
        if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
            raise ValueError(f"Nome de métrica inválido: {name}")
        if type(value) not in types:
            raise TypeError(f"A métrica {name} não é escalar: {type(value).__name__}")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"A métrica {name} não é finita.")
        records.append({"metric_name": name, "data_type": types[type(value)], "value": value})
    return records


def save_entities(directory: Path, entities: dict) -> None:
    """Exporta o consolidado volumoso por entidade, separado do resumo global."""
    write_json(directory / "entities.json.gz", {
        "schema_version": 1,
        "entities": {
            scope: {identifier: metric_records(values)
                    for identifier, values in sorted(objects.items())}
            for scope, objects in sorted(entities.items())
        },
    })


def save_episode(directory: Path, metrics: dict, manifest: dict) -> None:
    """Publica o resumo v2, preservando os nomes, tipos e valores do contrato v1."""
    records = [{**record, **describe_metric(record["metric_name"])}
               for record in metric_records(metrics)]
    records.sort(key=presentation_sort_key)
    write_json(directory / "metrics.json", {
        "schema_version": 2,
        "metrics": records,
        "entity_metrics_file": "entities.json.gz",
    })
    write_json(directory / "manifest.json", manifest)
