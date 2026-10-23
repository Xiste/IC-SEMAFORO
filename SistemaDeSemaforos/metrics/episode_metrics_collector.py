"""Consolida XMLs nativos do SUMO sem gravar arquivos.

Entrada: diretório de saídas e rede; saída: métricas globais e por entidade.
O runner normalmente chama ``collect_episode`` depois que o SUMO encerra.
Separa viagens concluídas, incompletas e removidas para respeitar cada população.
Os agregados usam amostras válidas; dados ausentes não são tratados como zero.
"""

from collections import Counter, defaultdict
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from functools import lru_cache
import gzip
import math
from pathlib import Path
import re
import time
import xml.etree.ElementTree as ET


# O core seleciona resultados do mesmo cálculo usado pelo full. As séries e
# os registros individuais nunca são retidos nesse perfil.
CORE_METRICS = {
    "metrics_profile", "simulation_begin_seconds", "simulation_end_seconds",
    "simulation_duration_seconds", "simulation_steps", "observation_step_seconds",
    "vehicles_loaded", "vehicles_inserted", "vehicles_removed", "vehicles_completed",
    "vehicles_discarded", "trip_records_unfinished", "trip_records_undeparted",
    "trip_records_vaporized", "completed_throughput_vehicles_per_hour",
    "teleports", "collisions", "queue_observation_steps",
    *(f"completed_trip_{field}_{aggregation}"
      for field in ("duration", "waiting_time", "time_loss", "depart_delay")
      for aggregation in ("mean", "samples")),
    *(f"{field}_{aggregation}"
      for field in ("vehicles_halting", "vehicles_waiting_insertion",
                    "network_queueing_length_lane_sum")
      for aggregation in ("mean", "max", "samples")),
    *(f"network_mean_speed_m_s_{aggregation}"
      for aggregation in ("mean", "samples", "excluded_samples")),
    "network_queueing_length_lane_sum_excluded_samples",
}


@lru_cache(maxsize=1024)
def _snake(name):
    """Converte nomes SUMO, como speedRelative, para speed_relative."""
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _number(value):
    """Mantém inteiros como inteiros; rejeita NaN/inf e atributos textuais."""
    try:
        result = int(value) if re.fullmatch(r"[+-]?\d+", value) else float(value)
    except (ValueError, TypeError):
        return None
    return result if math.isfinite(result) else None


def metasettran_observation_edges(spatial_model):
    """Reúne sensores, portais e seções de corredor, sem duplicar observações."""
    edges = {candidate["edge"] for sensor in spatial_model["sensors"]
             for candidate in sensor["candidates"]}
    for role in ("entries", "exits"):
        edges.update(portal["edge"] for portal in spatial_model.get("portals", {}).get(role, []))
    for corridor in spatial_model.get("corridors", []):
        edges.update(corridor.get("observation_edges", []))
    for movement in spatial_model.get("observation_movements", []):
        edges.update((movement["from_edge"], movement["to_edge"]))
    return tuple(sorted(edges))


def _metasettran_distance_stats(values):
    """Quantis interpolados da distância registrada, separados por população."""
    values = sorted(values)
    if not values:
        return {"samples": 0, "min": None, "p25": None, "median": None,
                "p75": None, "max": None, "mean": None}

    def quantile(fraction):
        position = (len(values) - 1) * fraction
        index = int(position)
        return values[index] + (values[min(index + 1, len(values) - 1)] - values[index]) * (position - index)

    return {"samples": len(values), "min": values[0], "p25": quantile(.25),
            "median": quantile(.5), "p75": quantile(.75), "max": values[-1],
            "mean": sum(values) / len(values)}


def _count_errors(simulated, reference):
    if len(simulated) != len(reference):
        raise ValueError("Curvas MetaSettran com janelas temporais incompatíveis.")
    pairs = [(actual, expected) for actual, expected in zip(simulated, reference)
             if actual is not None and expected is not None]
    errors = [abs(actual - expected) for actual, expected in pairs]
    total = sum(expected for _, expected in pairs)
    return {"n_windows": len(pairs), "mae_cars_per_15min": sum(errors) / len(errors) if errors else None,
            "wape": sum(errors) / total if total else None,
            "simulated_cars": sum(actual for actual, _ in pairs), "reference_cars": total}


