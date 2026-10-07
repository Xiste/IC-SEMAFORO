"""Valida um plano SETTRAN fixo e emite apenas seus programas SUMO.

Os campos da planilha permanecem separados dos suplementos operacionais.
Agenda e relógio diário não participam de um teste explicitamente selecionado.
"""

from copy import deepcopy
from datetime import date
from hashlib import sha256
from itertools import combinations
import math
from pathlib import Path
import xml.etree.ElementTree as ET


EVIDENCE_FIELDS = ("control_scope", "movement_mapping", "permissions", "sequence", "transitions",
                   "offset_reference")
TRANSITIONS = {"green": "green_seconds", "yellow": "yellow_seconds",
               "clearance_red": "clearance_red_seconds"}
ACCEPTED_EVIDENCE = {"CONFIRMADO", "INFERIVEL_COM_SEGURANCA"}


def _number(value, name, *, positive=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or (positive and value <= 0)):
        raise ValueError(f"{name}: número finito{' positivo' if positive else ''} obrigatório.")
    return float(value)


def _reference(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name}: source_reference ausente.")


def _topology(path):
    root = ET.parse(path).getroot()
    edges = {edge.get("id"): edge for edge in root.findall("edge")}
    nodes = {node.get("id"): node for node in root.findall("junction")}
    programs = {logic.get("id"): logic for logic in root.findall("tlLogic")}
    connections = root.findall("connection")
    links, vehicles = {}, {}
    for connection in connections:
        tls = connection.get("tl")
        if tls is None:
            continue
        index = int(connection.get("linkIndex"))
        links.setdefault(tls, {}).setdefault(index, []).append(connection)
        incoming = edges[connection.get("from")]
        lane = incoming.find(f"lane[@index='{connection.get('fromLane')}']")
        pedestrian = (incoming.get("function") in {"crossing", "walkingarea"}
                      or (lane is not None and lane.get("allow") == "pedestrian"))
        if pedestrian:
            continue
        node = nodes.get(incoming.get("to"))
        via = connection.get("via")
        final_lanes = node.get("intLanes", "").split() if node is not None else []
        # Em conversões longas, request refere-se à última parte interna.
        for _ in range(20):
            if via in final_lanes or not via:
                break
            internal, lane_index = via.rsplit("_", 1)
            following = [c for c in connections if c.get("from") == internal
                         and c.get("fromLane") == lane_index and c.get("to") == connection.get("to")
                         and c.get("toLane") == connection.get("toLane")]
            if len(following) != 1:
                break
            via = following[0].get("via")
        if node is None or via not in final_lanes:
            raise ValueError(f"TLS {tls}/signalIndex {index}: request veicular não identificado.")
        request_index = final_lanes.index(via)
        request = node.find(f"request[@index='{request_index}']")
        if request is None:
            raise ValueError(f"TLS {tls}/signalIndex {index}: request veicular ausente.")
        vehicles.setdefault(tls, {}).setdefault(index, []).append(
            (node.get("id"), request_index, request))
    for tls, indices in links.items():
        if tls not in programs or set(indices) != set(range(max(indices) + 1)):
            raise ValueError(f"TLS {tls}: programa ou controlledLinks incompletos.")
    return links, vehicles, programs


def _validate_green_conflicts(states, vehicles, previous_states):
    active = []
    for tls, state in states.items():
        for index, records in vehicles.get(tls, {}).items():
            if state[index] not in "Ggy":
                continue
            for node, request_index, request in records:
                if state[index] == "g" and "1" not in request.get("response", ""):
                    raise ValueError(f"TLS {tls}/signalIndex {index}: g sem prioridade de cessão.")
                active.append((tls, index, state[index], node, request_index, request))
    for first, second in combinations(active, 2):
        if first[3] != second[3]:
            continue
        a, b = first[4], second[4]
        if first[5].get("foes", "")[-1-b] != "1":
            continue
        if first[2] == second[2] == "y":
            continue
        labels = f"{first[0]}:{first[1]} e {second[0]}:{second[1]}"
        if "y" in (first[2], second[2]):
            green, amber = (second, first) if first[2] == "y" else (first, second)
            prior_green, prior_amber = previous_states.get(green[0], ""), previous_states.get(amber[0], "")
            if (len(prior_green) <= green[1] or prior_green[green[1]] not in "Gg"
                    or len(prior_amber) <= amber[1] or prior_amber[amber[1]] not in "Ggy"):
                raise ValueError(f"Verde novo conflitante com amarelo, sem limpeza: {labels}.")
        if first[2] == second[2] == "G":
            raise ValueError(f"Verdes protegidos conflitantes: {labels}.")
        first_yields = first[5].get("response", "")[-1-b] == "1"
        second_yields = second[5].get("response", "")[-1-a] == "1"
        if (first_yields == second_yields
                or (first[2] == "G" and first_yields)
                or (second[2] == "G" and second_yields)):
            raise ValueError(f"Permissão simultânea incompatível com prioridade SUMO: {labels}.")


