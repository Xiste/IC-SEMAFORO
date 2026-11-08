"""Topologia passenger, acessos de atividade e cobertura de rotas do MetaSettran.

A mesma leitura do XML sustenta os acessos locais e a validação de percursos.
A busca complementar usa limites de custo e comprimento para propor alternativas.
O duarouter confirma os percursos pela rede nativa.
"""

from collections import defaultdict
from copy import deepcopy
import hashlib
import heapq
import json
import math
from pathlib import Path
from typing import NamedTuple
import xml.etree.ElementTree as ET


class PassengerNetwork(NamedTuple):
    edges: dict
    connections: set
    returns: set
    connection_costs: dict
    departure_lanes: dict
    receiving_lanes: dict


def _passenger_allowed(lane):
    allow = lane.get("allow")
    disallow = lane.get("disallow", "").split()
    return (allow is None or "passenger" in allow.split() or "all" in allow.split()) and (
        "passenger" not in disallow and "all" not in disallow
    )


def read_network(path) -> PassengerNetwork:
    """Lê as permissões e os movimentos passenger do XML SUMO."""
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
    native_connections = root.findall("connection")
    continuations = {}
    for connection in native_connections:
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
    departure_lanes, receiving_lanes = {}, {}
    for connection in native_connections:
        source, target = connection.get("from"), connection.get("to")
        from_lane, to_lane = connection.get("fromLane"), connection.get("toLane")
        if source not in edges or target not in edges:
            continue
        if from_lane not in edges[source]["lanes"] or to_lane not in edges[target]["lanes"]:
            continue
        movement = source, target
        cost = internal_cost(connection.get("via"), target, to_lane)
        if cost is None:
            raise ValueError(f"Conexão interna passenger sem continuação: {source} -> {target}")
        connections.add(movement)
        previous = connection_costs.get(movement)
        if previous is None or cost < previous:
            connection_costs[movement] = cost
        if connection.get("dir") == "t":
            returns.add(movement)
        # Uma faixa de origem conta uma vez mesmo quando alcança várias faixas.
        departure_lanes.setdefault(movement, set()).add(from_lane)
        receiving_lanes.setdefault(movement, set()).add(to_lane)
    return PassengerNetwork(edges, connections, returns, connection_costs, departure_lanes, receiving_lanes)


def demand_endpoints(model, role):
    """Portais periféricos e acessos de atividade conservam identidades distintas."""
    endpoints = [dict(portal, endpoint_kind="boundary",
                      zone_id=portal.get("zone_id", portal["boundary_group"]),
                      position_xy_m=portal.get("position_xy_m", portal.get("boundary_xy_m")))
                 for portal in model["portals"][role]]
    activity_role = "origins" if role == "entries" else "destinations"
    for zone in model.get("activity_zones", []):
        if not zone.get("references") or not zone.get("id") or not zone.get("kind"):
            raise ValueError("Zona de atividade exige identificação, uso e referências geográficas.")
        for access in zone.get(activity_role, []):
            endpoints.append(dict(access, endpoint_kind="activity", zone_id=zone["id"],
                                  activity_role=zone["kind"], name=zone["name"],
                                  boundary_group="activity:" + zone["id"],
                                  corridor=access.get("corridor", "activity:" + zone["id"])))
    if len({item["edge"] for item in endpoints}) != len(endpoints):
        raise ValueError("Um acesso não pode pertencer a vários extremos de demanda do mesmo papel.")
    return endpoints