def _metasettran_sensor_timing(raw, planned_routes, scheduled, departures, teleported, spatial_model, duration):
    """Mede atrasos nativos, sem deslocar as janelas civis para melhorar o erro."""
    candidates = {candidate["edge"] for sensor in spatial_model["sensors"]
                  for candidate in sensor["candidates"]}
    records = {}
    for edge in sorted(candidates):
        identifiers = {identifier for identifier, route in planned_routes.items() if edge in route}
        inserted = identifiers & departures.keys()
        records[edge] = {
            "edge": edge, "planned_trips_crossing": len(identifiers),
            "not_inserted": len(identifiers - departures.keys()),
            "inserted_with_teleport_excluded": len(inserted & teleported),
            "inserted_without_teleport": len(inserted - teleported),
            "reached_without_teleport": 0, "not_reached_without_teleport": 0,
            "physical_passages_per_15min_without_teleport": [0] * (duration // 900),
            "physical_passages_during_clearance_without_teleport": 0,
            "_travel": [], "_delay": [],
        }
    movements = []
    for definition in spatial_model.get("observation_movements", []):
        pair = (definition["from_edge"], definition["to_edge"])
        identifiers = {identifier for identifier, route in planned_routes.items()
                       if pair in tuple(zip(route, route[1:]))}
        movements.append({
            **{key: definition[key] for key in ("id", "label", "from_edge", "to_edge") if key in definition},
            "planned_trips": len(identifiers), "not_inserted": len(identifiers - departures.keys()),
            "inserted_with_teleport_excluded": len(identifiers & departures.keys() & teleported),
            "physical_passages_per_15min_without_teleport": [0] * (duration // 900),
            "physical_passages_during_clearance_without_teleport": 0,
            "_identifiers": identifiers,
        })
    seen = set()
    for item in _elements(raw / "vehicle_routes.xml.gz", "vehicle"):
        identifier = item.get("id")
        depart = _number(item.get("depart"))
        if (identifier not in departures or identifier in seen or depart is None or
                abs(depart - departures[identifier]) > .00001):
            raise ValueError("Vehroute MetaSettran diverge das inserções observadas no tripinfo.")
        seen.add(identifier)
        # Mesmo uma passagem anterior ao teleporte fica fora desta população
        # conservadora: exitTimes não certifica deslocamentos físicos após TP.
        if identifier in teleported:
            continue
        routes = item.findall("route")
        if len(routes) != 1:
            raise ValueError("Vehroute MetaSettran sem uma rota individual verificável.")
        edges = routes[0].get("edges", "").split()
        times = [_number(value) for value in routes[0].get("exitTimes", "").split()]
        if (tuple(edge for edge in edges if not edge.startswith(":")) != planned_routes[identifier]
                or len(times) != len(edges) or any(value is None or value < -1 for value in times)):
            raise ValueError("Vehroute MetaSettran contém rota ou exitTimes inválidos.")
        previous = depart
        unfinished = False
        for timestamp in times:
            if timestamp == -1:
                unfinished = True
            elif unfinished or timestamp < previous:
                raise ValueError("Vehroute MetaSettran contém exitTimes fora de ordem.")
            else:
                previous = timestamp
        for edge in candidates.intersection(edges):
            record = records[edge]
            positions = [index for index, value in enumerate(edges) if value == edge]
            if len(positions) != 1:
                raise ValueError("Uma viagem MetaSettran atravessa repetidamente o mesmo sensor.")
            index = positions[0]
            # Internal=true inclui a conexão: a saída do predecessor é a
            # entrada no sensor, mesmo quando a viagem termina dentro dele.
            entry = depart if index == 0 else times[index - 1]
            if entry < 0:
                record["not_reached_without_teleport"] += 1
                continue
            record["reached_without_teleport"] += 1
            record["_travel"].append(entry - depart)
            record["_delay"].append(max(0.0, depart - scheduled[identifier]))
            if entry < duration:
                record["physical_passages_per_15min_without_teleport"][int(entry // 900)] += 1
            else:
                record["physical_passages_during_clearance_without_teleport"] += 1
        external = [(index, edge) for index, edge in enumerate(edges) if not edge.startswith(":")]
        for record in movements:
            if identifier not in record["_identifiers"]:
                continue
            for (_, previous_edge), (index, edge) in zip(external, external[1:]):
                if (previous_edge, edge) != (record["from_edge"], record["to_edge"]):
                    continue
                entry = times[index - 1]
                if entry < 0:
                    continue
                if entry < duration:
                    record["physical_passages_per_15min_without_teleport"][int(entry // 900)] += 1
                else:
                    record["physical_passages_during_clearance_without_teleport"] += 1
    if seen != departures.keys():
        raise ValueError("Vehroute MetaSettran não cobre todos os veículos inseridos.")
    for record in records.values():
        if record["reached_without_teleport"] + record["not_reached_without_teleport"] != record["inserted_without_teleport"]:
            raise ValueError("Populações de alcance dos sensores MetaSettran não se reconciliam.")
        record["entry_to_sensor_seconds"] = _metasettran_distance_stats(record.pop("_travel"))
        record["insertion_delay_seconds_for_reached_trips"] = _metasettran_distance_stats(record.pop("_delay"))
    for record in movements:
        del record["_identifiers"]
        reached = (sum(record["physical_passages_per_15min_without_teleport"])
                   + record["physical_passages_during_clearance_without_teleport"])
        record["not_reached_without_teleport"] = (
            record["planned_trips"] - record["not_inserted"]
            - record["inserted_with_teleport_excluded"] - reached)
        if record["not_reached_without_teleport"] < 0:
            raise ValueError("Uma viagem MetaSettran repete um movimento observado.")
    return {
        "source": "SUMO vehroute exitTimes with internal edges; previous-edge exit is sensor-edge entry",
        "insertion_delay_seconds_all_inserted": _metasettran_distance_stats(
            [max(0.0, depart - scheduled[identifier]) for identifier, depart in departures.items()]),
        "departure_rounding_tolerance_seconds": .0005,
        "candidates": list(records.values()),
        "movements": movements,
        "note": "Civil 15-minute count windows remain unchanged. Travel-time quantiles include only reached trips without any teleport; unreached, uninserted and teleport-affected populations remain explicit. No holdout-derived phase shift or hidden warm-up is applied.",
    }


def _metasettran_progress(raw, scheduled, natural_arrivals, horizon):
    """Quinze minutos de diagnóstico operacional no mesmo resultado do episódio."""
    intervals = {}
    for step in _elements(raw / "summary.xml.gz", "step"):
        timestamp = float(step.get("time"))
        index = int(timestamp // 900)
        row = intervals.setdefault(index, {"begin": index * 900, "end": min((index + 1) * 900, horizon),
                                           "halting_max": 0, "waiting_insertion_max": 0})
        row.update(snapshot_time=timestamp, inserted_cumulative=int(step.get("inserted")),
                   arrived_cumulative_including_teleports=int(step.get("arrived")),
                   running=int(step.get("running")), waiting_insertion=int(step.get("waiting")),
                   teleport_events_cumulative=int(step.get("teleports")))
        row["halting_max"] = max(row["halting_max"], int(step.get("halting")))
        row["waiting_insertion_max"] = max(row["waiting_insertion_max"], int(step.get("waiting")))
    scheduled, natural_arrivals = sorted(scheduled.values()), sorted(natural_arrivals)
    for row in intervals.values():
        row["programmed_cumulative"] = bisect_right(scheduled, row["snapshot_time"] + .0005)
        row["natural_arrivals_cumulative"] = bisect_right(natural_arrivals, row["snapshot_time"])
    return {"source": "Native summary snapshots and maxima in 900s windows; natural arrivals from tripinfo and verified teleport IDs",
            "intervals": list(intervals.values())}


def _metasettran_boundary_continuity(scheduled, departures, endings, trip_statuses,
                                    teleported, duration, horizon):
    """Certifica identidades em circulação nas fronteiras, sem novos snapshots.

    Diferenças de intervalos evitam uma varredura de todas as viagens para cada
    fronteira. Só três exemplos por intervalo de vida precisam ser retidos.
    """
    boundaries = list(range(10800, duration, 10800))
    differences = {name: [0] * (len(boundaries) + 1) for name in (
        "carried_without_any_teleport", "carried_with_teleport",
        "removed_with_unknown_end_time")}
    examples = {}
    for identifier, depart in departures.items():
        # Não antecipar a faixa de uma partida arredondada pelo SUMO (<0,5 ms).
        start = bisect_right(boundaries, max(scheduled[identifier], depart))
        unknown_removal = (trip_statuses[identifier] == "removed_without_completion"
                           and endings[identifier] is None)
        end = endings[identifier] if endings[identifier] is not None else horizon
        stop = bisect_left(boundaries, end)
        if start >= stop:
            continue
        population = ("removed_with_unknown_end_time" if unknown_removal else
                      "carried_with_teleport" if identifier in teleported else
                      "carried_without_any_teleport")
        differences[population][start] += 1
        differences[population][stop] -= 1
        if population == "carried_without_any_teleport":
            candidates = examples.setdefault((start, stop), [])
            if len(candidates) < 3 or identifier < candidates[-1]:
                candidates.append(identifier)
                candidates.sort()
                del candidates[3:]
    programmed = sorted(scheduled.values())
    released = sorted(max(scheduled[identifier], depart) for identifier, depart in departures.items())
    rows, populations = [], Counter()
    for index, boundary in enumerate(boundaries):
        populations.update({name: values[index] for name, values in differences.items()})
        candidates = sorted(identifier for (begin, end), identifiers in examples.items()
                            if begin <= index < end for identifier in identifiers)[:3]
        programmed_before = bisect_left(programmed, boundary)
        inserted_before = bisect_left(released, boundary)
        rows.append({
            "time_seconds": boundary,
            "programmed_before_boundary": programmed_before,
            "inserted_before_boundary": inserted_before,
            "pending_insertion_from_previous_sections": programmed_before - inserted_before,
            **populations,
            "continuity_examples": [{
                "id": identifier, "scheduled_departure_seconds": scheduled[identifier],
                "actual_departure_seconds": departures[identifier],
                "trip_end_seconds": endings[identifier],
                "final_status": trip_statuses[identifier],
            } for identifier in candidates],
        })
    return {
        "section_seconds": 10800, "departure_window_seconds": [0, duration],
        "clearance_window_seconds": [duration, horizon], "boundaries": rows,
        "source": "Native tripinfo identities, actual departures and arrivals/removals; verified teleport IDs from the SUMO log.",
        "note": "Carryover requires an insertion before the boundary and a trip end strictly after it. Pending insertions are separate. Teleport-affected lifetimes may include temporary absence from the road. No intermediate boundary is a final incomplete-trip classification; the clearance window occurs only at the end.",
    }


def _metasettran_portal_accounting(planned, scheduled, departures, trip_statuses, teleported,
                                  spatial_model, duration, horizon):
    """Reconstrói a espera de inserção por origem, sem observador por timestep."""
    metadata = {portal["edge"]: portal for portal in spatial_model.get("portals", {}).get("entries", [])}
    identifiers_by_origin = defaultdict(list)
    for identifier, (origin, _) in planned.items():
        identifiers_by_origin[origin].append(identifier)
    records = []
    for origin in sorted(set(identifiers_by_origin) | metadata.keys()):
        identifiers = identifiers_by_origin[origin]
        inserted_ids = [identifier for identifier in identifiers if identifier in departures]
        status_counts = Counter(trip_statuses[identifier] for identifier in identifiers)
        scheduled_times = sorted(scheduled[identifier] for identifier in identifiers)
        # An insertion rounded down by SUMO by <=0.5 ms must not subtract a
        # different pending vehicle before its own scheduled boundary.
        released_times = sorted(max(scheduled[identifier], departures[identifier]) for identifier in inserted_ids)
        programmed_bins = Counter(int(scheduled[identifier] // 900) for identifier in identifiers)
        delay_bins = defaultdict(list)
        for identifier in inserted_ids:
            delay_bins[int(departures[identifier] // 900)].append(max(0.0, departures[identifier] - scheduled[identifier]))
        intervals = []
        for index in range(math.ceil(horizon / 900)):
            begin, end = index * 900, min((index + 1) * 900, horizon)
            # Half-open civil windows. At a boundary, a departure exactly at
            # end belongs to the next interval, as does its scheduled time.
            pending = bisect_left(scheduled_times, end) - bisect_left(released_times, end)
            intervals.append({
                "begin": begin, "end": end,
                "phase": "demand" if begin < duration else "clearance",
                "programmed": programmed_bins[index], "inserted": len(delay_bins[index]),
                "pending_insertion_at_end": pending,
                "insertion_delay_seconds": _metasettran_distance_stats(delay_bins[index]),
            })
        portal = metadata.get(origin, {})
        records.append({
            "edge": origin,
            **{key: portal[key] for key in ("name", "boundary_group", "corridor") if key in portal},
            "programmed": len(identifiers), "inserted": len(inserted_ids),
            **{name: status_counts[name] for name in (
                "not_inserted", "completed_without_teleport", "completed_after_teleport",
                "incomplete_at_end", "removed_without_completion")},
            "vehicles_with_teleport": sum(identifier in teleported for identifier in identifiers),
            "inserted_during_clearance": sum(departures[identifier] >= duration for identifier in inserted_ids),
            "insertion_delay_seconds": _metasettran_distance_stats(
                [max(0.0, departures[identifier] - scheduled[identifier]) for identifier in inserted_ids]),
            "intervals": intervals,
        })
    return {
        "bin_seconds": 900, "entries": records,
        "source": "Scheduled routes plus native tripinfo; intervals are half-open. Pending means scheduled before the boundary but not inserted before it, including vehicles that insert later.",
        "note": "Trip statuses are exclusive; vehicles_with_teleport overlaps statuses. Clearance may contain late insertions as well as completion of trips already in the network.",
    }


def _metasettran_route_incidence(planned_routes, spatial_model):
    """Conta viagens únicas; incidências distintas nunca são somadas como demanda."""
    candidates = {candidate["edge"] for sensor in spatial_model["sensors"] for candidate in sensor["candidates"]}
    sensors = {str(sensor["sensor_id"]): {candidate["edge"] for candidate in sensor["candidates"]}
               for sensor in spatial_model["sensors"]}
    candidate_counts, combinations = Counter(), Counter()
    for route in planned_routes.values():
        edges = set(route)
        candidate_counts.update(candidates & edges)
        combination = tuple(sorted(sensor for sensor, observed_edges in sensors.items() if edges & observed_edges))
        combinations[combination] += 1
    return {
        "unique_programmed_trips": len(planned_routes),
        "candidate_edges": [{"edge": edge, "programmed_trips": candidate_counts[edge]} for edge in sorted(candidates)],
        "sensor_combinations": [{"sensor_ids": list(combination), "programmed_trips": count}
                                for combination, count in sorted(combinations.items())],
        "note": "Sensor membership is the union of its alternative candidate edges; it is not a confirmed physical sensor location. Each trip belongs to one combination and can cross multiple observed edges or sensors without duplication.",
    }


def collect_metasettran_validation(directory, generation, *, summary_metrics=None, vehicles=None):
    """Valida o piloto com as saídas nativas, preservando as métricas legadas.

    Chegada após teleporte não é conclusão natural. As comparações espaciais
    são condicionais ao cadastro de sensores ainda não confirmado; nenhum
    erro pequeno transforma o cadastro numa medição geográfica comprovada.
    """
    directory = Path(directory)
    raw = directory / "raw"
    duration = generation["duration"]
    if (isinstance(duration, bool) or not isinstance(duration, (int, float)) or
            not math.isfinite(duration) or duration <= 0 or duration % 900):
        raise ValueError("Janela MetaSettran deve conter intervalos completos de quinze minutos.")
    duration = int(duration)
    bins = duration // 900
    planned, planned_routes, scheduled, departures, endings = {}, {}, {}, {}, {}
    route_cache = {}
    route_count = 0
    for item in _elements(Path(generation["routes_file"]), "vehicle"):
        route_count += 1
        route = item.find("route")
        edges = tuple(route.get("edges", "").split()) if route is not None else ()
        if not edges or item.get("departPos") != "0" or item.get("arrivalPos") != "max":
            raise ValueError("Demanda MetaSettran não declara extremos completos da viagem.")
        # Uma semana repete o catálogo finito de percursos; não é necessário
        # conservar outro tuple de strings por veículo nem a árvore XML inteira.
        edges = route_cache.setdefault(edges, edges)
        planned[item.get("id")] = (edges[0], edges[-1])
        planned_routes[item.get("id")] = edges
        scheduled[item.get("id")] = _number(item.get("depart"))
        if scheduled[item.get("id")] is None or not 0 <= scheduled[item.get("id")] < generation["duration"]:
            raise ValueError("Partida programada MetaSettran fora da janela de demanda.")
    if (not planned or None in planned or "" in planned or
            len(planned) != route_count or len(planned) != generation["vehicles_generated"]):
        raise ValueError("Demanda MetaSettran com IDs repetidos ou contagem divergente.")
    del route_cache
    lane_lengths = {lane.get("id"): float(lane.get("length"))
                    for edge in ET.parse(generation["net_file"]).getroot().findall("edge")
                    for lane in edge.findall("lane")}
    teleported = set()
    events = 0
    with (directory / "sumo.log").open(encoding="utf-8") as stream:
        for line in stream:
            if "Teleporting vehicle" in line:
                match = re.search(r"Teleporting vehicle '([^']+)'", line)
                if match is None:
                    raise ValueError("Evento de teleporte sem identificação reconhecível.")
                events += 1
                teleported.add(match.group(1))
    if not teleported.issubset(planned):
        raise ValueError("Teleporte de veículo não pertencente à demanda MetaSettran.")
    if summary_metrics is None:
        summary_metrics = _summary(raw / "summary.xml.gz")
    if events != summary_metrics["teleports"]:
        raise ValueError("Log de teleportes incompleto; não é possível certificar conclusões naturais.")
    statuses = Counter()
    trip_statuses = {}
    distances = defaultdict(list)
    seen = set()
    inserted = late = 0
    natural_arrivals = []
    for item in _elements(raw / "trips.xml.gz", "tripinfo"):
        identifier = item.get("id")
        if identifier not in planned or identifier in seen:
            raise ValueError("Tripinfo MetaSettran com ID desconhecido ou repetido.")
        seen.add(identifier)
        depart, arrival = float(item.get("depart")), float(item.get("arrival"))
        if not math.isfinite(depart) or not math.isfinite(arrival) or depart < -1 or arrival < -1:
            raise ValueError("Tripinfo MetaSettran contém tempo inválido.")
        vaporized = item.get("vaporized", "") not in {"", "false", "0", "end"}
        if depart < 0:
            status = "not_inserted"
        else:
            origin, destination = planned[identifier]
            depart_position = _number(item.get("departPos"))
            if (item.get("departLane", "").rsplit("_", 1)[0] != origin or
                    depart_position is None or abs(depart_position) > .001):
                raise ValueError("Veículo MetaSettran inserido fora do início do portal previsto.")
            inserted += 1
            # SUMO representa tempo em milissegundos; o XML de demanda conserva
            # microssegundos. Até meio milissegundo é arredondamento, não antecipação.
            if depart < scheduled[identifier] - .00050001:
                raise ValueError("Inserção MetaSettran antecede a partida programada.")
            departures[identifier] = depart
            late += depart >= generation["duration"]
            trip_duration = _number(item.get("duration"))
            endings[identifier] = (arrival if arrival >= 0 else
                                   depart + trip_duration if vaporized and trip_duration is not None
                                   and trip_duration >= 0 else None)
            if vaporized:
                status = "removed_without_completion"
            elif arrival < 0:
                status = "incomplete_at_end"
            else:
                status = "completed_after_teleport" if identifier in teleported else "completed_without_teleport"
                if identifier not in teleported:
                    natural_arrivals.append(arrival)
                    lane = item.get("arrivalLane", "")
                    position = _number(item.get("arrivalPos"))
                    if (lane.rsplit("_", 1)[0] != destination or lane not in lane_lengths or
                            position is None or abs(position - lane_lengths[lane]) > .001):
                        raise ValueError("Conclusão natural MetaSettran fora do final do portal previsto.")
        statuses[status] += 1
        trip_statuses[identifier] = status
        if depart >= 0:
            distance = _number(item.get("routeLength"))
            if distance is None or distance < 0:
                raise ValueError("Tripinfo MetaSettran contém distância ausente ou inválida.")
            distance_group = status
            if status == "incomplete_at_end":
                distance_group += "_after_teleport" if identifier in teleported else "_without_teleport"
            distances[distance_group].append(distance)
        if vehicles is not None:
            record = vehicles.setdefault(identifier, {})
            record["metasettran_trip_status"] = status
            record["experienced_teleport"] = identifier in teleported
            record["scheduled_departure_seconds"] = scheduled[identifier]
            record["actual_departure_seconds"] = depart if depart >= 0 else None
            record["insertion_delay_seconds"] = max(0.0, depart - scheduled[identifier]) if depart >= 0 else None
    # Toda partida programada antecede o horizonte; ausência de Tripinfo é
    # falha de observação, e não evidência de veículo não inserido.
    if seen != set(planned) or inserted != summary_metrics["vehicles_inserted"]:
        raise ValueError("Tripinfo MetaSettran não cobre toda a demanda e suas inserções.")
    metrics = {f"vehicles_{name}": statuses[name] for name in (
        "completed_without_teleport", "completed_after_teleport", "not_inserted",
        "incomplete_at_end", "removed_without_completion")}
    metrics.update(vehicles_with_teleport=len(teleported), vehicles_inserted_after_demand_window=late)
    spatial_model = generation["spatial_model"]
    sensor_timing = _metasettran_sensor_timing(
        raw, planned_routes, scheduled, departures, teleported, spatial_model, duration)
    observation_edges = metasettran_observation_edges(spatial_model)
    entry_edges = {portal["edge"] for portal in spatial_model.get("portals", {}).get("entries", [])}
    exit_edges = {portal["edge"] for portal in spatial_model.get("portals", {}).get("exits", [])}
    counts = {edge: [None] * bins for edge in observation_edges}
    tail = Counter()
    portal_counts = {"departed": {edge: [None] * bins for edge in entry_edges},
                     "arrived": {edge: [None] * bins for edge in exit_edges}}
    portal_tail = {"departed": Counter(), "arrived": Counter()}
    previous_end = 0.0
    for interval in _elements(raw / "metasettran_counts.xml.gz", "interval"):
        begin, end = float(interval.get("begin")), float(interval.get("end"))
        if (not math.isfinite(begin) or not math.isfinite(end) or begin != previous_end
                or begin % 900 != 0 or not 0 < end - begin <= 900
                or (begin < duration and end - begin != 900)):
            raise ValueError("Intervalos de contagem MetaSettran incompletos ou duplicados.")
        previous_end = end
        interval_edges = set()
        for edge in interval.findall("edge"):
            identifier = edge.get("id")
            if identifier not in counts or identifier in interval_edges:
                raise ValueError("Observação MetaSettran contém via desconhecida ou duplicada.")
            interval_edges.add(identifier)
            value = int(edge.get("entered", "0"))
            if value < 0:
                raise ValueError("Contagem MetaSettran negativa.")
            if begin >= duration:
                tail[identifier] += value
            else:
                index = int(begin / 900)
                if begin != index * 900 or end - begin != 900 or counts[identifier][index] is not None:
                    raise ValueError("Intervalos de contagem MetaSettran incompletos ou duplicados.")
                counts[identifier][index] = value
            for attribute, selected_edges in (("departed", entry_edges), ("arrived", exit_edges)):
                if identifier not in selected_edges:
                    continue
                # departed é inserção; entered é passagem desde outra via.
                # arrived é conclusão no destino; left também inclui tráfego
                # que apenas continua sua rota e nunca representa chegada.
                if attribute not in edge.attrib:
                    raise ValueError(f"Contagem MetaSettran sem atributo de portal {attribute}.")
                value = int(edge.get(attribute))
                if value < 0:
                    raise ValueError("Contagem MetaSettran de portal negativa.")
                if begin >= generation["duration"]:
                    portal_tail[attribute][identifier] += value
                else:
                    portal_counts[attribute][identifier][index] = value
        if interval_edges != set(observation_edges):
            raise ValueError("Intervalo MetaSettran não contém todas as vias observadas.")
    if "clearance_limit_seconds" in generation and previous_end != generation["duration"] + generation["clearance_limit_seconds"]:
        raise ValueError("Contagens MetaSettran não cobrem o horizonte solicitado.")
    if any(depart >= previous_end for depart in departures.values()):
        raise ValueError("Inserção MetaSettran fora do horizonte observado.")
    if any(value is None for values in counts.values() for value in values):
        raise ValueError("Contagens MetaSettran não cobrem todos os intervalos de demanda.")
    comparisons = []
    physical_counts = {record["edge"]: record for record in sensor_timing["candidates"]}
    for sensor in spatial_model["sensors"]:
        profile = generation["calibration"]["sensors"][str(sensor["sensor_id"]) ]
        for candidate in sensor["candidates"]:
            observed = counts[candidate["edge"]]
            physical = physical_counts[candidate["edge"]]
            physical_observed = physical["physical_passages_per_15min_without_teleport"]
            checks, physical_checks = {}, {}
            for partition in ("primary", "post"):
                checks[partition] = []
                physical_checks[partition] = []
                for day in profile["validation"][partition]["daily_counts"]:
                    if any(len(day[key]) != bins for key in ("counts", "eligible", "exposure_seconds")):
                        raise ValueError("Referência MetaSettran com janelas temporais incompatíveis.")
                    # Comparação de contagens usa apenas quartos de hora com
                    # exposição integral, sem expandir intervalos faltantes.
                    reference = [value if eligible and exposure == 900 else None
                                 for value, eligible, exposure in zip(day["counts"], day["eligible"], day["exposure_seconds"])]
                    window = {key: day[key] for key in ("date", "start", "end") if key in day}
                    checks[partition].append({**window, **_count_errors(observed, reference)})
                    physical_checks[partition].append({**window, **_count_errors(physical_observed, reference)})
            comparisons.append({
                "sensor_id": sensor["sensor_id"], "edge": candidate["edge"],
                "candidate_position": candidate["position"], "mapping_status": sensor["status"],
                "simulated_cars_per_15min": observed, "cars_passing_during_clearance": tail[candidate["edge"]],
                "against_training_curve": _count_errors(observed, profile["target_counts"]),
                "against_held_out_dates": checks,
                "without_any_teleport": {
                    "physical_passages_per_15min": physical_observed,
                    "physical_passages_during_clearance": physical["physical_passages_during_clearance_without_teleport"],
                    "against_training_curve": _count_errors(physical_observed, profile["target_counts"]),
                    "against_held_out_dates": physical_checks,
                    "note": "Conservative physical population excludes every vehicle with any teleport, including passages before that event. No demand-window passage is shifted or replaced by clearance traffic.",
                },
            })
    observed_edge_set = set(observation_edges)
    planned_edge_counts = Counter(edge for route in planned_routes.values() for edge in set(route) & observed_edge_set)
    planned_origins = Counter(origin for origin, _ in planned.values())
    planned_destinations = Counter(destination for _, destination in planned.values())

    def flow_record(edge, attribute):
        series = counts[edge] if attribute == "entered" else portal_counts[attribute][edge]
        clearance = tail[edge] if attribute == "entered" else portal_tail[attribute][edge]
        planned_counts = {"entered": planned_edge_counts, "departed": planned_origins, "arrived": planned_destinations}
        return {"edge": edge, "measure": attribute, "programmed_trips": planned_counts[attribute][edge], "cars_per_15min": series,
                "cars_during_demand": sum(series), "cars_during_clearance": clearance,
                "cars_total": sum(series) + clearance}

    portals = {}
    for role, attribute in (("entries", "departed"), ("exits", "arrived")):
        portals[role] = [
            {**{key: portal[key] for key in ("name", "boundary_group", "corridor") if key in portal},
             **flow_record(portal["edge"], attribute)}
            for portal in spatial_model.get("portals", {}).get(role, [])
        ]
    reconciled = {}
    if entry_edges:
        total = sum(item["cars_total"] for item in portals["entries"])
        if total != inserted:
            raise ValueError("Inserções nos portais MetaSettran divergem do summary e tripinfo.")
        reconciled["departures"] = {
            "edge_data_departed": total, "summary_inserted": summary_metrics["vehicles_inserted"],
            "tripinfo_inserted": inserted, "status": "matched",
        }
    if exit_edges:
        total = sum(item["cars_total"] for item in portals["exits"])
        natural = statuses["completed_without_teleport"]
        arrived = natural + statuses["completed_after_teleport"]
        if (not natural <= total <= arrived or
                ("vehicles_completed" in summary_metrics and summary_metrics["vehicles_completed"] != arrived)):
            raise ValueError("Chegadas nos portais MetaSettran divergem das populações do tripinfo/summary.")
        reconciled["arrivals"] = {
            "edge_data_arrived": total, "tripinfo_arrived": arrived,
            "summary_arrived": summary_metrics.get("vehicles_completed"),
            "tripinfo_without_teleport": natural,
            "tripinfo_after_teleport": statuses["completed_after_teleport"],
            "arrivals_not_observed_at_exit": arrived - total,
            "status": "matched" if total == arrived else "teleport_affected",
            "note": "Portal arrived counts can include arrivals after a prior teleport; they are not natural-completion counts.",
        }
    spatial_observation = {
        "bin_seconds": 900, "departure_window_seconds": [0, generation["duration"]],
        "clearance_window_seconds": [generation["duration"], previous_end],
        "portals": portals, "portal_reconciliation": reconciled,
        "portal_trip_accounting": _metasettran_portal_accounting(
            planned, scheduled, departures, trip_statuses, teleported, spatial_model, duration, previous_end),
        "route_observation_incidence": _metasettran_route_incidence(planned_routes, spatial_model),
        "observed_movements": sensor_timing.pop("movements"),
        "corridor_probes": [
            {**{key: corridor[key] for key in ("id", "label", "direction") if key in corridor},
             "probes": [flow_record(edge, "entered") for edge in corridor.get("observation_edges", [])]}
            for corridor in spatial_model.get("corridors", [])
        ],
        "trip_distance_m": {
            "source": "SUMO tripinfo.routeLength; quantiles use linear interpolation between ordered samples",
            "completed_without_teleport": _metasettran_distance_stats(distances["completed_without_teleport"]),
            "completed_after_teleport": _metasettran_distance_stats(distances["completed_after_teleport"]),
            "incomplete_at_end_without_teleport": _metasettran_distance_stats(distances["incomplete_at_end_without_teleport"]),
            "incomplete_at_end_after_teleport": _metasettran_distance_stats(distances["incomplete_at_end_after_teleport"]),
            "removed_without_completion": _metasettran_distance_stats(distances["removed_without_completion"]),
            "note": "Unfinished/removed records describe distance reported up to interruption, not full OD length. Teleport-affected records are separate and do not certify physically travelled distance.",
        },
        "note": "Corridor probes are separate sections; sequential edges are never summed as distinct vehicles. Portal insertions use departed and destination completions use arrived.",
    }
    result = {
        "metrics": metrics,
        "status": "conditional_on_unconfirmed_sensor_mapping",
        "empirical_calibration_status": "conditional_on_unconfirmed_sensor_mapping_and_external_scope",
        "temporal_scope": {
            **generation.get("temporal_scope", {}),
            "start_week_second": generation.get("start_week_second"),
            "duration_seconds": duration, "bins": bins, "bin_seconds": 900,
        },
        "trip_accounting": {"generated": len(planned), "accounted": sum(statuses.values()),
                            "teleport_events": events, "teleport_vehicle_ids_verified": True},
        "boundary_integrity": {"insertions_at_expected_portal_start": inserted,
                               "natural_arrivals_at_expected_portal_end": statuses["completed_without_teleport"],
                               "invalid": 0, "position_tolerance_m": .001},
        "count_class": "car", "simulation_class": "passenger",
        "observation": "SUMO edgeData.entered at each candidate edge; before/after values are alternatives, not summed",
        "startup": "Empty network at t=0; trips reach sensors after departure. No hidden warm-up or phase shift.",
        "count_comparisons": comparisons,
        "sensor_passage_timing": sensor_timing,
        "operational_progression": _metasettran_progress(raw, scheduled, natural_arrivals, previous_end),
        "boundary_continuity": _metasettran_boundary_continuity(
            scheduled, departures, endings, trip_statuses, teleported, duration, previous_end),
        "spatial_observation": spatial_observation,
        "limitations": [
            "Physical passage counts may be affected by teleport events; any such events require inspection before empirical acceptance.",
            "OD distribution and unobserved demand are scenario estimates conditional on the spatial prior; internal trips and non-car classes are absent.",
            "Sensor populations may overlap; a route crossing both counters represents one vehicle. Sensor totals do not identify network-wide unique demand.",
            "Boundary departure rates and local passage targets are distinct. Freeflow projection omits queues and signal delays; empty initialization excludes vehicles already circulating at the civil start.",
            "Only fully covered held-out 15-minute windows are scored; missing or partial observations are not zero traffic.",
        ],
    }
    if "temporal_scope" not in generation:
        # Preserve the historic pilot schema; supported contexts are now a
        # generator declaration, separate from empirical calibration status.
        result["ready_for_weekly_expansion"] = False
    return result


def _elements(path, tag):
    """Lê um registro por vez e solta seus nós XML após o consumo.

    Um registro pode ser um timestep inteiro: seus filhos ainda são necessários
    para somar veículos/faixas, mas timesteps anteriores não ficam em memória.
    Arquivo ausente é erro: uma coleta incompleta não pode parecer completa.
    """
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as source:
        stack = []
        selected_depth = None
        for event, element in ET.iterparse(source, events=("start", "end")):
            if event == "start":
                stack.append(element)
                if (element.tag == tag or isinstance(tag, tuple) and element.tag in tag) and selected_depth is None:
                    selected_depth = len(stack)
                continue
            if selected_depth == len(stack):
                yield element
                selected_depth = None
            if selected_depth is None:
                element.clear()
                if len(stack) > 1:
                    stack[-2].remove(element)
            stack.pop()


@dataclass(slots=True)
class RunningStats:
    """Guarda apenas contagem, soma e extremos, em vez de toda a série."""

    count: int = 0
    total: float = 0.0
    minimum: float | None = None
    maximum: float | None = None

    def add(self, value, count=1):
        if count <= 0:
            return
        self.count += count
        self.total += value * count
        self.minimum = value if self.minimum is None else min(self.minimum, value)
        self.maximum = value if self.maximum is None else max(self.maximum, value)

    def values(self, name, include_sum=False):
        result = {f"{name}_samples": self.count}
        if self.count:
            result.update({f"{name}_min": self.minimum,
                           f"{name}_mean": self.total / self.count,
                           f"{name}_max": self.maximum})
            if include_sum:
                result[f"{name}_sum"] = self.total
        return result


def _summary(path):
    """Separa contadores cumulativos, estados temporais e sentinelas -1."""
    cumulative = {"loaded": "vehicles_loaded", "inserted": "vehicles_inserted",
                  "ended": "vehicles_removed", "arrived": "vehicles_completed",
                  "teleports": "teleports", "collisions": "collisions",
                  "discarded": "vehicles_discarded"}
    temporal = {"running": "vehicles_running", "waiting": "vehicles_waiting_insertion",
                "halting": "vehicles_halting", "stopped": "vehicles_scheduled_stop",
                "meanSpeed": "network_mean_speed_m_s",
                "meanSpeedRelative": "network_mean_relative_speed",
                "duration": "sumo_step_computation_ms"}
    final_means = {"meanWaitingTime": "cumulative_insertion_delay_mean_seconds",
                   "meanTravelTime": "cumulative_removed_travel_time_mean_seconds"}
    stats = defaultdict(RunningStats)
    invalid = Counter()
    metrics = {}
    first = last = None
    count = 0
    for step in _elements(path, "step"):
        time = float(step.attrib["time"])
        first = time if first is None else first
        last = time
        count += 1
        for attribute, name in cumulative.items():
            if attribute in step.attrib:
                metrics[name] = int(step.attrib[attribute])
        for attribute, name in temporal.items():
            if attribute not in step.attrib:
                continue
            value = _number(step.attrib[attribute])
            # SUMO pode escrever velocidade zero para rede vazia: não é uma
            # observação de velocidade de veículos e não entra na média.
            empty_speed = attribute.startswith("meanSpeed") and int(step.attrib["running"]) == 0
            if value is None or value < 0 or empty_speed:
                invalid[name] += 1
            else:
                stats[name].add(value)
        for attribute, name in final_means.items():
            value = _number(step.attrib.get(attribute, "-1"))
            if value is not None and value >= 0:
                metrics[name] = value
    if count == 0:
        raise ValueError("O summary do SUMO não contém timesteps.")
    # O runner mantém o passo padrão do SUMO (1 s) e saída a cada passo.
    metrics.update(simulation_begin_seconds=first, simulation_end_seconds=last + 1,
                   simulation_duration_seconds=last + 1 - first,
                   simulation_steps=count, observation_step_seconds=1.0)
    for name in temporal.values():
        metrics.update(stats[name].values(name))
        metrics[f"{name}_excluded_samples"] = invalid[name]
    duration = metrics["simulation_duration_seconds"]
    if duration > 0 and "vehicles_completed" in metrics:
        metrics["completed_throughput_vehicles_per_hour"] = metrics["vehicles_completed"] * 3600 / duration
    return metrics


def _network(net_file):
    """Mapeia faixas físicas e aproximações controladas, sem editar a rede."""
    lanes, edges, lane_edge = set(), set(), {}
    external_lanes = set()
    connections = []
    for edge in _elements(net_file, ("edge", "connection")):
        if edge.tag == "connection":
            if "tl" in edge.attrib:
                connections.append(dict(edge.attrib))
            continue
        edge_id = edge.attrib["id"]
        edges.add(edge_id)
        for lane in edge.findall("lane"):
            lane_id = lane.attrib["id"]
            lanes.add(lane_id)
            lane_edge[lane_id] = edge_id
            if edge.attrib.get("function") not in {"internal", "crossing", "walkingarea"}:
                external_lanes.add(lane_id)
    groups = defaultdict(set)
    for connection in connections:
        edge = connection["from"]
        lane = f"{edge}_{connection['fromLane']}"
        if lane not in external_lanes:
            continue
        tls = connection["tl"]
        groups[("intersections", tls)].add(lane)
        groups[("approaches", f"{tls}/{edge}")].add(lane)
    membership = defaultdict(list)
    for group, lane_ids in groups.items():
        for lane in lane_ids:
            membership[lane].append(group)
    return lanes, edges, lane_edge, groups, membership


def _trips(path, metrics, vehicles=None):
    """Agrega por situação; ``vehicles=None`` dispensa a retenção individual."""
    distributions = defaultdict(lambda: defaultdict(RunningStats))
    statuses = Counter()
    for trip in _elements(path, "tripinfo"):
        attributes = trip.attrib
        depart = float(attributes["depart"])
        arrival = float(attributes["arrival"])
        vaporized = attributes.get("vaporized", "")
        if depart < 0:
            status = "undeparted"
        elif arrival < 0:
            status = "unfinished"
        elif vaporized and vaporized not in {"false", "0"}:
            status = "vaporized"
        else:
            status = "completed"
        statuses[status] += 1
        record = vehicles.setdefault(attributes["id"], {}) if vehicles is not None else {}
        record["trip_status"] = status
        for key, raw in attributes.items():
            if key == "id":
                continue
            name = "vehicle_type" if key == "vtype" else f"trip_{_snake(key)}"
            value = _number(raw)
            if value is None or key in {"departLane", "arrivalLane", "vtype", "devices", "vaporized"}:
                record[name] = raw
            elif value >= 0:
                record[name] = value
                distributions[status][name].add(value)
        emissions = trip.find("emissions")
        if emissions is not None:
            for key, raw in emissions.attrib.items():
                value = _number(raw)
                if value is not None:  # eletricidade negativa pode representar recuperação.
                    name = f"emission_{_snake(key)}"
                    record[name] = value
                    distributions[status][name].add(value)
    for status in ("completed", "unfinished", "undeparted", "vaporized"):
        # Concluídas já são contadas por summary.arrived; não duplicar o total.
        if status != "completed":
            metrics[f"trip_records_{status}"] = statuses[status]
        for name, stat in distributions[status].items():
            include_sum = name.startswith("emission_") or name in {
                "trip_duration", "trip_route_length", "trip_waiting_time", "trip_time_loss", "trip_depart_delay"}
            metrics.update(stat.values(f"{status}_{name}", include_sum=include_sum))
    # Zero amostras é conhecido mesmo quando não há média válida. A ausência
    # de viagens concluídas nunca se transforma em tempo médio igual a zero.
    for name in ("duration", "waiting_time", "time_loss", "depart_delay"):
        metrics.setdefault(f"completed_trip_{name}_samples", 0)


def _statistics(path, metrics):
    """Preserva estatísticas exclusivas; summary/tripinfo são fontes dos totais."""
    skip = {"vehicles", "vehicleTripStatistics"}
    root = ET.parse(path).getroot()  # arquivo pequeno: um elemento por categoria.
    for category in root:
        if category.tag in skip:
            continue
        for attribute, raw in category.attrib.items():
            if (category.tag, attribute) in {("teleports", "total"), ("safety", "collisions")}:
                continue
            if category.tag == "performance" and attribute in {"begin", "end", "duration"}:
                continue
            value = _number(raw)
            if value is not None and value >= 0:
                metrics[f"sumo_{_snake(category.tag)}_{_snake(attribute)}"] = value


_TRAFFIC_COUNTS = {"departed", "arrived", "entered", "left", "laneChangedFrom", "laneChangedTo",
                   "vaporized", "vaporizedOnNextEdge", "teleported"}
_TRAFFIC_ZERO = _TRAFFIC_COUNTS | {"sampledSeconds", "density", "overlapDensity", "laneDensity",
                                     "occupancy", "waitingTime", "timeLoss"}


def _traffic(path, tag, ids, target, metrics):
    """Agrega intervalos de 1 s, repondo zeros omitidos por excludeEmpty."""
    observations = defaultdict(lambda: defaultdict(RunningStats))
    invalid = defaultdict(Counter)
    weighted_speed = defaultdict(float)
    speed_weight = defaultdict(float)
    intervals = 0
    duration = 0.0
    seen_attributes = set()
    for interval in _elements(path, "interval"):
        intervals += 1
        period = float(interval.attrib["end"]) - float(interval.attrib["begin"])
        if not math.isclose(period, 1.0):
            raise ValueError("A consolidação de tráfego requer intervalos de 1 segundo.")
        duration += period
        for record in interval.iter(tag):
            identifier = record.attrib["id"]
            if identifier not in ids:
                continue
            for attribute, raw in record.attrib.items():
                if attribute == "id":
                    continue
                value = _number(raw)
                seen_attributes.add(attribute)
                if value is None or (value < 0 and attribute not in {"timeLoss"}):
                    invalid[identifier][attribute] += 1
                    continue
                if attribute in _TRAFFIC_COUNTS:
                    value = int(value)
                observations[identifier][attribute].add(value)
            speed = _number(record.attrib.get("speed", "-1"))
            weight = _number(record.attrib.get("sampledSeconds", "0"))
            if speed is not None and speed >= 0 and weight is not None and weight > 0:
                weighted_speed[identifier] += speed * weight
                speed_weight[identifier] += weight
    metrics[f"{tag}_traffic_intervals"] = intervals
    metrics[f"{tag}_traffic_duration_seconds"] = duration
    metrics[f"{tag}_traffic_internal_included"] = True
    for identifier in ids:
        result = target.setdefault(identifier, {})
        for attribute in seen_attributes:
            stat = observations[identifier][attribute]
            missing = intervals - stat.count - invalid[identifier][attribute]
            if attribute in _TRAFFIC_ZERO:
                stat.add(0, missing)
            name = f"traffic_{_snake(attribute)}"
            include_sum = attribute in _TRAFFIC_COUNTS | {"sampledSeconds", "waitingTime", "timeLoss"}
            result.update(stat.values(name, include_sum))
            if invalid[identifier][attribute]:
                result[f"{name}_excluded_samples"] = invalid[identifier][attribute]
            if attribute in _TRAFFIC_COUNTS and stat.count:
                result[f"{name}_sum"] = int(stat.total)
                if duration:
                    result[f"{name}_flow_per_hour"] = stat.total * 3600 / duration
        if speed_weight[identifier]:
            result["traffic_speed_vehicle_seconds_weighted_mean"] = weighted_speed[identifier] / speed_weight[identifier]


def _tls(path, begin, end, lights):
    """Integra duração dos estados; índices de fase não têm média numérica."""
    previous = {}
    phase_start = {}
    durations = defaultdict(lambda: defaultdict(RunningStats))
    changes = defaultdict(Counter)

    def close(identifier, state, until):
        duration = max(0.0, min(until, end) - max(float(state["time"]), begin))
        if duration == 0:
            return
        # IDs e strings de estados são codificados em hex para preservar caixa,
        # pontuação e unicidade nos nomes snake_case (G e g são estados distintos).
        program = state["programID"].encode().hex()
        code = state["state"].encode().hex()
        result = lights.setdefault(identifier, {})
        key = f"state_{code}_duration_seconds"
        result[key] = result.get(key, 0.0) + duration
        result[f"state_{code}_value"] = state["state"]
        result[f"program_{program}_value"] = state["programID"]

    def close_phase(identifier, state, until):
        duration = max(0.0, min(until, end) - max(phase_start[identifier], begin))
        if duration:
            program = state["programID"].encode().hex()
            name = f"program_{program}_phase_{state['phase']}_duration_seconds"
            durations[identifier][name].add(duration)

    for element in _elements(path, "tlsState"):
        identifier = element.attrib["id"]
        state = dict(element.attrib)
        time = float(state["time"])
        if time >= end:
            continue
        if identifier in previous:
            old = previous[identifier]
            if time < float(old["time"]):
                raise ValueError("Estados semafóricos fora de ordem temporal.")
            close(identifier, old, time)
            phase_changed = (old["programID"], old["phase"]) != (state["programID"], state["phase"])
            if phase_changed:
                close_phase(identifier, old, time)
                phase_start[identifier] = time
            if time >= begin:
                changes[identifier]["phase_changes"] += phase_changed
                changes[identifier]["program_changes"] += old["programID"] != state["programID"]
                changes[identifier]["state_changes"] += old["state"] != state["state"]
        else:
            phase_start[identifier] = time
        previous[identifier] = state
    for identifier, state in previous.items():
        close(identifier, state, end)
        close_phase(identifier, state, end)
        record = lights.setdefault(identifier, {})
        for name in ("phase_changes", "program_changes", "state_changes"):
            record[name] = changes[identifier][name]
        record["final_program_id"] = state["programID"]
        record["final_phase_index"] = int(state["phase"])
        record["final_state"] = state["state"]
        record["phase_duration_includes_boundary_fragments"] = True
        for name, stat in durations[identifier].items():
            record.update(stat.values(name, include_sum=True))


def _queues(path, lanes, groups, membership, entities, metrics):
    """Soma filas por passo; ``entities=None`` guarda somente o agregado global.

    O comprimento global soma os comprimentos das filas por faixa. Não é uma
    fila física única. Faixas omitidas pelo SUMO não têm fila naquele passo.
    """
    observations = defaultdict(lambda: defaultdict(RunningStats))
    group_stats = defaultdict(lambda: defaultdict(RunningStats))
    network_length = RunningStats()
    excluded = 0
    count = 0
    attributes = {"queueing_time", "queueing_length", "queueing_length_experimental"}
    for timestep in _elements(path, "data"):
        count += 1
        totals = defaultdict(Counter)
        length = 0.0
        valid_length = True
        for lane in timestep.iter("lane"):
            identifier = lane.attrib["id"]
            value = _number(lane.attrib.get("queueing_length"))
            if value is None or value < 0:
                valid_length = False
            else:
                length += value
            if entities is None:
                continue
            for attribute in attributes:
                value = _number(lane.attrib.get(attribute, "0"))
                if value is None or value < 0:
                    continue
                observations[identifier][attribute].add(value)
                for group in membership[identifier]:
                    totals[group][attribute] += value
        if valid_length:
            network_length.add(length)
        else:
            excluded += 1
        for group, values in totals.items():
            for attribute, value in values.items():
                group_stats[group][attribute].add(value)
    metrics["queue_observation_steps"] = count
    metrics.update(network_length.values("network_queueing_length_lane_sum"))
    metrics["network_queueing_length_lane_sum_excluded_samples"] = excluded
    if entities is None:
        return
    for identifier in lanes | set(observations):
        record = entities["lanes"].setdefault(identifier, {})
        for attribute in attributes:
            stat = observations[identifier][attribute]
            stat.add(0.0, count - stat.count)
            record.update(stat.values(attribute))
    for group, lane_ids in groups.items():
        scope, identifier = group
        record = entities[scope].setdefault(identifier, {})
        for attribute in attributes:
            stat = group_stats[group][attribute]
            stat.add(0.0, count - stat.count)
            record.update(stat.values(f"{attribute}_lane_sum"))


def _trajectories(path, lanes, membership, groups, entities, metrics):
    """FCD: dinâmica individual e contagem de parados (não confundir com fila)."""
    observations = defaultdict(lambda: defaultdict(RunningStats))
    signals = defaultdict(Counter)
    heading = defaultdict(lambda: [0.0, 0.0, 0])
    halting = defaultdict(RunningStats)
    group_halting = defaultdict(RunningStats)
    steps = 0
    for timestep in _elements(path, "timestep"):
        steps += 1
        stopped = Counter()
        for vehicle in timestep.findall("vehicle"):
            identifier = vehicle.attrib["id"]
            record = entities["vehicles"].setdefault(identifier, {})
            if "type" in vehicle.attrib:
                record.setdefault("vehicle_type", vehicle.attrib["type"])
            for attribute, raw in vehicle.attrib.items():
                if attribute in {"id", "type", "lane", "edge"}:
                    continue
                value = _number(raw)
                if value is None:
                    continue
                if attribute == "signals":
                    signals[identifier][int(value)] += 1
                elif attribute == "angle":
                    radians = math.radians(value)
                    heading[identifier][0] += math.sin(radians)
                    heading[identifier][1] += math.cos(radians)
                    heading[identifier][2] += 1
                else:
                    observations[identifier][attribute].add(value)
            if float(vehicle.attrib.get("speed", "inf")) <= 0.1:
                stopped[vehicle.attrib.get("lane", "")] += 1
        group_counts = Counter()
        for lane, count in stopped.items():
            if lane:
                halting[lane].add(count)
            for group in membership[lane]:
                group_counts[group] += count
        for group, count in group_counts.items():
            group_halting[group].add(count)
    metrics["fcd_observation_steps"] = steps
    for identifier, attributes in observations.items():
        record = entities["vehicles"][identifier]
        for attribute, stat in attributes.items():
            record.update(stat.values(f"fcd_{_snake(attribute)}"))
        for signal, count in signals[identifier].items():
            record[f"signals_bitmask_{signal}_samples"] = count
        sine, cosine, count = heading[identifier]
        if count:
            concentration = math.hypot(sine, cosine) / count
            record["heading_samples"] = count
            record["heading_resultant_length"] = concentration
            if concentration > 1e-12:
                record["heading_circular_mean_degrees"] = math.degrees(math.atan2(sine, cosine)) % 360
    for identifier in lanes | set(halting):
        stat = halting[identifier]
        stat.add(0, steps - stat.count)
        entities["lanes"].setdefault(identifier, {}).update(stat.values("stopped_vehicles"))
    for group in groups:
        scope, identifier = group
        stat = group_halting[group]
        stat.add(0, steps - stat.count)
        entities[scope].setdefault(identifier, {}).update(stat.values("stopped_vehicles"))


def _emissions(path, vehicles, metrics):
    """Agrega taxas por veículo; totais de viagem vêm exclusivamente do tripinfo."""
    attributes = {"CO", "CO2", "HC", "PMx", "NOx", "fuel", "electricity"}
    individual = defaultdict(lambda: defaultdict(RunningStats))
    network = defaultdict(RunningStats)
    noise_energy = defaultdict(float)
    noise_stats = defaultdict(RunningStats)
    waiting_stats = defaultdict(RunningStats)
    for timestep in _elements(path, "timestep"):
        totals = Counter()
        for vehicle in timestep.findall("vehicle"):
            identifier = vehicle.attrib["id"]
            for attribute in attributes:
                value = _number(vehicle.attrib.get(attribute, ""))
                if value is not None:
                    individual[identifier][attribute].add(value)
                    totals[attribute] += value
            noise = _number(vehicle.attrib.get("noise", ""))
            if noise is not None:
                noise_stats[identifier].add(noise)
                noise_energy[identifier] += 10 ** (noise / 10)
            waiting = _number(vehicle.attrib.get("waiting", ""))
            if waiting is not None and waiting >= 0:
                waiting_stats[identifier].add(waiting)
        for attribute in attributes:
            network[attribute].add(totals[attribute])
    for identifier, attributes_stats in individual.items():
        result = vehicles.setdefault(identifier, {})
        for attribute, stat in attributes_stats.items():
            result.update(stat.values(f"emission_{_snake(attribute)}_rate"))
        result.update(waiting_stats[identifier].values("current_waiting_time_seconds"))
        stat = noise_stats[identifier]
        if stat.count:
            # dB é logarítmico: média energética (Leq), nunca média aritmética.
            result.update(noise_db_min=stat.minimum, noise_db_max=stat.maximum,
                          noise_db_samples=stat.count,
                          noise_db_equivalent=10 * math.log10(noise_energy[identifier] / stat.count))
    for attribute, stat in network.items():
        metrics.update(stat.values(f"network_emission_{_snake(attribute)}_rate"))


def _events(path, tag, prefix, entities, metrics):
    """Eventos discretos: contagem, categorias e distribuição dos atributos."""
    count = 0
    stats = defaultdict(RunningStats)
    categories = Counter()
    for event in _elements(path, tag):
        count += 1
        for attribute, raw in event.attrib.items():
            if attribute in {"id", "collider", "victim", "from", "to", "lane", "type", "reason", "colliderType", "victimType"}:
                continue
            value = _number(raw)
            # Ausência de líder é representada como None/inf em lanechange.
            if value is not None:
                stats[attribute].add(value)
        for category in ("reason", "type"):
            if category in event.attrib:
                categories[(category, event.attrib[category])] += 1
        vehicle = event.attrib.get("id")
        if vehicle:
            record = entities["vehicles"].setdefault(vehicle, {})
            record[f"{prefix}_count"] = record.get(f"{prefix}_count", 0) + 1
        lane = event.attrib.get("from", event.attrib.get("lane"))
        if lane:
            record = entities["lanes"].setdefault(lane, {})
            record[f"{prefix}_count"] = record.get(f"{prefix}_count", 0) + 1
    # O total de colisões já vem de Summary; não exportar um segundo total.
    if prefix != "collision":
        metrics[f"{prefix}_events"] = count
    for attribute, stat in stats.items():
        metrics.update(stat.values(f"{prefix}_{_snake(attribute)}"))
    for (category, value), number in categories.items():
        key = f"{prefix}_{category}_{value.encode().hex()}"
        metrics[f"{key}_value"] = value
        metrics[f"{key}_count"] = number


def collect_episode(raw_dir: Path, net_file: Path, profile: str = "core") -> dict:
    """Consolida somente as fontes habilitadas; nenhuma linha por timestep.

    ``metrics`` contém escalares globais. ``entities`` organiza escalares por
    escopo e ID; nomes e tipos são normalizados pela camada de persistência.
    Core exige resumo/viagens/estatísticas/filas e mantém entidades vazias.
    Full conserva detalhes e fontes para reanálise. Timers de coleta retornam
    com os resultados para o runner registrar o custo separado das medições.
    """
    if profile not in {"core", "full"}:
        raise ValueError("O perfil de métricas deve ser core ou full.")
    raw_dir, net_file = Path(raw_dir), Path(net_file)
    started = time.perf_counter()
    metrics = _summary(raw_dir / "summary.xml.gz")
    metrics["collection_summary_time_seconds"] = time.perf_counter() - started
    metrics["metrics_profile"] = profile
    entities = {scope: {} for scope in ("vehicles", "lanes", "edges", "traffic_lights", "approaches", "intersections")}
    lanes, groups, membership = set(), {}, {}
    if profile == "full":
        started = time.perf_counter()
        lanes, edges, _, groups, membership = _network(net_file)
        metrics["collection_network_time_seconds"] = time.perf_counter() - started
    parsers = [
        ("trips", _trips, (raw_dir / "trips.xml.gz", metrics, entities["vehicles"] if profile == "full" else None)),
        ("statistics", _statistics, (raw_dir / "statistics.xml", metrics)),
        ("queues", _queues, (raw_dir / "queues.xml.gz", lanes, groups, membership, entities if profile == "full" else None, metrics)),
    ]
    if profile == "full":
        parsers.extend([
            ("tls", _tls, (raw_dir / "tls.xml.gz", metrics["simulation_begin_seconds"], metrics["simulation_end_seconds"], entities["traffic_lights"])),
            ("lanechanges", _events, (raw_dir / "lanechanges.xml.gz", "change", "lane_change", entities, metrics)),
            ("collisions", _events, (raw_dir / "collisions.xml.gz", "collision", "collision", entities, metrics)),
            ("lanes", _traffic, (raw_dir / "lanes.xml.gz", "lane", lanes, entities["lanes"], metrics)),
            ("edges", _traffic, (raw_dir / "edges.xml.gz", "edge", edges, entities["edges"], metrics)),
            ("fcd", _trajectories, (raw_dir / "fcd.xml.gz", lanes, membership, groups, entities, metrics)),
            ("emissions", _emissions, (raw_dir / "emissions.xml.gz", entities["vehicles"], metrics)),
        ])
    for source, parser, arguments in parsers:
        started = time.perf_counter()
        parser(*arguments)
        metrics[f"collection_{source}_time_seconds"] = time.perf_counter() - started
    if profile == "core":
        metrics = {name: value for name, value in metrics.items()
                   if name in CORE_METRICS or name.startswith(("sumo_teleports_", "sumo_safety_", "collection_"))}
    # A associação faixa→via já pertence à rede utilizada; não duplicá-la
    # em cada episódio. Métricas continuam identificadas pelo ID original.
    return {"metrics": metrics, "entities": entities}