def _validate_program(program, topology, network_hash):
    links, vehicles, existing = topology
    geographic_tls = program.get("sumo_tls_ids")
    if (not isinstance(geographic_tls, list) or not geographic_tls
            or len(set(geographic_tls)) != len(geographic_tls)):
        raise ValueError("associação interseção→TLS completa ausente.")
    if any(tls not in links for tls in geographic_tls):
        raise ValueError(f"TLS desconhecido: {','.join(t for t in geographic_tls if t not in links)}.")
    operational = program.get("operational")
    if operational is None:
        missing = [f"TLS {tls}: falta quadro veicular de intervalos (permissões, sequência, "
                   "amarelo/limpeza), escopo operacional e referência da defasagem" for tls in geographic_tls]
        missing.extend(f"Grupo {stage['stage_id']}: {stage.get('mapping_note', 'movimentos não demonstrados')}"
                       for stage in program.get("stages", [])
                       if stage.get("scope") == "vehicle"
                       and stage.get("mapping_status") == "DADO_EXTERNO_AUSENTE")
        raise ValueError("DADO_EXTERNO_AUSENTE: " + "; ".join(missing) + ".")
    if not isinstance(operational, dict):
        raise ValueError("operational deve ser objeto ou null.")
    tls_ids, current_tls_ids = operational.get("tls_ids"), operational.get("current_tls_ids")
    for name, values in (("tls_ids", tls_ids), ("current_tls_ids", current_tls_ids)):
        if (not isinstance(values, list) or any(not isinstance(value, str) for value in values)
                or len(set(values)) != len(values)):
            raise ValueError(f"operational.{name}: lista explícita de TLS distintos obrigatória.")
    if (not tls_ids or set(tls_ids) & set(current_tls_ids)
            or set(tls_ids) | set(current_tls_ids) != set(geographic_tls)):
        raise ValueError("operational.tls_ids/current_tls_ids: partição explícita, disjunta e completa "
                         "dos TLS geográficos obrigatória, com ao menos um TLS aplicado.")
    if operational.get("network_sha256") != network_hash:
        raise ValueError("network_sha256: vínculos operacionais pertencem a outra rede.")
    evidence = operational.get("evidence", {})
    if not isinstance(evidence, dict):
        raise ValueError("evidence: requisitos operacionais ausentes.")
    for field in EVIDENCE_FIELDS:
        item = evidence.get(field, {})
        if not isinstance(item, dict) or item.get("status") not in ACCEPTED_EVIDENCE:
            raise ValueError(f"DADO_EXTERNO_AUSENTE: evidence.{field}.")
        _reference(item.get("source_reference"), f"evidence.{field}")

    stages = {stage["stage_id"]: stage for stage in program["stages"]}
    if len(stages) != len(program["stages"]):
        raise ValueError("stage_id duplicado.")
    stage_links = operational.get("stage_links")
    if not isinstance(stage_links, dict) or set(stage_links) - set(stages):
        raise ValueError("stage_links: mapa estágio→controlledLinks ausente ou desconhecido.")
    mapped = {stage_id: set() for stage_id in stages}
    for stage_id, stage in stages.items():
        bindings = stage_links.get(stage_id)
        if stage.get("scope") == "pedestrian":
            continue
        if stage.get("scope") != "vehicle" or not isinstance(bindings, list) or not bindings:
            raise ValueError(f"DADO_EXTERNO_AUSENTE: stage_links[{stage_id}] veicular.")
        for binding in bindings:
            if not isinstance(binding, dict):
                raise ValueError(f"stage_links[{stage_id}]: vínculo deve ser objeto.")
            tls, indices = binding.get("tls_id"), binding.get("link_indices")
            if (tls not in tls_ids or not isinstance(indices, list) or not indices
                    or any(isinstance(i, bool) or not isinstance(i, int) for i in indices)):
                raise ValueError(f"stage_links[{stage_id}]: TLS/indices inválidos.")
            for index in indices:
                key = (tls, index)
                if index not in vehicles.get(tls, {}) or key in mapped[stage_id]:
                    raise ValueError(f"stage_links[{stage_id}]: link veicular {tls}:{index} inválido/duplicado.")
                mapped[stage_id].add(key)
    all_mapped = set().union(*mapped.values())
    all_vehicle = {(tls, index) for tls in tls_ids for index in vehicles.get(tls, {})}
    if all_mapped != all_vehicle:
        raise ValueError(f"controlledLinks veiculares sem grupo: {sorted(all_vehicle - all_mapped)}.")

    phases = operational.get("phases")
    if not isinstance(phases, list) or not phases:
        raise ValueError("DADO_EXTERNO_AUSENTE: phases/estados e duração das transições.")
    totals = {(stage, transition): 0.0 for stage in stages for transition in TRANSITIONS}
    for phase_index, phase in enumerate(phases):
        if not isinstance(phase, dict):
            raise ValueError("phase: objeto obrigatório.")
        stage_id, transition = phase.get("stage_id"), phase.get("transition")
        if stage_id not in stages or transition not in TRANSITIONS:
            raise ValueError("phase: stage_id/transition desconhecido.")
        duration = _number(phase.get("duration_seconds"), "phase.duration_seconds", positive=True)
        _reference(phase.get("source_reference"), "phase")
        totals[stage_id, transition] += duration
        states = phase.get("states")
        if not isinstance(states, dict) or set(states) != set(tls_ids):
            raise ValueError("phase.states: todos e somente os TLS da interseção são obrigatórios.")
        for tls, state in states.items():
            if (not isinstance(state, str) or len(state) != len(links[tls])
                    or set(state) - set("rGgy")):
                raise ValueError(f"TLS {tls}: vetor state/dimensão inválido; apenas r/G/g/y.")
            for index in links[tls]:
                if index not in vehicles.get(tls, {}) and state[index] != "r":
                    raise ValueError(f"TLS {tls}:{index}: atendimento pedestre fora do escopo.")
            if transition == "green" and stages[stage_id].get("scope") == "vehicle":
                actual = {(tls, index) for index in vehicles.get(tls, {}) if state[index] in "Gg"}
                expected = {key for key in mapped[stage_id] if key[0] == tls}
                if actual != expected:
                    raise ValueError(f"TLS {tls}: estado green difere do grupo {stage_id}.")
            elif stages[stage_id].get("scope") == "vehicle":
                for index in vehicles.get(tls, {}):
                    key = (tls, index)
                    if key not in mapped[stage_id] and state[index] != "r":
                        raise ValueError(f"TLS {tls}:{index}: movimento fora do grupo {stage_id} na transição.")
                    if key in mapped[stage_id] and state[index] not in (
                            "yGg" if transition == "yellow" else "rGg"):
                        raise ValueError(f"TLS {tls}:{index}: estado incompatível com {transition}.")
        _validate_green_conflicts(states, vehicles, phases[phase_index-1].get("states", {}))
    for (stage, transition), total in totals.items():
        expected = _number(stages[stage].get(TRANSITIONS[transition]), f"{stage}.{transition}")
        if expected < 0 or not math.isclose(total, expected, rel_tol=0, abs_tol=1e-8):
            raise ValueError(f"{stage}.{transition}: duração {total:g} difere da fonte ({expected:g}).")
    cycle = _number(program.get("cycle_seconds"), "cycle_seconds", positive=True)
    if not math.isclose(sum(p["duration_seconds"] for p in phases), cycle, rel_tol=0, abs_tol=1e-8):
        raise ValueError("phase.duration_seconds: soma não fecha cycle_seconds.")
    served = {(tls, index) for phase in phases for tls in tls_ids for index in vehicles.get(tls, {})
              if phase["states"][tls][index] in "Gg"}
    if served != all_vehicle:
        raise ValueError(f"controlledLinks veiculares sem atendimento: {sorted(all_vehicle - served)}; "
                         "restrição operacional permanente exige documentação explícita.")
    # Validar blocos cíclicos não escolhe a ordem A/B/C nem muda a phase zero.
    starts = [i for i, phase in enumerate(phases)
              if phase["stage_id"] != phases[i-1]["stage_id"]]
    if not starts:
        starts = [i for i, phase in enumerate(phases) if phase["transition"] == "green"
                  and phases[i-1]["transition"] != "green"] or [0]
    start = starts[0]
    seen, previous_stage, rank = set(), None, -1
    for phase in phases[start:] + phases[:start]:
        stage = phase["stage_id"]
        if stage != previous_stage:
            if stage in seen:
                raise ValueError(f"Grupo {stage}: blocos operacionais não contíguos.")
            seen.add(stage)
            previous_stage, rank = stage, -1
        current_rank = list(TRANSITIONS).index(phase["transition"])
        if current_rank < rank:
            raise ValueError(f"Grupo {stage}: transições fora da ordem verde/amarelo/limpeza.")
        rank = current_rank
    for current, following in zip(phases, phases[1:] + phases[:1]):
        for tls in tls_ids:
            for index in vehicles.get(tls, {}):
                before, after = current["states"][tls][index], following["states"][tls][index]
                if before in "Gg" and after == "r":
                    raise ValueError(f"TLS {tls}:{index}: verde→vermelho sem amarelo.")
                if before == "y" and after in "Gg":
                    raise ValueError(f"TLS {tls}:{index}: amarelo→verde sem intervalo de limpeza.")
                if (following["transition"] != "green" and after in "Gg"
                        and before not in "Gg"):
                    raise ValueError(f"TLS {tls}:{index}: continuidade de verde sem origem comprovada.")

    reference = operational.get("offset_reference")
    if isinstance(reference, dict) and "by_tls" in reference:
        references = reference["by_tls"]
        if (set(reference) != {"by_tls"} or not isinstance(references, dict)
                or set(references) != set(tls_ids)):
            raise ValueError("offset_reference.by_tls: referência exata para cada TLS aplicado obrigatória.")
    else:
        references = {tls: reference for tls in tls_ids}
    offsets = {}
    for tls, item in references.items():
        try:
            offsets[tls] = _offset(program, item, phases, cycle, existing)
        except ValueError as error:
            raise ValueError(f"TLS {tls}: {error}") from error
    if any(logic.get("programID") == f"settran_{program['plan_id']}"
           for tls in tls_ids for logic in [existing[tls]]):
        raise ValueError("programID settran já existe na rede-base.")
    return offsets


