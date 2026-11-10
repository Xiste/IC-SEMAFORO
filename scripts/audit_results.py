"""Auditoria dos resultados publicados e da distribuição de rotas.

Use --episodes PASTA para validar o contrato core/full.
Use --routes-file ROTAS --output RELATORIO para cobertura, acessos e observações.
A leitura compara hashes e publica relatórios em um arquivo novo.
"""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import json
import math
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from SistemaDeSemaforos.metrics.metrics_storage import (
    describe_metric, open_result, read_json, result_path, result_sha256,
)
from SistemaDeSemaforos.demand.metasettran_demand_generator import _route_pairs, _sha256
from SistemaDeSemaforos.demand.metasettran_network import demand_endpoints, expand_local_activity, read_network
from SistemaDeSemaforos.demand.random_demand_generator import DEFAULT_NET_FILE


def records_valid(records, observed):
    """Confere contrato, unicidade, finitude e ordem dos agregados temporais."""
    types = {"int": int, "float": float, "bool": bool, "string": str}
    values = {}
    for record in records:
        name, value = record["metric_name"], record["value"]
        if (not re.fullmatch(r"[a-z][a-z0-9_]*", name) or name in values
                or type(value) is not types.get(record["data_type"])):
            raise ValueError(f"Tipo/chave inválido: {record}")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"Valor não finito: {name}")
        values[name] = value
        observed.add(name)
    for name in values:
        if name.endswith("_min"):
            prefix = name[:-4]
            if prefix + "_mean" in values and prefix + "_max" in values:
                if not values[name] - 1e-8 <= values[prefix + "_mean"] <= values[prefix + "_max"] + 1e-8:
                    raise ValueError(f"Agregados fora de ordem: {prefix}")
    return len(records)


def episode_records_valid(document, observed):
    """Confere os registros tipados e a apresentação, sem recalcular resultados."""
    version = document.get("schema_version")
    if type(version) is not int or version not in {1, 2, 3}:
        raise ValueError(f"Schema de métricas não suportado: {version}")
    records = document["metrics"]
    # A semântica vem do mesmo módulo usado para publicar os resultados.
    for record in records:
        describe_metric(record["metric_name"])
    if version in {2, 3}:
        previous_priority = 0
        categories = {
            "performance": {1}, "operation": {2}, "integrity": {3},
            "diagnostic": {4}, "context": {4},
        }
        for record in records:
            for key in ("label_pt", "description_pt"):
                if not isinstance(record.get(key), str) or not record[key].strip():
                    raise ValueError(f"Apresentação sem {key}: {record['metric_name']}")
            if "unit" not in record or (record["unit"] is not None and
                    (not isinstance(record["unit"], str) or not record["unit"].strip())):
                raise ValueError(f"Unidade inválida: {record['metric_name']}")
            if record.get("kind") not in {"result", "context", "diagnostic"}:
                raise ValueError(f"Natureza inválida: {record['metric_name']}")
            priority = record.get("priority")
            if (type(priority) is not int or
                    priority not in categories.get(record.get("category"), set())):
                raise ValueError(f"Prioridade/categoria inválida: {record['metric_name']}")
            if priority < previous_priority:
                raise ValueError("Métricas fora da ordem de importância")
            previous_priority = priority
    return records_valid(records, observed)