def terminal_branches(edges):
    """Blocos ligados à malha por uma única junção, incluindo sua haste.

    Um percurso que entra e sai dessa região sem origem/destino interno precisa
    revisitar a junção de ligação. Isso não torna a rua impossível: pode exigir
    um acesso de atividade no interior da região. Usa biconexão não direcionada
    apenas para identificar essa estrutura, nunca para autorizar movimentos.
    """
    graph, physical = {}, {}
    for identifier, edge in edges.items():
        a, b = edge["from"], edge["to"]
        if a == b:
            continue
        graph.setdefault(a, set()).add(b)
        graph.setdefault(b, set()).add(a)
        physical.setdefault(frozenset((a, b)), set()).add(identifier)
    discovered, low, parents, pending, blocks = {}, {}, {}, [], []
    clock = 0
    for start in sorted(graph):
        if start in discovered:
            continue
        clock += 1
        discovered[start] = low[start] = clock
        stack = [(start, iter(sorted(graph[start])))]
        while stack:
            source, neighbors = stack[-1]
            target = next(neighbors, None)
            if target is not None:
                if target not in discovered:
                    parents[target] = source
                    pending.append((source, target))
                    clock += 1
                    discovered[target] = low[target] = clock
                    stack.append((target, iter(sorted(graph[target]))))
                elif target != parents.get(source) and discovered[target] < discovered[source]:
                    pending.append((source, target))
                    low[source] = min(low[source], discovered[target])
            else:
                stack.pop()
                if source not in parents:
                    continue
                parent = parents[source]
                low[parent] = min(low[parent], low[source])
                if low[source] >= discovered[parent]:
                    members, identifiers = set(), set()
                    while pending:
                        a, b = pending.pop()
                        members.update((a, b))
                        identifiers.update(physical[frozenset((a, b))])
                        if (a, b) == (parent, source):
                            break
                    blocks.append({"nodes": members, "edges": identifiers})
    membership = {}
    for index, block in enumerate(blocks):
        for node in block["nodes"]:
            membership.setdefault(node, set()).add(index)
    articulation = {node for node, members in membership.items() if len(members) > 1}
    result = []
    for index, block in enumerate(blocks):
        attachments = block["nodes"] & articulation
        if len(attachments) != 1:
            continue
        attachment = next(iter(attachments))
        current = index
        members = set(block["edges"])
        visited = {index}
        while len(membership[attachment]) == 2:
            neighbor = next(iter(membership[attachment] - {current}))
            following = blocks[neighbor]
            if neighbor in visited or len(following["nodes"]) != 2:
                break
            visited.add(neighbor)
            members.update(following["edges"])
            attachment = next(iter(following["nodes"] - {attachment}))
            current = neighbor
        result.append({"attachment": attachment, "terminal_edges": sorted(block["edges"]),
                       "edges": sorted(members)})
    return sorted(result, key=lambda branch: (branch["attachment"], branch["terminal_edges"]))


def _midpoint(shape):
    lengths = [math.dist(a, b) for a, b in zip(shape, shape[1:])]
    remaining = sum(lengths) / 2
    for a, b, length in zip(shape, shape[1:], lengths):
        if length and remaining <= length:
            fraction = remaining / length
            return [a[0] + fraction * (b[0] - a[0]), a[1] + fraction * (b[1] - a[1])]
        remaining -= length
    raise ValueError("Atividade local requer geometria viária com comprimento positivo.")


def _street(identifier):
    # Segmentos e sentidos da mesma via OSM não são atividades independentes.
    return identifier.lstrip("-").split("#")[0].split(".")[0]