def _offset(program, reference, phases, cycle, existing):
    if not isinstance(reference, dict):
        raise ValueError("DADO_EXTERNO_AUSENTE: offset_reference.")
    if reference.get("reference_type") not in {"clock", "tls_event"}:
        raise ValueError("offset_reference.reference_type: clock/tls_event obrigatório.")
    _reference(reference.get("reference_id"), "offset_reference.reference_id")
    if reference["reference_type"] == "tls_event" and reference["reference_id"] not in existing:
        raise ValueError("offset_reference.reference_id: TLS de referência desconhecido.")
    if reference["reference_type"] == "tls_event":
        event = reference.get("reference_event")
        if not ((isinstance(event, str) and event.strip())
                or (isinstance(event, int) and not isinstance(event, bool) and event >= 0)):
            raise ValueError("offset_reference.reference_event: evento do TLS de referência obrigatório.")
    _reference(reference.get("source_reference"), "offset_reference")
    instant = _number(reference.get("reference_time_seconds"), "offset_reference.reference_time_seconds")
    direction, target = reference.get("direction"), reference.get("target_phase_index")
    if (direction not in {"delay", "advance"} or isinstance(target, bool)
            or not isinstance(target, int) or not 0 <= target < len(phases)):
        raise ValueError("offset_reference: direction/target_phase_index inválidos.")
    raw = _number(program.get("offset_seconds"), "offset_seconds")
    q = sum(phase["duration_seconds"] for phase in phases[:target])
    return (instant + (raw if direction == "delay" else -raw) - q) % cycle