def audit(episodes):
    directory = Path(episodes)
    if not directory.is_dir():
        raise ValueError(f"Pasta de episódios não encontrada: {episodes}")
    found = sorted([*directory.rglob("metrics.json"), *directory.rglob("metrics.json.gz")])
    by_episode = {}
    for path in found:
        previous = by_episode.get(path.parent)
        if previous is not None and result_sha256(previous) != result_sha256(path):
            raise ValueError(f"Resultados de métricas divergentes em: {path.parent}")
        by_episode[path.parent] = path
    episode_paths = list(by_episode.values())
    if not episode_paths:
        raise ValueError(f"Nenhum episódio encontrado em: {episodes}")
    observed, record_count = set(), 0
    for path in episode_paths:
        document = read_json(path)
        if document.get("schema_version") != 3:
            raise ValueError(f"Episódio exige schema_version=3: {path}")
        record_count += episode_records_valid(document, observed)
        metrics = {record["metric_name"]: record["value"] for record in document["metrics"]}
        execution = document.get("execution", {})
        if execution.get("status") != "completed" or metrics.get("status") != "completed":
            raise ValueError(f"Episódio incompleto: {path}")
        profile = execution.get("collection", {}).get("profile")
        if profile not in {"core", "full", "diagnostic"} or metrics.get("metrics_profile") != profile:
            raise ValueError(f"Perfil inconsistente: {path}")
        if not isinstance(execution.get("sumo_version"), str) or not execution["sumo_version"].strip():
            raise ValueError(f"Versão SUMO ausente ou inválida: {path}")
        if "entity_metrics_file" not in document:
            raise ValueError(f"Declaração de entidades ausente: {path}")
        entity_file = document["entity_metrics_file"]
        if profile == "core":
            if entity_file is not None:
                raise ValueError(f"Core não deve declarar detalhes por entidade: {path}")
            if (path.parent / "entities.json.gz").exists():
                raise ValueError(f"Entidades existentes mas não declaradas: {path}")
            continue
        if entity_file != "entities.json.gz" or not (path.parent / entity_file).is_file():
            raise ValueError(f"Arquivo de entidades {profile} ausente ou inválido: {path}")
        with gzip.open(path.parent / entity_file, "rt", encoding="utf-8") as source:
            entities_document = json.load(source)
        if entities_document.get("schema_version") != 1:
            raise ValueError(f"Schema de entidades não suportado: {path}")
        for entities in entities_document["entities"].values():
            for records in entities.values():
                record_count += records_valid(records, observed)
    result = {"episodes_verified": len(episode_paths),
              "typed_records_verified": record_count,
              "distinct_metric_names": len(observed)}
    return result


def _reachable(seeds, graph):
    visited, pending = set(seeds), list(seeds)
    while pending:
        for target in graph.get(pending.pop(), ()):
            if target not in visited:
                visited.add(target)
                pending.append(target)
    return visited


def _edge_observations(path, edges, metric_values):
    """Lê um único conjunto edgeData, sem transformar registros ausentes em zeros."""
    path = result_path(Path(path).resolve())
    samples, records = Counter(), Counter()
    interval_count, gaps, first, last = 0, 0, None, None
    ignored = set()
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as source:
        parsed = ET.iterparse(source, events=("start", "end"))
        _, root = next(parsed)
        if root.tag != "meandata":
            raise ValueError("Observação deve ser um edgeData SUMO com raiz meandata.")
        for event, interval in parsed:
            if event != "end" or interval.tag != "interval":
                continue
            begin, end = float(interval.get("begin", "nan")), float(interval.get("end", "nan"))
            if (not math.isfinite(begin) or not math.isfinite(end) or end <= begin
                    or (last is not None and begin < last)):
                raise ValueError("Intervalos edgeData inválidos ou sobrepostos.")
            if last is not None and begin > last:
                gaps += 1
            if first is None:
                first = begin
            last = end
            interval_count += 1
            seen = set()
            for record in interval.findall("edge"):
                identifier = record.get("id")
                if not identifier or identifier in seen:
                    raise ValueError("Trecho edgeData sem ID ou repetido no intervalo.")
                seen.add(identifier)
                value = float(record.get("sampledSeconds", "nan"))
                if not math.isfinite(value) or value < 0:
                    raise ValueError("sampledSeconds deve ser finito e não negativo.")
                if identifier not in edges:
                    ignored.add(identifier)
                    continue
                samples[identifier] += value
                records[identifier] += 1
            root.clear()
    expected_begin = metric_values.get("simulation_begin_seconds")
    expected_end = metric_values.get("simulation_end_seconds")
    matches = None
    if expected_begin is not None and expected_end is not None:
        matches = (first is not None and gaps == 0
                   and math.isclose(first, expected_begin, abs_tol=1e-6)
                   and math.isclose(last, expected_end, abs_tol=1e-6))
    return {
        "file": str(path), "sha256": _sha256(path), "intervals": interval_count,
        "begin": first, "end": last, "interval_gaps": gaps,
        "matches_episode_time_window": matches,
        "observed_passenger_edges": len(records),
        "occupied_passenger_edges": sum(value > 0 for value in samples.values()),
        "passenger_edges_without_records": len(edges) - len(records),
        "ignored_edge_ids": sorted(ignored),
        "meaning": "sampledSeconds > 0 is occupancy, not completed passage; missing records remain unknown, including excludeEmpty output",
        "association": "explicitly supplied file; time-window agreement alone does not prove same episode",
    }, samples, records


