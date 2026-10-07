"""Geração de rotas sintéticas ou fluxos informados por via."""

import subprocess
import sys
import json
import math
import random
import xml.etree.ElementTree as ET

from semaforos.cenario.configuracao import sumo_executable


def create_edge_volume_demand(config, network, output, seed):
    """Converte contagens por via em viagens com saídas conectadas.

    Na ausência de destino informado, a saída é sintética e sorteada entre
    bordas alcançáveis por automóveis. As partidas são espaçadas no horizonte.
    """
    entries = config["demand"].get("edge_volumes", [])
    if not entries:
        raise ValueError("Informe ao menos uma via em demand.edge_volumes")
    edges = {edge.getID(): edge for edge in network.getEdges(withInternal=False)}
    exits = [edge for edge in edges.values() if not edge.getOutgoing() and edge.allows("passenger")]
    if not exits:
        raise ValueError("A rede não contém vias de saída para gerar destinos automáticos")
    rng = random.Random(seed)
    duration = float(config["duration_seconds"])
    profile = config["demand"].get("time_profile") or [
        {"begin": 0, "end": duration, "multiplier": 1.0}]
    previous_end = 0.0
    for window in profile:
        begin, end, multiplier = (float(window[key]) for key in ("begin", "end", "multiplier"))
        if (not all(math.isfinite(value) for value in (begin, end, multiplier))
                or abs(begin - previous_end) > 1e-6 or end <= begin or end > duration
                or multiplier < 0):
            raise ValueError("Perfil temporal deve cobrir o horizonte sem lacunas e ter multiplicadores não negativos")
        previous_end = end
    if abs(previous_end - duration) > 1e-6:
        raise ValueError("Perfil temporal deve terminar em duration_seconds")
    weights_time = [(float(item["end"]) - float(item["begin"])) * float(item["multiplier"])
                    for item in profile]
    if sum(weights_time) <= 0:
        raise ValueError("Perfil temporal tem volume total zero")
    vehicle_types = config["demand"].get("vehicle_types") or [
        {"id": "car", "vClass": "passenger", "share": 1.0}]
    allowed_classes = {"passenger", "bus", "truck", "delivery", "motorcycle", "bicycle"}
    if (len({item["id"] for item in vehicle_types}) != len(vehicle_types)
            or any(item.get("vClass") not in allowed_classes
                   or not math.isfinite(float(item.get("share", 0)))
                   or float(item.get("share", 0)) <= 0
                   for item in vehicle_types)
            or abs(sum(float(item["share"]) for item in vehicle_types) - 1) > 1e-6):
        raise ValueError("Tipos de veículo exigem IDs únicos, classes válidas e proporções somando 1")
    seen = set()
    trips = []
    manifest = []
    for index, entry in enumerate(entries):
        origin = str(entry.get("from_edge", "")).strip()
        if origin in seen:
            raise ValueError(f"Via de origem repetida: {origin}")
        seen.add(origin)
        try:
            rate = float(entry["vehicles_per_hour"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"Via {index}: informe veículos/h numérico") from error
        if origin not in edges or not edges[origin].allows("passenger"):
            raise ValueError(f"Via {index}: origem ausente ou sem permissão para automóveis: {origin}")
        if not math.isfinite(rate) or rate < 0:
            raise ValueError(f"Via {index}: veículos/h deve ser finito e não negativo")
        count = math.floor(rate * duration / 3600 + 0.5)
        if count > 100000 or len(trips) + count > 100000:
            raise ValueError("Demanda acima do limite de 100000 viagens por cenário")
        fixed_exit = str(entry.get("to_edge") or "").strip()
        destination_mix = entry.get("destinations") or []
        if fixed_exit and destination_mix:
            raise ValueError(f"Via {index}: use to_edge ou destinations, não ambos")
        if fixed_exit and fixed_exit not in edges:
            raise ValueError(f"Via {index}: destino inexistente: {fixed_exit}")
        if destination_mix:
            if (any(item.get("to_edge") not in edges
                    or not math.isfinite(float(item.get("share", 0)))
                    or float(item.get("share", 0)) <= 0
                    for item in destination_mix)
                    or abs(sum(float(item["share"]) for item in destination_mix) - 1) > 1e-6):
                raise ValueError(f"Via {index}: destinos precisam existir e proporções somar 1")
            candidate_ids = [item["to_edge"] for item in destination_mix]
            destination_weights = [float(item["share"]) for item in destination_mix]
            destination_source = "weighted_user"
        elif fixed_exit:
            candidate_ids = [fixed_exit]
            destination_weights = [1.0]
            destination_source = "informed"
        else:
            candidate_ids = [edge.getID() for edge in exits]
            destination_weights = [1.0] * len(exits)
            destination_source = "synthetic_uniform_reachable_exits"
        available = {}
        if count:
            for vehicle_type in vehicle_types:
                vehicle_class = vehicle_type["vClass"]
                if not edges[origin].allows(vehicle_class):
                    raise ValueError(f"Via {index}: origem não aceita {vehicle_class}")
                valid = [(edge_id, weight) for edge_id, weight in zip(candidate_ids, destination_weights)
                         if edge_id != origin and edges[edge_id].allows(vehicle_class)
                         and network.getShortestPath(edges[origin], edges[edge_id],
                                                     vClass=vehicle_class)[0]]
                if destination_source != "synthetic_uniform_reachable_exits" and len(valid) != len(candidate_ids):
                    raise ValueError(f"Via {index}: destino informado não é alcançável por {vehicle_class}")
                if not valid:
                    raise ValueError(f"Via {index}: não há saída alcançável para {vehicle_class}")
                available[vehicle_type["id"]] = valid
        allocated = 0
        cumulative = 0.0
        for window, weight in zip(profile, weights_time):
            cumulative += count * weight / sum(weights_time)
            in_window = math.floor(cumulative + 0.5) - allocated
            allocated += in_window
            begin, end = float(window["begin"]), float(window["end"])
            for number in range(in_window):
                vehicle_type = rng.choices(vehicle_types,
                                           weights=[float(item["share"]) for item in vehicle_types])[0]
                valid = available[vehicle_type["id"]]
                destination = rng.choices([item[0] for item in valid],
                                          weights=[item[1] for item in valid])[0]
                depart = begin + (number + 0.5) * (end - begin) / in_window
                trips.append((depart, {"id": f"via_{index}_{len(trips)}",
                                       "depart": f"{depart:.3f}", "from": origin,
                                       "to": destination, "type": vehicle_type["id"]}))
        manifest.append({"from_edge": origin, "vehicles_per_hour": rate,
                         "planned_vehicles": count, "to_edge": fixed_exit or None,
                         "destinations": destination_mix,
                         "destination_source": destination_source})
    if not trips:
        raise ValueError("Os volumes e a duração selecionados geram zero veículos")
    root = ET.Element("routes")
    for vehicle_type in vehicle_types:
        ET.SubElement(root, "vType", {"id": vehicle_type["id"], "vClass": vehicle_type["vClass"]})
    for _, attributes in sorted(trips, key=lambda item: item[0]):
        ET.SubElement(root, "trip", attributes)
    routes = output / "routes.rou.xml"
    ET.ElementTree(root).write(routes, encoding="utf-8", xml_declaration=True)
    (output / "demand_manifest.json").write_text(json.dumps({
        "mode": "edge_volumes", "seed": seed, "duration_seconds": duration,
        "total_planned_vehicles": len(trips), "time_profile": profile,
        "vehicle_types": vehicle_types, "entries": manifest,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return routes


def create_demand(config, network, output, seed):
    demand = config["demand"]
    routes = output / "routes.rou.xml"
    if demand["mode"] == "edge_volumes":
        return create_edge_volume_demand(config, network, output, seed)
    if demand["mode"] == "random":
        rate = demand["vehicles_per_hour"]
        if rate <= 0:
            raise ValueError("vehicles_per_hour deve ser positivo")
        tool = sumo_executable().parent.parent / "tools" / "randomTrips.py"
        if not tool.is_file():
            raise RuntimeError(f"randomTrips.py não encontrado: {tool}")
        result = subprocess.run([
            sys.executable, str(tool), "-n", str(config["network"]),
            "-o", str(output / "trips.trips.xml"), "--route-file", str(routes),
            "-b", "0", "-e", str(config["duration_seconds"]),
            "-p", str(3600 / rate), "--seed", str(seed),
        ], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f"Falha ao gerar rotas: {result.stderr[-2000:]}")
    else:
        known_edges = {edge.getID(): edge for edge in network.getEdges(withInternal=False)}
        if not demand["flows"]:
            raise ValueError("demand.flows está vazio")
        root = ET.Element("routes")
        for index, flow in enumerate(demand["flows"]):
            origin, destination = flow["from_edge"], flow["to_edge"]
            rate = float(flow["vehicles_per_hour"])
            if origin not in known_edges or destination not in known_edges or not math.isfinite(rate) or rate <= 0:
                raise ValueError(f"Fluxo {index}: vias ausentes ou taxa inválida")
            if origin == destination:
                raise ValueError(f"Fluxo {index}: origem e destino devem ser diferentes")
            path, _ = network.getShortestPath(known_edges[origin], known_edges[destination])
            if not path:
                raise ValueError(f"Fluxo {index}: não há percurso conectado de {origin} até {destination}")
            ET.SubElement(root, "flow", {
                "id": f"flow_{index}", "from": origin, "to": destination,
                "begin": "0", "end": str(config["duration_seconds"]),
                "vehsPerHour": str(rate),
            })
        ET.ElementTree(root).write(routes, encoding="utf-8", xml_declaration=True)
    return routes
