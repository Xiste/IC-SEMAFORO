"""Inventário e validação das fases presentes na rede SUMO."""

import xml.etree.ElementTree as ET
from math import ceil

import sumolib

from .planos import read_plans


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
        lower = max(training["minimum_yellow_seconds"], ceil(duration))
        upper = max(lower + 1, ceil(duration * 1.4))
    else:
        lower = max(training["minimum_all_red_seconds"], ceil(duration))
        upper = max(lower + 2, ceil(duration * 1.4))
    return lower, upper


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


def baseline_values(config, programs):
    return {
        f'{target["tls_id"]}:{index}': programs[target["tls_id"]][index]["duration"]
        for target in config["targets"] for index in target["phase_indices"]
    }


def inventory(config):
    network = sumolib.net.readNet(str(config["network"]))
    programs = network_programs(config["network"])
    return {
        "spreadsheet_intersections": read_plans(config["plans"]),
        "network_traffic_lights": [
            {"id": light.getID(),
             "x": light.getConnections()[0][0].getEdge().getToNode().getCoord()[0],
             "y": light.getConnections()[0][0].getEdge().getToNode().getCoord()[1],
             "incoming_edges": sorted({connection[0].getEdge().getID()
                                       for connection in light.getConnections()}),
             "phases": programs[light.getID()]}
            for light in network.getTrafficLights()
        ],
        "note": "A planilha não contém IDs SUMO; confira a correspondência antes de adicionar targets.",
    }