def _teleport_observations(path, net_file, metric_values):
    """Conta avisos nativos; agregação/truncamento do log não vira zero de eventos."""
    path = result_path(Path(path).resolve())
    network = ET.parse(net_file).getroot()
    lane_edges = {lane.get("id"): edge.get("id") for edge in network.findall("edge")
                  for lane in edge.findall("lane")}
    by_edge, by_reason, vehicles, unknown_lanes = defaultdict(Counter), Counter(), set(), set()
    messages, unparsed = 0, 0
    pattern = re.compile(r"Teleporting vehicle '([^']+)'; (.*), lane='([^']+)', time=([0-9]+(?:\.[0-9]+)?)")
    with open_result(path, "rt", encoding="utf-8") as source:
        for line in source:
            if "Teleporting vehicle '" not in line:
                continue
            messages += 1
            match = pattern.search(line)
            if match is None:
                unparsed += 1
                continue
            vehicle, description, lane, _ = match.groups()
            reason_match = re.search(r"waited too long \(([^)]+)\)", description)
            reason = reason_match.group(1) if reason_match else "other"
            vehicles.add(vehicle)
            by_reason[reason] += 1
            if lane not in lane_edges:
                unknown_lanes.add(lane)
                continue
            by_edge[lane_edges[lane]][reason] += 1
    expected = metric_values.get("teleports")
    return {
        "file": str(path), "sha256": result_sha256(path),
        "reported_start_messages": messages, "unparsed_start_messages": unparsed,
        "unique_vehicles_in_parsed_messages": len(vehicles),
        "expected_episode_events": expected,
        "count_status": ("not_verifiable_without_episode_total" if expected is None else
                         "matches_episode_event_total" if messages == expected else
                         "incomplete_or_mismatched_log"),
        "by_reason": dict(by_reason), "unknown_lane_ids": sorted(unknown_lanes),
        "by_edge": [{"edge": edge, "internal": edge.startswith(":"),
                     "reported_events": sum(reasons.values()), "by_reason": dict(reasons)}
                    for edge, reasons in sorted(by_edge.items(), key=lambda item: (-sum(item[1].values()), item[0]))],
        "meaning": "reported start messages, not physical capacity or unique vehicles; suppressed or missing warnings cannot establish zero events",
    }


