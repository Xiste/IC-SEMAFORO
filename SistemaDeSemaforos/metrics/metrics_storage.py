"""Normaliza métricas e grava os resultados de um episódio.

Entrada: dicionários de valores escalares, entidades e contexto da execução.
Saída: JSON tipado com o contexto da execução; usado pelo runner após a coleta.
metrics.json reúne indicadores e dados da execução; full também grava entidades.
A gravação é atômica para evitar arquivos parcialmente escritos em uma interrupção.
"""

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


def save_episode(directory: Path, metrics: dict, execution: dict, *, include_entities: bool = True) -> None:
    """Publica métricas e contexto juntos, sem arquivar as entradas da execução."""
    records = [{**record, **describe_metric(record["metric_name"])}
               for record in metric_records(metrics)]
    records.sort(key=presentation_sort_key)
    write_json(directory / "metrics.json", {
        "schema_version": 3,
        "metrics": records,
        "execution": execution,
        "entity_metrics_file": "entities.json.gz" if include_entities else None,
    })
