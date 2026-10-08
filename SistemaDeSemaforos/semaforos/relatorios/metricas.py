"""Métricas obtidas dos arquivos SUMO, sem somar acumulados repetidamente."""

import math
import xml.etree.ElementTree as ET

import numpy as np


TRIP_FIELDS = {
    "duration": "travel_time_seconds",
    "waitingTime": "trip_waiting_seconds",
    "timeLoss": "time_loss_seconds",
    "waitingCount": "stops",
    "routeLength": "route_length_meters",
    "departDelay": "departure_delay_seconds",
}


def trip_summary(path, start=None, end=None):
    """Agrega apenas viagens concluídas; conta incompletas separadamente."""
    completed = []
    unfinished = 0
    for _, element in ET.iterparse(path, events=("end",)):
        if element.tag != "tripinfo":
            continue
        arrival = float(element.attrib.get("arrival", -1))
        departure = float(element.attrib.get('depart', 0))
        if end is not None and departure >= end:
            element.clear()
            continue
        if arrival < 0 or end is not None and arrival > end:
            unfinished += 1
        elif start is None or arrival > start:
            completed.append(element.attrib.copy())
        element.clear()
    result = {"tripinfo_completed": len(completed), "tripinfo_unfinished": unfinished}
    for attribute, label in TRIP_FIELDS.items():
        values = np.asarray([float(row[attribute]) for row in completed if attribute in row], dtype=float)
        result[f"mean_{label}"] = float(np.mean(values)) if len(values) else None
        result[f"p95_{label}"] = float(np.percentile(values, 95)) if len(values) else None
        for stat, function in (("std", np.std), ("min", np.min), ("max", np.max), ("median", np.median)):
            result[f"{stat}_{label}"] = float(function(values)) if len(values) else None
        for percentile in (50, 90, 99):
            result[f'p{percentile}_{label}'] = float(np.percentile(values, percentile)) if len(values) else None
    return result


def planned_vehicle_count(path):
    """Conta viagens explícitas e estima fluxos; informa a cobertura da contagem."""
    count = 0
    estimated = False
    for _, element in ET.iterparse(path, events=("end",)):
        if element.tag in ("vehicle", "trip"):
            count += 1
        elif element.tag == "flow":
            if "number" in element.attrib:
                count += int(element.attrib["number"])
            elif "vehsPerHour" in element.attrib:
                duration = float(element.attrib["end"]) - float(element.attrib.get("begin", 0))
                count += math.floor(float(element.attrib["vehsPerHour"]) * duration / 3600 + 0.5)
                estimated = True
            else:
                estimated = True
        element.clear()
    return {"planned_vehicles": count, "planned_vehicles_estimated": estimated}
