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
from semaforos.apresentacao.vias import edit_road_volumes
from semaforos.apresentacao.pedestres import pedestrian_editor, pedestrian_route_details
from semaforos.apresentacao.treinamento import adaptive_limits_editor
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


def map_road_scope(geometry, include_unnamed):
    if include_unnamed:
        return geometry
    named = [row for row in geometry['roads'] if row['street']]
    background = [{'path': row['path']} for row in geometry['roads'] if not row['street']]
    return {**geometry, 'roads': named, 'context': [*geometry['context'], *background],
            'all_roads': geometry['roads']}


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


def locate_map_object(namespace, row, field):
    selection = {key: row[key] for key in ('kind', 'crossing', field)}
    open_map_adjustment(st.session_state, namespace, selection)
    st.session_state[namespace + '_located'] = selection


def render_map_search(geometry, namespace, focus, focus_object):
    category_key = namespace + '_search_category'
    focus_category = {'roads': 'Vias', 'signals': 'Semáforos', 'pedestrians': 'Travessias'}.get(focus)
    if focus_category:
        st.session_state[category_key] = focus_category
        _, collection, field = MAP_OBJECTS[focus_category]
        target_id = focus_object.get(field)
        target = next((row for row in geometry[collection] if row[field] == target_id), None)
        if target is not None:
            locate_map_object(namespace, target, field)
            st.session_state[f'{namespace}_search_{collection}'] = target_id
        else:
            st.session_state[namespace + '_panel_closed'] = True
            st.info('Escolha um item na busca ou clique no mapa para abrir o ajuste.')
    category = st.radio('Tipo de ajuste', list(MAP_OBJECTS), horizontal=True, key=category_key)
    _, collection, field = MAP_OBJECTS[category]
    choices = {row[field]: row for row in geometry[collection]}

    def label(object_id):
        row = choices[object_id]
        if category == 'Semáforos':
            return f"{row['crossing']} · {row['description'].split(' · ', 1)[0]}"
        if category == 'Vias':
            return f"{row['title']} · {row['crossing']} · {row['description']}"
        return f"{row['crossing']} · {row['title']}"

    search_key = f'{namespace}_search_{collection}'

    def open_choice():
        target_id = st.session_state[search_key]
        if target_id in choices:
            locate_map_object(namespace, choices[target_id], field)

    st.selectbox('Buscar rua ou cruzamento no mapa', list(choices), index=None,
                 placeholder='Digite um nome para localizar e abrir os ajustes',
                 format_func=label, key=search_key, on_change=open_choice, disabled=not choices)
    if st.session_state.get(namespace + '_located'):
        def reset_view():
            st.session_state.pop(namespace + '_located', None)
            for _, collection_name, _ in MAP_OBJECTS.values():
                st.session_state.pop(f'{namespace}_search_{collection_name}', None)

        st.button('Voltar à visão geral do mapa', key=namespace + '_overview', on_click=reset_view)


def configuration_deck(geometry, crossing, selected, *, locate=False):
    roads = []
    arrows = []
    for row in geometry['roads']:
        focused = row['edge_id'] == selected.get('edge_id')
        controlled = selected.get('kind') == 'signal' and selected.get('tls_id') in row['controllers']
        roads.append({**{k: row[k] for k in ('kind','edge_id','crossing','path','title','description','controllers')},
                      'color': [37, 99, 235] if focused else [14, 165, 164] if controlled else [71,105,130,150],
                      'width': 7 if focused else 4 if controlled else 3})
        if row['direction_polygon']:
            arrows.append({'polygon': row['direction_polygon']})
    # A vista inicial e os objetos exibidos nao dependem da selecao. O clique
    # altera somente o destaque/painel, preservando o enquadramento do usuario.
    local = geometry['signals']
    points = [p for r in geometry.get('all_roads', geometry['roads']) for p in r['path']] or [r['position'] for r in local]
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


@st.cache_data(show_spinner=False)
def configured_signal_timings(network, version, controller, details, edits):
    from semaforos.apresentacao.sinais import signal_movement_timings
    return signal_movement_timings(network, controller, details, include_timeline=True, edited_durations=edits)


def cycle_edit_key(network):
    return configuration_key('cycle_durations_' + str(network))


@st.cache_data(show_spinner=False)
def editable_cycle(network, version, target, labels):
    from semaforos.cenario.rede import initial_signal_timings
    return (network_programs(network),
            initial_signal_timings({'network': network, 'targets': [target]}, labels))


