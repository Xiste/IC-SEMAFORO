"""Cenário sintético conservador: um índice de sinal aberto por controlador."""

import copy
import hashlib
import json
import math
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from semaforos.caminhos import PROJECT_ROOT


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_experimental(config):
    metadata = config.get("experimental", {})
    from semaforos.cenario.configuracao import control_parameters
    if control_parameters(config).get("action_mode") != "phase_durations":
        raise ValueError("O cenário conjunto experimental requer controle de duração das fases")
    if metadata.get("method") != "serial_links_v1" or digest(config["network"]) != metadata.get("network_sha256"):
        raise ValueError("Rede experimental ausente ou modificada; prepare novamente pela interface")
    root = ET.parse(config["network"]).getroot()
    targets = config["targets"]
    ids = [item["tls_id"] for item in targets]
    if len(ids) != 17 or len(set(ids)) != 17 or len({item["name"] for item in targets}) != 9:
        raise ValueError("O cenário experimental deve controlar os 17 controladores dos nove cruzamentos")
    edge_nodes = {edge.get("id"): edge.get("to") for edge in root.findall("edge") if edge.get("to")}
    owners = {}
    rows = []
    minimums = metadata.get("minimum_durations", {})
    for target in targets:
        tls = target["tls_id"]
        connections = [c for c in root.findall("connection") if c.get("tl") == tls]
        indices = sorted({int(c.get("linkIndex")) for c in connections})
        edge_functions = {edge.get("id"): edge.get("function") for edge in root.findall("edge")}
        for index in indices:
            local = [c for c in connections if int(c.get("linkIndex")) == index]
            if len(local) > 1:
                crossings = {c.get("from") for c in local if edge_functions.get(c.get("from")) == "crossing"}
                crossings.update(c.get("to") for c in local if edge_functions.get(c.get("to")) == "crossing")
                if len(crossings) != 1 or any(edge_functions.get(c.get("from")) not in ("crossing", "walkingarea") for c in local):
                    raise ValueError(f"Índice {tls}:{index} compartilha movimentos independentes")
        logics = [logic for logic in root.findall("tlLogic") if logic.get("id") == tls]
        if not indices or len(logics) != 1 or indices != list(range(max(indices) + 1)):
            raise ValueError(f"Links ou programa incompletos em {tls}")
        # Não permitir controladores independentes no mesmo nó de conflito.
        for c in connections:
            node = edge_nodes.get(c.get("from"))
            if node:
                if node in owners and owners[node] != tls:
                    raise ValueError(f"Controladores {tls} e {owners[node]} compartilham o nó {node}")
                owners[node] = tls
        phases = logics[0].findall("phase")
        if len(phases) != 3 * len(indices) or target["phase_indices"] != list(range(0, len(phases), 3)):
            raise ValueError(f"Sequência experimental inválida em {tls}")
        for index in indices:
            for position, color, minimum in ((0, "G", 8), (1, "y", 3), (2, "r", 3)):
                phase = phases[3 * index + position]
                expected = "r" * len(indices)
                if color != "r":
                    expected = expected[:index] + color + expected[index + 1:]
                if phase.get("state") != expected or float(phase.get("duration")) < minimum:
                    raise ValueError(f"Atendimento ou intervalo inválido em {tls}:{index}")
                if float(phase.get("duration")) != minimums.get(f"{tls}:{3 * index + position}"):
                    raise ValueError(f"Tempos de referência modificados em {tls}:{index}")
        rows.append({"cruzamento": target["name"], "controlador": tls,
                     "movimentos_atendidos": len(indices), "fases": len(phases),
                     "ciclo_inicial_s": sum(float(p.get("duration")) for p in phases)})
    return rows


