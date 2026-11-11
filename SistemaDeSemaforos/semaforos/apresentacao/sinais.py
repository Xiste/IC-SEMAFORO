"""Nomes e desenho dos movimentos do programa inicial dos semáforos."""
import xml.etree.ElementTree as ET

from semaforos.cenario.rede import initial_signal_timings
from semaforos.apresentacao.mapa_vias import short_path


def signal_movement_timings(network, controller, details):
    """Duracoes por entrada/movimento do programa inicial, sem amostrar o treino."""
    root = ET.parse(network).getroot()
    edges = {edge.get('id'): edge for edge in root.findall('edge')}
    programs = {logic.get('id'): logic.findall('phase') for logic in root.findall('tlLogic')}
    phases = programs.get(controller, [])
    cycle = sum(float(phase.get('duration')) for phase in phases)
    turns = {'s': 'Em frente', 'l': 'À esquerda', 'L': 'À esquerda',
             'r': 'À direita', 'R': 'À direita', 't': 'Retorno'}
    grouped = {}
    for connection in root.findall('connection'):
        if connection.get('tl') != controller:
            continue
        index = int(connection.get('linkIndex'))
        sequence = tuple(phase.get('state')[index] for phase in phases)
        source, destination = connection.get('from'), connection.get('to')
        pedestrian = any(edges.get(edge) is not None and edges[edge].get('function') in ('crossing', 'walkingarea')
                         for edge in (source, destination))
        edge_id = next((edge for edge in (source, destination)
                        if edges.get(edge) is not None and edges[edge].get('function') == 'crossing'), source)
        # Protegido/permissivo (G/g) tem a mesma cor e duracao nesta tabela.
        colors = tuple('g' if state in 'Gg' else 'y' if state in 'Yy' else 'r' if state in 'Rr' else state
                       for state in sequence)
        key = (edge_id, colors)
        if key not in grouped:
            info = details.get(edge_id, {})
            times = {'green': 0., 'yellow': 0., 'red': 0., 'other': 0.}
            for phase, state in zip(phases, sequence):
                color = 'green' if state in 'Gg' else 'yellow' if state in 'Yy' else 'red' if state in 'Rr' else 'other'
                times[color] += float(phase.get('duration'))
            grouped[key] = {'edge_id': edge_id, 'tls_id': controller, 'movements': set(),
                'Entrada': info.get('reference', 'Pedestres' if pedestrian else 'Entrada'),
                'Via': info.get('street') or ('Travessia de pedestres' if pedestrian else 'Nome não cadastrado'),
                'Sentido': info.get('approach', ''), 'Verde (s)': times['green'],
                'Amarelo (s)': times['yellow'], 'Vermelho (s)': times['red'],
                'Outros (s)': times['other'], 'Ciclo (s)': cycle}
        grouped[key]['movements'].add('Atravessar' if pedestrian else turns.get(connection.get('dir'), 'Movimento'))
    return [{**{k: v for k, v in row.items() if k != 'movements'},
             'Movimento': ' / '.join(sorted(row['movements']))} for row in grouped.values()]


