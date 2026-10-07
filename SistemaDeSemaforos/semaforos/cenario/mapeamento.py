"""Auditoria explícita da correspondência planilha ↔ semáforos SUMO."""
from semaforos.caminhos import PROJECT_ROOT

import json
import csv
import math
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import sumolib

from semaforos.cenario.planos import read_plans
from semaforos.cenario.rede import network_programs, phase_kind


DEFAULT_MAPPING = PROJECT_ROOT / "config" / "mapeamento.json"
TLS_AUDIT = PROJECT_ROOT / "dados" / "auditoria" / "current_tls_audit.csv"


def audit_phase_kind(state):
    try:
        return phase_kind(state)
    except ValueError:
        return "other"


def _assigned_controllers(entry):
    """O formato antigo com um tls_id continua aceito."""
    if "controllers" in entry:
        controllers = entry["controllers"]
        if not isinstance(controllers, list):
            raise ValueError(f"controllers deve ser uma lista em {entry.get('name')}")
        return controllers
    return [{"tls_id": entry["tls_id"], "stage_to_phase": entry.get("stage_to_phase", {})}]


def _multi_controller_report(entry, plan, programs, lights, audit):
    """Audita separadamente cada controlador de um cruzamento físico."""
    controllers = _assigned_controllers(entry)
    issues = []
    if plan is None:
        issues.append("plano ausente da planilha")
    if not controllers:
        issues.append("nenhum controlador atribuído")
    candidate_ids = set(entry.get("candidate_tls_ids", []))
    assigned_ids = {controller.get("tls_id") for controller in controllers}
    if candidate_ids and assigned_ids != candidate_ids:
        issues.append("IDs candidatos sem atribuição completa ao cruzamento")
    expected_stages = set(plan["stages"]) if plan else set()
    covered_stages = set()
    controller_reports = []
    all_links = []
    comparisons = []
    for controller in controllers:
        tls_id = controller.get("tls_id")
        phases = programs.get(tls_id, [])
        stage_map = controller.get("stage_to_phase", {})
        local_issues = []
        if not tls_id or tls_id not in lights or not phases:
            local_issues.append("ID SUMO ausente da rede")
        if not isinstance(stage_map, dict):
            local_issues.append("stage_to_phase deve ser um objeto")
            stage_map = {}
        covered_stages.update(stage_map)
        green_indices = [index for index, phase in enumerate(phases)
                         if audit_phase_kind(phase["state"]) == "green"]
        indices = list(stage_map.values())
        if (not stage_map or any(type(index) is not int for index in indices)
                or len(indices) != len(set(indices)) or any(index not in green_indices for index in indices)):
            local_issues.append("estágios sem correspondência biunívoca com verdes válidos")
        if set(stage_map) - expected_stages:
            local_issues.append("estágio desconhecido na planilha")
        cycle = sum(phase["duration"] for phase in phases) if phases else None
        if plan and cycle is not None and abs(cycle - plan["cycle"]) > 0.01 and not controller.get("reconciliation_note"):
            local_issues.append("ciclos divergentes sem reconciliação documentada")
        for stage, phase_index in stage_map.items():
            if stage not in expected_stages or type(phase_index) is not int or phase_index not in green_indices:
                continue
            yellow = phases[(phase_index + 1) % len(phases)]
            clearance = phases[(phase_index + 2) % len(phases)]
            network_times = {
                "green": phases[phase_index]["duration"],
                "yellow": yellow["duration"] if audit_phase_kind(yellow["state"]) == "yellow" else None,
                "clearance": clearance["duration"] if audit_phase_kind(clearance["state"]) == "all_red" else None,
            }
            expected = plan["stages"][stage]
            if (any(network_times[key] is None or abs(network_times[key] - expected[key]) > 0.01
                    for key in ("green", "yellow", "clearance"))
                    and not controller.get("reconciliation_note")):
                local_issues.append(f"tempos divergentes no estágio {stage} sem reconciliação")
            comparisons.append({"tls_id": tls_id, "stage": stage, "plan": expected,
                                "network_phase_index": phase_index, "network": network_times})
        for flag, label in (("controlled_links_verified", "faixas e links"),
                            ("movements_verified", "movimentos"),
                            ("pedestrians_verified", "pedestres"),
                            ("safety_verified", "intervalos de segurança")):
            if controller.get(flag) is not True:
                local_issues.append(f"{label} não validados")
        if not controller.get("review_source"):
            local_issues.append("fonte da conferência não registrada")
        links = []
        if tls_id in lights:
            links = [{"tls_id": tls_id, "index": item[2], "from_lane": item[0].getID(),
                      "to_lane": item[1].getID()} for item in lights[tls_id].getConnections()]
            all_links.extend(links)
        controller_reports.append({"tls_id": tls_id, "stage_to_phase": stage_map,
                                   "network_cycle_seconds": cycle,
                                   "network_green_indices": green_indices,
                                   "controlled_links": links, "issues": local_issues})
        issues.extend(f"{tls_id}: {issue}" for issue in local_issues)
    if plan and covered_stages != expected_stages:
        issues.append("estágios da planilha sem correspondência completa")
    candidates = [{"tls_id": candidate, "present_in_network": candidate in programs,
                   "physical_status": audit.get(candidate, {}).get("physical_status"),
                   "pedestrian_status": audit.get(candidate, {}).get("pedestrian_status"),
                   "settran_status": audit.get(candidate, {}).get("settran_status"),
                   "note": audit.get(candidate, {}).get("note")}
                  for candidate in entry.get("candidate_tls_ids", [])]
    return {"name": entry["name"], "tls_id": controllers[0].get("tls_id") if controllers else None,
            "tls_ids": [controller.get("tls_id") for controller in controllers],
            "controllers": controller_reports, "validated": not issues, "issues": issues,
            "candidate_controllers": candidates, "candidate_source": entry.get("candidate_source"),
            "plan_cycle_seconds": plan["cycle"] if plan else None,
            "network_cycle_seconds": None, "plan_stages": list(plan["stages"]) if plan else [],
            "network_green_indices": [], "stage_comparison": comparisons,
            "stage_to_phase": {}, "controlled_links": all_links}