def prepare_experimental(config, output):
    """Cria arquivos novos; não altera a rede original nem o cadastro real."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    source = PROJECT_ROOT / "dados/rede/uberlandia.rondon_norte_corrigida.net.xml"
    mapping_path = PROJECT_ROOT / "config/mapeamento_associado.json"
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    binary = shutil.which("netconvert")
    if not binary:
        raise ValueError("netconvert não encontrado no PATH")
    network = output / "nove_experimental.net.xml"
    command = [binary, "-s", str(source), "-o", str(network), "--tls.rebuild",
               "--tls.ungroup-signals", "--tls.yellow.time", "3", "--tls.allred.time", "3"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=120,
                            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    (output / "netconvert.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        raise ValueError("Falha ao reconstruir os sinais; consulte netconvert.log")
    root = ET.parse(network).getroot()
    original = ET.parse(source).getroot()
    selected_ids = {controller["tls_id"] for entry in mapping["intersections"] for controller in entry["controllers"]}
    def connection_key(c):
        return tuple(c.get(key) for key in ("tl", "from", "to", "fromLane", "toLane"))
    original_links = {connection_key(c): int(c.get("linkIndex")) for c in original.findall("connection") if c.get("tl")}
    # Transportar estados pela conexão preserva o atendimento dos demais sinais
    # mesmo quando netconvert renumera os seus índices.
    for logic in list(root.findall("tlLogic")):
        tls = logic.get("id")
        if tls in selected_ids:
            continue
        root.remove(logic)
        connections = [c for c in root.findall("connection") if c.get("tl") == tls]
        for old_logic in original.findall("tlLogic"):
            if old_logic.get("id") != tls:
                continue
            restored = copy.deepcopy(old_logic)
            for phase in restored.findall("phase"):
                states = [None] * (max(int(c.get("linkIndex")) for c in connections) + 1)
                for c in connections:
                    old_index = original_links.get(connection_key(c))
                    if old_index is None:
                        raise ValueError(f"Conexão externa ao controle mudou em {tls}; preparação interrompida")
                    new_index = int(c.get("linkIndex"))
                    color = phase.get("state")[old_index]
                    if states[new_index] not in (None, color):
                        raise ValueError(f"Renumerar {tls} alteraria estados existentes")
                    states[new_index] = color
                phase.set("state", "".join(color or "r" for color in states))
            root.append(restored)
    targets = []
    lanes = {lane.get("id"): lane for edge in root.findall("edge") for lane in edge.findall("lane")}
    edges = {edge.get("id"): edge for edge in root.findall("edge")}
    minimums = {}
    green_floors = {}
    for entry in mapping["intersections"]:
        for controller in entry["controllers"]:
            tls = controller["tls_id"]
            connections = [c for c in root.findall("connection") if c.get("tl") == tls]
            indices = sorted({int(c.get("linkIndex")) for c in connections})
            if not indices:
                raise ValueError(f"Controlador sem conexões: {tls}")
            logics = [logic for logic in root.findall("tlLogic") if logic.get("id") == tls]
            for logic in logics:
                root.remove(logic)
            logic = ET.SubElement(root, "tlLogic", id=tls, type="static", programID="experimental", offset="0")
            for index in indices:
                local = [c for c in connections if int(c.get("linkIndex")) == index]
                pedestrian = [c for c in local if edges[c.get("from")].get("function") in ("crossing", "walkingarea")]
                # Tempo geométrico conservador de travessia (0,8 m/s), não tempo real medido.
                crossing_seconds = max([math.ceil(float(lanes[f"{c.get('from')}_{c.get('fromLane')}"] .get("length")) / 0.8) + 2 for c in pedestrian] or [8])
                clearance = max([math.ceil(float(lanes[c.get("via")].get("length")) / max(1.0, float(lanes[c.get("via")].get("speed")))) + 2 for c in local if c.get("via") in lanes] or [3])
                if pedestrian:
                    clearance = max(clearance, crossing_seconds)
                green = max(30, crossing_seconds) if pedestrian else 30
                green_floors[f"{tls}:{3 * index}"] = max(8, crossing_seconds) if pedestrian else 8
                for position, (color, duration) in enumerate((("G", green), ("y", 3), ("r", max(3, clearance)))):
                    state = "r" * (max(indices) + 1)
                    if color != "r":
                        state = state[:index] + color + state[index + 1:]
                    ET.SubElement(logic, "phase", duration=str(duration), state=state)
                    minimums[f"{tls}:{3 * index + position}"] = duration
            targets.append({"name": entry["name"], "tls_id": tls,
                            "phase_indices": list(range(0, 3 * len(indices), 3))})
    # SUMO espera programas antes de junction/connection.
    for logic in list(root.findall("tlLogic")):
        root.remove(logic)
        root.insert(0, logic)
    ET.ElementTree(root).write(network, encoding="utf-8", xml_declaration=True)
    prepared = copy.deepcopy(config)
    prepared.update(network=network.resolve(), targets=targets, targets_from_mapping=False,
                    experimental={"method": "serial_links_v1", "network_sha256": digest(network),
                                  "source_sha256": digest(source), "mapping_sha256": digest(mapping_path),
                                  "synthetic": True, "minimum_durations": minimums,
                                  "green_floors": green_floors})
    # O piso verde evita encurtar a travessia calculada na geração.
    parameters = copy.deepcopy(prepared.get("control", prepared.get("ppo", {})))
    parameters["action_mode"] = "phase_durations"
    parameters["phase_types"] = ["green", "yellow", "all_red"]
    parameters["phase_duration_bounds"] = {key: {"minimum_seconds": value} for key, value in green_floors.items()}
    parameters["duration_limits"] = {"yellow": {"maximum_seconds": 6},
                                       "all_red": {"maximum_seconds": max(minimums.values())}}
    prepared["ppo"] = {**prepared["ppo"], **parameters}
    prepared["control"] = parameters
    rows = validate_experimental(prepared)
    prepared["duration_seconds"] = max(prepared["duration_seconds"], int(max(row["ciclo_inicial_s"] for row in rows) * 2))
    (output / "verificacao.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "cenario.json").write_text(json.dumps(prepared, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return prepared, rows


def preview_experimental(config, output):
    """Confere carregamento e passos reais; não substitui avaliação completa."""
    from semaforos.simulacao.ambiente import SemaforosEnv
    preview = copy.deepcopy(config)
    preview["duration_seconds"] = 30
    control = preview.get("control", preview.get("ppo", {}))
    env = SemaforosEnv(preview, output, gui=bool(control.get("gui", False)))
    try:
        env.reset(seed=preview["seeds"][0])
        done = False
        while not done:
            _, _, done, _, info = env.step([1] * len(env.action_spec))
        (Path(output) / "preview.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
        return info
    finally:
        env.close()