def signal_presentation(config, labels):
    root = ET.parse(config['network']).getroot()
    edges = {e.get('id'): e for e in root.findall('edge')}
    lanes = {lane.get('id'): lane for e in edges.values() for lane in e.findall('lane')}
    turns = {'s': 'seguir em frente', 'l': 'virar à esquerda', 'L': 'virar à esquerda',
             'r': 'virar à direita', 'R': 'virar à direita', 't': 'retornar'}

    def shape(lane):
        return [tuple(map(float, p.split(','))) for p in lane.get('shape', '').split()] if lane is not None else []

    def describe(c):
        source = edges[c.get('from')]
        destination = edges[c.get('to')]
        if source.get('function') in ('walkingarea', 'crossing') or destination.get('function') in ('walkingarea', 'crossing'):
            return 'Travessia de pedestres'
        label = labels.get(c.get('from'), source.get('name') or 'Acesso de veículos')
        parts = label.split(' · ')
        # O cruzamento já aparece no seletor; preserva entrada, rua e sentido.
        if len(parts) > 2 and parts[0].startswith('Entrada '):
            label = ' · '.join([parts[0], *parts[2:]])
        return f"{label}: {turns.get(c.get('dir'), 'passagem de veículos')}"

    rows = initial_signal_timings(config, labels)
    for target in config['targets']:
        tls = target['tls_id']
        connections = [c for c in root.findall('connection') if c.get('tl') == tls]
        references = sorted({labels[c.get('from')].split(' · ')[0] for c in connections if c.get('from') in labels})
        controller_label = 'Semáforos — ' + ', '.join(references) if references else 'Semáforos das travessias de pedestres'
        phases = next(p for p in root.findall('tlLogic') if p.get('id') == tls).findall('phase')
        local = [r for r in rows if r['controlador'] == tls]
        starts = [i for i in target['phase_indices'] if any(v in 'Gg' for v in phases[i].get('state'))]
        for number, (row, start) in enumerate(zip(local, starts), 1):
            state = phases[start].get('state')
            opened = [c for c in connections if state[int(c.get('linkIndex'))] in 'Gg']
            row['Grupo'] = f'Etapa {number}'
            row['Movimentos liberados'] = '; '.join(sorted({describe(c) for c in opened}))
            row['_controller_label'] = controller_label
            paths = []
            for c in connections:
                source = edges[c.get('from')].find(f"lane[@index='{c.get('fromLane')}']")
                destination = edges[c.get('to')].find(f"lane[@index='{c.get('toLane')}']")
                before, after = shape(source), shape(destination)
                via = shape(lanes.get(c.get('via')))
                path = short_path(before, 65, end=True) + via + short_path(after, 65) if before and after else []
                if len(path) > 1:
                    reference = labels.get(c.get('from'), '').split(' · ')[0]
                    paths.append({'path': path, 'green': state[int(c.get('linkIndex'))] in 'Gg', 'reference': reference})
            row['_paths'] = paths
    # Quando há mais de um conjunto só de pedestres, a posição distingue os locais.
    for crossing in {r['cruzamento'] for r in rows}:
        local = [r for r in rows if r['cruzamento'] == crossing]
        points = [p for r in local for item in r['_paths'] for p in item['path']]
        if not points:
            continue
        cx = (min(p[0] for p in points) + max(p[0] for p in points)) / 2
        cy = (min(p[1] for p in points) + max(p[1] for p in points)) / 2
        for row in local:
            if row['_controller_label'] == 'Semáforos das travessias de pedestres':
                positions = [p for item in row['_paths'] for p in item['path']]
                if positions:
                    x = sum(p[0] for p in positions) / len(positions)
                    y = sum(p[1] for p in positions) / len(positions)
                    row['_controller_label'] += f" — lado {'norte' if y >= cy else 'sul'}/{'leste' if x >= cx else 'oeste'}"
    return rows


def movement_figure(paths):
    from matplotlib.figure import Figure
    figure = Figure(figsize=(9, 5), facecolor='#f8fafc')
    ax = figure.subplots()
    labeled = set()
    for item in sorted(paths, key=lambda p: p['green']):
        path = item['path']
        x, y = zip(*path)
        color = '#059669' if item['green'] else '#cbd5e1'
        ax.plot(x, y, color=color, linewidth=3 if item['green'] else 1.5, zorder=3 if item['green'] else 1)
        if item['green']:
            a, b = path[-2:]
            ax.annotate('', xy=b, xytext=a, arrowprops={'arrowstyle': '-|>', 'color': color, 'lw': 2}, zorder=4)
        reference = item.get('reference')
        if reference and reference not in labeled:
            labeled.add(reference)
            ax.annotate(reference, path[0], xytext=(5, 5), textcoords='offset points', fontsize=9,
                        bbox={'facecolor': 'white', 'alpha': .85, 'edgecolor': 'none'}, zorder=5)
    ax.set_aspect('equal', adjustable='datalim')
    ax.margins(.12)
    ax.axis('off')
    ax.text(.97, .96, 'N ↑', transform=ax.transAxes, ha='right', va='top', fontsize=12)
    ax.set_title('Verde: movimentos liberados nesta etapa • Cinza: demais movimentos', fontsize=11)
    figure.tight_layout()
    return figure
