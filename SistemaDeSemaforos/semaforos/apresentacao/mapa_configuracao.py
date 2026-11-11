"""Mapa único: seleciona objetos da rede e abre seus ajustes no painel lateral."""
import math
from pathlib import Path
from urllib.parse import quote
import xml.etree.ElementTree as ET

import pydeck as pdk
import streamlit as st
from sumolib.net.lane import get_allowed
from pyproj import Proj

from semaforos.apresentacao.estado import configuration_key
from semaforos.apresentacao.vias import edit_road_volumes
from semaforos.apresentacao.pedestres import pedestrian_editor, pedestrian_route_details
from semaforos.apresentacao.treinamento import adaptive_limits_editor


SIGNAL_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" width="40" height="64" viewBox="0 0 40 64">
<rect x="17" y="46" width="6" height="16" rx="2" fill="#475569"/>
<rect x="6" y="2" width="28" height="48" rx="8" fill="#152235" stroke="white" stroke-width="2"/>
<circle cx="20" cy="13" r="5" fill="#ef4444"/><circle cx="20" cy="26" r="5" fill="#fbbf24"/>
<circle cx="20" cy="39" r="5" fill="#34d399"/></svg>'''
SIGNAL_ICON = {'url': 'data:image/svg+xml;charset=utf-8,' + quote(SIGNAL_SVG),
               'width': 40, 'height': 64, 'anchorY': 55}


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


def map_selection(event, geometry):
    """Aceita somente objetos conhecidos desta rede, nunca dados arbitrários do evento."""
    objects = event.get('selection', {}).get('objects', {})
    for layer, key, field in (('configuration-signals', 'signals', 'tls_id'),
                              ('configuration-roads', 'roads', 'edge_id'),
                              ('configuration-pedestrians', 'pedestrians', 'crossing_id')):
        for picked in objects.get(layer, []):
            picked = {**picked.get('properties', {}), **picked}
            for row in geometry[key]:
                if picked.get(field) == row[field]:
                    return {k: row[k] for k in ('kind', 'crossing', field)}
    return None


def apply_map_selection(state, namespace, geometry, event, demand_mode_key=None):
    selection = map_selection(event, geometry)
    if selection:
        state[namespace + '_selected'] = selection
        state[namespace + '_panel_closed'] = False
        state[namespace + '_crossing'] = selection['crossing']
        state[namespace + '_mode'] = {'signal': 'Semáforos', 'road': 'Veículos', 'pedestrian': 'Pedestres'}[selection['kind']]
        if selection['kind'] == 'signal':
            state[namespace + '_controller_' + selection['crossing']] = selection['tls_id']
        elif selection['kind'] == 'road' and demand_mode_key:
            state[demand_mode_key] = 'Volume por via'
    return selection


def configuration_deck(geometry, crossing, selected):
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
    points = [p for r in geometry['roads'] for p in r['path']] or [r['position'] for r in local]
    west, east = min(p[0] for p in points), max(p[0] for p in points)
    south, north = min(p[1] for p in points), max(p[1] for p in points)
    center = [(west + east) / 2, (south + north) / 2]
    longitude_span = max(east - west, .001)
    latitude_span = max(north - south, .001) / max(.1, math.cos(math.radians(center[1])))
    zoom = max(1, min(17, math.log2(min(900 * 360 / (512 * longitude_span), 650 * 360 / (512 * latitude_span))) - .35))
    pedestrians = geometry['pedestrians']
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
                      get_color=[37,99,235], get_width=5, width_units="'pixels'", pickable=True, auto_highlight=True),
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
def configured_signal_timings(network, version, controller, details):
    from semaforos.apresentacao.sinais import signal_movement_timings
    return signal_movement_timings(network, controller, details)


def render_configuration_map(base, initial, details, incoming_ids, specs, labels, ped_defaults, *, volume_by_road):
    network = str(base['network'])
    namespace = configuration_key('configuration_map_' + network)
    geometry = configuration_geometry(network, Path(network).stat().st_mtime_ns,
        tuple((t['tls_id'], t['name']) for t in base['targets']), details, ped_defaults,
        tuple(row['from_edge'] for row in initial))
    crossings = list(dict.fromkeys(t['name'] for t in base['targets']))
    selected_key = namespace + '_selected'
    selected = st.session_state.get(selected_key, {})
    panel_visible = bool(selected) and not st.session_state.get(namespace + '_panel_closed', False)
    crossing = selected.get('crossing')
    mode = {'signal': 'Semáforos', 'road': 'Veículos', 'pedestrian': 'Pedestres'}.get(selected.get('kind'))
    st.caption('Clique diretamente em uma via para informar veículos/h. Os ícones de semáforo e as travessias abrem seus ajustes. Use o zoom para ver o sentido de cada trecho.')
    # Mesmo caminho de elementos em todos os cliques: so muda a largura por CSS.
    # Trocar containers por colunas desmontava o canvas e perdia a camera do mapa.
    collapsed_style = '''
    [data-testid="stColumn"]:has(.st-key-configuration_map_panel){display:none!important;}
    [data-testid="stColumn"]:has(.st-key-configuration_map_canvas){width:100%!important;flex:1 1 100%!important;}
    ''' if not panel_visible else ''
    st.markdown('<style>' + collapsed_style + '</style>', unsafe_allow_html=True)
    map_column, panel = st.columns([2, 1.4], gap='medium')
    map_column = map_column.container(key='configuration_map_canvas')
    panel = panel.container(key='configuration_map_panel')
    with map_column:
        if geometry:
            chart_key = namespace + '_chart_0'
            def picked():
                apply_map_selection(st.session_state, namespace, geometry, st.session_state.get(chart_key, {}))
            # Na versao instalada, o JSON participa da identidade do widget mesmo
            # com key. Realces feitos no Python recriavam o mapa a cada selecao.
            # O frontend nativo destaca a selecao sem alterar este JSON/camera.
            st.pydeck_chart(configuration_deck(geometry, None, {}), key=chart_key,
                            height=760, on_select=picked, selection_mode='single-object')
            st.caption('Vias destacadas: trechos configuráveis da rede simulada. Ícones: controladores em posições aproximadas, sem estado ao vivo. © OpenStreetMap · © CARTO')
            if selected and not panel_visible:
                st.button('Mostrar ajustes', key=namespace + '_reopen',
                          on_click=lambda: st.session_state.update({namespace + '_panel_closed': False}))
        else:
            st.info('Esta rede não tem localização geográfica disponível.')
    with panel:
        if selected:
            def close_panel():
                st.session_state[namespace + '_panel_closed'] = True
            st.button('Fechar ajustes', key=namespace + '_close', on_click=close_panel)
            st.markdown('**' + mode + '**')
            st.caption(crossing)
        for label, suffix in [('Semáforos','signals'), ('Veículos','vehicles'), ('Pedestres','pedestrians')]:
            if mode != label:
                st.markdown(f'<style>.st-key-{suffix}_{abs(hash(namespace))}' + '{display:none!important;}</style>', unsafe_allow_html=True)
        with st.container(key=f'signals_{abs(hash(namespace))}'):
            phase_table = adaptive_limits_editor(base, specs, labels, key=f'adaptive_limits_{network}',
                selected_crossing=crossing, selected_controller=selected.get('tls_id'), map_only=True)
            st.caption('Amarelo e intervalos de segurança são preservados. Estes limites orientam os ajustes do agente.')
        with st.container(key=f'vehicles_{abs(hash(namespace))}'):
            # O resultado inclui toda a rede mesmo sem selecao ou com o painel fechado.
            road_table = edit_road_volumes(network, initial, details, incoming_ids, None,
                selected_crossing=crossing, selected_edge=selected.get('edge_id'), show_map=False, map_only=True)
        with st.container(key=f'pedestrians_{abs(hash(namespace))}'):
            enabled = st.toggle('Incluir pedestres?', value=bool(base.get('pedestrians', {}).get('enabled', False)),
                key=configuration_key('Incluir pedestres?'))
            speed = float(base.get('pedestrians', {}).get('walking_speed_meters_per_second', .8))
            with st.expander('Velocidade dos pedestres'):
                speed = st.number_input('Velocidade de caminhada (m/s)', min_value=.8, max_value=3.,
                    value=speed, step=.1, key=configuration_key('Velocidade de caminhada (m/s)'))
            pedestrian_table = None
            if ped_defaults:
                pedestrian_table = pedestrian_editor(network, ped_defaults,
                    key=f'pedestrian_flows_{network}_{tuple(crossings)}', selected_crossing=crossing,
                    selected_route=selected.get('crossing_id'), show_map=False, map_only=True)
                st.caption('Pessoas/h em cada sentido. Os valores só entram na simulação com Incluir pedestres ativado.')
            else:
                st.info('Não há travessias cadastradas neste local.')
    if selected.get('kind') == 'signal' and panel_visible:
        st.markdown('**Tempos configurados por via — ' + crossing + '**')
        timing_details = {**details, **{row['crossing_id']: {
            'reference': row['title'], 'street': 'Travessia de pedestres',
            'approach': row['origin_side'] + ' ↔ ' + row['destination_side']} for row in geometry['pedestrians']}}
        timings = configured_signal_timings(network, Path(network).stat().st_mtime_ns, selected['tls_id'], timing_details)
        columns = ['Entrada', 'Via', 'Sentido', 'Movimento', 'Verde (s)', 'Amarelo (s)', 'Vermelho (s)']
        if any(row['Outros (s)'] for row in timings):
            columns.append('Outros (s)')
        st.dataframe([{name: row[name] for name in columns} for row in timings], hide_index=True, width='stretch')
        cycle = timings[0]['Ciclo (s)'] if timings else 0
        st.caption(f'Programa inicial da simulação · tempos totais por ciclo de {cycle:g} s. Não é uma contagem ao vivo. '
                   'Conversões com tempos diferentes aparecem separadas. Os limites de verde acima orientam os ajustes do agente.')
    return road_table if volume_by_road else None, pedestrian_table, phase_table, enabled, speed