def expand_local_activity(model, edges, connections):
    """Expande o cadastro uma vez; gates compartilham a oportunidade da célula."""
    policy = model["regional_demand"].get("local_activity_distribution")
    if not policy or model.get("local_activity_expansion"):
        return model
    if policy.get("method") != "local_street_length_grid":
        raise ValueError("Método de distribuição de atividade local desconhecido.")
    for key in ("cell_size_m", "opportunity_per_km", "minimum_access_length_m"):
        value = policy.get(key)
        if (isinstance(value, bool) or not isinstance(value, (int, float)) or
                not math.isfinite(value) or value <= 0):
            raise ValueError(f"Parâmetro de atividade local inválido: {key}.")
    maximum = policy.get("max_accesses_per_cell")
    if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= 8:
        raise ValueError("Atividade local requer 1–8 acessos por célula.")
    for key in ("include_terminal_accesses", "allow_intrazonal_trips"):
        if not isinstance(policy.get(key, False), bool):
            raise ValueError(f"Atividade local exige booleano para {key}.")
    directional = policy.get("directional_terminal_edges", [])
    if (not isinstance(directional, list) or any(not isinstance(item, str) or not item for item in directional)
            or len(set(directional)) != len(directional)):
        raise ValueError("Acessos direcionais exigem uma lista de trechos únicos.")
    if directional and not policy.get("include_terminal_accesses"):
        raise ValueError("Acessos direcionais requerem a expansão de acessos terminais.")
    references = policy.get("references")
    if not isinstance(references, list) or not references or not all(isinstance(x, str) and x for x in references):
        raise ValueError("Atividade local requer referências geográficas explícitas.")
    replaced = policy.get("replace_activity_zones", [])
    configured = {zone["id"] for zone in model.get("activity_zones", [])}
    if not isinstance(replaced, list) or not set(replaced) <= configured:
        raise ValueError("Distribuição local substitui zona de atividade desconhecida.")
    urban = model["regional_demand"].get("urban_activity_model", {})
    profiles = next((zone["profiles"] for zone in urban.get("zones", [])
                     if zone["id"] == policy.get("profile_zone")), None)
    if profiles is None:
        raise ValueError("Distribuição local exige um perfil temporal cadastrado.")
    result = deepcopy(model)
    result["activity_zones"] = [z for z in result.get("activity_zones", []) if z["id"] not in replaced]
    result["regional_demand"]["urban_activity_model"]["zones"] = [
        z for z in result["regional_demand"]["urban_activity_model"]["zones"] if z["id"] not in replaced]
    excluded = {p["edge"] for role in ("entries", "exits") for p in model["portals"][role]}
    excluded.update(p["edge"] for zone in result["activity_zones"]
                    for role in ("origins", "destinations") for p in zone.get(role, []))
    incoming, outgoing = {b for _, b in connections}, {a for a, _ in connections}
    overrides = model["regional_demand"].get("road_hierarchy_overrides", {})
    eligible = {identifier: edge for identifier, edge in edges.items()
                if identifier not in excluded and identifier in incoming and identifier in outgoing
                and overrides.get(identifier, edge["hierarchy"]) == "highway.residential"}
    cells, points, exposure, reverse_directions = defaultdict(list), {}, {}, {}
    size = policy["cell_size_m"]
    for identifier, edge in sorted(eligible.items()):
        shape = edge["shape"] or [edge["from_xy"], edge["to_xy"]]
        if len(shape) < 2 or any(point is None for point in shape):
            raise ValueError("Atividade local requer coordenadas de todos os trechos elegíveis.")
        point = points[identifier] = _midpoint(shape)
        cells[math.floor(point[0] / size), math.floor(point[1] / size)].append(identifier)
        reverse = identifier[1:] if identifier.startswith("-") else "-" + identifier
        counterpart = eligible.get(reverse)
        bidirectional = (counterpart is not None and edge["from"] == counterpart["to"]
                         and edge["to"] == counterpart["from"])
        if bidirectional:
            reverse_directions[identifier] = reverse
        # Dois sentidos reconhecidos compartilham a extensão da rua física;
        # somá-los integralmente duplicaria sua oportunidade de atividade.
        exposure[identifier] = edge["length"] / (2 if bidirectional else 1)

    def access_gate(identifier, status):
        edge = eligible[identifier]
        return {"edge": identifier, "position_xy_m": points[identifier],
                "passenger_lanes": len(edge["lanes"]), "road_type": edge["hierarchy"],
                "corridor": "local:" + _street(identifier), "status": status}

    generated, unrepresented = [], []
    selected_edges = []
    for (x, y), identifiers in sorted(cells.items()):
        length = sum(exposure[identifier] for identifier in identifiers)
        available = {identifier for identifier in identifiers
                     if eligible[identifier]["length"] >= policy["minimum_access_length_m"]}
        if not available:
            unrepresented.append({"cell": [x, y], "local_street_length_m": length})
            continue
        center = ((x + .5) * size, (y + .5) * size)
        selected = [min(available, key=lambda identifier: (math.dist(points[identifier], center), identifier))]
        available.remove(selected[0])
        while available and len(selected) < maximum:
            distinct = {identifier for identifier in available
                        if _street(identifier) not in {_street(item) for item in selected}}
            candidates = distinct or available
            chosen = min(candidates, key=lambda identifier: (
                -min(math.dist(points[identifier], points[item]) for item in selected), identifier))
            selected.append(chosen)
            available.remove(chosen)
        identifier = f"local_activity_{x}_{y}"
        if identifier in configured or identifier in {z["id"] for z in urban["zones"]}:
            raise ValueError("Identificador de célula local colide com zona cadastrada.")
        gates = [access_gate(edge, "aggregate_local_activity_public_road_proxy") for edge in selected]
        name = f"Atividades locais — célula {x}/{y}"
        result["activity_zones"].append({"id": identifier, "name": name, "kind": "residential_mixed",
            "center_xy_m": list(center), "references": references,
            "allow_intrazonal_trips": policy.get("allow_intrazonal_trips", False),
            "basis": "Atividades residenciais/mistas agregadas no viário local, sem cadastro de lotes, população ou portões. Célula computacional; não é limite de bairro nem densidade medida.",
            "origins": gates, "destinations": deepcopy(gates)})
        # Esta escala distribui probabilidade entre áreas; não mede população
        # nem acrescenta veículos ao orçamento temporal da demanda.
        opportunity = length / 1000 * policy["opportunity_per_km"]
        result["regional_demand"]["urban_activity_model"]["zones"].append({
            "id": identifier, "name": name, "kind": "residential_mixed",
            "opportunity": opportunity, "profiles": deepcopy(profiles), "references": references,
            "basis": "Oportunidade proporcional à extensão local, contada uma vez por via física bidirecional e compartilhada entre acessos; escala relativa experimental, sem veículos adicionais."})
        generated.append({"zone_id": identifier, "local_street_length_m": length,
                          "opportunity": opportunity, "accesses": len(gates)})
        selected_edges.extend(selected)
    terminal_diagnostics, directional_accesses = [], []
    if policy.get("include_terminal_accesses", False):
        zones = {zone["id"]: zone for zone in result["activity_zones"]}
        known = {role: {gate["edge"] for zone in result["activity_zones"] for gate in zone.get(role, [])}
                 for role in ("origins", "destinations")}
        boundaries = {p["edge"] for role in ("entries", "exits") for p in model["portals"][role]}
        coordinates = {node: point for edge in edges.values()
                       for node, point in ((edge["from"], edge["from_xy"]), (edge["to"], edge["to_xy"]))
                       if point is not None}

        def add_terminal_access(identifier, role, status):
            if identifier in known[role]:
                return False
            x, y = points[identifier]
            zone = zones[f"local_activity_{math.floor(x / size)}_{math.floor(y / size)}"]
            zone[role].append(access_gate(identifier, status))
            known[role].add(identifier)
            return True

        for branch in terminal_branches(edges):
            if set(branch["terminal_edges"]) & (boundaries | known["origins"] | known["destinations"]):
                continue
            frontage = [identifier for identifier in branch["terminal_edges"]
                        if identifier in eligible and eligible[identifier]["length"] >= policy["minimum_access_length_m"]]
            if not frontage:
                frontage = [identifier for identifier in branch["edges"]
                            if identifier in eligible and eligible[identifier]["length"] >= policy["minimum_access_length_m"]]
            if not frontage:
                terminal_diagnostics.append({**branch, "status": "no_eligible_local_frontage_access"})
                continue
            selected = min(frontage, key=lambda identifier: (-eligible[identifier]["length"], identifier))
            physical = {eligible[selected]["from"], eligible[selected]["to"]}
            directions = [identifier for identifier in frontage
                          if {eligible[identifier]["from"], eligible[identifier]["to"]} == physical]
            attachment = coordinates.get(branch["attachment"])
            added = {}
            for role, endpoint in (("origins", "to_xy"), ("destinations", "from_xy")):
                identifier = min(directions, key=lambda item: (
                    math.dist(eligible[item][endpoint] or eligible[item]["shape"][-1 if endpoint=="to_xy" else 0],
                              attachment) if attachment is not None else 0, item))
                if add_terminal_access(identifier, role, "aggregate_terminal_activity_public_road_proxy"):
                    added[role] = identifier
            terminal_diagnostics.append({**branch, "status": "terminal_frontage_access_represented",
                                         "added_accesses": added})
        if directional:
            predecessors, successors = defaultdict(set), defaultdict(set)
            for source, target in connections:
                predecessors[target].add(source)
                successors[source].add(target)
            # Uma junção pode ter outras ruas e, ainda assim, permitir apenas
            # retorno para este sentido. O acesso usa o lado conectado à malha.
            for identifier in directional:
                reverse = reverse_directions.get(identifier)
                if reverse is None or eligible[identifier]["length"] < policy["minimum_access_length_m"]:
                    raise ValueError(f"Acesso direcional sem frente local elegível: {identifier}.")
                valid_role = False
                for role, restricted, connected in (("origins", predecessors, successors),
                                                     ("destinations", successors, predecessors)):
                    if restricted[identifier] != {reverse} or not connected[identifier] - {reverse}:
                        continue
                    valid_role = True
                    if add_terminal_access(identifier, role, "aggregate_directional_terminal_activity_proxy"):
                        directional_accesses.append({"edge": identifier, "role": role, "return_edge": reverse})
                if not valid_role:
                    raise ValueError(f"Acesso direcional sem restrição de retorno em um lado: {identifier}.")
        for cell in generated:
            zone = zones[cell["zone_id"]]
            cell["origin_accesses"] = len(zone["origins"])
            cell["destination_accesses"] = len(zone["destinations"])
            cell["accesses"] = cell["origin_accesses"] if cell["origin_accesses"] == cell["destination_accesses"] else None
    if not generated:
        raise ValueError("Nenhuma célula de atividade local possui acesso admissível.")
    result["local_activity_expansion"] = {
        "version": policy.get("version"), "method": policy["method"], "cell_size_m": size,
        "eligible_directed_edges": len(eligible), "represented_cells": len(generated),
        "accesses_per_role": len(selected_edges), "replaced_activity_zones": replaced,
        "local_street_length_m": sum(exposure.values()),
        "represented_local_street_length_m": sum(row["local_street_length_m"] for row in generated),
        "total_opportunity": sum(row["opportunity"] for row in generated),
        "cells": generated, "cells_without_admissible_access": unrepresented,
        "scope": "spatial_opportunity_only; midpoint_cell_assignment; no measured_density_or_trip_budget",
    }
    if policy.get("include_terminal_accesses", False):
        summary = result["local_activity_expansion"]
        summary["origin_accesses"] = sum(row["origin_accesses"] for row in generated)
        summary["destination_accesses"] = sum(row["destination_accesses"] for row in generated)
        summary["accesses_per_role"] = (summary["origin_accesses"] if
            summary["origin_accesses"] == summary["destination_accesses"] else None)
        summary["terminal_branches"] = terminal_diagnostics
        if directional:
            summary["directional_terminal_accesses"] = directional_accesses
    return result


