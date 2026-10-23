"""MetaSettran regional: viagens entre portais e observações compartilhadas.

Os dados medidos definem taxas; uma seed sorteia partidas e pares OD. O
duarouter calcula os percursos e o gerador verifica todos os endpoints antes
de publicar os XMLs. Correspondências espaciais inferidas continuam explícitas
nos metadados: executar o protótipo não confirma a localização dos sensores.
"""

from datetime import datetime, timezone
from contextlib import ExitStack
from bisect import bisect_left, bisect_right
from copy import deepcopy
import hashlib
from itertools import accumulate, product
import json
import math
from pathlib import Path
import random
import secrets
import shutil
import subprocess
from tempfile import TemporaryDirectory
import time
import xml.etree.ElementTree as ET

from SistemaDeSemaforos.demand.metasettran_calibration import (
    integrate_rate, interpolate_rate,
)
from SistemaDeSemaforos.demand.metasettran_transitions import compose_rate_curves, transport_times
from SistemaDeSemaforos.demand.random_demand_generator import (
    DEFAULT_NET_FILE, DEFAULT_OUTPUT_DIR,
)


MODEL_VERSION = "metasettran-regional-integrated-v4.3.2-utc"
SEED_NAMESPACE = "metasettran-prototype-v1"
ROUTING_SEED = 0
COMPOSITION_VERSION = "metasettran-chronological-v1"
SPATIAL_SCENARIOS = ("regional-integrated", "regional-midpoint")
DEFAULT_DURATION = 10800.0
DEFAULT_CLEARANCE = 2700.0
DEFAULT_CSV_FILE = Path(__file__).resolve().parents[2] / "docs" / "Medicoes_5_6.csv"
DEFAULT_SPATIAL_FILE = Path(__file__).with_name("metasettran_spatial.json")
WEEK_START_SECONDS = 86400 + 15 * 3600
DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def validate_selection(day="tuesday", start="15:00", sections=1, variation=1, seed=None):
    """Uma janela semanal consecutiva, sem seleções descontínuas ou datas implícitas."""
    if day not in DAYS or start not in {f"{hour:02d}:00" for hour in range(0, 24, 3)}:
        raise ValueError("day/start devem identificar um dia e uma seção de três horas.")
    if isinstance(sections, bool) or not isinstance(sections, int) or not 1 <= sections <= 56:
        raise ValueError("sections deve ser um inteiro entre 1 e 56, em sequência.")
    if isinstance(variation, bool) or not isinstance(variation, int) or not 1 <= variation <= 25:
        raise ValueError("variation deve ser um inteiro entre 1 e 25.")
    if seed is not None and (
        isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**31
    ):
        raise ValueError("seed deve ser um inteiro entre 0 e 2147483647.")


def effective_seed(variation, seed=None):
    """Identificador estável, independente de controlador e perfil de métricas."""
    validate_selection(variation=variation, seed=seed)
    if seed is not None:
        return seed
    value = hashlib.sha256(f"{SEED_NAMESPACE}:variation:{variation}".encode()).digest()
    return int.from_bytes(value[:4], "big") & 0x7FFFFFFF


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _stream_seed(seed, group_id, purpose):
    return int.from_bytes(hashlib.sha256(f"{seed}:{group_id}:{purpose}".encode()).digest(), "big")