def edit_initial_cycle(base, controller, labels, namespace):
    if base.get('experimental', {}).get('method') != 'compatible_groups_v2':
        st.info('A edição do ciclo inicial está disponível na rede preparada com grupos compatíveis.')
        return
    network = str(base['network'])
    key = cycle_edit_key(network)
    edits = st.session_state.get(key, {})
    target = next(t for t in base['targets'] if t['tls_id'] == controller)
    programs, groups = editable_cycle(network, Path(network).stat().st_mtime_ns, target, labels)
    choice = st.selectbox('Grupo de movimentos', range(len(groups)),
        format_func=lambda i: f"{groups[i]['Grupo']} · {groups[i]['Movimentos liberados']}",
        key=namespace + '_cycle_group_' + controller, help='Movimentos que recebem verde juntos.')
    start = target['phase_indices'][choice]
    form_key = f'{namespace}_cycle_{controller}_{start}'
    step = float(base['step_seconds'])
    cap = float(base.get('control', base['ppo'])['maximum_cycle_seconds'])
    with st.form(form_key, border=False):
        columns = st.columns(3)
        changes = {}
        for offset, (column, label, kind) in enumerate(zip(columns,
                ('Verde (s)', 'Amarelo (s)', 'Todos em vermelho (s)'), ('green', 'yellow', 'all_red'))):
            phase_index = start + offset
            original = programs[controller][phase_index]['duration']
            phase_key = f'{controller}:{phase_index}'
            minimum = float(minimum_phase_seconds(base, phase_key, kind))
            changes[phase_key] = column.number_input(label, min_value=minimum, max_value=cap,
                value=edits.get(phase_key, original), step=step)
        submitted = st.form_submit_button('Aplicar tempos', type='primary')
    if submitted:
        candidate = {**edits, **changes}
        candidate = {k: v for k, v in candidate.items()
                     if v != programs[k.rsplit(':', 1)[0]][int(k.rsplit(':', 1)[1])]['duration']}
        try:
            adjusted_programs(base, programs, candidate)
        except ValueError as error:
            st.error(str(error))
        else:
            st.session_state[key] = candidate
            st.success('Tempos aplicados ao cenário.')


