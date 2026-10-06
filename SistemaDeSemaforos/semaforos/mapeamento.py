"""Auditoria explícita da correspondência planilha ↔ semáforos SUMO."""

import json
from pathlib import Path

import sumolib

from .planos import read_plans
from .rede import network_programs, phase_kind


DEFAULT_MAPPING = Path(__file__).resolve().parents[1] / "config" / "mapeamento.json"


def mapping_report(config, path=None):
    mapping = json.loads(Path(path or DEFAULT_MAPPING).read_text(encoding="utf-8"))
    plans = read_plans(config["plans"])
    programs = network_programs(config["network"])
    network = sumolib.net.readNet(str(config["network"]))
    lights = {light.getID(): light for light in network.getTrafficLights()}
    entries = mapping.get("intersections", [])
    if len(entries) != len(plans) or {entry.get("name") for entry in entries} != set(plans):
        raise ValueError("O mapeamento deve conter exatamente os nove nomes da planilha")
    used_ids = [entry["tls_id"] for entry in entries if entry.get("tls_id")]
    if len(used_ids) != len(set(used_ids)):
        raise ValueError("Um ID SUMO foi atribuído a mais de um cruzamento")
    result = []
    for entry in entries:
        name = entry["name"]
        plan = plans[name]["plans"].get(str(mapping.get("plan_id", config["plan_id"])))
        tls_id = entry.get("tls_id")
        issues = []
        if plan is None:
            issues.append("plano ausente da planilha")
        if not tls_id:
            issues.append("ID SUMO não informado")
        elif tls_id not in programs or tls_id not in lights:
            issues.append("ID SUMO ausente da rede")
        phases = programs.get(tls_id, [])
        stage_map = entry.get("stage_to_phase", {})
        stage_comparison = []
        if plan and phases:
            green_indices = [index for index, phase in enumerate(phases)
                             if phase_kind(phase["state"]) == "green"]
            expected_stages = set(plan["stages"])
            if set(stage_map) != expected_stages:
                issues.append("estágios da planilha sem correspondência completa")
            indices = list(stage_map.values())
            if len(indices) != len(set(indices)) or any(index not in green_indices for index in indices):
                issues.append("correspondência de estágios não é biunívoca com verdes válidos")
            cycle_network = sum(phase["duration"] for phase in phases)
            if abs(cycle_network - plan["cycle"]) > 0.01 and not entry.get("reconciliation_note"):
                issues.append("ciclos divergentes sem reconciliação documentada")
            for stage_name, plan_times in plan["stages"].items():
                phase_index = stage_map.get(stage_name)
                network_times = None
                if isinstance(phase_index, int) and phase_index in green_indices:
                    yellow = phases[(phase_index + 1) % len(phases)]
                    clearance = phases[(phase_index + 2) % len(phases)]
                    network_times = {
                        "green": phases[phase_index]["duration"],
                        "yellow": yellow["duration"] if phase_kind(yellow["state"]) == "yellow" else None,
                        "clearance": clearance["duration"] if phase_kind(clearance["state"]) == "all_red" else None,
                    }
                    if (any(network_times[key] is None or abs(network_times[key] - plan_times[key]) > 0.01
                            for key in ("green", "yellow", "clearance"))
                            and not entry.get("reconciliation_note")):
                        issues.append(f"tempos divergentes no estagio {stage_name} sem reconciliacao")
                stage_comparison.append({"stage": stage_name, "plan": plan_times,
                                         "network_phase_index": phase_index, "network": network_times})
        else:
            cycle_network = None
            green_indices = []
        for flag, label in (("controlled_links_verified", "faixas e links"),
                            ("movements_verified", "movimentos"),
                            ("pedestrians_verified", "pedestres"),
                            ("safety_verified", "intervalos de segurança")):
            if entry.get(flag) is not True:
                issues.append(f"{label} não validados")
        if not entry.get("review_source"):
            issues.append("fonte da conferência não registrada")
        links = []
        if tls_id in lights:
            links = [{"index": item[2], "from_lane": item[0].getID(),
                      "to_lane": item[1].getID()}
                     for item in lights[tls_id].getConnections()]
        result.append({"name": name, "tls_id": tls_id,
                       "validated": not issues, "issues": issues,
                       "plan_cycle_seconds": plan["cycle"] if plan else None,
                       "network_cycle_seconds": cycle_network,
                       "plan_stages": list(plan["stages"]) if plan else [],
                       "network_green_indices": green_indices,
                       "stage_comparison": stage_comparison,
                       "stage_to_phase": stage_map,
                       "controlled_links": links})
    return {"plan_id": mapping.get("plan_id", config["plan_id"]),
            "validated_count": sum(item["validated"] for item in result),
            "total": len(result), "intersections": result}


def require_validated_targets(config, report):
    checked = {item["tls_id"] for item in report["intersections"] if item["validated"]}
    missing = [target["tls_id"] for target in config["targets"] if target["tls_id"] not in checked]
    if missing:
        raise ValueError(f"Controle conjunto requer mapeamento validado: {', '.join(missing)}")