def apply_local_activity_weights(model, weights_file, base_spatial_sha256):
    """Substitui apenas as oportunidades das células e registra sua origem."""
    path = Path(weights_file).expanduser().resolve()
    content = path.read_bytes()
    weights = json.loads(content)
    if not isinstance(weights, dict) or weights.get("base_spatial_sha256") != base_spatial_sha256:
        raise ValueError("Os pesos de atividade local exigem o cadastro espacial de referência.")
    version = weights.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("Os pesos de atividade local exigem uma versão explícita.")

    expansion = model.get("local_activity_expansion", {})
    cells = {row["zone_id"]: row for row in expansion.get("cells", [])}
    opportunities = weights.get("opportunities")
    if not cells or not isinstance(opportunities, dict) or opportunities.keys() != cells.keys():
        raise ValueError("Informe uma oportunidade para cada célula de atividade local.")
    reference = expansion["total_opportunity"]
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= reference
           for value in opportunities.values()):
        raise ValueError("Cada oportunidade de atividade local deve ser finita e positiva.")
    total = sum(opportunities.values())
    if not math.isclose(total, reference, rel_tol=1e-12):
        raise ValueError("Os pesos devem conservar a oportunidade total das células de atividade local.")

    for zone in model["regional_demand"]["urban_activity_model"]["zones"]:
        identifier = zone["id"]
        if identifier in cells:
            cells[identifier]["opportunity"] = zone["opportunity"] = opportunities[identifier]
            zone["basis"] = "Oportunidade experimental do arquivo de pesos, compartilhada pelos acessos da célula."
    expansion["total_opportunity"] = total
    return {"file": str(path), "version": version, "sha256": hashlib.sha256(content).hexdigest(),
            "base_spatial_sha256": base_spatial_sha256}