def resolve_contexts(day="tuesday", start="15:00", sections=1, variation=None,
                     seed=None, master_seed=None, variations=None):
    """Resolve uma sequência uma vez, independente do controlador/observação."""
    validate_selection(day, start, sections, 1 if variation is None else variation, seed)
    if master_seed is not None and (isinstance(master_seed, bool) or not isinstance(master_seed, int)
                                    or not 0 <= master_seed < 2**63):
        raise ValueError("master_seed deve ser inteiro entre 0 e 2**63-1.")
    if variation is not None and (sections != 1 or variations is not None or master_seed is not None):
        raise ValueError("--variation escolhe uma faixa individual; use --variations ou --master-seed para sequências.")
    if seed is not None and (sections != 1 or variations is not None or master_seed is not None):
        raise ValueError("seed efetiva legada exige uma faixa; utilize master_seed para composição.")
    if variations is not None:
        if not isinstance(variations, (list, tuple)) or len(variations) != sections:
            raise ValueError("Forneça exatamente uma variação para cada faixa.")
        for selected in variations:
            validate_selection(variation=selected)
        selected_variations = list(variations)
        method = "explicit_sequence"
    elif sections == 1 and master_seed is None:
        selected_variations = [1 if variation is None else variation]
        method = "individual_variation"
    else:
        master_seed = secrets.randbits(63) if master_seed is None else master_seed
        rng = random.Random(_stream_seed(master_seed, COMPOSITION_VERSION, "context_variations"))
        selected_variations = [rng.randrange(1, 26) for _ in range(sections)]
        method = "independent_uniform_1_to_25"
    begin = selection_start_week_second(day, start)
    contexts = []
    for index, selected in enumerate(selected_variations):
        absolute = begin + index * int(DEFAULT_DURATION)
        clock = absolute % 86400
        contexts.append({"index": index, "day": DAYS[(absolute // 86400) % 7],
                         "start": f"{clock // 3600:02}:00", "start_week_second": absolute,
                         "begin": index * int(DEFAULT_DURATION), "end": (index + 1) * int(DEFAULT_DURATION),
                         "week_offset": absolute // 604800,
                         "variation": selected, "effective_seed": effective_seed(selected, seed)})
    # A sequência explícita reproduz a demanda sem precisar da seed que a sorteou.
    token = f"{COMPOSITION_VERSION}|{day}|{start}|{','.join(map(str, selected_variations))}"
    run_seed = (contexts[0]["effective_seed"] if sections == 1 else
                int.from_bytes(hashlib.sha256(token.encode()).digest()[:4], "big") & 0x7fffffff)
    return {"version": COMPOSITION_VERSION, "method": method, "master_seed": master_seed,
            "seed": run_seed, "contexts": contexts, "variations": selected_variations,
            "combinations": 25**sections}


def _passenger_allowed(lane):
    allow = lane.get("allow")
    disallow = lane.get("disallow", "").split()
    return (allow is None or "passenger" in allow.split() or "all" in allow.split()) and (
        "passenger" not in disallow and "all" not in disallow
    )


def _read_network(path):
    """Lê permissões e conexões para validar; não calcula caminhos."""
    root = ET.parse(path).getroot()
    junctions = {j.get("id"): (float(j.get("x")), float(j.get("y")))
                 for j in root.findall("junction") if j.get("x") is not None}
    edges, lane_index = {}, {}
    for edge in root.findall("edge"):
        for position, lane in enumerate(edge.findall("lane")):
            lane_index[lane.get("id")] = (edge, lane, str(position))
        if edge.get("function") == "internal":
            continue
        lanes = {lane.get("index"): lane for lane in edge.findall("lane") if _passenger_allowed(lane)}
        if lanes:
            edges[edge.get("id")] = {
                "lanes": lanes,
                "length": min(float(lane.get("length")) for lane in lanes.values()),
                "time": min(float(lane.get("length")) / float(lane.get("speed", "13.89")) for lane in lanes.values()),
                "hierarchy": edge.get("type", "unclassified"),
                "shape": [tuple(map(float, point.split(","))) for point in next(iter(lanes.values())).get("shape", "").split()],
                "from": edge.get("from"), "to": edge.get("to"),
                "from_xy": junctions.get(edge.get("from")), "to_xy": junctions.get(edge.get("to")),
            }
    continuations = {}
    for connection in root.findall("connection"):
        continuations.setdefault((connection.get("from"), connection.get("fromLane")), []).append(connection)

    def internal_cost(via, destination, destination_lane, visited=frozenset()):
        if not via:
            return (0.0, 0.0)
        if via in visited or via not in lane_index:
            return None
        edge, lane, lane_position = lane_index[via]
        if edge.get("function") != "internal" or not _passenger_allowed(lane):
            return None
        options = []
        for connection in continuations.get((edge.get("id"), lane_position), []):
            if connection.get("to") == destination and connection.get("toLane") == destination_lane:
                remainder = internal_cost(connection.get("via"), destination, destination_lane, visited | {via})
                if remainder is not None:
                    length = float(lane.get("length"))
                    options.append((length + remainder[0], length / float(lane.get("speed", "13.89")) + remainder[1]))
        return min(options) if options else None

    connections, returns, connection_costs = set(), set(), {}
    for connection in root.findall("connection"):
        source, target = connection.get("from"), connection.get("to")
        if source in edges and target in edges:
            if (connection.get("fromLane") in edges[source]["lanes"] and
                    connection.get("toLane") in edges[target]["lanes"]):
                connections.add((source, target))
                cost = internal_cost(connection.get("via"), target, connection.get("toLane"))
                if cost is None:
                    raise ValueError(f"Conexão interna passenger sem continuação: {source} -> {target}")
                previous = connection_costs.get((source, target))
                if previous is None or cost < previous:
                    connection_costs[source, target] = cost
                if connection.get("dir") == "t":
                    returns.add((source, target))
    return edges, connections, returns, connection_costs


def _write_xml(path, root):
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _routes_root():
    root = ET.Element("routes")
    # Somente a classe é declarada; parâmetros físicos permanecem nos defaults SUMO.
    ET.SubElement(root, "vType", id="metasettran_car", vClass="passenger")
    return root


def _route_pairs(model, net_file, directory, seed, log_file):
    """Descobre caminhos nativos; filtra candidatos antes de sortear viagens."""
    edges, connections, returns, connection_costs = _read_network(net_file)
    # A lane changing into several destination lanes remains ONE opportunity.
    # These are geometric priors, never green times or observed discharge rates.
    movement_lanes = {}
    for connection in ET.parse(net_file).getroot().findall("connection"):
        source, target = connection.get("from"), connection.get("to")
        if (source, target) in connections:
            if (connection.get("fromLane") in edges[source]["lanes"] and
                    connection.get("toLane") in edges[target]["lanes"]):
                movement_lanes.setdefault((source, target), set()).add(connection.get("fromLane"))
    entries = {portal["edge"]: portal for portal in model["portals"]["entries"]}
    exits = {portal["edge"]: portal for portal in model["portals"]["exits"]}
    if not entries or not exits or not (entries.keys() | exits.keys()) <= edges.keys():
        raise ValueError("Portais ausentes ou sem permissão passenger na rede selecionada.")
    if len(entries) != len(model["portals"]["entries"]) or len(exits) != len(model["portals"]["exits"]):
        raise ValueError("Portal duplicado no cadastro.")
    if entries.keys() & {target for _, target in connections} or exits.keys() & {source for source, _ in connections}:
        raise ValueError("Cadastro contém portais internos à conectividade passenger.")
    for portal in (*entries.values(), *exits.values()):
        if portal["passenger_lanes"] != len(edges[portal["edge"]]["lanes"]):
            raise ValueError("Faixas passenger do portal divergem da rede usada no prior.")
        if (portal.get("status") != "geographically_audited_boundary" or
                not portal.get("references") or not portal.get("boundary_evidence")):
            raise ValueError("Portal exige qualificação cartográfica explícita além da conectividade.")
        endpoint = "from" if portal["edge"] in entries else "to"
        if portal.get("boundary_node") != edges[portal["edge"]][endpoint]:
            raise ValueError("Nó geográfico do portal diverge do extremo da rede.")
        coordinates = edges[portal["edge"]].get(endpoint + "_xy")
        if coordinates and math.dist(coordinates, portal.get("boundary_xy_m", [])) > 0.05:
            raise ValueError("Coordenadas cartográficas do portal divergem da rede.")
    sensors = {str(item["sensor_id"]): item["selected_observation_edge"] for item in model["sensors"]}
    if set(sensors) != {"5", "6"} or len(set(sensors.values())) != 2 or not set(sensors.values()) <= edges.keys():
        raise ValueError("A calibração requer dois edges distintos e válidos para sensores 5 e 6.")
    probes = dict(sensors)
    directional = model["regional_demand"].get("directional_prior", {})
    if directional.get("probe_edge"):
        probes["rondon_reverse_estimate"] = directional["probe_edge"]
        if directional["probe_edge"] not in edges:
            raise ValueError("Seção direcional estimada ausente da rede.")
    rejected, pairs = {}, {}

    def reject(reason):
        rejected[reason] = rejected.get(reason, 0) + 1

    trips = _routes_root()
    for origin, entry in sorted(entries.items()):
        for destination, exit_portal in sorted(exits.items()):
            identifier = f"od_{len(pairs):04d}"
            pairs[identifier] = {"id": identifier, "origin": origin, "destination": destination}
            ET.SubElement(trips, "trip", {
                "id": identifier, "type": "metasettran_car", "depart": "0",
                "from": origin, "to": destination, "departPos": "0", "arrivalPos": "max",
            })
    # Alternativas são caminhos nativos via corredores documentados. A incidência
    # observada nunca seleciona uma população exclusiva de origens.
    for template in model.get("route_templates", []):
        for origin in template["origins"]:
            for destination in sorted(template.get("destinations", exits)):
                if origin not in entries or destination not in exits or not set(template["via"]) <= edges.keys():
                    raise ValueError("Template de corredor usa entrada ou via desconhecida.")
                identifier = f"od_{len(pairs):04d}"
                pairs[identifier] = {"id": identifier, "origin": origin, "destination": destination,
                                     "template": template["id"], "via": template["via"],
                                     "require_junction_simple": template.get("require_junction_simple", False)}
                ET.SubElement(trips, "trip", id=identifier, type="metasettran_car", depart="0",
                              **{"from": origin, "to": destination, "via": " ".join(template["via"]),
                                 "departPos": "0", "arrivalPos": "max"})
    if not pairs:
        raise ValueError("Nenhum par entre entradas e saídas da fronteira.")
    template_trips, template_routes = directory / "portals.trips.xml", directory / "portals.rou.xml"
    _write_xml(template_trips, trips)
    binary = shutil.which("duarouter")
    if binary is None:
        raise FileNotFoundError("Executável duarouter não encontrado no PATH.")
    command = [binary, "--net-file", str(net_file), "--route-files", str(template_trips),
               "--output-file", str(template_routes), "--alternatives-output", str(directory / "alternatives.xml"),
               "--seed", str(ROUTING_SEED), "--ignore-errors", "true", "--no-step-log", "true"]
    if log_file is None:
        subprocess.run(command, check=True)
    else:
        log_file = Path(log_file).expanduser().resolve()
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("w", encoding="utf-8") as log:
            subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)
    found, accepted, distinct = set(), {}, set()
    for vehicle in ET.parse(template_routes).getroot().findall("vehicle"):
        identifier = vehicle.get("id")
        if identifier not in pairs or identifier in found:
            raise ValueError("duarouter produziu identificador OD inesperado ou duplicado.")
        found.add(identifier)
        pair = pairs[identifier]
        route_element = vehicle.find("route")
        route = route_element.get("edges", "").split() if route_element is not None else []
        if (not route or route[0] != pair["origin"] or route[-1] != pair["destination"] or
                any(edge not in edges for edge in route) or
                any(connection not in connections for connection in zip(route, route[1:]))):
            raise ValueError(f"Percurso inválido ou endpoints alterados: {identifier}")
        via = pair.get("via", [])
        if any(edge not in route for edge in via) or [route.index(edge) for edge in via] != sorted({route.index(edge) for edge in via}):
            raise ValueError(f"Percurso não respeita as seções ordenadas do template: {identifier}")
        if len(route) != len(set(route)):
            reject("repeated_edge_detour")
            continue
        route_nodes = [edges[route[0]]["from"]] + [edges[edge]["to"] for edge in route]
        if pair.get("require_junction_simple") and len(route_nodes) != len(set(route_nodes)):
            # Uma via imposta para atravessar um corredor não deve criar uma
            # volta até o mesmo cruzamento. Retornos nativos entre portais
            # continuam permitidos; o filtro não depende de sensores.
            reject("through_template_revisits_junction")
            continue
        if tuple(route) in distinct:
            reject("duplicate_route_alternative")
            continue
        distinct.add(tuple(route))
        entry, exit_portal = entries[pair["origin"]], exits[pair["destination"]]
        normal_length = sum(edges[e]["length"] for e in route)
        internal_length = sum(connection_costs[c][0] for c in zip(route, route[1:]))
        travel_time = sum(edges[e]["time"] for e in route) + sum(connection_costs[c][1] for c in zip(route, route[1:]))
        sensor_ids = sorted(sensor for sensor, edge in sensors.items() if edge in route)
        corridors = sorted(item["id"] for item in model.get("corridors", []) if set(item["edges"]) & set(route))
        passage_delays, elapsed = {}, 0.0
        for position, edge in enumerate(route):
            for sensor, probe in probes.items():
                if edge == probe:
                    passage_delays[sensor] = elapsed
            elapsed += edges[edge]["time"]
            if position + 1 < len(route):
                elapsed += connection_costs[edge, route[position + 1]][1]
        pair.update(route=route, sensor_ids=sensor_ids,
                    movement_opportunities=[len(movement_lanes[c]) for c in zip(route, route[1:])],
                    movement_angles=[_movement_angle(edges[a], edges[b]) for a, b in zip(route, route[1:])],
                    observation_freeflow_delay_s=passage_delays,
                    observation_movements={sensor: {"edge": sensors[sensor],
                        "next_edge": route[route.index(sensors[sensor]) + 1] if route.index(sensors[sensor]) + 1 < len(route) else None}
                        for sensor in sensor_ids},
                    returns_to_same_access=entry["boundary_group"] == exit_portal["boundary_group"],
                    has_uturn=any(connection in returns for connection in zip(route, route[1:])),
                    normal_edge_count=len(route),
                    origin_corridor=entry["corridor"], destination_corridor=exit_portal["corridor"],
                    corridors=corridors, normal_length_m=normal_length, internal_length_m=internal_length,
                    length_m=normal_length + internal_length, freeflow_time_s=travel_time)
        accepted[identifier] = pair
    for _ in set(pairs) - found:
        reject("unreachable")
    if not accepted:
        raise ValueError("Nenhum percurso contínuo entre os portais de entrada e saída.")
    catalog = {"candidate_pairs": len(pairs), "distinct_endpoint_pairs": len(entries) * len(exits), "routed_candidates": len(pairs),
               "accepted_pairs": len(accepted), "rejected_by_reason": rejected,
               "entry_portals_available": len(entries), "exit_portals_available": len(exits),
               "entries_without_admissible_route": sorted(entries.keys() - {p["origin"] for p in accepted.values()}),
               "exits_without_admissible_route": sorted(exits.keys() - {p["destination"] for p in accepted.values()})}
    if len(accepted) + sum(rejected.values()) != catalog["candidate_pairs"]:
        raise ValueError("Auditoria de pares OD não conserva todos os candidatos.")
    return accepted, command, catalog, edges


def _movement_angle(source, target):
    """Magnitude of the actual change of heading, including permitted returns."""
    a, b = source.get("shape", []), target.get("shape", [])
    if len(a) < 2 or len(b) < 2:
        return 0.0
    incoming = (a[-1][0] - a[-2][0], a[-1][1] - a[-2][1])
    outgoing = (b[1][0] - b[0][0], b[1][1] - b[0][1])
    denominator = math.hypot(*incoming) * math.hypot(*outgoing)
    return math.acos(max(-1.0, min(1.0, sum(x*y for x,y in zip(incoming,outgoing)) / denominator))) if denominator else 0.0


def _mapping_sensitivity(pairs, model, calibration):
    """Projeta a MESMA demanda nos candidatos; nunca reescala o total."""
    sensors = {str(s["sensor_id"]): s for s in model["sensors"]}
    alternatives = [sorted({sensors[s]["selected_observation_edge"]} |
                           {c["edge"] for c in sensors[s].get("candidates", [])}) for s in ("5", "6")]
    results = []
    for edge5, edge6 in product(*alternatives):
        expected = {s: sum(p["expected_departures"] for p in pairs.values() if edge in p["route"])
                    for s, edge in (("5", edge5), ("6", edge6))}
        results.append({"observation_edges": {"5": edge5, "6": edge6},
                        "selected": edge5 == sensors["5"]["selected_observation_edge"] and edge6 == sensors["6"]["selected_observation_edge"],
                        "expected_sensor_passages": expected,
                        "expected_network_departures": sum(p["expected_departures"] for p in pairs.values()),
                        "scope": "full_planned_route_incidence; not physical passages within the civil window",
                        "status": "fixed_demand_projection_not_confirmed_mapping"})
    return results


def _linear_segments(knots, multiplier=1.0, begin=WEEK_START_SECONDS, duration=DEFAULT_DURATION):
    """Recorta uma curva contínua nos limites da janela de partidas."""
    end = begin + duration
    times = [begin] + [item["week_second"] for item in knots if begin < item["week_second"] < end] + [end]
    if times != sorted(set(times)):
        raise ValueError("Knots temporais devem ser únicos e ordenados.")
    points = [(timestamp - begin, interpolate_rate(knots, timestamp) * multiplier) for timestamp in times]
    if any(not math.isfinite(rate) or rate < 0 for _, rate in points):
        raise ValueError("Taxa temporal negativa ou não finita.")
    return [(t0, t1, r0, r1) for (t0, r0), (t1, r1) in zip(points, points[1:])]


def _departures(segments, rng):
    """Processo Poisson não homogêneo por inversão da intensidade integrada.

    Esta variabilidade é condicional à curva calibrada. Não pretende reproduzir
    a dispersão empírica entre datas, que fica disponível na calibração.
    """
    hazard = rng.expovariate(1.0)
    for begin, end, rate0, rate1 in segments:
        duration = end - begin
        area = duration * (rate0 + rate1) / 2
        slope = (rate1 - rate0) / duration
        while hazard < area:
            # Forma racionalizada da raiz quadrática evita cancelamento.
            denominator = rate0 + math.sqrt(max(0.0, rate0 * rate0 + 2 * slope * hazard))
            offset = 2 * hazard / denominator if denominator else 0.0
            yield begin + offset
            hazard += rng.expovariate(1.0)
        hazard -= area


def selection_start_week_second(day, start):
    return DAYS.index(day) * 86400 + int(start[:2]) * 3600


def _regional_prior(pairs, model):
    """Um prior OD; alternativas não multiplicam a oportunidade de um par."""
    config = model["regional_demand"]
    importance = config["destination_hierarchy_weights"]
    relative_evidence = config.get("relative_corridor_evidence", {})
    observed_vmd = model.get("sources", {}).get("regional_counts", {})
    source_values = sorted(observed_vmd[key]["vmd"] / observed_vmd[key]["monitored_lanes"]
                           for key in relative_evidence.values())
    reference = sum(source_values) / len(source_values) if source_values else 1.0

    def portal_weights(portals):
        by_access = {}
        for portal in portals:
            by_access.setdefault(portal["boundary_group"], []).append(portal)
        result = {}
        for members in by_access.values():
            # Oportunidade por acesso físico orientado, não orçamento por nome
            # de rua: duas extremidades da Rondon não dividem uma única faixa.
            # Representações alternativas do mesmo acesso repartem sua massa.
            opportunities = []
            for portal in members:
                hierarchy = portal.get("prior_road_type", portal.get("road_type", ""))
                value = importance.get(hierarchy, 1.0) * portal["passenger_lanes"]
                if portal["corridor"] in relative_evidence:
                    source = observed_vmd[relative_evidence[portal["corridor"]]]
                    value *= source["vmd"] / source["monitored_lanes"] / reference
                opportunities.append(value)
            mass, denominator = max(opportunities), sum(opportunities)
            for portal, value in zip(members, opportunities):
                result[portal["edge"]] = mass * value / denominator
        return result

    entries = portal_weights(model["portals"]["entries"])
    exits = portal_weights(model["portals"]["exits"])
    origin_portals = {p["edge"]: p for p in model["portals"]["entries"]}
    if config.get("route_choice", {}).get("method") == "native_path_branch_opportunities":
        _branch_prior(pairs, entries, origin_portals, config["route_choice"])
        return
    alternatives = {}
    for pair in pairs.values():
        alternatives.setdefault((pair["origin"], pair["destination"]), []).append(pair)
    for (origin, destination), members in alternatives.items():
        shortest = min(p["freeflow_time_s"] for p in members)
        efficiencies = [shortest / p["freeflow_time_s"] for p in members]
        for pair, efficiency in zip(members, efficiencies):
            pair.update(prior_weight=entries[origin] * exits[destination] * efficiency / sum(efficiencies),
                        demand_eligible=True, temporal_role=("arterial" if
                        origin_portals[origin].get("prior_road_type", origin_portals[origin].get("road_type", "")).startswith(("highway.primary", "highway.secondary"))
                        else "local"))
    total = sum(p["prior_weight"] for p in pairs.values())
    for pair in pairs.values():
        pair["prior_weight"] /= total


def _branch_prior(pairs, entries, portals, config):
    """Distribute an origin's mass across native path branches, not OD counts.

    Adding downstream destinations must not multiply the attractiveness of a
    turn upstream. The trie only samples existing duarouter paths; it does not
    find paths, inspect queues or change any permitted connection.
    """
    angular_cost = float(config.get("angular_cost", 1.0))
    if not math.isfinite(angular_cost) or angular_cost < 0:
        raise ValueError("Custo angular deve ser finito e não negativo.")
    by_origin = {}
    for pair in pairs.values():
        by_origin.setdefault(pair["origin"], []).append(pair)
    origin_total = sum(entries[origin] for origin in by_origin)
    for origin, members in by_origin.items():
        root = {}
        for pair in members:
            node = root
            for index, edge in enumerate(pair["route"][1:]):
                weight = pair["movement_opportunities"][index] / (1 + angular_cost * pair["movement_angles"][index] / (math.pi / 2))
                node = node.setdefault(edge, {"weight": weight, "children": {}})["children"]
            node["__route__"] = pair

        def assign(node, mass):
            if "__route__" in node:
                if len(node) != 1:
                    raise ValueError("Uma saída periférica não pode continuar para outro destino.")
                pair = node["__route__"]
                hierarchy = portals[origin].get("prior_road_type", portals[origin].get("road_type", ""))
                pair.update(prior_weight=mass, demand_eligible=True,
                            temporal_role="arterial" if hierarchy.startswith(("highway.primary", "highway.secondary")) else "local")
                return
            denominator = sum(branch["weight"] for branch in node.values())
            for branch in node.values():
                assign(branch["children"], mass * branch["weight"] / denominator)
        assign(root, entries[origin] / origin_total)


def _basis_segments(index, bins, duration):
    """Pesos lineares entre centros de 15 min; não há degrau entre seções."""
    center = index * 900 + 450
    parts = []
    if index == 0:
        parts.append((0.0, center, 0.0, 1.0))
    else:
        parts.append((center - 900, center, 1 / 900, -(center - 900) / 900))
    if index == bins - 1:
        parts.append((center, duration, 0.0, 1.0))
    else:
        parts.append((center, center + 900, -1 / 900, (center + 900) / 900))
    return parts


def _directional_ratio(config, week_second):
    """Transferência explícita entre seções; não é uma contagem neste recorte."""
    knots = config.get("daily_ratio_knots", [])
    if not knots:
        ratios = config.get("ratios", [1.0])
        return sum(ratios) / len(ratios)
    clock = week_second % 86400
    for left, right in zip(knots, knots[1:]):
        if left["second"] <= clock <= right["second"]:
            fraction = (clock - left["second"]) / (right["second"] - left["second"])
            return left["ratio"] + fraction * (right["ratio"] - left["ratio"])
    raise ValueError("Prior direcional deve cobrir o dia civil completo.")


def _observation_projection(pairs, model, calibration, begin, duration, knots, fixed_schedule=None, curve_key="knots"):
    """Raking de probabilidades com partidas fixas e atraso livre explícito.

    A matriz integra a base linear de escolha OD e a passagem no probe em
    t_partida + tempo_livre. Não desloca a medição nem aumenta o total. É uma
    aproximação sem filas; só passagens SUMO validam a demanda realizada.
    """
    bins = round(duration / 900)
    routes = list(pairs.values())
    if fixed_schedule is not None:
        samples = [(float(attrs["depart"]), 1.0) for attrs in fixed_schedule]
    else:
        # Quadratura de 45 s da curva linear; não são partidas discretizadas.
        samples = [(t + 22.5, interpolate_rate(knots, begin + t + 22.5) * 45)
                   for t in range(0, int(duration), 45)]
    times = [row[0] for row in samples]
    prefix_mass, prefix_time = [0.0], [0.0]
    for timestamp, weight in samples:
        prefix_mass.append(prefix_mass[-1] + weight)
        prefix_time.append(prefix_time[-1] + timestamp * weight)

    def weighted_basis(index, lower=0.0, upper=duration):
        value = 0.0
        for left, right, slope, intercept in _basis_segments(index, bins, duration):
            lo, hi = max(left, lower), min(right, upper)
            if hi <= lo:
                continue
            a, b = bisect_left(times, lo), bisect_left(times, hi)
            value += slope * (prefix_time[b] - prefix_time[a]) + intercept * (prefix_mass[b] - prefix_mass[a])
        return max(value, 0.0)

    masses = [weighted_basis(index) for index in range(bins)]
    base, weights = [], []
    reference = calibration.get("baseline_reference_cars_15_18", {})
    for index in range(bins):
        timestamp = begin + index * 900 + 450
        relative = {sensor: interpolate_rate(calibration["sensors"][sensor][curve_key], timestamp) /
                    max(reference.get(sensor, 1.0) / DEFAULT_DURATION, 1e-12) for sensor in ("5", "6")}
        # Sem contagens transversais semanais, classes de via usam priors de
        # forma distintos explicitamente hipotéticos, nunca intensidade copiada.
        row = [pair["prior_weight"] * relative["6" if pair["temporal_role"] == "arterial" else "5"]
               for pair in routes]
        denominator = sum(row)
        row = [value / denominator for value in row] if denominator else [p["prior_weight"] for p in routes]
        base.append(row)
        weights.append(row.copy())
    constraints = []
    observation_ids = ["5", "6"]
    direction = model["regional_demand"].get("directional_prior", {})
    if direction.get("probe_edge"):
        observation_ids.append("rondon_reverse_estimate")
    for sensor in observation_ids:
        for observed_bin in range(bins):
            source_sensor = "6" if sensor == "rondon_reverse_estimate" else sensor
            target = integrate_rate(calibration["sensors"][source_sensor][curve_key], begin + observed_bin * 900,
                                    begin + (observed_bin + 1) * 900)
            if sensor == "rondon_reverse_estimate":
                target *= _directional_ratio(direction, begin + observed_bin * 900 + 450)
            terms = []
            for route_index, pair in enumerate(routes):
                delay = pair["observation_freeflow_delay_s"].get(sensor)
                if delay is None:
                    continue
                lower, upper = observed_bin * 900 - delay, (observed_bin + 1) * 900 - delay
                first = max(0, math.floor((lower - 450) / 900))
                last = min(bins - 1, math.ceil((upper - 450) / 900))
                for index in range(first, last + 1):
                    coefficient = weighted_basis(index, lower, upper)
                    if coefficient > 1e-12 and masses[index] > 0:
                        terms.append((index, route_index, coefficient))
            constraints.append((sensor, observed_bin, target, terms))
    # Deterministic generalized iterative scaling. Half-steps damp overlapping
    # fractional constraints, not traffic intensity; no demand multiplier.
    maximum_iterations = 80
    for iteration in range(maximum_iterations):
        greatest_error = 0.0
        for sensor, observed_bin, target, terms in constraints:
            predicted = sum(weights[i][r] * coefficient for i, r, coefficient in terms)
            greatest_error = max(greatest_error, abs(predicted - target) / max(target, 1.0))
            if predicted <= 0:
                continue
            correction = .5 * math.log(max(target, 1e-12) / predicted)
            changed = set()
            for index, route_index, coefficient in terms:
                weights[index][route_index] *= math.exp(max(-30.0, min(30.0,
                    correction * coefficient / masses[index])))
                changed.add(index)
            for index in changed:
                denominator = sum(weights[index])
                weights[index] = [value / denominator for value in weights[index]]
        if greatest_error < .001:
            break
    observations = []
    for sensor, observed_bin, target, terms in constraints:
        estimated = sum(weights[i][r] * coefficient for i, r, coefficient in terms)
        observations.append({"observation_id": sensor, "bin": observed_bin, "target_passages": target,
                             "target_kind": "estimated_external_direction_transfer" if sensor == "rondon_reverse_estimate" else "measured_car_curve_conditional_on_mapping",
                             "projected_freeflow_passages": estimated, "residual": estimated - target})
    for route_index, pair in enumerate(routes):
        pair.update(expected_departures=sum(masses[index] * weights[index][route_index] for index in range(bins)),
                    generated_departures=0, generated_departures_per_bin=[0] * bins)
    return weights, {
        "method": "fixed_departure_mass_fractional_raking_shared_observations",
        "operator": "continuous_linear_OD_probability; passage=departure+native_freeflow_time_to_probe_entry",
        "iterations": iteration + 1, "maximum_iterations": maximum_iterations,
        "total_fixed": sum(masses), "target_basis": curve_key + "_car_passages_assuming_boundary_to_boundary_representation",
        "observations": observations,
        "mean_prior_relative_entropy": sum(masses[i] * sum(p * math.log(p / q) for p, q in zip(row, base[i]) if p > 0 and q > 0)
                                           for i, row in enumerate(weights)) / max(sum(masses), 1),
        "status": "planning_projection_not_empirical_calibration",
        "limits": ["Sensor geography remains hypothetical.", "Freeflow excludes insertion queues and signal delays.",
                   "Empty start excludes pre-window vehicles; late passages remain outside the civil window.",
                   "Residual or infeasible constraints never add departures."],
    }


def _choose_route(weights, timestamp, rng, uniforms=None, cumulative_weights=None):
    coordinate = timestamp / 900 - .5
    left = max(0, min(len(weights) - 1, math.floor(coordinate)))
    right = max(0, min(len(weights) - 1, math.ceil(coordinate)))
    fraction = max(0.0, min(1.0, coordinate - math.floor(coordinate)))
    if uniforms is None:
        row = weights[right if rng.random() < fraction else left]
        return rng.choices(range(len(row)), weights=row, k=1)[0]
    selected = right if uniforms[0] < fraction else left
    cumulative = cumulative_weights[selected]
    return bisect_right(cumulative, uniforms[1] * cumulative[-1], 0, len(cumulative) - 1)


def _retained_indices(count, fraction, seed):
    """Seleção sistemática na agenda ordenada, sem mudar partidas ou rotas.

    O tamanho é exato; o deslocamento aleatório torna cada posição igualmente
    elegível. Amostrar posições espaçadas preserva a curva de intensidade e
    evita que uma realização esparsa perca a redução mínima por acaso.
    """
    retained = math.floor(count * fraction)
    if retained == count:
        return set(range(count))
    if not retained:
        return set()
    rng = random.Random(_stream_seed(seed, "regional", "volume_retention"))
    offset = rng.random()
    return {math.floor((index + offset) * count / retained) for index in range(retained)}


def _regional_knots(calibration, scale, curve_key):
    curves = [calibration["sensors"][sensor][curve_key] for sensor in ("5", "6")]
    times = sorted({k["week_second"] for curve in curves for k in curve})
    return [{"week_second": timestamp,
             "rate_per_second": scale * sum(interpolate_rate(curve, timestamp) for curve in curves)}
            for timestamp in times]


def _compose_sections(pairs, model, components, contexts, scale, retention):
    """Compõe comportamentos aprovados, conservando cada população selecionada.

    A projeção OD continua sendo a da faixa individual. Suas probabilidades nos
    centros de 15 minutos são interpoladas também entre faixas. Só os horários
    próximos às fronteiras são transportados pela integral conservada da taxa.
    """
    starts = [context["start_week_second"] for context in contexts]
    curves = [_regional_knots(calibration, scale, "realization_knots") for calibration in components]
    knots, transition = compose_rate_curves(curves, starts)
    weights, observations, schedule, reference_count = [], [], [], 0
    for context, calibration, curve in zip(contexts, components, curves):
        begin, seed = context["start_week_second"], context["effective_seed"]
        local_weights, projection = _observation_projection(
            pairs, model, calibration, begin, int(DEFAULT_DURATION), curve, curve_key="realization_knots")
        weights.extend(local_weights)
        observations.extend(dict(row, bin=row["bin"] + context["index"] * 12)
                            for row in projection["observations"])
        original = list(_departures(_linear_segments(curve, begin=begin, duration=DEFAULT_DURATION),
                                    random.Random(_stream_seed(seed, "regional", "departures"))))
        unreduced = len(original)
        kept = sorted(_retained_indices(unreduced, retention, seed))
        # As marcas de cada viagem são as da realização individual aprovada.
        # Pré-computadas uma vez, não há reinício de processo na fronteira nem
        # influência de uma variação futura sobre percursos anteriores.
        od_rng = random.Random(_stream_seed(seed, "regional", "od"))
        marks = [(od_rng.random(), od_rng.random()) for _ in range(unreduced)]
        # Reproduzir o arredondamento da faixa individual antes do transporte.
        original = [float(f"{min(original[i], DEFAULT_DURATION - .000001):.6f}") + begin for i in kept]
        moved = transport_times(original, curve, knots, begin, int(DEFAULT_DURATION))
        for original_index, timestamp in zip(kept, moved):
            relative = min(timestamp - starts[0], context["end"] - .000001)
            schedule.append({"id": f"ms_s{context['index']:03d}_{original_index:06d}", "type": "metasettran_car",
                             "depart": f"{relative:.6f}", "departPos": "0", "arrivalPos": "max",
                             "_od_uniforms": marks[original_index]})
        context.update(reference_programmed=len(kept), programmed=len(kept), unreduced_programmed=unreduced)
        reference_count += unreduced
    duration, begin = len(contexts) * int(DEFAULT_DURATION), starts[0]
    # Simpson integra exatamente o produto quadrático, subdividindo tanto nos
    # nós da ponte quanto nos centros das probabilidades OD aprovadas.
    masses = [0.0] * len(weights)
    breaks = sorted({0, duration} | set(range(450, duration, 900)) |
                    {row["week_second"] - begin for row in knots if begin < row["week_second"] < begin + duration})
    for left, right in zip(breaks, breaks[1:]):
        for timestamp, coefficient in ((left, (right - left) / 6),
                                       ((left + right) / 2, 2 * (right - left) / 3),
                                       (right, (right - left) / 6)):
            coordinate = timestamp / 900 - .5
            lo = max(0, min(len(weights) - 1, math.floor(coordinate)))
            hi = max(0, min(len(weights) - 1, math.ceil(coordinate)))
            fraction = coordinate - math.floor(coordinate)
            mass = coefficient * interpolate_rate(knots, begin + timestamp)
            masses[lo] += mass * (1 - fraction)
            masses[hi] += mass * fraction
    total = integrate_rate(knots, begin, begin + duration)
    normalization = total / sum(masses) if sum(masses) else 1.0
    for index, pair in enumerate(pairs.values()):
        pair.update(expected_departures=normalization * math.fsum(m * row[index] for m, row in zip(masses, weights)),
                    generated_departures=0, generated_departures_per_bin=[0] * len(weights))
    timestamps = [float(row["depart"]) for row in schedule]
    for boundary in transition["boundaries"]:
        for key in ("original_left_rate_per_second", "original_right_rate_per_second",
                    "joined_rate_per_second", "harmonic_join_rate_per_second",
                    "peak_rate_before_per_second", "peak_rate_after_per_second",
                    "minimum_rate_before_per_second", "minimum_rate_after_per_second",
                    "expected_left_half_window_before", "expected_left_half_window_after",
                    "expected_right_half_window_before", "expected_right_half_window_after"):
            boundary[key] *= retention
        relative = boundary["week_second"] - begin
        row = round(relative / 900)
        boundary["od_neighbor_total_variation"] = sum(abs(a - b) for a, b in zip(weights[row - 1], weights[row])) / 2
        boundary["od_half_window_seconds"] = 450
        boundary["od_boundary_jump"] = 0.0
        for window in boundary["windows"]:
            width = window["seconds"]
            window["programmed_left"] = bisect_left(timestamps, relative) - bisect_left(timestamps, relative - width)
            window["programmed_right"] = bisect_left(timestamps, relative + width) - bisect_left(timestamps, relative)
            for key in ("before_left", "before_right", "after_left", "after_right"):
                window[key] *= retention
    transition.update(expected_before=transition["expected_before"] * retention,
                      expected_after=transition["expected_after"] * retention,
                      standalone_programmed_sum=sum(c["reference_programmed"] for c in contexts),
                      combined_programmed=len(schedule), programmed_difference=0,
                      od_method="linear_interpolation_of_approved_context_probability_rows; no_refitting",
                      od_limit="Interpolation changes route expectations only within 450 seconds of each boundary.",
                      rate_knots=[dict(row, rate_per_second=row["rate_per_second"] * retention) for row in knots])
    for row in transition["sections"]:
        for key in ("expected_before", "expected_after", "difference"):
            row[key] *= retention
    projection = {"method": "composition_of_approved_individual_context_projections",
                  "total_fixed": total, "observations": observations,
                  "status": "individual_projection_references_not_recomputed_passages_after_harmonization",
                  "limits": ["Passage predictions below refer to individual contexts before boundary transport.",
                             "Combined physical passages are measured by the shared SUMO collector."]}
    return knots, weights, projection, schedule, reference_count, transition


def generate_metasettran_demand(
    *, net_file=DEFAULT_NET_FILE, output_dir=DEFAULT_OUTPUT_DIR,
    csv_file=DEFAULT_CSV_FILE, spatial_file=DEFAULT_SPATIAL_FILE,
    day="tuesday", start="15:00", sections=1, variation=None, seed=None,
    master_seed=None, variations=None,
    spatial_scenario="regional-integrated", metadata=None, log_file=None,
    schedule_file=None, source_time_convention="utc", volume_retention=None,
):
    """Gera viagens regionais; schedule_file isola a distribuição espacial."""
    from SistemaDeSemaforos.demand.metasettran_calibration import calibrate_weekly, weekly_window

    selection = resolve_contexts(day, start, sections, variation, seed, master_seed, variations)
    if schedule_file is not None and sections != 1:
        raise ValueError("Agenda pareada legada exige uma faixa; reutilize o XML completo para comparar controladores.")
    variation = selection["variations"][0] if sections == 1 else None
    if spatial_scenario not in SPATIAL_SCENARIOS:
        raise ValueError("Cenário regional retirado; utilize regional-integrated.")
    requested_scenario, spatial_scenario = spatial_scenario, "regional-integrated"
    seed = selection["seed"]
    begin = selection_start_week_second(day, start)
    duration = int(DEFAULT_DURATION) * sections
    bins = 12 * sections
    net_file, csv_file, spatial_file = (Path(path).expanduser().resolve() for path in (net_file, csv_file, spatial_file))
    for path in (net_file, csv_file, spatial_file):
        if not path.is_file():
            raise FileNotFoundError(f"Entrada MetaSettran não encontrada: {path}")
    started = time.perf_counter()
    spatial_bytes = spatial_file.read_bytes()
    model = json.loads(spatial_bytes)
    network_sha256 = _sha256(net_file)
    if model.get("network_sha256") != network_sha256:
        raise ValueError("O cadastro de portais pertence a outra versão da rede.")
    reference_total = model["regional_demand"]["reference_expected_departures"]
    if isinstance(reference_total, bool) or not isinstance(reference_total, (float, int)) or not math.isfinite(reference_total) or reference_total <= 0:
        raise ValueError("Volume regional de referência deve ser finito e positivo.")
    retention = (model["regional_demand"].get("volume_recalibration", {}).get("retained_fraction", 1.0)
                 if volume_retention is None else volume_retention)
    if isinstance(retention, bool) or not isinstance(retention, (float, int)) or not math.isfinite(retention) or not 0 < retention <= 1:
        raise ValueError("Fração de retenção deve estar em (0, 1].")
    # Agenda pareada é um contrato de população fixa; não reduzir novamente.
    if schedule_file is not None:
        retention = 1.0
    weekly = calibrate_weekly(csv_file, variation=selection["contexts"][0]["variation"], seed=selection["contexts"][0]["effective_seed"],
                              source_time_convention=source_time_convention)
    calibration = weekly_window(weekly, begin, duration)
    reference_counts = model["regional_demand"].get("frozen_scale_reference_cars", {
        sensor: weekly["sensors"][sensor]["baseline_reference_cars_15_18"] for sensor in ("5", "6")})
    if any(not math.isfinite(value) or value <= 0 for value in reference_counts.values()):
        raise ValueError("Referência temporal requer contagens car positivas e finitas para ambos os sensores.")
    calibration["baseline_reference_cars_15_18"] = reference_counts
    scale = reference_total / sum(reference_counts.values())
    curve_key = "knots" if schedule_file is not None else "realization_knots"
    knots = _regional_knots(calibration, scale, curve_key)
    components = []
    if sections > 1:
        cache = {selection["contexts"][0]["effective_seed"]: weekly}
        for context in selection["contexts"]:
            context_seed = context["effective_seed"]
            if context_seed not in cache:
                cache[context_seed] = calibrate_weekly(csv_file, variation=context["variation"], seed=context_seed,
                                                       source_time_convention=source_time_convention)
            component = weekly_window(cache[context_seed], context["start_week_second"], int(DEFAULT_DURATION))
            component["baseline_reference_cars_15_18"] = reference_counts
            components.append(component)
        for sensor in ("5", "6"):
            profile = calibration["sensors"][sensor]
            profile.pop("realization_knots", None)
            profile["realization_contexts"] = [{"index": c["index"], "variation": c["variation"],
                "knots": component["sensors"][sensor]["realization_knots"]}
                for c, component in zip(selection["contexts"], components)]
            profile["realized_target_counts"] = [value for component in components for value in
                component["sensors"][sensor].get("realized_target_counts", component["sensors"][sensor]["target_counts"])]
            profile["realized_expected_cars"] = sum(profile["realized_target_counts"])
        calibration["realization"] = {"method": "independent_context_variations", "variations": selection["variations"]}
        del cache
    fixed_schedule, vehicle_types = None, None
    if schedule_file is not None:
        schedule_file = Path(schedule_file).expanduser().resolve()
        source = ET.parse(schedule_file).getroot()
        vehicle_types = [deepcopy(item) for item in source.findall("vType")]
        fixed_schedule = [dict(vehicle.attrib) for vehicle in source.findall("vehicle")]
        departure_times = [float(attrs["depart"]) for attrs in fixed_schedule]
        if (not fixed_schedule or departure_times != sorted(departure_times) or
                len({attrs["id"] for attrs in fixed_schedule}) != len(fixed_schedule) or
                any(not 0 <= timestamp < duration for timestamp in departure_times) or
                any(attrs.get("departPos") != "0" or attrs.get("arrivalPos") != "max" for attrs in fixed_schedule)):
            raise ValueError("Agenda pareada requer IDs únicos, partidas ordenadas na janela e extremos completos.")
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    trips_file, routes_file = output_dir / "metasettran.trips.xml", output_dir / "metasettran.rou.xml"
    if metadata is None:
        metadata = {}
    ending = (begin + duration) % 604800
    metadata.update(
        demand_model="metasettran", model_version=MODEL_VERSION, seed=seed, variation=variation,
        context_selection=selection, composition_version=COMPOSITION_VERSION,
        spatial_scenario=spatial_scenario, requested_spatial_scenario=requested_scenario,
        seed_namespace=SEED_NAMESPACE, routing_seed=ROUTING_SEED,
        day=day, start=start, end=f"{int(ending % 86400 // 3600):02d}:00", end_day=DAYS[int(ending // 86400)],
        start_week_second=begin, sections=sections, begin=0.0, duration=duration,
        vehicle_class="passenger", measured_class="car", validate=True,
        net_file=str(net_file), source_network_sha256=network_sha256,
        csv_file=str(csv_file), spatial_file=str(spatial_file), spatial_sha256=hashlib.sha256(spatial_bytes).hexdigest(),
        trips_file=str(trips_file), routes_file=str(routes_file), calibration=calibration,
        spatial_model=model, status=model.get("status", "experimental_regional_model_sensor_mapping_unconfirmed"),
        variability=calibration.get("realization", weekly.get("realization", {})),
        temporal_scope={"contexts": 56, "variations_per_context": 25,
                        "shared_model": True, "continuous_selection": True,
                        "empirical_status": "local_car_curves; regional_OD_and_scale_experimental"},
        started_at_utc=datetime.now(timezone.utc).isoformat(),
    )
    if fixed_schedule is not None:
        metadata["paired_schedule"] = {"file": str(schedule_file), "sha256": _sha256(schedule_file),
            "preserved": ["vehicle_ids", "departure_times", "vehicle_attributes", "vehicle_types", "vehicle_count"],
            "changed": ["origin", "destination", "route"], "count": len(fixed_schedule)}
    try:
        with TemporaryDirectory(prefix=".metasettran-", dir=output_dir) as temporary:
            directory = Path(temporary)
            pairs, command, catalog, network_edges = _route_pairs(model, net_file, directory, seed, log_file)
            metadata["command"] = command
            _regional_prior(pairs, model)
            if sections > 1:
                knots, weights, projection, schedule, reference_count, transition = _compose_sections(
                    pairs, model, components, selection["contexts"], scale, retention)
                metadata["chronological_composition"] = transition
                retained_indices = range(len(schedule))
            else:
                weights, projection = _observation_projection(pairs, model, calibration, begin, duration, knots, fixed_schedule, curve_key)
                temporal_rng = random.Random(_stream_seed(seed, "regional", "departures"))
                schedule = fixed_schedule if fixed_schedule is not None else [
                    {"id": f"ms_{index:06d}", "type": "metasettran_car",
                     "depart": f"{min(timestamp, duration - .000001):.6f}", "departPos": "0", "arrivalPos": "max"}
                    for index, timestamp in enumerate(_departures(_linear_segments(knots, begin=begin, duration=duration), temporal_rng))]
                reference_count = len(schedule)
                retained_indices = _retained_indices(reference_count, retention, seed)
                selection["contexts"][0].update(reference_programmed=len(retained_indices), programmed=len(retained_indices),
                                                unreduced_programmed=reference_count)
            od_rng = random.Random(_stream_seed(seed, "regional", "od"))
            if not retained_indices:
                raise ValueError("A redução não deixou viagens nesta realização; não forçar inserções.")
            trips, routes = _routes_root(), _routes_root()
            if vehicle_types is not None:
                trips, routes = ET.Element("routes"), ET.Element("routes")
                for item in vehicle_types:
                    trips.append(deepcopy(item))
                    routes.append(deepcopy(item))
            route_list = list(pairs.values())
            cumulative_weights = [list(accumulate(row)) for row in weights] if sections > 1 else None
            used_lengths, generated_bins = [], [0] * bins
            new_trips, new_routes = directory / trips_file.name, directory / routes_file.name
            with ExitStack() as stack:
                streams = []
                if sections > 1:
                    for path in (new_trips, new_routes):
                        stream = stack.enter_context(path.open("wb"))
                        stream.write(b"<?xml version='1.0' encoding='utf-8'?>\n<routes>\n  <vType id=\"metasettran_car\" vClass=\"passenger\" />\n")
                        streams.append(stream)
                for schedule_index, attributes in enumerate(schedule):
                    timestamp = float(attributes["depart"])
                    pair = route_list[_choose_route(weights, timestamp, od_rng, attributes.pop("_od_uniforms", None), cumulative_weights)]
                    # Consumir a escolha OD também nas viagens removidas mantém o
                    # percurso de cada ID retido idêntico ao da referência UTC.
                    if schedule_index not in retained_indices:
                        continue
                    bin_index = min(int(timestamp // 900), bins - 1)
                    pair["generated_departures"] += 1
                    pair["generated_departures_per_bin"][bin_index] += 1
                    generated_bins[bin_index] += 1
                    used_lengths.append(pair["length_m"])
                    trip = ET.Element("trip", dict(attributes, **{"from": pair["origin"], "to": pair["destination"]}))
                    vehicle = ET.Element("vehicle", attributes)
                    ET.SubElement(vehicle, "route", edges=" ".join(pair["route"]))
                    if streams:
                        for stream, element in zip(streams, (trip, vehicle)):
                            ET.indent(element, space="  ", level=1)
                            stream.write(b"  " + ET.tostring(element, encoding="utf-8") + b"\n")
                    else:
                        trips.append(trip)
                        routes.append(vehicle)
                for stream in streams:
                    stream.write(b"</routes>")
            schedule = [attrs for index, attrs in enumerate(schedule) if index in retained_indices]
            for pair in pairs.values():
                pair["expected_departures"] *= retention
            projection["unreduced_total_fixed"] = projection["total_fixed"]
            projection["total_fixed"] *= retention
            for observation in projection["observations"]:
                observation["unreduced_projected_freeflow_passages"] = observation["projected_freeflow_passages"]
                observation["projected_freeflow_passages"] *= retention
                observation["experimental_target_passages"] = observation["target_passages"] * retention
                observation["residual"] = observation["projected_freeflow_passages"] - observation["target_passages"]
            projection["retention_note"] = "OD fitted at unreduced reference; measured targets unchanged. Reduced projections are experimental, not a recalibration of observed counts."
            used_lengths.sort()
            new_trips, new_routes = directory / trips_file.name, directory / routes_file.name
            if sections == 1:
                _write_xml(new_trips, trips)
                _write_xml(new_routes, routes)
            expected_bins = [retention * integrate_rate(knots, begin + index * 900, begin + (index + 1) * 900) for index in range(bins)]
            groups = [{"id": "regional", "sensor_ids": [], "basis": {"kind": "fixed_regional_scale_hypothesis",
                       "reference_expected_departures": reference_total,
                       "scale": "retention * frozen_v4.3.1_coefficient * (car5(t)+car6(t)); not sensor coverage",
                       "unreduced_coefficient": scale, "frozen_reference_cars": reference_counts},
                       "expected_departures": projection["total_fixed"], "generated_departures": len(schedule),
                       "expected_departures_per_bin": ([sum(1 for attrs in schedule if index * 900 <= float(attrs['depart']) < (index + 1) * 900)
                           for index in range(bins)] if fixed_schedule is not None else expected_bins),
                       "generated_departures_per_bin": generated_bins}]
            portal_counts = {}
            for role, endpoint in (("entries", "origin"), ("exits", "destination")):
                portal_counts[role] = [{"edge": portal["edge"], "corridor": portal["corridor"],
                    "qualification": portal.get("qualification"),
                    "expected_departures": sum(p["expected_departures"] for p in pairs.values() if p[endpoint] == portal["edge"]),
                    "generated_departures": sum(p["generated_departures"] for p in pairs.values() if p[endpoint] == portal["edge"])}
                    for portal in model["portals"][role]]
            corridors = [{"id": corridor["id"], "label": corridor["label"], "direction": corridor["direction"],
                "expected_departures": sum(p["expected_departures"] for p in pairs.values() if corridor["id"] in p["corridors"]),
                "generated_departures": sum(p["generated_departures"] for p in pairs.values() if corridor["id"] in p["corridors"])}
                for corridor in model.get("corridors", [])]
            def percentile(fraction):
                position = (len(used_lengths) - 1) * fraction
                left, right = math.floor(position), math.ceil(position)
                return used_lengths[left] + (position - left) * (used_lengths[right] - used_lengths[left])
            used_entries = sum(item["generated_departures"] > 0 for item in portal_counts["entries"])
            used_exits = sum(item["generated_departures"] > 0 for item in portal_counts["exits"])
            catalog_edges = {edge for pair in pairs.values() for edge in pair["route"]}
            used_edges = {edge for pair in pairs.values() if pair["generated_departures"] for edge in pair["route"]}
            coverage = {"passenger_normal_edges": len(network_edges), "catalog_normal_edges": len(catalog_edges),
                        "used_normal_edges": len(used_edges), "by_road_hierarchy": {}}
            for hierarchy in sorted({edge["hierarchy"] for edge in network_edges.values()}):
                identifiers = {edge for edge, data in network_edges.items() if data["hierarchy"] == hierarchy}
                coverage["by_road_hierarchy"][hierarchy] = {"network_edges": len(identifiers),
                    "catalog_edges": len(identifiers & catalog_edges), "used_edges": len(identifiers & used_edges)}
            incidence = {label: sum(p["generated_departures"] for p in pairs.values()
                         if ("both" if len(p["sensor_ids"]) == 2 else p["sensor_ids"][0] if p["sensor_ids"] else "neither") == label)
                         for label in ("5", "6", "both", "neither")}
            metadata.update(
                volume_recalibration={"retained_fraction": retention,
                    "reference_programmed": reference_count, "retained_programmed": len(schedule),
                    "actual_reduction_fraction": 1 - len(schedule) / reference_count,
                    "method": ("per_context_fixed_count_subset_then_mass_conserving_time_transport" if sections > 1
                               else "fixed_count_systematic_subset_of_reference_schedule"),
                    "paired_schedule_bypasses_reduction": fixed_schedule is not None,
                    "preserved": (["context_vehicle_budgets", "individual_context_probability_rows", "vehicle_attributes"] if sections > 1
                                  else ["retained_vehicle_ids", "departure_times", "routes", "vehicle_attributes"]),
                    "status": "project_experimental_reduction_not_measured_percentage"},
                vehicles_requested=len(schedule), vehicles_generated=len(schedule), trips_generated=len(schedule),
                groups=groups, routes_sha256=_sha256(new_routes), trips_sha256=_sha256(new_trips),
                spatial_distribution={"scenario": spatial_scenario, "method": "integrated_OD_shared_observations",
                    "total_equation": "one regional vehicle population; observations are route incidences, never independent trip budgets",
                    "expected_network_departures": projection["total_fixed"], "groups": groups,
                    "routes": [{key: value for key, value in pair.items() if key != "route"} for pair in pairs.values()],
                    "portals": portal_counts, "observation_incidence_generated": incidence,
                    "observation_projection": projection,
                    "sensor_mapping_sensitivity": _mapping_sensitivity(pairs, model, calibration),
                    "corridors": corridors, "corridor_counts_overlap": True, "catalog": catalog, "coverage": coverage,
                    "distance_distribution": {"min": used_lengths[0], "p25": percentile(.25), "median": percentile(.5),
                         "p75": percentile(.75), "max": used_lengths[-1], "mean": sum(used_lengths) / len(used_lengths)},
                    "limitations": model["regional_demand"]["limitations"]},
                route_validation={"generated": len(schedule), "valid_boundary_routes": len(schedule), "invalid": 0,
                    "routed_pairs": len(pairs), "used_pairs": sum(p["generated_departures"] > 0 for p in pairs.values()),
                    "entry_portals_used": used_entries, "exit_portals_used": used_exits,
                    "minimum_length_m": used_lengths[0], "maximum_length_m": used_lengths[-1],
                    "length_basis": "normal_edges_plus_minimum_passenger_internal_connections",
                    "depart_pos": "0", "arrival_pos": "max"},
            )
            new_trips.replace(trips_file)
            new_routes.replace(routes_file)
    finally:
        metadata.update(finished_at_utc=datetime.now(timezone.utc).isoformat(),
                        duration_seconds=time.perf_counter() - started)
    return routes_file


