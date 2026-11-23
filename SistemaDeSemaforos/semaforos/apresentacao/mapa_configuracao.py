"""Mapa único: seleciona objetos da rede e abre uma janela de ajustes."""
import math
from pathlib import Path
from urllib.parse import quote
import xml.etree.ElementTree as ET

import pydeck as pdk
import streamlit as st
from sumolib.net.lane import get_allowed
from pyproj import Proj

from semaforos.apresentacao.estado import configuration_key
from semaforos.apresentacao.layout import SETUP_TAB
from semaforos.apresentacao.vias import edit_road_volumes, render_road_volume_table, studied_volume_roads
from semaforos.apresentacao.pedestres import pedestrian_editor, pedestrian_route_details
from semaforos.cenario.ciclos import adjusted_programs, minimum_phase_seconds
from semaforos.cenario.rede import network_programs


SIGNAL_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" width="40" height="64" viewBox="0 0 40 64">
<rect x="17" y="46" width="6" height="16" rx="2" fill="#475569"/>
<rect x="6" y="2" width="28" height="48" rx="8" fill="#152235" stroke="white" stroke-width="2"/>
<circle cx="20" cy="13" r="5" fill="#ef4444"/><circle cx="20" cy="26" r="5" fill="#fbbf24"/>
<circle cx="20" cy="39" r="5" fill="#34d399"/></svg>'''
SIGNAL_ICON = {'url': 'data:image/svg+xml;charset=utf-8,' + quote(SIGNAL_SVG),
               'width': 40, 'height': 64, 'anchorY': 55}
MAP_OBJECTS = {
    'Vias': ('configuration-roads', 'roads', 'edge_id'),
    'Semáforos': ('configuration-signals', 'signals', 'tls_id'),
    'Travessias': ('configuration-pedestrians', 'pedestrians', 'crossing_id'),
}


def road_centerline(shapes):
    """Media as faixas de veiculos em distancias relativas equivalentes."""
    lines = []
    fractions = {0., 1.}
    for shape in shapes:
        segments = [(a, b, math.dist(a, b)) for a, b in zip(shape, shape[1:]) if a != b]
        total = sum(length for _, _, length in segments)
        if not total:
            continue
        position = 0.
        for _, _, length in segments:
            position += length
            fractions.add(round(position / total, 10))
        lines.append((segments, total))
    if not lines:
        return []
    result = []
    for fraction in sorted(fractions):
        points = []
        for segments, total in lines:
            remaining = total * fraction
            point = segments[-1][1]
            for a, b, length in segments:
                if remaining <= length:
                    ratio = remaining / length
                    point = [a[i] + (b[i] - a[i]) * ratio for i in (0, 1)]
                    break
                remaining -= length
            points.append(point)
        result.append([sum(p[i] for p in points) / len(points) for i in (0, 1)])
    return result


def road_direction_polygon(shape, geographic):
    """Centraliza uma seta pequena na metade do comprimento da linha da via."""
    segments = [(a, b, math.dist(a, b)) for a, b in zip(shape, shape[1:]) if a != b]
    total = sum(length for _, _, length in segments)
    if not total:
        return []
    remaining = total / 2
    for a, b, length in segments:
        if remaining <= length:
            ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
            center = [a[0] + ux * remaining, a[1] + uy * remaining]
            size = min(5., total * .15, length * .4)
            half_width = min(.9, size * .24)
            # O centroide do triangulo coincide com a linha, inclusive na projecao:
            # vertices em metros passam pela mesma conversao usada pelo PathLayer.
            tip = [center[0] + ux * size * 2 / 3, center[1] + uy * size * 2 / 3]
            base = [center[0] - ux * size / 3, center[1] - uy * size / 3]
            return [geographic(tip), geographic([base[0] - uy * half_width, base[1] + ux * half_width]),
                    geographic([base[0] + uy * half_width, base[1] - ux * half_width])]
        remaining -= length
    return []


def road_highlight_polygons(shape, geographic, half_width=3.):
    """Faixa visual em torno da via; nao altera as faixas do simulador."""
    polygons = []
    for a, b in zip(shape, shape[1:]):
        length = math.dist(a, b)
        if not length:
            continue
        nx, ny = -(b[1] - a[1]) / length * half_width, (b[0] - a[0]) / length * half_width
        ring = [geographic([a[0]+nx,a[1]+ny]), geographic([b[0]+nx,b[1]+ny]),
                geographic([b[0]-nx,b[1]-ny]), geographic([a[0]-nx,a[1]-ny])]
        polygons.append([ring + [ring[0]]])
    return polygons


@st.cache_data(show_spinner=False)
def configuration_geometry(network, version, targets, road_details, pedestrian_routes, editable_ids=None):
    root = ET.parse(network).getroot()
    location = root.find('location')
    if location is None or location.get('projParameter') in (None, '!', '-', '.'):
        return None
    projection = Proj(location.get('projParameter'))
    offset = tuple(map(float, location.get('netOffset').split(',')))
    def geographic(point):
        return list(projection(point[0] - offset[0], point[1] - offset[1], inverse=True))
    edges = {e.get('id'): e for e in root.findall('edge')}
    def edge_shape(edge):
        shapes = [[list(map(float, p.split(','))) for p in lane.get('shape', '').split()]
                  for lane in edge.findall('lane') if 'passenger' in get_allowed(lane.get('allow'), lane.get('disallow'))]
        return road_centerline(shapes)
    names = dict(targets)
    owners = {}
    for c in root.findall('connection'):
        if c.get('tl') in names:
            owners.setdefault(c.get('from'), []).append(c.get('tl'))
    paths, signals, contexts = [], [], []
    endpoints = {}
    for edge_id in dict.fromkeys([*owners, *(editable_ids or [])]):
        controllers = owners.get(edge_id, [])
        edge = edges.get(edge_id)
        if edge is None:
            continue
        lane = edge.find('lane')
        if lane is None:
            continue
        xy = edge_shape(edge) or [list(map(float, p.split(','))) for p in lane.get('shape', '').split()]
        if len(xy) < 2:
            continue
        for tls in set(controllers):
            endpoints.setdefault(tls, []).append(xy[-1])
        if edge_id not in road_details:
            continue
        info = road_details[edge_id]
        if editable_ids is not None and edge_id not in editable_ids:
            continue
        paths.append({'kind': 'road', 'edge_id': edge_id, 'tls_id': controllers[0] if controllers else '',
                      'controllers': sorted(set(controllers)),
                      'crossing': names[controllers[0]] if controllers else info.get('crossing') or 'Outras vias da rede',
                      'street': info['street'],
                      'path': [geographic(p) for p in xy],
                      'title': info['reference'] + ' · ' + (info['street'] or 'Nome não cadastrado'),
                      'description': info['approach'], 'xy': xy,
                      'direction_polygon': road_direction_polygon(xy, geographic)})
    signal_numbers = {}
    for tls, name in targets:
        signal_numbers[name] = signal_numbers.get(name, 0) + 1
        number = signal_numbers[name]
        points = endpoints.get(tls, [])
        # Alguns controladores atendem apenas pedestres: usa o nó ou a própria travessia.
        if not points:
            points = [list(map(float, (j.get('x'), j.get('y')))) for j in root.findall('junction') if j.get('id') == tls]
        if not points:
            continue
        center = [sum(p[i] for p in points) / len(points) for i in (0, 1)]
        signals.append({'kind': 'signal', 'tls_id': tls, 'crossing': name, 'position': geographic(center),
                        'title': name, 'description': f'Semáforo {number} · clique para ajustar', 'icon': SIGNAL_ICON})
    if not signals:
        return None
    mapped_edges = {row['edge_id'] for row in paths}
    for edge in edges.values():
        if edge.get('id') in mapped_edges:
            continue
        if edge.get('function') in ('internal', 'crossing', 'walkingarea'):
            continue
        lane = edge.find('lane')
        if lane is None:
            continue
        xy = edge_shape(edge) or [list(map(float, p.split(','))) for p in lane.get('shape', '').split()]
        if len(xy) >= 2:
            contexts.append({'path': [geographic(p) for p in xy]})
    pedestrians = []
    seen = set()
    for row in pedestrian_route_details(network, pedestrian_routes) if pedestrian_routes else []:
        if row['crossing_id'] in seen:
            continue
        seen.add(row['crossing_id'])
        path = [geographic(p) for p in row['shape']]
        pedestrians.append({'kind': 'pedestrian', 'crossing_id': row['crossing_id'], 'crossing': row['intersection'],
                            'path': path, 'position': path[len(path) // 2], 'title': row['reference'],
                            'origin_side': row['origin_side'], 'destination_side': row['destination_side'],
                            'description': 'Clique para configurar os pedestres',
                            'controllers': sorted({c.get('tl') for c in root.findall('connection')
                                if c.get('tl') in names and row['crossing_id'] in (c.get('from'), c.get('to'))}),
                            'highlight_polygons': road_highlight_polygons(row['shape'], geographic, 1.5)})
    for signal in signals:
        controlled = [road for road in paths if signal['tls_id'] in road['controllers']]
        crossings = [row for row in pedestrians if signal['tls_id'] in row['controllers']]
        polygons = [polygon for road in controlled for polygon in road_highlight_polygons(road['xy'], geographic)]
        polygons.extend(polygon for row in crossings for polygon in row['highlight_polygons'])
        signal['affected_edges'] = [road['edge_id'] for road in controlled]
        signal['affected_crossings'] = [row['crossing_id'] for row in crossings]
        signal['properties'] = {key: signal[key] for key in
            ('kind','tls_id','crossing','title','description','icon','affected_edges','affected_crossings')}
        signal['type'] = 'Feature'
        signal['geometry'] = {'type': 'GeometryCollection', 'geometries': [
            {'type': 'Point', 'coordinates': signal['position']},
            {'type': 'MultiPolygon', 'coordinates': polygons}]}
    return {'signals': signals, 'roads': paths, 'context': contexts, 'pedestrians': pedestrians}


def map_road_scope(geometry, visible_ids, primary_ids):
    editable = [row for row in geometry['roads'] if row['edge_id'] in visible_ids]
    background = [{'path': row['path']} for row in geometry['roads'] if row['edge_id'] not in visible_ids]
    overview = [row for row in geometry['roads'] if row['edge_id'] in primary_ids]
    return {**geometry, 'roads': editable, 'context': [*geometry['context'], *background],
            'overview_roads': overview}


def map_selection(event, geometry):
    """Aceita somente objetos conhecidos desta rede, nunca dados arbitrários do evento."""
    objects = event.get('selection', {}).get('objects', {})
    for name in ('Semáforos', 'Vias', 'Travessias'):
        layer, key, field = MAP_OBJECTS[name]
        for picked in objects.get(layer, []):
            picked = {**picked.get('properties', {}), **picked}
            for row in geometry[key]:
                if picked.get(field) == row[field]:
                    return {k: row[k] for k in ('kind', 'crossing', field)}
    return None


def apply_map_selection(state, namespace, geometry, event, demand_mode_key=None):
    selection = map_selection(event, geometry)
    event_key = namespace + '_last_map_selection'
    previous = state[event_key] if event_key in state else None
    state[event_key] = selection
    # O gráfico pode reenviar o objeto destacado em outra interação da página.
    if selection == previous:
        return selection
    if selection:
        open_map_adjustment(state, namespace, selection)
        if selection['kind'] == 'road' and demand_mode_key:
            state[demand_mode_key] = 'Volume por via'
    return selection


def open_map_adjustment(state, namespace, selection):
    state[namespace + '_selected'] = selection
    state[namespace + '_panel_closed'] = False
    state[namespace + '_crossing'] = selection['crossing']
    state[namespace + '_mode'] = {'signal': 'Semáforos', 'road': 'Veículos', 'pedestrian': 'Pedestres'}[selection['kind']]
    if selection['kind'] == 'signal':
        state[namespace + '_controller_' + selection['crossing']] = selection['tls_id']


def render_map_search(geometry, namespace, focus, focus_object):
    search_key = namespace + '_search_object'
    choices = {(collection, row[field]): (category, field, row)
               for category, (_, collection, field) in MAP_OBJECTS.items()
               for row in geometry[collection]}
    if st.session_state.get(search_key) not in choices:
        st.session_state.pop(search_key, None)
    if focus in ('roads', 'signals', 'pedestrians'):
        field = next(field for _, collection, field in MAP_OBJECTS.values() if collection == focus)
        target = (focus, focus_object.get(field))
        if target in choices:
            st.session_state[search_key] = target

    def label(option):
        category, _, row = choices[option]
        if category == 'Semáforos':
            return f'{category} · {row["crossing"]} · {row["description"].split(" · ", 1)[0]}'
        if category == 'Vias':
            return f"{category} · {row['title']} · {row['crossing']} · {row['description']}"
        return f"{category} · {row['crossing']} · {row['title']}"

    target = st.selectbox('Buscar rua ou cruzamento no mapa', list(choices), index=None,
                          placeholder='Digite um nome para localizar no mapa',
                          format_func=label, key=search_key, disabled=not choices)
    located = {}
    if target in choices:
        _, field, row = choices[target]
        located = {key: row[key] for key in ('kind', 'crossing', field)}
    location_key = namespace + '_located'
    if located != (st.session_state.get(location_key) or {}):
        st.session_state[location_key] = located
        st.session_state.pop(namespace + '_selected', None)
        st.session_state.pop(namespace + '_last_map_selection', None)
        st.session_state[namespace + '_panel_closed'] = True


def configuration_deck(geometry, crossing, selected, *, locate=False):
    roads = []
    arrows = []
    for row in geometry['roads']:
        focused = row['edge_id'] == selected.get('edge_id')
        controlled = selected.get('kind') == 'signal' and selected.get('tls_id') in row['controllers']
        roads.append({**{k: row[k] for k in ('kind','edge_id','crossing','path','title','description','controllers')},
                      'color': [37, 99, 235] if focused else [14, 165, 164] if controlled else [71,105,130,150],
                      'width': 10 if focused else 9 if controlled else 8})
        if row['direction_polygon']:
            arrows.append({'polygon': row['direction_polygon']})
    # A vista inicial e os objetos exibidos nao dependem da selecao. O clique
    # altera somente o destaque/painel, preservando o enquadramento do usuario.
    local = geometry['signals']
    points = [p for r in geometry.get('overview_roads', geometry['roads']) for p in r['path']]
    points.extend(r['position'] for r in local)
    west, east = min(p[0] for p in points), max(p[0] for p in points)
    south, north = min(p[1] for p in points), max(p[1] for p in points)
    center = [(west + east) / 2, (south + north) / 2]
    longitude_span = max(east - west, .001)
    latitude_span = max(north - south, .001) / max(.1, math.cos(math.radians(center[1])))
    zoom = max(1, min(17, math.log2(min(900 * 360 / (512 * longitude_span), 650 * 360 / (512 * latitude_span))) - .35))
    if locate:
        for _, collection, field in MAP_OBJECTS.values():
            item = next((r for r in geometry[collection] if r[field] == selected.get(field)), None)
            if item:
                if 'position' in item:
                    center = item['position']
                else:
                    path = item['path']
                    middle = path[(len(path) - 1) // 2 : len(path) // 2 + 1]
                    center = [sum(point[axis] for point in middle) / len(middle) for axis in (0, 1)]
                zoom = max(zoom, 16.5)
                break
    pedestrians = [{**r, 'color': [8, 127, 115] if r['crossing_id'] == selected.get('crossing_id') else [37, 99, 235]}
                   for r in geometry['pedestrians']]
    pedestrian_ends = []
    for row in pedestrians:
        if row['crossing_id'] == selected.get('crossing_id'):
            pedestrian_ends.extend([{'position': row['path'][0], 'label': row['origin_side']},
                                    {'position': row['path'][-1], 'label': row['destination_side']}])
    return pdk.Deck(map_provider='carto', map_style='light',
        initial_view_state=pdk.ViewState(longitude=center[0], latitude=center[1], zoom=zoom, pitch=0),
        tooltip={'text': '{title}\n{description}'}, layers=[
            pdk.Layer('PathLayer', geometry['context'], id='configuration-context', get_path='path',
                      get_color=[148,163,184,90], get_width=1, width_units="'pixels'"),
            pdk.Layer('PathLayer', roads, id='configuration-roads', get_path='path', get_color='color',
                      get_width='width', width_units="'pixels'", pickable=True, auto_highlight=True),
            # Icone e vias afetadas pertencem ao mesmo objeto GeoJSON. A selecao
            # nativa realca todos os poligonos desse controlador, sem trocar o JSON.
            # Alpha 1 mantem os corredores invisiveis ate serem selecionados.
            pdk.Layer('GeoJsonLayer', geometry['signals'], id='configuration-signals',
                      point_type="'icon'", get_icon='properties.icon', get_icon_size=28, icon_size_units="'meters'",
                      icon_size_min_pixels=16, icon_size_max_pixels=42, get_icon_color=[255,255,255,255],
                      get_fill_color=[14,165,164,1], filled=True, stroked=False, pickable=True,
                      _sub_layer_props={'polygons-fill': {'pickable': False}}),
            pdk.Layer('PolygonLayer', arrows, id='configuration-directions', get_polygon='polygon',
                      get_fill_color=[14, 110, 135], stroked=False),
            pdk.Layer('PathLayer', pedestrians, id='configuration-pedestrians', get_path='path',
                      get_color='color', get_width=5, width_units="'pixels'", pickable=True, auto_highlight=True),
            pdk.Layer('ScatterplotLayer', pedestrian_ends, id='configuration-crossing-ends', get_position='position',
                      get_fill_color=[37,99,235], radius_units="'pixels'", get_radius=5),
            pdk.Layer('TextLayer', pedestrian_ends, id='configuration-crossing-sides', get_position='position',
                      get_text='label', get_size=13, get_pixel_offset=[0,-17], get_color=[15,23,42], background=True,
                      get_background_color=[255,255,255,240], character_set="'auto'"),
            pdk.Layer('ScatterplotLayer', [r for r in local if r['tls_id'] == selected.get('tls_id')],
                      id='configuration-selected', get_position='position', radius_units="'pixels'", get_radius=25,
                      get_fill_color=[245,158,11,60], stroked=True, get_line_color=[217,119,6], line_width_min_pixels=2),
        ])


def cycle_edit_key(network):
    return configuration_key('cycle_durations_' + str(network))


CYCLE_COLUMNS = ('Verde (s)', 'Amarelo (s)', 'Todos em vermelho (s)')


@st.cache_data(show_spinner=False)
def editable_cycles(network, version, targets, details, include_pedestrians):
    from semaforos.apresentacao.sinais import green_stage_choices

    programs = network_programs(network)
    return programs, green_stage_choices(network, programs, targets, details, include_pedestrians)


def apply_cycle_edits(base, programs, changes):
    state_key = cycle_edit_key(base['network'])
    candidate = dict(st.session_state.get(state_key, {}))
    for key, value in changes.items():
        tls, index = key.rsplit(':', 1)
        if value == programs[tls][int(index)]['duration']:
            candidate.pop(key, None)
        else:
            candidate[key] = value
    adjusted_programs(base, programs, candidate)
    st.session_state[state_key] = candidate


def render_signal_cycle_table(base, details, namespace, *, include_pedestrians=False):
    import pandas as pd

    if base.get('experimental', {}).get('method') != 'compatible_groups_v2':
        return
    network = str(base['network'])
    crossings = list(dict.fromkeys(t['name'] for t in base['targets']))
    with st.container():
        crossing = st.selectbox('Cruzamento dos semáforos', crossings, key=namespace + '_table_signals')
        targets = [t for t in base['targets'] if t['name'] == crossing]
        programs, groups = editable_cycles(network, Path(network).stat().st_mtime_ns, targets, details, include_pedestrians)
        edits = st.session_state.get(cycle_edit_key(network), {})
        rows = []
        phase_keys = []
        for number, target in enumerate(targets, 1):
            controller = target['tls_id']
            for start, label in groups[controller]:
                indices = range(start, start + len(CYCLE_COLUMNS))
                keys = tuple(f'{controller}:{index}' for index in indices)
                durations = [edits.get(key, programs[controller][index]['duration'])
                             for key, index in zip(keys, indices)]
                phase_keys.append(keys)
                rows.append({'Semáforo': f'Conjunto {number}', 'Quem recebe verde': label,
                             **dict(zip(CYCLE_COLUMNS, durations))})
        snapshot = tuple(tuple(row[column] for column in CYCLE_COLUMNS) for row in rows)
        editor_key = f'{namespace}_signal_table_{hash((tuple(phase_keys), snapshot))}'
        feedback_key = namespace + '_signal_table_feedback'

        def apply_timing_table():
            edited_rows = st.session_state[editor_key]['edited_rows']
            changes = {key: cells[column] for index, cells in edited_rows.items()
                       for key, column in zip(phase_keys[index], CYCLE_COLUMNS) if column in cells}
            try:
                apply_cycle_edits(base, programs, changes)
            except ValueError as error:
                st.session_state[feedback_key] = str(error)
            else:
                st.session_state[feedback_key] = ''

        step = float(base['step_seconds'])
        st.caption('Edite as fases do ciclo inicial em segundos. Os tempos só mudam depois de aplicar a tabela.')
        with st.form(namespace + '_signal_table_form'):
            st.data_editor(pd.DataFrame(rows), hide_index=True, width='stretch', key=editor_key,
                disabled=['Semáforo', 'Quem recebe verde'],
                column_config={
                    'Quem recebe verde': st.column_config.TextColumn(width='large'),
                    **{column: st.column_config.NumberColumn(min_value=0., step=step, required=True)
                       for column in CYCLE_COLUMNS},
                })
            st.form_submit_button('Aplicar tempos da tabela', on_click=apply_timing_table)
        feedback = st.session_state.pop(feedback_key, None)
        if feedback:
            st.error(feedback)
        elif feedback == '':
            st.success('Tempos aplicados ao cenário.')


def edit_initial_cycle(base, controller, details, namespace, *, include_pedestrians=False):
    if base.get('experimental', {}).get('method') != 'compatible_groups_v2':
        st.info('A edição do ciclo inicial está disponível na rede preparada com grupos compatíveis.')
        return
    network = str(base['network'])
    key = cycle_edit_key(network)
    edits = st.session_state.get(key, {})
    target = next(t for t in base['targets'] if t['tls_id'] == controller)
    programs, groups = editable_cycles(network, Path(network).stat().st_mtime_ns, [target], details, include_pedestrians)
    labels = dict(groups[controller])
    start = st.selectbox('Quem recebe verde', list(labels), format_func=labels.__getitem__,
        key=namespace + '_cycle_stage_' + controller, help='O tempo de verde vale para todos os movimentos da opção escolhida.')
    if len(labels[start]) > 36:
        st.caption(labels[start])
    form_key = f'{namespace}_cycle_{controller}_{start}'
    step = float(base['step_seconds'])
    cap = float(base.get('control', base['ppo'])['maximum_cycle_seconds'])
    with st.form(form_key, border=False):
        columns = st.columns(3)
        changes = {}
        for offset, (column, label, kind) in enumerate(zip(columns, CYCLE_COLUMNS, ('green', 'yellow', 'all_red'))):
            phase_index = start + offset
            original = programs[controller][phase_index]['duration']
            phase_key = f'{controller}:{phase_index}'
            minimum = float(minimum_phase_seconds(base, phase_key, kind))
            changes[phase_key] = column.number_input(label, min_value=minimum, max_value=cap,
                value=edits.get(phase_key, original), step=step)
        submitted = st.form_submit_button('Aplicar tempos', type='primary')
    if submitted:
        try:
            apply_cycle_edits(base, programs, changes)
        except ValueError as error:
            st.error(str(error))
        else:
            st.success('Tempos aplicados ao cenário.')


def render_configuration_map(base, initial, details, incoming_ids, ped_defaults, *,
                             duration=None, focus=None, focus_object=None,
                             pedestrian_controls=None, filter_controls=None):
    network = str(base['network'])
    namespace = configuration_key('configuration_map_' + network)
    with (pedestrian_controls if pedestrian_controls is not None else st.container()):
        enabled = st.toggle('Incluir pedestres?',
            value=bool(ped_defaults and base.get('pedestrians', {}).get('enabled', False)),
            key=configuration_key('Incluir pedestres?'), disabled=not ped_defaults,
            help='Mostra as travessias no mapa para configurar a quantidade de pedestres.')
    edge_ids = tuple(row['from_edge'] for row in initial)
    details, primary_ids, road_notes = studied_volume_roads(edge_ids, details)
    visible_ids = primary_ids
    if len(primary_ids) < len(edge_ids):
        with (filter_controls if filter_controls is not None else st.container()):
            with st.expander('Filtros'):
                show_other_roads = st.toggle('Mostrar outros trechos da rede', key=namespace + '_other_roads',
                    help='Inclui acessos adicionais na busca, no mapa e na tabela de volumes.')
                if show_other_roads:
                    visible_ids = set(edge_ids)
    geometry = configuration_geometry(network, Path(network).stat().st_mtime_ns,
        tuple((t['tls_id'], t['name']) for t in base['targets']), details, ped_defaults if enabled else [],
        edge_ids)
    crossings = list(dict.fromkeys(t['name'] for t in base['targets']))
    selected_key = namespace + '_selected'
    if geometry:
        geometry = map_road_scope(geometry, visible_ids, primary_ids)
        mapped_ids = {row['edge_id'] for row in geometry['roads']}
        for key in (selected_key, namespace + '_located', namespace + '_last_map_selection'):
            selection = st.session_state.get(key) or {}
            if ((selection.get('kind') == 'road' and selection['edge_id'] not in mapped_ids)
                    or (selection.get('kind') == 'pedestrian' and not geometry['pedestrians'])):
                st.session_state.pop(key, None)
    map_view, table_view = st.tabs(['Mapa', 'Tabela'])
    with map_view:
        if geometry:
            render_map_search(geometry, namespace, focus, focus_object or {})
    selected = st.session_state.get(selected_key, {})
    on_setup = st.session_state.get('ui_workflow_selection', SETUP_TAB) == SETUP_TAB
    if not on_setup:
        st.session_state[namespace + '_panel_closed'] = True
    popup_open = bool(selected) and not st.session_state.get(namespace + '_panel_closed', True)

    def close_popup():
        st.session_state[namespace + '_panel_closed'] = True

    dialog = None
    if geometry and selected and on_setup:
        title = {'road': 'Configurar via', 'signal': 'Configurar semáforo',
                 'pedestrian': 'Configurar travessia'}[selected['kind']]
        # O diálogo fica no fragmento do mapa para que os botões de fechar e o X
        # só atualizem a configuração. O conteúdo tem seu próprio fragmento.
        dialog = st._event._dialog(title, on_dismiss=close_popup)
        if popup_open:
            dialog.open()
        else:
            dialog.close()

    objects = 'uma via, um semáforo ou uma travessia' if enabled else 'uma via ou um semáforo'
    with map_view, st.container(key='configuration_map_canvas'):
        if geometry:
            st.caption(f'Selecione {objects} para editar.')
            chart_key = namespace + '_chart_0'
            def picked():
                apply_map_selection(st.session_state, namespace, geometry, st.session_state.get(chart_key, {}))
            # Na versao instalada, o JSON participa da identidade do widget mesmo
            # com key. Realces feitos no Python recriavam o mapa a cada selecao.
            # O frontend nativo destaca a selecao sem alterar este JSON/camera.
            located = st.session_state.get(namespace + '_located', {})
            st.pydeck_chart(configuration_deck(geometry, None, located, locate=bool(located)), key=chart_key,
                            height=520, on_select=picked, selection_mode='single-object')
            st.caption('Vias destacadas podem ser editadas. © OpenStreetMap · © CARTO')
        else:
            st.info('Esta rede não tem localização geográfica disponível.')

    pedestrian_key = f'pedestrian_flows_{network}_{tuple(crossings)}'
    with table_view:
        table_tabs = ['Volumes das vias', 'Tempos dos semáforos']
        if enabled:
            table_tabs.append('Travessias')
        roads_view, signals_view, *pedestrian_view = st.tabs(table_tabs)
        with roads_view:
            render_road_volume_table(network, initial, details, primary_ids, visible_ids, road_notes)
        with signals_view:
            render_signal_cycle_table(base, details, namespace, include_pedestrians=enabled)
        if pedestrian_view:
            with pedestrian_view[0]:
                pedestrian_editor(network, ped_defaults, key=pedestrian_key, show_map=False, apply_table=True)

    def road_editor(edge=None):
        return edit_road_volumes(network, initial, details, incoming_ids, None,
            selected_edge=edge, show_map=False, map_only=True, duration=duration)

    def pedestrian_flows(crossing=None, route=None):
        if enabled:
            return pedestrian_editor(network, ped_defaults, key=pedestrian_key,
                selected_crossing=crossing, selected_route=route, show_map=False, map_only=True)
        return None

    if dialog is not None and popup_open:
        kind = selected['kind']

        @st.fragment
        def adjustment_fields():
            st.caption(selected['crossing'])
            if kind == 'road':
                road_editor(selected['edge_id'])
            elif kind == 'signal':
                edit_initial_cycle(base, selected['tls_id'], details, namespace, include_pedestrians=enabled)
            else:
                pedestrian_flows(selected['crossing'], selected['crossing_id'])
                st.caption('Pessoas/h em cada sentido.')

        with dialog, st.container(key='configuration_map_popup'):
            adjustment_fields()
            st.button('Fechar ajustes', key=namespace + '_close', on_click=close_popup)

    # Os editores alteram o rascunho da sessão. A coleta para a execução inclui toda a rede.
    road_table, pedestrian_table = road_editor(), pedestrian_flows()
    if len(visible_ids) < len(edge_ids):
        hidden_flow = ~road_table['from_edge'].isin(visible_ids) & road_table['vehicles_per_hour'].gt(0)
        if hidden_flow.any():
            st.caption('Há volumes ativos em outros trechos. Abra Filtros para revisar esses valores.')
    return road_table, pedestrian_table, enabled