def prepare_selection(document, plan_id, net_file, intersections=None):
    """Recusa requisitos locais ausentes antes de seed, arquivos ou simulação."""
    if not isinstance(document, dict) or document.get("schema_version") != 2:
        raise ValueError("Contrato SETTRAN schema_version=2 obrigatório.")
    programs = document.get("programs")
    if (not isinstance(programs, list) or not programs
            or any(not isinstance(p, dict) or not isinstance(p.get("plan_id"), str)
                   or not isinstance(p.get("intersection"), str) for p in programs)):
        raise ValueError("programs SETTRAN ausentes.")
    available = list(dict.fromkeys(p["plan_id"] for p in programs))
    if not isinstance(plan_id, str) or plan_id not in available:
        raise ValueError(f"Plano SETTRAN {plan_id!r} inexistente. Planos disponíveis na fonte: {'/'.join(available)}.")
    selected = [program for program in programs if program["plan_id"] == plan_id]
    if intersections is not None:
        if (isinstance(intersections, str) or not isinstance(intersections, (list, tuple))
                or not intersections or any(not isinstance(i, str) or not i for i in intersections)
                or len(set(intersections)) != len(intersections)):
            raise ValueError("Seleção parcial exige lista explícita de interseções distintas.")
        unknown = set(intersections) - {p["intersection"] for p in selected}
        if unknown:
            raise ValueError(f"Interseções SETTRAN desconhecidas no plano {plan_id}: {sorted(unknown)}.")
        selected = [p for p in selected if p["intersection"] in intersections]
    if len({p["intersection"] for p in selected}) != len(selected):
        raise ValueError("Definição duplicada para interseção/plano SETTRAN.")
    net_file = Path(net_file)
    network_hash = sha256(net_file.read_bytes()).hexdigest()
    topology = _topology(net_file)
    offsets, errors, selected_tls = {}, [], set()
    for program in selected:
        label = f"Plano {plan_id}; {program['intersection']}; TLS {','.join(program.get('sumo_tls_ids') or [])}"
        try:
            result = _validate_program(program, topology, network_hash)
            if selected_tls & result.keys():
                raise ValueError("TLS compartilhado por definições selecionadas incompatíveis.")
            selected_tls.update(result)
            offsets.update(result)
        except (ValueError, KeyError, TypeError, IndexError) as error:
            errors.append(f"{label}: {error}")
    if errors:
        raise ValueError("SETTRAN recusado antes da simulação. " + " | ".join(errors)
                         + " Agenda ausente não impede plano fixo. Consulte docs/guias/GUIA_DE_FUNCIONAMENTO.md.")
    return {"plan_id": plan_id, "intersections": [p["intersection"] for p in selected],
            "tls_ids": sorted(selected_tls), "current_tls_ids": sorted(set(topology[0]) - selected_tls),
            "programs": deepcopy(selected), "offsets": offsets,
            "network_sha256": network_hash, "document_snapshot": deepcopy(document)}


