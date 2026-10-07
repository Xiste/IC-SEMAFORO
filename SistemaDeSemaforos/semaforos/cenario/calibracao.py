"""Ajuste não negativo de rotas de borda a contagens em trechos internos."""
import json
import math
import random
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

import numpy as np
import sumolib
from scipy.optimize import nnls


@lru_cache(maxsize=8)
def fit_routes(network_path, measurements, classes, network_version=None):
    net = sumolib.net.readNet(network_path)
    edges = {e.getID(): e for e in net.getEdges(withInternal=False)}
    valid = lambda e: all(e.allows(cls) for cls in classes)
    origins = [e for e in edges.values() if valid(e) and not any(valid(p) for p in e.getIncoming())]
    exits = [e for e in edges.values() if valid(e) and not any(valid(p) for p in e.getOutgoing())]
    if not origins or not exits:
        raise ValueError("Calibração precisa de entradas e saídas nas bordas da rede")
    candidates = set()
    for edge_id, rate in measurements:
        if edge_id not in edges or not valid(edges[edge_id]) or not math.isfinite(rate) or rate < 0:
            raise ValueError(f"Contagem inválida ou classe sem acesso em {edge_id}")
        if rate == 0:
            continue
        measured = edges[edge_id]
        incoming, outgoing = [], []
        for origin in origins:
            path, cost = net.getShortestPath(origin, measured, vClass=classes[0])
            if path and all(valid(e) for e in path):
                incoming.append((cost, tuple(e.getID() for e in path)))
        for destination in exits:
            path, cost = net.getShortestPath(measured, destination, vClass=classes[0])
            if path and all(valid(e) for e in path):
                outgoing.append((cost, tuple(e.getID() for e in path)))
        for _, before in sorted(incoming)[:6]:
            for _, after in sorted(outgoing)[:6]:
                path = before + after[1:]
                if len(path) == len(set(path)):
                    candidates.add(path)
    routes = sorted(candidates)
    if not routes:
        raise ValueError("Nenhuma rota de borda alcança as contagens informadas")
    matrix = np.asarray([[float(edge in path) for path in routes] for edge, _ in measurements])
    target = np.asarray([rate for _, rate in measurements])
    rates, _ = nnls(matrix, target, maxiter=max(100, len(routes) * 10))
    predicted = matrix @ rates
    rows = [{"from_edge": edge, "measured_vehicles_per_hour": rate,
             "fitted_vehicles_per_hour": float(value), "error_vehicles_per_hour": float(value - rate),
             "relative_error": float(abs(value - rate) / max(rate, 1))}
            for (edge, rate), value in zip(measurements, predicted)]
    selected = [(path, float(rate)) for path, rate in zip(routes, rates) if rate > 1e-6]
    return selected, rows


def calibration_report(config):
    entries = config["demand"].get("edge_volumes", [])
    measurements = tuple(sorted((row["from_edge"], float(row["vehicles_per_hour"])) for row in entries))
    if not measurements or len({edge for edge, _ in measurements}) != len(measurements) or not any(rate > 0 for _, rate in measurements):
        raise ValueError("Informe contagens distintas e ao menos um volume positivo")
    types = config["demand"].get("vehicle_types") or [{"vClass": "passenger"}]
    routes, rows = fit_routes(str(config["network"]), measurements, tuple(sorted({t["vClass"] for t in types})),
                             Path(config["network"]).stat().st_mtime_ns)
    return {"method": "nnls_border_routes", "synthetic_destinations": True,
            "total_generated_vehicles_per_hour": sum(rate for _, rate in routes),
            "route_count": len(routes), "measurements": rows,
            "routes": [{"edges": list(path), "vehicles_per_hour": rate} for path, rate in routes]}


def create_calibrated_demand(config, output, seed):
    from .demanda import validate_time_profile, validate_vehicle_types
    report = calibration_report(config)
    tolerance = float(config["demand"].get("calibration_tolerance", 0.2))
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("Tolerância de calibração inválida")
    (output / "calibration.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if any(row["relative_error"] > tolerance for row in report["measurements"]):
        raise ValueError("As rotas de borda não reproduzem as contagens na tolerância escolhida; confira o relatório de calibração")
    duration = float(config["duration_seconds"])
    profile = validate_time_profile(config)
    types = validate_vehicle_types(config)
    weights = [(float(w["end"]) - float(w["begin"])) * float(w["multiplier"]) for w in profile]
    rng = random.Random(seed)
    root = ET.Element("routes")
    for t in types:
        ET.SubElement(root, "vType", id=t["id"], vClass=t["vClass"])
    departures = []
    for index, route in enumerate(report["routes"]):
        ET.SubElement(root, "route", id=f"calibrated_{index}", edges=" ".join(route["edges"]))
        count = math.floor(route["vehicles_per_hour"] * duration / 3600 + 0.5)
        if len(departures) + count > 100000:
            raise ValueError("Calibração excede 100000 viagens")
        allocated = 0
        cumulative = 0.0
        for window, weight in zip(profile, weights):
            cumulative += count * weight / sum(weights)
            n = math.floor(cumulative + 0.5) - allocated
            allocated += n
            for k in range(n):
                depart = float(window["begin"]) + (k + 0.5) * (float(window["end"]) - float(window["begin"])) / n
                vehicle_type = rng.choices(types, weights=[float(t["share"]) for t in types])[0]
                departures.append((depart, {"id": f"calibrated_{index}_{allocated-n+k}", "route": f"calibrated_{index}",
                                             "type": vehicle_type["id"], "depart": f"{depart:.3f}"}))
    if not departures or len(departures) > 100000:
        raise ValueError("Calibração gera zero veículos ou excede 100000 viagens")
    for _, attributes in sorted(departures, key=lambda x: x[0]):
        ET.SubElement(root, "vehicle", attributes)
    routes_file = output / "routes.rou.xml"
    ET.ElementTree(root).write(routes_file, encoding="utf-8", xml_declaration=True)
    (output / "demand_manifest.json").write_text(json.dumps({**report, "seed": seed, "duration_seconds": duration,
                                                             "total_planned_vehicles": len(departures), "time_profile": profile,
                                                             "vehicle_types": types}, ensure_ascii=False, indent=2), encoding="utf-8")
    return routes_file
