"""Consolida XMLs nativos do SUMO sem gravar arquivos.

Entrada: diretório de saídas e rede; saída: métricas globais e por entidade.
O runner normalmente chama ``collect_episode`` depois que o SUMO encerra.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache
import gzip
import math
from pathlib import Path
import re
import time
import xml.etree.ElementTree as ET


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


def _trips(path, metrics, vehicles):
    """Agrega viagens por situação, sem misturar finais e viagens truncadas."""
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
        record = vehicles.setdefault(attributes["id"], {})
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
    """Filas em metros e espera por faixa; soma das faixas por aproximação/TLS."""
    observations = defaultdict(lambda: defaultdict(RunningStats))
    group_stats = defaultdict(lambda: defaultdict(RunningStats))
    count = 0
    attributes = {"queueing_time", "queueing_length", "queueing_length_experimental"}
    for timestep in _elements(path, "data"):
        count += 1
        totals = defaultdict(Counter)
        for lane in timestep.iter("lane"):
            identifier = lane.attrib["id"]
            for attribute in attributes:
                value = _number(lane.attrib.get(attribute, "0"))
                if value is None or value < 0:
                    continue
                observations[identifier][attribute].add(value)
                for group in membership[identifier]:
                    totals[group][attribute] += value
        for group, values in totals.items():
            for attribute, value in values.items():
                group_stats[group][attribute].add(value)
    metrics["queue_observation_steps"] = count
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
    Os XMLs brutos continuam sendo a fonte para reanálises detalhadas. Core
    exige viagens/eventos/filas/TLS; full também exige tráfego/FCD/emissões.
    """
    if profile not in {"core", "full"}:
        raise ValueError("O perfil de métricas deve ser core ou full.")
    raw_dir, net_file = Path(raw_dir), Path(net_file)
    started = time.perf_counter()
    metrics = _summary(raw_dir / "summary.xml.gz")
    metrics["collection_summary_time_seconds"] = time.perf_counter() - started
    metrics["metrics_profile"] = profile
    entities = {scope: {} for scope in ("vehicles", "lanes", "edges", "traffic_lights", "approaches", "intersections")}
    started = time.perf_counter()
    lanes, edges, lane_edge, groups, membership = _network(net_file)
    metrics["collection_network_time_seconds"] = time.perf_counter() - started
    parsers = [
        ("trips", _trips, (raw_dir / "trips.xml.gz", metrics, entities["vehicles"])),
        ("statistics", _statistics, (raw_dir / "statistics.xml", metrics)),
        ("tls", _tls, (raw_dir / "tls.xml.gz", metrics["simulation_begin_seconds"], metrics["simulation_end_seconds"], entities["traffic_lights"])),
        ("queues", _queues, (raw_dir / "queues.xml.gz", lanes, groups, membership, entities, metrics)),
        ("lanechanges", _events, (raw_dir / "lanechanges.xml.gz", "change", "lane_change", entities, metrics)),
        ("collisions", _events, (raw_dir / "collisions.xml.gz", "collision", "collision", entities, metrics)),
    ]
    if profile == "full":
        parsers.extend([
            ("lanes", _traffic, (raw_dir / "lanes.xml.gz", "lane", lanes, entities["lanes"], metrics)),
            ("edges", _traffic, (raw_dir / "edges.xml.gz", "edge", edges, entities["edges"], metrics)),
            ("fcd", _trajectories, (raw_dir / "fcd.xml.gz", lanes, membership, groups, entities, metrics)),
            ("emissions", _emissions, (raw_dir / "emissions.xml.gz", entities["vehicles"], metrics)),
        ])
    for source, parser, arguments in parsers:
        started = time.perf_counter()
        parser(*arguments)
        metrics[f"collection_{source}_time_seconds"] = time.perf_counter() - started
    # A associação faixa→via já pertence à rede do baseline; não duplicá-la
    # em cada episódio. Métricas continuam identificadas pelo ID original.
    return {"metrics": metrics, "entities": entities}