def compile_selection(selection, destination):
    """Emite programas fixos já validados, sem modificar rede ou observações."""
    root = ET.Element("additional", {
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:noNamespaceSchemaLocation": "http://sumo.dlr.de/xsd/additional_file.xsd",
    })
    for program in selection["programs"]:
        for tls in program["operational"]["tls_ids"]:
            logic = ET.SubElement(root, "tlLogic", {
                "id": tls, "type": "static", "programID": f"settran_{selection['plan_id']}",
                "offset": f"{selection['offsets'][tls]:.12g}",
            })
            for phase in program["operational"]["phases"]:
                ET.SubElement(logic, "phase", {
                    "duration": f"{phase['duration_seconds']:.12g}",
                    "state": phase["states"][tls],
                    "name": f"SETTRAN {phase['stage_id']} {phase['transition']}",
                })
    ET.indent(root)
    destination = Path(destination)
    ET.ElementTree(root).write(destination, encoding="utf-8", xml_declaration=True)
    return destination


def _date(value, field):
    try:
        result = date.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field}: data ISO YYYY-MM-DD obrigatória.") from error
    if result.isoformat() != value:
        raise ValueError(f"{field}: data ISO YYYY-MM-DD obrigatória.")
    return result


def _time(value, field):
    try:
        hour, minute, second = map(int, value.split(":"))
        if (f"{hour:02d}:{minute:02d}:{second:02d}" != value
                or not 0 <= hour <= 24 or not 0 <= minute < 60 or not 0 <= second < 60
                or (hour == 24 and (minute or second))):
            raise ValueError
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError(f"{field}: horário HH:MM:SS entre 00:00:00 e 24:00:00 obrigatório.") from error
    return hour * 3600 + minute * 60 + second


