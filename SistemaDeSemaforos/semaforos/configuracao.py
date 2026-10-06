"""Leitura e validação da configuração de uma execução."""

import json
import os
import shutil
from pathlib import Path


def read_config(path):
    path = Path(path).resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("network", "plans"):
        data[key] = (path.parent / data[key]).resolve()
        if not data[key].is_file():
            raise ValueError(f"Arquivo ausente: {data[key]}")
    if "mapping_path" in data:
        data["mapping_path"] = (path.parent / data["mapping_path"]).resolve()
        if not data["mapping_path"].is_file():
            raise ValueError(f"Mapeamento ausente: {data['mapping_path']}")
    if data.get("targets_from_mapping"):
        if not data.get("mapping_path"):
            raise ValueError("targets_from_mapping exige mapping_path")
        mapping = json.loads(data["mapping_path"].read_text(encoding="utf-8"))
        entries = mapping.get("intersections", [])
        from .mapeamento import mapping_report
        report = mapping_report(data, data["mapping_path"])
        if len(entries) != 9 or report["validated_count"] != 9:
            raise ValueError(f"Mapeamento dos nove cruzamentos ainda incompleto: {report['validated_count']}/9 validados")
        targets = []
        for item in entries:
            controllers = item.get("controllers", [{"tls_id": item.get("tls_id"),
                                                     "stage_to_phase": item.get("stage_to_phase", {})}])
            for controller in controllers:
                targets.append({"name": item["name"], "tls_id": controller["tls_id"],
                                "phase_indices": sorted(set(controller["stage_to_phase"].values()))})
        data["targets"] = targets
    if data["duration_seconds"] <= 0 or data["step_seconds"] <= 0:
        raise ValueError("Duração e passo devem ser positivos")
    if data["demand"]["mode"] not in ("random", "flows", "edge_volumes"):
        raise ValueError("demand.mode deve ser random, flows ou edge_volumes")
    if not data["seeds"] or any(not isinstance(seed, int) for seed in data["seeds"]):
        raise ValueError("seeds deve conter ao menos um inteiro")
    training = data["training"]
    if any(training[key] < 1 for key in ("iterations", "warmup_random", "candidate_pool")):
        raise ValueError("Parâmetros de treinamento devem ser positivos")
    if any(training[key] <= 0 for key in (
            "minimum_green_seconds", "minimum_yellow_seconds", "minimum_all_red_seconds")):
        raise ValueError("Tempos mínimos das fases devem ser positivos")
    return data


def sumo_executable():
    binary = shutil.which("sumo")
    if binary:
        return Path(binary)
    home = os.environ.get("SUMO_HOME")
    if home:
        candidate = Path(home) / "bin" / "sumo.exe"
        if candidate.is_file():
            return candidate
    raise RuntimeError("SUMO não encontrado no PATH ou em SUMO_HOME")


def validate_reference_plan(config, plans):
    for target in config["targets"]:
        name = target.get("name")
        if name not in plans:
            raise ValueError(f"Cruzamento ausente da planilha: {name}")
        if str(config["plan_id"]) not in plans[name]["plans"]:
            raise ValueError(f'Plano {config["plan_id"]} ausente para {name}')