def render_configuration_map(base, initial, details, incoming_ids, specs, labels, ped_defaults, *, volume_by_road,
                             duration=None, focus=None, focus_object=None):
    network = str(base['network'])
    namespace = configuration_key('configuration_map_' + network)
    geometry = configuration_geometry(network, Path(network).stat().st_mtime_ns,
        tuple((t['tls_id'], t['name']) for t in base['targets']), details, ped_defaults,
        tuple(row['from_edge'] for row in initial))
    crossings = list(dict.fromkeys(t['name'] for t in base['targets']))
    selected_key = namespace + '_selected'
    include_unnamed = False
    if geometry:
        search_column, pedestrians_column = st.columns([2, 1])
        with search_column:
            if any(not row['street'] for row in geometry['roads']):
                include_unnamed = st.toggle('Mostrar também vias sem nome', key=namespace + '_include_unnamed',
                    help='Inclui trechos sem nome da rede simulada na busca e na edição. O filtro não altera os volumes já preenchidos.')
            geometry = map_road_scope(geometry, include_unnamed)
            visible_ids = {row['edge_id'] for row in geometry['roads']}
            for key in (selected_key, namespace + '_located'):
                selection = st.session_state.get(key, {})
                if selection.get('kind') == 'road' and selection['edge_id'] not in visible_ids:
                    st.session_state.pop(key, None)
            search_key = namespace + '_search_roads'
            searched_road = st.session_state.get(search_key)
            if searched_road is not None and searched_road not in visible_ids:
                st.session_state.pop(search_key, None)
            render_map_search(geometry, namespace, focus, focus_object or {})
    else:
        pedestrians_column = st.container()
    with pedestrians_column:
        enabled = st.toggle('Incluir pedestres?', value=bool(base.get('pedestrians', {}).get('enabled', False)),
            key=configuration_key('Incluir pedestres?'), disabled=not ped_defaults,
            help='Com a opção ativa, a simulação usa os fluxos definidos nas travessias.')
        if not ped_defaults:
            st.caption('Sem travessias cadastradas nesta rede.')
        elif not enabled:
            st.caption('Os fluxos de pedestres ficam fora da simulação enquanto esta opção estiver desligada.')
    selected = st.session_state.get(selected_key, {})
    popup_open = bool(selected) and not st.session_state.get(namespace + '_panel_closed', False)
    st.caption('Clique em uma via, semáforo ou travessia para editar em uma janela. Use o zoom para ver o sentido de cada trecho.')
    with st.container(key='configuration_map_canvas'):
        if geometry:
            chart_key = namespace + '_chart_0'
            def picked():
                apply_map_selection(st.session_state, namespace, geometry, st.session_state.get(chart_key, {}))
            # Na versao instalada, o JSON participa da identidade do widget mesmo
            # com key. Realces feitos no Python recriavam o mapa a cada selecao.
            # O frontend nativo destaca a selecao sem alterar este JSON/camera.
            located = st.session_state.get(namespace + '_located', {})
            st.pydeck_chart(configuration_deck(geometry, None, located, locate=bool(located)), key=chart_key,
                            height=760, on_select=picked, selection_mode='single-object')
            road_legend = 'Vias destacadas: trechos configuráveis da rede simulada.' if include_unnamed else 'Vias destacadas: trechos com nome disponíveis para configurar.'
            st.caption(road_legend + ' Ícones: controladores em posições aproximadas, sem estado ao vivo. © OpenStreetMap · © CARTO')
            if selected and not popup_open:
                st.button('Mostrar ajustes', key=namespace + '_reopen',
                          on_click=lambda: st.session_state.update({namespace + '_panel_closed': False}))
        else:
            st.info('Esta rede não tem localização geográfica disponível.')

    def road_editor(edge=None):
        return edit_road_volumes(network, initial, details, incoming_ids, None,
            selected_edge=edge, show_map=False, map_only=True, duration=duration)

    def green_limits(crossing=None, controller=None):
        return adaptive_limits_editor(base, specs, labels, key=f'adaptive_limits_{network}',
            selected_crossing=crossing, selected_controller=controller, map_only=True)

    def pedestrian_flows(crossing=None, route=None):
        if ped_defaults:
            return pedestrian_editor(network, ped_defaults, key=f'pedestrian_flows_{network}_{tuple(crossings)}',
                selected_crossing=crossing, selected_route=route, show_map=False, map_only=True)
        return None

    if geometry and selected.get('kind') == 'signal':
        controller, crossing = selected['tls_id'], selected['crossing']
        timing_details = {**details, **{row['crossing_id']: {
            'reference': row['title'], 'street': 'Travessia de pedestres',
            'approach': row['origin_side'] + ' ↔ ' + row['destination_side']} for row in geometry['pedestrians']}}
        from semaforos.apresentacao.sinais import render_initial_cycle

        edits = st.session_state.get(cycle_edit_key(network), {})
        timings = configured_signal_timings(network, Path(network).stat().st_mtime_ns, controller, timing_details, edits)
        with st.expander(f'Ciclo e tempos por via · {crossing}'):
            render_initial_cycle(timings, key=namespace + '_cycle_' + controller)
            columns = ['Entrada', 'Via', 'Sentido', 'Movimento', 'Verde (s)', 'Amarelo (s)', 'Vermelho (s)']
            if any(row['Outros (s)'] for row in timings):
                columns.append('Outros (s)')
            st.dataframe([{name: row[name] for name in columns} for row in timings], hide_index=True, width='stretch')
        with st.expander('Limites de verde do treinamento'):
            phase_table = green_limits(crossing, controller)
    else:
        phase_table = green_limits()

    def close_popup():
        st.session_state[namespace + '_panel_closed'] = True

    if geometry and popup_open and st.session_state.get('ui_workflow_selection', SETUP_TAB) == SETUP_TAB:
        kind = selected['kind']
        title = {'road': 'Configurar via', 'signal': 'Configurar semáforo', 'pedestrian': 'Configurar travessia'}[kind]

        @st.dialog(title, on_dismiss=close_popup)
        def adjustment_popup():
            if st.session_state[namespace + '_panel_closed']:
                st.rerun()
            with st.container(key='configuration_map_popup'):
                st.caption(selected['crossing'])
                if kind == 'road':
                    road_editor(selected['edge_id'])
                elif kind == 'signal':
                    edit_initial_cycle(base, selected['tls_id'], labels, namespace)
                else:
                    pedestrian_flows(selected['crossing'], selected['crossing_id'])
                    st.caption('Pessoas/h em cada sentido. Ative Incluir pedestres para usar esses valores.')
                st.button('Fechar ajustes', key=namespace + '_close', on_click=close_popup)

        adjustment_popup()

    # Os editores alteram o rascunho da sessão. A coleta para a execução inclui toda a rede.
    road_table, pedestrian_table = road_editor(), pedestrian_flows()
    if geometry and volume_by_road and not include_unnamed:
        unnamed_ids = {row['edge_id'] for row in geometry['all_roads'] if not row['street']}
        if (road_table['from_edge'].isin(unnamed_ids) & road_table['vehicles_per_hour'].gt(0)).any():
            st.caption('Há fluxo configurado em vias sem nome. Use “Mostrar também vias sem nome” para revisar esses valores.')
    return road_table if volume_by_road else None, pedestrian_table, phase_table, enabled
