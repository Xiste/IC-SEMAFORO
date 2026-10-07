"""Inventário e validação das fases presentes na rede SUMO."""

import xml.etree.ElementTree as ET
from math import ceil
import math

import sumolib

from semaforos.cenario.planos import read_plans
from semaforos.cenario.configuracao import control_parameters


def network_programs(path):
    programs = {}
    for _, element in ET.iterparse(path, events=("end",)):
        if element.tag == "tlLogic":
            programs[element.attrib["id"]] = [
                {"duration": float(phase.attrib["duration"]), "state": phase.attrib["state"]}
                for phase in element.findall("phase")
            ]
            element.clear()
    return programs


def phase_kind(state):
    if any(color in "yY" for color in state):
        return "yellow"
    if any(color in "Gg" for color in state):
        return "green"
    if state and all(color in "rR" for color in state):
        return "all_red"
    raise ValueError(f"Estado de fase não suportado para treino: {state}")


def phase_bounds(config, phase):
    duration = phase["duration"]
    kind = phase_kind(phase["state"])
    training = config["training"]
    if kind == "green":
        lower = max(training["minimum_green_seconds"], int(duration * 0.6))
        upper = max(lower, ceil(duration * 1.4))
    elif kind == "yellow":
        if duration < training["minimum_yellow_seconds"]:
            raise ValueError("Amarelo da rede abaixo do mínimo configurado; valide o plano")
        lower = upper = duration
    else:
        if duration < training["minimum_all_red_seconds"]:
            raise ValueError("Limpeza da rede abaixo do mínimo configurado; valide o plano")
        lower = upper = duration
    return lower, upper


def phase_action_spec(config, programs):
    """Lista as durações que cada componente da ação PPO pode selecionar."""
    params = control_parameters(config)
    mode = params.get("action_mode", "green_extension")
    if mode == "green_extension":
        return mode, [{"tls_id": target["tls_id"]} for target in config["targets"]]
    if mode != "phase_durations":
        raise ValueError("ppo.action_mode deve ser green_extension ou phase_durations")
    kinds = params.get("phase_types", ["green", "yellow", "all_red"])
    if not kinds or set(kinds) - {"green", "yellow", "all_red"}:
        raise ValueError("ppo.phase_types contém tipos de fase inválidos")
    overrides = params.get("phase_duration_bounds", {})
    limits = params.get("duration_limits", {})
    specs = []
    for target in config["targets"]:
        tls_id = target["tls_id"]
        for index, phase in enumerate(programs[tls_id]):
            try:
                kind = phase_kind(phase["state"])
            except ValueError:
                continue
            if kind not in kinds or (kind == "green" and index not in target["phase_indices"]):
                continue
            default_low, default_high = phase_bounds(config, phase)
            settings = {**limits.get(kind, {}), **overrides.get(f"{tls_id}:{index}", {})}
            low = float(settings.get("minimum_seconds", default_low))
            high = float(settings.get("maximum_seconds", default_high))
            reference = phase["duration"]
            floor = (config["training"]["minimum_green_seconds"] if kind == "green"
                     else max(reference, default_low))
            if kind == "green" and config.get("experimental"):
                floor = max(floor, config["experimental"].get("green_floors", {}).get(f"{tls_id}:{index}", floor))
            if (not all(math.isfinite(value) for value in (low, high, reference))
                    or low < floor or low > reference or high < reference or high < low):
                raise ValueError(f"Limites PPO inválidos para {tls_id}:{index}; precisam incluir a duração original e respeitar o mínimo {floor} s")
            step = float(config["step_seconds"])
            if any(abs(value / step - round(value / step)) > 1e-6 for value in (low, reference, high)):
                raise ValueError(f"Durações PPO de {tls_id}:{index} devem ser múltiplos de step_seconds")
            specs.append({"tls_id": tls_id, "phase_index": index, "kind": kind,
                          "durations_seconds": [low, reference, high]})
    if not specs:
        raise ValueError("Nenhuma fase selecionada para o PPO")
    if set(overrides) - {f"{item['tls_id']}:{item['phase_index']}" for item in specs}:
        raise ValueError("phase_duration_bounds contém fases fora do controle PPO")
    cap = params.get("maximum_cycle_seconds")
    if cap is not None:
        if not math.isfinite(float(cap)) or float(cap) <= 0:
            raise ValueError("Máximo de ciclo deve ser finito e positivo")
        for target in config["targets"]:
            maxima = {item["phase_index"]: max(item["durations_seconds"]) for item in specs if item["tls_id"] == target["tls_id"]}
            longest = sum(maxima.get(index, phase["duration"]) for index, phase in enumerate(programs[target["tls_id"]]))
            if longest > float(cap):
                raise ValueError(f"Limites de {target['tls_id']} excedem o máximo de ciclo {cap} s")
    return mode, specs


def validate_targets(config, programs):
    seen = set()
    for target in config["targets"]:
        tls_id = target["tls_id"]
        if tls_id not in programs or tls_id in seen:
            raise ValueError(f"ID de semáforo inválido ou repetido: {tls_id}")
        seen.add(tls_id)
        indices = target["phase_indices"]
        if len(indices) != len(set(indices)) or not indices:
            raise ValueError(f"Índices de fases inválidos em {tls_id}")
        for index in indices:
            if not isinstance(index, int) or index < 0 or index >= len(programs[tls_id]):
                raise ValueError(f"Índice de fase inválido: {tls_id}:{index}")
            phase_kind(programs[tls_id][index]["state"])
            phase_bounds(config, programs[tls_id][index])


def baseline_values(config, programs):
    return {
        f'{target["tls_id"]}:{index}': programs[target["tls_id"]][index]["duration"]
        for target in config["targets"] for index in target["phase_indices"]
    }


def inventory(config):
    network = sumolib.net.readNet(str(config["network"]))
    programs = network_programs(config["network"])
    import xml.etree.ElementTree as ET
    counts = {tag: 0 for tag in ("tlLogic", "route", "vehicle", "flow")}
    for _, element in ET.iterparse(config["network"], events=("end",)):
        if element.tag in counts:
            counts[element.tag] += 1
        element.clear()
    return {
        "spreadsheet_intersections": read_plans(config["plans"]),
        "network_element_counts": counts,
        "network_traffic_lights": [
            {"id": light.getID(),
             "x": light.getConnections()[0][0].getEdge().getToNode().getCoord()[0],
             "y": light.getConnections()[0][0].getEdge().getToNode().getCoord()[1],
             "incoming_edges": sorted({connection[0].getEdge().getID()
                                       for connection in light.getConnections()}),
             "controlled_movements": [
                 {"index": connection[2], "from_lane": connection[0].getID(),
                  "to_lane": connection[1].getID()}
                 for connection in light.getConnections()],
             "phases": programs[light.getID()]}
            for light in network.getTrafficLights()
        ],
        "note": "A planilha não contém IDs SUMO; confirme nomes, links e estágios antes de controlar os nove cruzamentos.",
    }