def _distances(seed, graph, initial, component, track_parents=False, *, excluded=frozenset()):
    distances, pending = {seed: initial}, [(initial, seed)]
    parents = {seed: None}
    while pending:
        value, source = heapq.heappop(pending)
        if value != distances[source]:
            continue
        for target, cost, length in graph.get(source, ()):
            if target in excluded:
                continue
            candidate = value + (cost if component == "cost" else length)
            if candidate < distances.get(target, math.inf):
                distances[target] = candidate
                parents[target] = source
                heapq.heappush(pending, (candidate, target))
    return (distances, parents) if track_parents else distances


def _trace(parents, edge, reverse=False):
    path = []
    while edge is not None:
        path.append(edge)
        edge = parents[edge]
    return list(reversed(path)) if reverse else path


def coverage_candidates(edges, connections, connection_costs, pairs, *,
                        cost_factors, hierarchy_overrides, max_cost_ratio,
                        max_length_ratio, candidates_per_edge=3,
                        compatible_witness_search_limit=0):
    """Escolhe poucos ODs existentes por lacuna, respeitando limites prévios.

    Um limite inferior acima do teto prova incompatibilidade com esse teto e
    esses extremos. Um limite abaixo dele não prova viabilidade: a validação
    nativa ainda pode encontrar repetições ou outro custo/comprimento.
    """
    if (isinstance(candidates_per_edge, bool) or not isinstance(candidates_per_edge, int)
            or not 1 <= candidates_per_edge <= 8):
        raise ValueError("A cobertura exige 1–8 candidatos OD por trecho.")
    if (type(compatible_witness_search_limit) is not int or
            not 0 <= compatible_witness_search_limit <= 128):
        raise ValueError("A busca complementar exige 0–128 buscas por trecho.")
    for value in (max_cost_ratio, max_length_ratio):
        if (isinstance(value, bool) or not isinstance(value, (int, float)) or
                not math.isfinite(value) or value < 1):
            raise ValueError("Limites de cobertura devem ser finitos e maiores ou iguais a um.")
    covered = {edge for pair in pairs.values() for edge in pair["route"]}
    missing = sorted(edges.keys() - covered)
    if not missing:
        return [], {"missing_before": 0, "edges": []}
    costs = {identifier: edge["time"] * cost_factors.get(
        hierarchy_overrides.get(identifier, edge["hierarchy"]), 1.0)
        for identifier, edge in edges.items()}
    forward, backward = {}, {}
    for a, b in sorted(connections):
        length, seconds = connection_costs[a, b]
        transition = costs[b] + seconds, edges[b]["length"] + length
        forward.setdefault(a, []).append((b, *transition))
        backward.setdefault(b, []).append((a, *transition))
    best = {}
    for pair in pairs.values():
        od = pair["origin"], pair["destination"]
        item = best.setdefault(od, {"cost": math.inf, "length": math.inf})
        item["cost"] = min(item["cost"], pair["urban_generalized_cost_s"])
        item["length"] = min(item["length"], pair["length_m"])
    origins = sorted({a for a, _ in best})
    destinations = sorted({b for _, b in best})
    origin_search = {a: _distances(a, forward, costs[a], "cost", True) for a in origins}
    from_cost = {a: value[0] for a, value in origin_search.items()}
    from_length = {a: _distances(a, forward, edges[a]["length"], "length") for a in origins}
    destination_search = {b: _distances(b, backward, 0.0, "cost", True) for b in destinations}
    to_cost = {b: value[0] for b, value in destination_search.items()}
    to_length = {b: _distances(b, backward, 0.0, "length") for b in destinations}
    candidates, rows = [], []
    baselines = sorted(best.items())
    has_nodes = all("from" in item and "to" in item for item in edges.values())

    def path_nodes(path):
        return [edges[path[0]]["from"]] + [edges[item]["to"] for item in path]

    def simple(path):
        if len(path) != len(set(path)):
            return False
        nodes = path_nodes(path) if has_nodes else []
        return len(nodes) == len(set(nodes))

    entering, leaving = {}, {}
    if compatible_witness_search_limit and has_nodes:
        for identifier, item in edges.items():
            entering.setdefault(item["to"], set()).add(identifier)
            leaving.setdefault(item["from"], set()).add(identifier)
    for edge in missing:
        possible, reachable = [], 0
        minimum_cost_ratio, minimum_length_ratio = math.inf, math.inf
        for (origin, destination), baseline in baselines:
            cost = from_cost[origin].get(edge, math.inf) + to_cost[destination].get(edge, math.inf)
            length = from_length[origin].get(edge, math.inf) + to_length[destination].get(edge, math.inf)
            if not math.isfinite(cost) or not math.isfinite(length):
                continue
            reachable += 1
            cost_ratio, length_ratio = cost / baseline["cost"], length / baseline["length"]
            minimum_cost_ratio = min(minimum_cost_ratio, cost_ratio)
            minimum_length_ratio = min(minimum_length_ratio, length_ratio)
            if cost_ratio <= max_cost_ratio + 1e-10 and length_ratio <= max_length_ratio + 1e-10:
                possible.append((cost_ratio, length_ratio, cost, origin, destination))
        prefixes, suffixes, selected = {}, {}, []
        possible.sort()
        for candidate in possible:
            origin, destination = candidate[3:]
            if origin not in prefixes:
                prefixes[origin] = _trace(origin_search[origin][1], edge, True)
            if destination not in suffixes:
                suffixes[destination] = _trace(destination_search[destination][1], edge)
            witness = prefixes[origin] + suffixes[destination][1:]
            if not simple(witness):
                continue
            selected.append((candidate, witness))
            if len(selected) == candidates_per_edge:
                break
        searches = {}
        if not selected and compatible_witness_search_limit and has_nodes:
            # As duas metades mínimas podem se cruzar. Tente manter uma
            # delas e rotear a outra sem entrar nas junções já consumidas.
            for candidate in possible:
                origin, destination = candidate[3:]
                for key, fixed, graph, excluded_by_node, endpoint, reverse in (
                    (("suffix", origin), prefixes[origin], forward, entering, destination, False),
                    (("prefix", destination), suffixes[destination], backward, leaving, origin, True),
                ):
                    if key not in searches:
                        if len(searches) == compatible_witness_search_limit:
                            continue
                        blocked = set().union(*(excluded_by_node.get(node, ()) for node in path_nodes(fixed)))
                        searches[key] = _distances(edge, graph, 0.0, "cost", True, excluded=blocked)[1]
                    parents = searches[key]
                    if endpoint not in parents:
                        continue
                    other = _trace(parents, endpoint, not reverse)
                    witness = other + fixed[1:] if reverse else fixed + other[1:]
                    if not simple(witness):
                        continue
                    links = tuple(zip(witness, witness[1:]))
                    cost = sum(costs[item] for item in witness) + sum(connection_costs[link][1] for link in links)
                    length = sum(edges[item]["length"] for item in witness) + sum(connection_costs[link][0] for link in links)
                    baseline = best[origin, destination]
                    if cost <= max_cost_ratio * baseline["cost"] + 1e-10 and length <= max_length_ratio * baseline["length"] + 1e-10:
                        selected.append((candidate, witness))
                        break
                if len(selected) == candidates_per_edge:
                    break
        for (cost_ratio, length_ratio, _, origin, destination), witness in selected:
            candidates.append({"origin": origin, "destination": destination,
                               # Fixar só o trecho pode fazer o roteador escolher um
                               # retorno no prefixo. A sequência comprova o caminho
                               # simples; o custo real ainda passa pela validação.
                               "via": witness[1:-1], "coverage_edge": edge,
                               "lower_bound_cost_ratio": cost_ratio,
                               "lower_bound_length_ratio": length_ratio})
        rows.append({"edge": edge, "reachable_endpoint_pairs": reachable,
                     "endpoint_pairs_within_lower_bounds": len(possible),
                     "native_candidates": len(selected),
                     **({"compatible_witness_searches": len(searches)} if searches else {}),
                     "minimum_cost_ratio_lower_bound": minimum_cost_ratio if reachable else None,
                     "minimum_length_ratio_lower_bound": minimum_length_ratio if reachable else None,
                     "status": "native_validation_required" if selected else
                         "no_simple_shortest_witness_for_current_endpoints" if possible else
                         "outside_detour_limits_for_current_endpoints" if reachable else
                         "no_directed_path_between_current_endpoints"})
    return candidates, {"missing_before": len(missing), "edges": rows,
                        "candidate_limit_per_edge": candidates_per_edge,
                        "basis": "directed_graph_lower_bounds; native_validation_required; no_minimum_vehicle_count"}
