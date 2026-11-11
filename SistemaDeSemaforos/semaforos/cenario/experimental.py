"""Preparação e auditoria de programas semafóricos sintéticos."""

import copy
import hashlib
import json
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from semaforos.caminhos import PROJECT_ROOT


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def intersection_names():
    mapping = json.loads((PROJECT_ROOT / 'config/mapeamento_associado.json').read_text(encoding='utf-8'))
    return [entry['name'] for entry in mapping['intersections']]


def select_intersection(config, name):
    """Recorta o controle, preservando a rede preparada e os sinais de referência."""
    validate_experimental(config)
    if name not in intersection_names():
        raise ValueError(f'Cruzamento desconhecido: {name}')
    selected = copy.deepcopy(config)
    selected['targets'] = [t for t in selected['targets'] if t['name'] == name]
    if not selected['targets']:
        raise ValueError('Prepare o cenário completo antes de selecionar outro cruzamento')
    selected['experimental']['selected_intersections'] = [name]
    ids = {t['tls_id'] for t in selected['targets']}
    for key in ('minimum_durations', 'green_floors'):
        selected['experimental'][key] = {k: v for k, v in selected['experimental'][key].items() if k.rsplit(':', 1)[0] in ids}
    for key in ('ppo', 'control'):
        selected[key]['phase_duration_bounds'] = {k: v for k, v in selected[key].get('phase_duration_bounds', {}).items() if k.rsplit(':', 1)[0] in ids}
    validate_experimental(selected)
    return selected


def validate_experimental(config):
    metadata = config.get("experimental", {})
    from semaforos.cenario.configuracao import control_parameters
    if control_parameters(config).get("action_mode") not in ('phase_durations', 'adaptive_signals'):
        raise ValueError("O cenário conjunto experimental requer controle de duração das fases")
    if metadata.get("method") not in ("serial_links_v1", "compatible_groups_v2") or digest(config["network"]) != metadata.get("network_sha256"):
        raise ValueError("Rede experimental ausente ou modificada; prepare novamente pela interface")
    root = ET.parse(config["network"]).getroot()
    targets = config["targets"]
    ids = [item["tls_id"] for item in targets]
    selection = metadata.get('selected_intersections')
    if selection:
        mapping = json.loads((PROJECT_ROOT / 'config/mapeamento_associado.json').read_text(encoding='utf-8'))
        expected = {(entry['name'], c['tls_id']) for entry in mapping['intersections'] if entry['name'] in selection for c in entry['controllers']}
        if len(selection) != 1 or not expected or len(ids) != len(set(ids)) or {(t['name'], t['tls_id']) for t in targets} != expected:
            raise ValueError('Seleção experimental incompleta: inclua todos os controladores do cruzamento')
    elif len(ids) != 17 or len(set(ids)) != 17 or len({item["name"] for item in targets}) != 9:
        raise ValueError("O cenário experimental deve controlar os 17 controladores dos nove cruzamentos")
    if metadata["method"] == "compatible_groups_v2":
        from .grupos import audit_program
        rows = []
        owners = {}
        edge_nodes = {e.get("id"): e.get("to") for e in root.findall("edge") if e.get("to")}
        for tls in ids + metadata.get("external_repaired", []):
            for connection in root.findall("connection"):
                if connection.get("tl") != tls:
                    continue
                node = edge_nodes.get(connection.get("from"))
                if node:
                    if node in owners and owners[node] != tls:
                        raise ValueError(f"Controladores independentes compartilham o nó {node}")
                    owners[node] = tls
            row = audit_program(root, tls)
            if tls in ids:
                target = next(t for t in targets if t["tls_id"] == tls)
                if target["phase_indices"] != list(range(0, row["fases"], 3)):
                    raise ValueError(f"Índices verdes incompletos em {tls}")
                row.update(cruzamento=target["name"], controlado=True)
                rows.append(row)
        return rows
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
    from .preparacao import prepare_grouped
    return prepare_grouped(config, output)


def prepare_or_reuse(config, results):
    """Reutiliza somente a infraestrutura; mantém os parâmetros do estudo atual."""
    from .configuracao import read_config
    results = Path(results)
    source_hash = digest(PROJECT_ROOT / 'dados/rede/uberlandia.rondon_norte_corrigida.net.xml')
    mapping_hash = digest(PROJECT_ROOT / 'config/mapeamento_associado.json')
    candidates = sorted(results.glob('cenario_nove_*/cenario.json'), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in candidates:
        try:
            saved = read_config(path)
            metadata = saved.get('experimental', {})
            if (metadata.get('method') != 'compatible_groups_v2'
                    or metadata.get('source_sha256') != source_hash
                    or metadata.get('mapping_sha256') != mapping_hash
                    or metadata.get('selected_intersections')):
                continue
            rows = validate_experimental(saved)
        except (OSError, ValueError, TypeError, KeyError, ET.ParseError):
            continue
        prepared = copy.deepcopy(config)
        for key in ('network', 'targets', 'experimental'):
            prepared[key] = copy.deepcopy(saved[key])
        prepared['targets_from_mapping'] = False
        prepared['control'] = copy.deepcopy(config.get('control', config['ppo']))
        for key in ('action_mode', 'phase_types', 'phase_duration_bounds', 'duration_limits', 'maximum_cycle_seconds'):
            prepared['control'][key] = copy.deepcopy(saved['control'][key])
        prepared['ppo'] = {**prepared['ppo'], **prepared['control']}
        prepared['duration_seconds'] = max(int(config['duration_seconds']), int(prepared['control']['maximum_cycle_seconds'] * 2))
        return prepared, rows, True
    results.mkdir(parents=True, exist_ok=True)
    prepared, rows = prepare_experimental(config, results / f'cenario_nove_{uuid.uuid4().hex[:12]}')
    return prepared, rows, False


def preview_experimental(config, output):
    """Confere carregamento e passos reais; não substitui avaliação completa."""
    from semaforos.simulacao.ambiente import SemaforosEnv
    preview = copy.deepcopy(config)
    horizon = min(30, float(config["duration_seconds"]))
    preview["duration_seconds"] = horizon
    # Preview de infraestrutura não executa um aquecimento longo nem a janela do estudo.
    preview['measurement'] = {'warmup_seconds': 0, 'start_seconds': 0, 'end_seconds': horizon}
    control = preview.get("control", preview.get("ppo", {}))
    # Gerar a demanda completa preserva taxas e janelas sem tráfego no início.
    # Somente a execução é interrompida aos 30 s; não redistribuir viagens.
    env = SemaforosEnv(preview, output, gui=bool(control.get("gui", False)), demand_config=config)
    try:
        env.reset(seed=preview["seeds"][0])
        done = False
        while not done:
            _, _, done, _, info = env.step([1] * len(env.action_spec))
        (Path(output) / "preview.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
        return info
    finally:
        env.close()
