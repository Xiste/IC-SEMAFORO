"""Verifica cobertura do catálogo e integridade de resultados já produzidos.

Entrada: catálogo CSV, instalação SUMO e episódios opcionais. Saída: resumo
JSON no terminal; não modifica catálogo nem resultados. Uso: --episodes <pasta>.
"""

import argparse
import csv
import gzip
import inspect
import json
import math
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from SistemaDeSemaforos.metrics.metrics_storage import file_info


def records_valid(records, patterns, observed):
    """Confere contrato, unicidade, finitude e ordem dos agregados temporais."""
    types = {"int": int, "float": float, "bool": bool, "string": str}
    values = {}
    for record in records:
        name, value = record["metric_name"], record["value"]
        if name in values or type(value) is not types[record["data_type"]]:
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


def episode_records_valid(document, patterns, observed):
    """Aceita resumos v1 e v2; valida a apresentação sem recalcular resultados."""
    version = document.get("schema_version")
    if type(version) is not int or version not in {1, 2}:
        raise ValueError(f"Schema de métricas não suportado: {version}")
    records = document["metrics"]
    if version == 2:
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
    return records_valid(records, patterns, observed)


def audit(episodes=None, benchmark=None):
    rows = list(csv.DictReader((ROOT / "docs/catalogos/metrics_catalog.csv").open(encoding="utf-8")))
    names = [row["metric_name"] for row in rows]
    if len(names) != len(set(names)):
        raise ValueError("Nomes duplicados no catálogo")
    required = ("metric_name", "description", "source_api", "call", "entity", "data_type",
                "unit", "nature", "aggregation", "priority", "reason", "verification")
    for row in rows:
        if not all(row[field] for field in required):
            raise ValueError(f"Entrada sem explicação: {row['metric_name']}")
        if row["priority"] not in {"CORE", "OPTIONAL", "DIAGNOSTIC", "CATALOG_ONLY"}:
            raise ValueError("Prioridade inválida")
    patterns = [re.compile(row["result_name_regex"]) for row in rows if row["result_name_regex"]]
    sumo_home = Path(os.environ.get("SUMO_HOME", "/usr/share/sumo"))
    sys.path.insert(0, str(sumo_home / "tools"))
    import traci
    # Introspecção de nomes/docstrings somente: não abre conexão ou chama getters.
    available = {name + "." + method for name, domain in vars(traci).items()
                 if isinstance(domain, traci.domain.Domain)
                 for method, function in inspect.getmembers(domain, inspect.ismethod)
                 if method.startswith("get")}
    catalogued = {row["readable_name"] for row in rows if row["category"].startswith("TraCI/")}
    if available - catalogued:
        raise ValueError(f"Getters não catalogados: {sorted(available - catalogued)}")
    observed, record_count, episode_count = set(), 0, 0
    if episodes:
        checked_baselines = set()
        for path in sorted(Path(episodes).rglob("manifest.json")):
            manifest = json.loads(path.read_text())
            if manifest["status"] != "completed":
                raise ValueError(f"Episódio incompleto: {path}")
            baseline_path = Path(manifest["baseline"]["manifest"])
            if file_info(baseline_path) != {k: manifest["baseline"][k] for k in ("bytes", "sha256")}:
                raise ValueError(f"Baseline divergente: {path}")
            if baseline_path not in checked_baselines:
                baseline = json.loads(baseline_path.read_text())
                for name, expected in baseline["files"].items():
                    if file_info(baseline_path.parent / name) != expected:
                        raise ValueError(f"Arquivo estático modificado: {name}")
                checked_baselines.add(baseline_path)
            for name, expected in manifest["files"].items():
                if file_info(path.parent / name) != expected:
                    raise ValueError(f"Arquivo do episódio modificado: {name}")
            document = json.loads((path.parent / "metrics.json").read_text())
            record_count += episode_records_valid(document, patterns, observed)
            with gzip.open(path.parent / "entities.json.gz", "rt") as source:
                for entities in json.load(source)["entities"].values():
                    for records in entities.values():
                        record_count += records_valid(records, patterns, observed)
            episode_count += 1
    if benchmark:
        comparison = json.loads(Path(benchmark).read_text())
        for run in comparison["runs"]:
            if not run["same_trip_attributes_as_minimal"]:
                raise ValueError("Benchmark não preservou atributos das viagens")
            path = Path(run["directory"]) / "entities.json.gz"
            if path.exists():
                with gzip.open(path, "rt") as source:
                    for entities in json.load(source)["entities"].values():
                        for records in entities.values():
                            record_count += records_valid(records, patterns, observed)
    missing = [name for name in sorted(observed) if not any(pattern.fullmatch(name) for pattern in patterns)]
    if missing:
        raise ValueError(f"Métricas coletadas sem correspondência no catálogo: {missing}")
    print(json.dumps({"catalogue_entries": len(rows), "traci_getters_covered": len(available),
                      "episodes_verified": episode_count, "typed_records_verified": record_count,
                      "result_names_matched": len(observed)}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=Path)
    parser.add_argument("--benchmark", type=Path)
    audit(**vars(parser.parse_args()))
