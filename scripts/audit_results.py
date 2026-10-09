"""Verifica integridade e contrato dos resultados já produzidos.

Uso: python3 scripts/audit_results.py --episodes outputs/outputs-random.
Não executa SUMO, não altera arquivos e não exige catálogos derivados.
Confere tipos, perfis, contexto da execução e entidades exigidas no full.
A verificação avalia a estrutura dos dados, sem recalcular as métricas.
"""

import argparse
import gzip
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from SistemaDeSemaforos.metrics.metric_presentation import describe_metric


def records_valid(records, observed):
    """Confere contrato, unicidade, finitude e ordem dos agregados temporais."""
    types = {"int": int, "float": float, "bool": bool, "string": str}
    values = {}
    for record in records:
        name, value = record["metric_name"], record["value"]
        if (not re.fullmatch(r"[a-z][a-z0-9_]*", name) or name in values
                or type(value) is not types.get(record["data_type"])):
            raise ValueError(f"Tipo/chave inválido: {record}")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"Valor não finito: {name}")
        values[name] = value
        observed.add(name)
    for name in values:
        if name.endswith("_min"):
            prefix = name[:-4]
            if prefix + "_mean" in values and prefix + "_max" in values:
                if not values[name] - 1e-8 <= values[prefix + "_mean"] <= values[prefix + "_max"] + 1e-8:
                    raise ValueError(f"Agregados fora de ordem: {prefix}")
    return len(records)


def episode_records_valid(document, observed):
    """Confere os registros tipados e a apresentação, sem recalcular resultados."""
    version = document.get("schema_version")
    if type(version) is not int or version not in {1, 2, 3}:
        raise ValueError(f"Schema de métricas não suportado: {version}")
    records = document["metrics"]
    # A semântica vem do mesmo módulo usado para publicar os resultados.
    for record in records:
        describe_metric(record["metric_name"])
    if version in {2, 3}:
        previous_priority = 0
        categories = {
            "performance": {1}, "operation": {2}, "integrity": {3},
            "diagnostic": {4}, "context": {4},
        }
        for record in records:
            for key in ("label_pt", "description_pt"):
                if not isinstance(record.get(key), str) or not record[key].strip():
                    raise ValueError(f"Apresentação sem {key}: {record['metric_name']}")
            if "unit" not in record or (record["unit"] is not None and
                    (not isinstance(record["unit"], str) or not record["unit"].strip())):
                raise ValueError(f"Unidade inválida: {record['metric_name']}")
            if record.get("kind") not in {"result", "context", "diagnostic"}:
                raise ValueError(f"Natureza inválida: {record['metric_name']}")
            priority = record.get("priority")
            if (type(priority) is not int or
                    priority not in categories.get(record.get("category"), set())):
                raise ValueError(f"Prioridade/categoria inválida: {record['metric_name']}")
            if priority < previous_priority:
                raise ValueError("Métricas fora da ordem de importância")
            previous_priority = priority
    return records_valid(records, observed)



def audit(episodes):
    directory = Path(episodes)
    if not directory.is_dir():
        raise ValueError(f"Pasta de episódios não encontrada: {episodes}")
    episode_paths = sorted(directory.rglob("metrics.json"))
    if not episode_paths:
        raise ValueError(f"Nenhum episódio encontrado em: {episodes}")
    observed, record_count = set(), 0
    for path in episode_paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != 3:
            raise ValueError(f"Episódio exige schema_version=3: {path}")
        record_count += episode_records_valid(document, observed)
        metrics = {record["metric_name"]: record["value"] for record in document["metrics"]}
        execution = document.get("execution", {})
        if execution.get("status") != "completed" or metrics.get("status") != "completed":
            raise ValueError(f"Episódio incompleto: {path}")
        profile = execution.get("collection", {}).get("profile")
        if profile not in {"core", "full"} or metrics.get("metrics_profile") != profile:
            raise ValueError(f"Perfil inconsistente: {path}")
        if not isinstance(execution.get("sumo_version"), str) or not execution["sumo_version"].strip():
            raise ValueError(f"Versão SUMO ausente ou inválida: {path}")
        if "entity_metrics_file" not in document:
            raise ValueError(f"Declaração de entidades ausente: {path}")
        entity_file = document["entity_metrics_file"]
        if profile == "core":
            if entity_file is not None:
                raise ValueError(f"Core não deve declarar detalhes por entidade: {path}")
            if (path.parent / "entities.json.gz").exists():
                raise ValueError(f"Entidades existentes mas não declaradas: {path}")
            continue
        if entity_file != "entities.json.gz" or not (path.parent / entity_file).is_file():
            raise ValueError(f"Arquivo de entidades full ausente ou inválido: {path}")
        with gzip.open(path.parent / entity_file, "rt", encoding="utf-8") as source:
            entities_document = json.load(source)
        if entities_document.get("schema_version") != 1:
            raise ValueError(f"Schema de entidades não suportado: {path}")
        for entities in entities_document["entities"].values():
            for records in entities.values():
                record_count += records_valid(records, observed)
    result = {"episodes_verified": len(episode_paths),
              "typed_records_verified": record_count,
              "distinct_metric_names": len(observed)}
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=Path, required=True)
    audit(**vars(parser.parse_args()))
