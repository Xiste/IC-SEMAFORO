"""Nomes e desenho dos movimentos do programa inicial dos semáforos."""
from collections import Counter
from itertools import accumulate
import xml.etree.ElementTree as ET

from semaforos.cenario.rede import initial_signal_timings
from semaforos.apresentacao.mapa_vias import short_path
from semaforos.apresentacao.vias import DIRECTIONS


def _short_street(street):
    if street == 'Avenida Governador Rondon Pacheco':
        return 'Av. Rondon Pacheco'
    return street.replace('Avenida ', 'Av. ', 1) if street.startswith('Avenida ') else street


def controller_approaches(network, details):
    """Identifica o conjunto pelas entradas de veículos que ele controla."""
    labels = {}
    for light in network.getTrafficLights():
        streets = {}
        for incoming, outgoing, _ in light.getConnections():
            edge = incoming.getEdge()
            if not edge.allows('passenger') or not outgoing.getEdge().allows('passenger'):
                continue
            info = details.get(edge.getID(), {})
            street = info.get('street') or info.get('reference')
            if street:
                origins = streets.setdefault(_short_street(street), set())
                if info.get('origin'):
                    origins.add(info['origin'])
        if streets:
            labels[light.getID()] = ' / '.join(
                f"{street} (chegada pelo {' e '.join(sorted(origins))})" if origins else street
                for street, origins in sorted(streets.items())
            )
    return labels


def green_stage_choices(network, programs, targets, details, include_pedestrians):
    root = ET.parse(network).getroot()
    edges = {edge.get('id'): edge for edge in root.findall('edge')}
    pedestrian_edges = {edge for edge, data in edges.items() if data.get('function') in ('walkingarea', 'crossing')}
    connections = {}
    for connection in root.findall('connection'):
        tls = connection.get('tl')
        if tls:
            connections.setdefault(tls, []).append(connection)
    turns = {'l': 'à esquerda', 'r': 'à direita', 't': 'retorno'}
    choices = {}
    for target in targets:
        tls = target['tls_id']
        stages = []
        for start in target['phase_indices']:
            state = programs[tls][start]['state']
            straight = {}
            other = set()
            pedestrians = False
            for connection in connections.get(tls, []):
                if state[int(connection.get('linkIndex'))] not in 'Gg':
                    continue
                source = connection.get('from')
                if source in pedestrian_edges or connection.get('to') in pedestrian_edges:
                    pedestrians = True
                    continue
                info = details.get(source, {})
                street = info.get('street') or edges[source].get('name') or info.get('reference') or 'Via sem nome'
                street = _short_street(street)
                turn = (connection.get('dir') or '').lower()
                if turn == 's':
                    straight.setdefault(street, set()).add(info.get('direction') or '')
                else:
                    origin = info.get('origin')
                    approach = f' pelo {origin}' if origin else ''
                    other.add(f"{street}{approach} ({turns.get(turn, 'passagem')})")
            movements = []
            for street, directions in straight.items():
                if len(directions) == 2 and any(
                    {direction, DIRECTIONS[(index + 4) % 8]} == directions
                    for index, direction in enumerate(DIRECTIONS)
                ):
                    movements.append(f'{street} nos dois sentidos')
                else:
                    movements.extend(f'{street} → {direction}' if direction else f'{street} (reto)'
                                     for direction in directions)
            label = ' + '.join(sorted([*movements, *other]))
            if label and pedestrians and include_pedestrians:
                label += ' + pedestres'
            elif not label:
                label = 'Travessia de pedestres' if pedestrians else 'Movimentos do semáforo'
            stages.append((start, label))
        counts = Counter(label for _, label in stages)
        choices[tls] = [(start, f'{label} · etapa {number}' if counts[label] > 1 else label)
                        for number, (start, label) in enumerate(stages, 1)]
    return choices


def _initial_cycle(phases, colors):
    intervals = []
    ends = accumulate(float(phase.get('duration')) for phase in phases)
    start = 0.
    for phase, color, end in zip(phases, colors, ends):
        state = {'g': 'green', 'y': 'yellow', 'r': 'red'}.get(color, 'other')
        if state == 'red' and set(phase.get('state')) <= {'r', 'R'}:
            state = 'clearance'
        if end > start:
            if intervals and intervals[-1]['state'] == state:
                intervals[-1]['end'] = end
            else:
                intervals.append({'start': start, 'end': end, 'state': state})
        start = end
    return intervals


def signal_movement_timings(network, controller, details, *, include_timeline=False, edited_durations=None):
    """Duracoes por entrada/movimento do programa inicial, sem amostrar o treino."""
    return _movement_timings(ET.parse(network).getroot(), controller, details,
                             include_timeline=include_timeline, edited_durations=edited_durations)


def _movement_timings(root, controller, details, *, include_timeline=False, edited_durations=None):
    edges = {edge.get('id'): edge for edge in root.findall('edge')}
    programs = {logic.get('id'): logic for logic in root.findall('tlLogic')}
    logic = programs.get(controller)
    phases = logic.findall('phase') if logic is not None else []
    for index, phase in enumerate(phases):
        value = (edited_durations or {}).get(f'{controller}:{index}')
        if value is not None:
            phase.set('duration', str(value))
    cycle = sum(float(phase.get('duration')) for phase in phases)
    sequential = bool(phases) and logic.get('type', 'static') == 'static' and all(
        phase.get('next', '').split() in ([], [str((index + 1) % len(phases))])
        for index, phase in enumerate(phases)
    )
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
            grouped[key] = {'edge_id': edge_id, 'tls_id': controller, '_link_index': index,
                '_static_cycle': sequential, 'movements': set(),
                'Entrada': info.get('reference', 'Pedestres' if pedestrian else 'Entrada'),
                'Via': info.get('street') or ('Travessia de pedestres' if pedestrian else 'Nome não cadastrado'),
                'Sentido': info.get('approach', ''), 'Verde (s)': times['green'],
                'Amarelo (s)': times['yellow'], 'Vermelho (s)': times['red'],
                'Outros (s)': times['other'], 'Ciclo (s)': cycle}
            if include_timeline and sequential:
                grouped[key]['_timeline'] = _initial_cycle(phases, colors)
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