def audit_distribution(*, routes_file, net_file=DEFAULT_NET_FILE, spatial_file=None, metrics_file=None,
          edge_data=None, sumo_log=None):
    """Retorna resumo e uma linha por trecho passenger, incluindo os não usados."""
    routes_file, net_file = result_path(Path(routes_file).resolve()), Path(net_file).resolve()
    hashes = {"network_sha256": _sha256(net_file), "routes_sha256": result_sha256(routes_file)}
    generation, metric_values = {}, {}
    if metrics_file is not None:
        document = read_json(metrics_file)
        generation = document["execution"]["generation"]
        metric_values = {record["metric_name"]: record["value"] for record in document["metrics"]}
        for field, actual in (("source_network_sha256", hashes["network_sha256"]),
                              ("routes_sha256", hashes["routes_sha256"])):
            if generation.get(field) and generation[field] != actual:
                raise ValueError(f"Arquivo diverge do episódio: {field}")
    network = read_network(net_file)
    edges, connections = network.edges, network.connections
    counts, movements, origins, destinations = Counter(), Counter(), Counter(), Counter()
    route_counts, departure_lanes, identifiers = Counter(), Counter(), set()
    first, last, previous, repeated_routes = math.inf, -math.inf, -math.inf, 0
    with open_result(routes_file) as source:
        parsed = ET.iterparse(source, events=("start", "end"))
        _, root = next(parsed)
        if root.tag != "routes":
            raise ValueError("Arquivo de rotas deve ter raiz routes.")
        for event, vehicle in parsed:
            if event != "end" or vehicle.tag != "vehicle":
                continue
            identifier = vehicle.get("id")
            if not identifier or identifier in identifiers:
                raise ValueError("Veículo sem ID ou duplicado no arquivo de rotas.")
            identifiers.add(identifier)
            route = vehicle.find("route")
            path = route.get("edges", "").split() if route is not None else []
            if (not path or any(edge not in edges for edge in path) or
                    any(pair not in connections for pair in zip(path, path[1:]))):
                raise ValueError(f"Rota passenger ausente ou descontínua: {identifier}")
            depart = float(vehicle.get("depart"))
            if not math.isfinite(depart) or depart < 0 or depart < previous:
                raise ValueError(f"Partida inválida ou fora de ordem: {identifier}")
            previous = last = depart
            first = min(first, depart)
            # Uma viagem conta uma vez por trecho, mesmo quando contém voltas.
            counts.update(set(path))
            movements.update(set(zip(path, path[1:])))
            origins[path[0]] += 1
            destinations[path[-1]] += 1
            route_counts[tuple(path)] += 1
            departure_lanes[vehicle.get("departLane", "SUMO_default")] += 1
            repeated_routes += len(path) != len(set(path))
            root.clear()
    if not identifiers:
        raise ValueError("Arquivo sem veículos com rotas explícitas.")
    if generation.get("vehicles_generated", len(identifiers)) != len(identifiers):
        raise ValueError("Quantidade de veículos diverge do episódio.")

    catalog, catalog_counts, model = None, Counter(), None
    if spatial_file is not None:
        hashes["spatial_sha256"] = _sha256(spatial_file)
        if generation.get("spatial_sha256", hashes["spatial_sha256"]) != hashes["spatial_sha256"]:
            raise ValueError("Cadastro espacial diverge do episódio.")
        model = json.loads(Path(spatial_file).read_text(encoding="utf-8"))
        if model["network_sha256"] != hashes["network_sha256"]:
            raise ValueError("Cadastro espacial pertence a outra rede.")
        model = expand_local_activity(model, edges, connections)
        with TemporaryDirectory(prefix="demand-catalog-audit-") as temporary:
            directory = Path(temporary)
            pairs, _, catalog, _ = _route_pairs(
                model, net_file, directory, directory / "routing.log", network=network)
        for pair in pairs.values():
            catalog_counts.update(set(pair["route"]))
        entry_ids = {p["edge"] for p in demand_endpoints(model, "entries")}
        exit_ids = {p["edge"] for p in demand_endpoints(model, "exits")}
        if not set(route_counts) <= {tuple(pair["route"]) for pair in pairs.values()}:
            raise ValueError("Rotas fornecidas não pertencem ao catálogo reconstruído.")
    else:
        entry_ids, exit_ids = set(origins), set(destinations)
    forward, backward = defaultdict(set), defaultdict(set)
    for a, b in connections:
        forward[a].add(b)
        backward[b].add(a)
    from_origins = _reachable(entry_ids, forward)
    to_destinations = _reachable(exit_ids, backward)
    rows, classes = [], Counter()
    hierarchy_counts = defaultdict(Counter)
    overrides = model["regional_demand"].get("road_hierarchy_overrides", {}) if model else {}
    coverage_review = {row["edge"]: row for row in (catalog or {}).get(
        "coverage_completion", {}).get("edges", [])}
    for identifier, edge in sorted(edges.items()):
        if counts[identifier]:
            reason = "used_in_planned_routes"
        elif model is None:
            reason = "not_in_planned_routes"
        elif identifier not in from_origins:
            reason = "unreachable_from_configured_origins"
        elif identifier not in to_destinations:
            reason = "cannot_reach_configured_destinations"
        elif not catalog_counts[identifier]:
            reason = "outside_route_catalog"
        else:
            reason = "catalog_route_not_sampled"
        classes[reason] += 1
        hierarchy_counts[edge["hierarchy"]][reason] += 1
        row = {"edge": identifier, "native_hierarchy": edge["hierarchy"],
                     "demand_hierarchy": overrides.get(identifier, edge["hierarchy"]),
                     "length_m": edge["length"], "passenger_lanes": len(edge["lanes"]),
                     "planned_vehicles": counts[identifier], "status": reason,
                     "catalog_routes": catalog_counts[identifier] if model else None,
                     "configured_origin": identifier in entry_ids,
                     "configured_destination": identifier in exit_ids}
        if reason == "outside_route_catalog" and identifier in coverage_review:
            row["coverage_review"] = coverage_review[identifier]
        rows.append(row)
    total = len(identifiers)
    duration = generation.get("duration")
    def ranked(counter):
        return [{"edge": edge, "vehicles": count, "share_of_vehicles": count / total}
                for edge, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:20]]
    report = {
        "schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "routes_file": str(routes_file), "net_file": str(net_file), **hashes,
        "basis": "planned_route_incidence; not physical passage, congestion or capacity",
        "vehicles": total, "distinct_routes": len(route_counts),
        "routes_with_repeated_edge": repeated_routes,
        "first_departure_seconds": first, "last_departure_seconds": last,
        "departure_lane_attributes": dict(departure_lanes),
        "coverage": {"passenger_normal_edges": len(edges), "planned_used_edges": len(counts),
                     "unused_edges": len(edges) - len(counts), "by_reason": dict(classes),
                     "network_length_m": sum(e["length"] for e in edges.values()),
                     "planned_used_length_m": sum(edges[e]["length"] for e in counts),
                     "by_native_hierarchy": dict(hierarchy_counts)},
        "catalog": catalog,
        "configured_endpoints": {"origins": len(entry_ids), "destinations": len(exit_ids),
            "network_sources_without_origin": sorted(set(edges) - set(backward) - entry_ids),
            "network_sinks_without_destination": sorted(set(edges) - set(forward) - exit_ids)},
        "top_origins": ranked(origins), "top_destinations": ranked(destinations),
        "top_edges": ranked(counts),
        "top_movements": [{"from": a, "to": b, "planned_vehicles": count,
            "planned_vehicles_per_hour": count * 3600 / duration if duration else None}
            for (a, b), count in sorted(movements.items(), key=lambda item: (-item[1], item[0]))[:30]],
        "edges": rows,
        "limitations": [
            "Reachability is an edge graph necessary condition, not proof of a loop-free admissible OD route.",
            "Unused catalog routes may have low probability; no minimum traffic is imposed.",
            "A route catalogue is fixed by network and spatial configuration, independently of demand seed/time.",
            "Missing observed passage data does not mean zero physical traffic.",
        ],
    }
    if metric_values:
        observed = metric_values.get("simulation_duration_seconds")
        report["episode"] = {"metrics_file": str(Path(metrics_file).resolve()),
            "demand_model": generation.get("demand_model"), "seed": generation.get("seed"),
            "duration_seconds": duration, "simulation_duration_seconds": observed,
            "simulation_end_requested_seconds": metric_values.get("simulation_end_requested_seconds"),
            "ended_before_last_scheduled_departure": observed < last if observed is not None else None,
            "teleports": metric_values.get("teleports"),
            "trip_populations": generation.get("spatial_distribution", {}).get("trip_populations"),
            "urban_prior_drift": generation.get("spatial_distribution", {}).get(
                "observation_projection", {}).get("urban_prior_drift")}
    if edge_data is not None:
        observation, samples, records = _edge_observations(edge_data, edges, metric_values)
        report["physical_observation"] = observation
        for row in rows:
            identifier = row["edge"]
            row["physical_observation"] = {
                "sampled_seconds": samples[identifier] if records[identifier] else None,
                "interval_records": records[identifier],
                "status": ("not_observed" if not records[identifier] else
                           "occupied_in_supplied_intervals" if samples[identifier] > 0 else
                           "no_occupancy_in_supplied_records"),
            }
    if sumo_log is not None:
        report["teleport_observation"] = _teleport_observations(sumo_log, net_file, metric_values)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--episodes", type=Path)
    source.add_argument("--routes-file", type=Path)
    parser.add_argument("--net-file", type=Path)
    parser.add_argument("--spatial-file", type=Path)
    parser.add_argument("--metrics-file", type=Path)
    parser.add_argument("--edge-data", type=Path)
    parser.add_argument("--sumo-log", type=Path)
    parser.add_argument("--output", type=Path)
    args = vars(parser.parse_args(argv))
    episodes = args.pop("episodes")
    if episodes is not None:
        if any(value is not None for value in args.values()):
            parser.error("--episodes aceita somente a pasta de resultados.")
        audit(episodes)
        return 0
    if args["output"] is None:
        parser.error("--routes-file exige --output.")
    output = args.pop("output").resolve()
    if args["net_file"] is None:
        args.pop("net_file")
    inputs = [Path(value).resolve() for value in args.values() if value is not None]
    if output in inputs or output.exists():
        parser.error("Escolha um arquivo de relatório novo, distinto das entradas.")
    report = audit_distribution(**args)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as destination:
        json.dump(report, destination, ensure_ascii=False, indent=2, allow_nan=False)
        destination.write("\n")
    print(json.dumps({"report": str(output), "vehicles": report["vehicles"],
                      "coverage": report["coverage"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