def validate_schedule(document):
    """Confere agenda declarativa; não escolhe plano, relógio ou modo temporal.

    Validade usa datas inclusivas; faixas usam [início, fim). Exceção com plano
    substitui/ativa a faixa naquela data; null cancela a ocorrência daquela data.
    """
    if not isinstance(document, dict):
        raise ValueError("Contrato SETTRAN deve ser objeto.")
    schedule = document.get("schedule")
    if schedule is None:
        return "DADO_EXTERNO_AUSENTE"
    if not isinstance(schedule, list):
        raise ValueError("schedule: lista declarativa ou null obrigatório.")
    if not schedule:
        return "CONFIRMADO_SEM_ATIVACOES"
    plans = {}
    for program in document.get("programs", []):
        plans.setdefault(program["intersection"], set()).add(program["plan_id"])
    rows = []
    for index, row in enumerate(schedule):
        label = f"schedule[{index}]"
        if (not isinstance(row, dict) or not isinstance(row.get("intersection"), str)
                or row["intersection"] not in plans):
            raise ValueError(f"{label}.intersection: interseção SETTRAN desconhecida.")
        intersection = row["intersection"]
        if not isinstance(row.get("plan_id"), str) or row["plan_id"] not in plans[intersection]:
            raise ValueError(f"{label}.plan_id: plano inexistente para a interseção.")
        _reference(row.get("source_reference"), label)
        start, end = _time(row.get("start_time"), label + ".start_time"), _time(row.get("end_time"), label + ".end_time")
        if start >= end:
            raise ValueError(f"{label}: início deve anteceder fim; dividir faixas que cruzam meia-noite.")
        weekdays = row.get("weekdays")
        if (not isinstance(weekdays, list) or not weekdays
                or any(isinstance(day, bool) or not isinstance(day, int) or not 1 <= day <= 7 for day in weekdays)
                or len(set(weekdays)) != len(weekdays)):
            raise ValueError(f"{label}.weekdays: lista de dias ISO distintos entre 1 e 7 obrigatória.")
        first, last = _date(row.get("valid_from"), label + ".valid_from"), _date(row.get("valid_until"), label + ".valid_until")
        if first > last:
            raise ValueError(f"{label}: validade invertida.")
        exceptions = row.get("exceptions")
        if not isinstance(exceptions, list):
            raise ValueError(f"{label}.exceptions: lista explícita obrigatória, inclusive vazia.")
        overrides = {}
        for exception in exceptions:
            if not isinstance(exception, dict) or "plan_id" not in exception:
                raise ValueError(f"{label}.exceptions: date e plan_id/null obrigatórios.")
            day = _date(exception.get("date"), label + ".exceptions.date")
            plan = exception["plan_id"]
            if not first <= day <= last or day in overrides:
                raise ValueError(f"{label}.exceptions: data fora da validade ou duplicada.")
            if plan is not None and (not isinstance(plan, str) or plan not in plans[intersection]):
                raise ValueError(f"{label}.exceptions: plano inexistente para a interseção.")
            overrides[day] = plan
        rows.append({"index": index, "intersection": intersection, "start": start, "end": end,
                     "weekdays": set(weekdays), "first": first, "last": last, "exceptions": overrides})

    def active(row, day):
        return (row["exceptions"][day] is not None if day in row["exceptions"]
                else day.isoweekday() in row["weekdays"])

    for first, second in combinations(rows, 2):
        if (first["intersection"] != second["intersection"]
                or max(first["start"], second["start"]) >= min(first["end"], second["end"])):
            continue
        lower, upper = max(first["first"], second["first"]), min(first["last"], second["last"])
        if lower > upper:
            continue
        candidates = set(first["exceptions"]) | set(second["exceptions"])
        for weekday in first["weekdays"] & second["weekdays"]:
            ordinal = lower.toordinal() + (weekday - lower.isoweekday()) % 7
            while ordinal <= upper.toordinal():
                day = date.fromordinal(ordinal)
                if active(first, day) and active(second, day):
                    candidates.add(day)
                    break
                ordinal += 7
        if any(lower <= day <= upper and active(first, day) and active(second, day) for day in candidates):
            raise ValueError(f"schedule[{first['index']}] e schedule[{second['index']}]: "
                             f"faixas sobrepostas para {first['intersection']} em dias/validade comuns.")
    return "CONFIRMADO"