def mapping_report(config, path=None):
    mapping = json.loads(Path(path or DEFAULT_MAPPING).read_text(encoding="utf-8"))
    plans = read_plans(config["plans"])
    programs = network_programs(config["network"])
    network = sumolib.net.readNet(str(config["network"]))
    lights = {light.getID(): light for light in network.getTrafficLights()}
    with TLS_AUDIT.open(newline="", encoding="utf-8") as file:
        audit = {row["tls_id"]: row for row in csv.DictReader(file)}
    entries = mapping.get("intersections", [])
    if len(entries) != len(plans) or {entry.get("name") for entry in entries} != set(plans):
        raise ValueError("O mapeamento deve conter exatamente os nove nomes da planilha")
    used_ids = [controller.get("tls_id") for entry in entries
                for controller in _assigned_controllers(entry) if controller.get("tls_id")]
    if len(used_ids) != len(set(used_ids)):
        raise ValueError("Um ID SUMO foi atribuído a mais de um cruzamento")
    result = []
    for entry in entries:
        name = entry["name"]
        plan = plans[name]["plans"].get(str(mapping.get("plan_id", config["plan_id"])))
        if "controllers" in entry:
            result.append(_multi_controller_report(entry, plan, programs, lights, audit))
            continue
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
                             if audit_phase_kind(phase["state"]) == "green"]
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
                        "yellow": yellow["duration"] if audit_phase_kind(yellow["state"]) == "yellow" else None,
                        "clearance": clearance["duration"] if audit_phase_kind(clearance["state"]) == "all_red" else None,
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
        candidates = entry.get("candidate_tls_ids", [])
        candidate_controllers = [{"tls_id": candidate, "present_in_network": candidate in programs,
                                  "physical_status": audit.get(candidate, {}).get("physical_status"),
                                  "pedestrian_status": audit.get(candidate, {}).get("pedestrian_status"),
                                  "settran_status": audit.get(candidate, {}).get("settran_status"),
                                  "note": audit.get(candidate, {}).get("note")}
                                 for candidate in candidates]
        result.append({"name": name, "tls_id": tls_id,
                       "candidate_controllers": candidate_controllers,
                       "candidate_source": entry.get("candidate_source"),
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
    checked = {tls_id for item in report["intersections"] if item["validated"]
               for tls_id in item.get("tls_ids", [item["tls_id"]])}
    missing = [target["tls_id"] for target in config["targets"] if target["tls_id"] not in checked]
    if missing:
        raise ValueError(f"Controle conjunto requer mapeamento validado: {', '.join(missing)}")


def export_mapping_scaffold(config, output):
    """Gera um rascunho editável sem promover candidatos a alvos validados."""
    source = Path(config.get("mapping_path") or DEFAULT_MAPPING)
    mapping = json.loads(source.read_text(encoding="utf-8"))
    report = mapping_report(config, source)
    if report["total"] != 9:
        raise ValueError("O rascunho exige os nove cruzamentos da planilha")
    for entry in mapping["intersections"]:
        if "controllers" in entry:
            continue
        entry["controllers"] = [{"tls_id": tls_id, "stage_to_phase": {},
                                 "controlled_links_verified": False,
                                 "movements_verified": False,
                                 "pedestrians_verified": False,
                                 "safety_verified": False,
                                 "review_source": "", "reconciliation_note": ""}
                                for tls_id in entry.get("candidate_tls_ids", [])]
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    destination = output / "mapeamento_rascunho.json"
    destination.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"file": str(destination), "intersections": len(mapping["intersections"]),
            "controllers_to_review": sum(len(entry["controllers"]) for entry in mapping["intersections"])}


def export_mapping_review(config, output):
    """Exporta evidências espaciais e semafóricas para revisão humana."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    network = sumolib.net.readNet(str(config["network"]))
    programs = network_programs(config["network"])
    report = mapping_report(config, config.get("mapping_path"))
    known = {tls_id: item["name"] for item in report["intersections"]
             for tls_id in item.get("tls_ids", [item["tls_id"]]) if tls_id}
    candidates = {candidate["tls_id"]: item["name"] for item in report["intersections"]
                  for candidate in item["candidate_controllers"]}
    location = {}
    edge_functions = {"crossing": 0, "walkingarea": 0}
    for _, element in ET.iterparse(config["network"], events=("end",)):
        if element.tag == "location":
            location = element.attrib.copy()
        if element.tag == "edge" and element.get("function") in edge_functions:
            edge_functions[element.get("function")] += 1
        element.clear()
    controllers = []
    links = []
    phases = []
    for review_index, light in enumerate(network.getTrafficLights(), start=1):
        tls_id = light.getID()
        connections = light.getConnections()
        nodes = {item[0].getEdge().getToNode().getID(): item[0].getEdge().getToNode().getCoord()
                 for item in connections}
        x = sum(point[0] for point in nodes.values()) / len(nodes)
        y = sum(point[1] for point in nodes.values()) / len(nodes)
        controllers.append({"review_index": review_index, "tls_id": tls_id,
                            "x_sumo_m": round(x, 2),
                            "y_sumo_m": round(y, 2), "junction_node_ids": ";".join(sorted(nodes)),
                            "controlled_links": len(connections), "phase_count": len(programs[tls_id]),
                            "mapped_spreadsheet_name": known.get(tls_id, ""),
                            "candidate_spreadsheet_name": candidates.get(tls_id, "")})
        for from_lane, to_lane, index in connections:
            links.append({"tls_id": tls_id, "link_index": index,
                          "from_lane": from_lane.getID(), "to_lane": to_lane.getID(),
                          "from_edge": from_lane.getEdge().getID(),
                          "to_edge": to_lane.getEdge().getID()})
        for index, phase in enumerate(programs[tls_id]):
            kind = audit_phase_kind(phase["state"])
            phases.append({"tls_id": tls_id, "phase_index": index,
                           "duration_seconds": phase["duration"], "state": phase["state"],
                           "kind": kind})
    nearby = []
    for index, first in enumerate(controllers):
        for second in controllers[index + 1:]:
            distance = math.hypot(first["x_sumo_m"] - second["x_sumo_m"],
                                  first["y_sumo_m"] - second["y_sumo_m"])
            if distance <= 60:
                nearby.append({"first_tls_id": first["tls_id"],
                               "second_tls_id": second["tls_id"],
                               "distance_m": round(distance, 1)})
    for name, rows in (("controllers.csv", controllers), ("links.csv", links),
                       ("phases.csv", phases), ("nearby_pairs.csv", nearby)):
        if rows:
            with (output / name).open("w", newline="", encoding="utf-8-sig") as file:
                writer = csv.DictWriter(file, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
    os.environ.setdefault("MPLCONFIGDIR", str(output / "matplotlib_cache"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection

    segments = [edge.getShape() for edge in network.getEdges(withInternal=False)
                if len(edge.getShape()) > 1]
    figure, axis = plt.subplots(figsize=(13, 12))
    axis.add_collection(LineCollection(segments, colors="#bec6cc", linewidths=0.5))
    for item in controllers:
        color = ("#21866d" if item["mapped_spreadsheet_name"] else
                 "#d18b00" if item["candidate_spreadsheet_name"] else "#bc312b")
        axis.scatter(item["x_sumo_m"], item["y_sumo_m"], s=24, color=color, zorder=3)
        axis.annotate(str(item["review_index"]),
                      (item["x_sumo_m"], item["y_sumo_m"]),
                      xytext=(3, 3), textcoords="offset points", fontsize=7)
    axis.autoscale()
    axis.set_aspect("equal")
    axis.set_xlabel("X local SUMO (m)")
    axis.set_ylabel("Y local SUMO (m)")
    axis.set_title("Controladores SUMO (número = review_index em controllers.csv)")
    figure.tight_layout()
    figure.savefig(output / "controllers_map.png", dpi=160)
    plt.close(figure)
    summary = {"controllers": len(controllers), "links": len(links),
               "nearby_pairs_within_60m": len(nearby), "edge_functions": edge_functions,
               "location": location, "mapping_validated_count": report["validated_count"],
               "note": "Proximidade espacial gera candidatos, não comprova nome ou agrupamento."}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
