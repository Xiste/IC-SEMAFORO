"""Mapa das entradas e das saídas conectadas, com fundo geográfico opcional."""
import math
import xml.etree.ElementTree as ET

import pydeck as pdk
import streamlit as st
import sumolib
from matplotlib.figure import Figure


BLUE = [37, 99, 235, 255]
GREEN = [5, 150, 105, 255]
AMBER = [217, 119, 6, 220]


def point_at(shape, distance):
    for start, end in zip(shape, shape[1:]):
        length = math.dist(start, end)
        if length >= distance and length:
            fraction = max(0, distance) / length
            return [start[0] + fraction * (end[0] - start[0]), start[1] + fraction * (end[1] - start[1])]
        distance -= length
    return list(shape[-1])


def short_path(shape, length=160, end=False):
    points = list(reversed(shape)) if end else list(shape)
    result, remaining = [list(points[0])], length
    for start, finish in zip(points, points[1:]):
        segment = math.dist(start, finish)
        if segment > remaining:
            result.append(point_at([start, finish], remaining))
            break
        result.append(list(finish))
        remaining -= segment
    return list(reversed(result)) if end else result


def arrow_polygon(shape, fraction=.65):
    length = sum(math.dist(a, b) for a, b in zip(shape, shape[1:]))
    position = length * fraction
    tip = point_at(shape, position)
    previous = point_at(shape, max(0, position - 10))
    dx, dy = tip[0] - previous[0], tip[1] - previous[1]
    norm = math.hypot(dx, dy)
    if not norm:
        return []
    ux, uy = dx / norm, dy / norm
    size = min(14, max(3, length * .25))
    base = [tip[0] - ux * size, tip[1] - uy * size]
    return [tip, [base[0] - uy * size / 2, base[1] + ux * size / 2], [base[0] + uy * size / 2, base[1] - ux * size / 2]]


def junction_exits(net, selected):
    """Segue as ligações intermediárias do mesmo cruzamento, sem sair para a rede."""
    tls_ids = {c.getTLSID() for connections in selected.getOutgoing().values() for c in connections if c.getTLSID()}
    nodes = {selected.getToNode().getID()}
    for tls in net.getTrafficLights():
        if tls.getID() in tls_ids:
            nodes.update(c[0].getEdge().getToNode().getID() for c in tls.getConnections())
    known_nodes = {n.getID() for n in net.getNodes()}
    nodes.update(tls_ids & known_nodes)
    pending = [(selected, [], [])]
    found = {}
    while pending:
        current, roads, links = pending.pop(0)
        if len(roads) > 12:
            continue
        for edge, connections in sorted(current.getOutgoing().items(), key=lambda pair: pair[0].getID()):
            allowed = [c for c in connections if c.getFromLane().allows('passenger') and c.getToLane().allows('passenger')]
            if not edge.allows('passenger') or not allowed or edge in roads or edge == selected:
                continue
            trail, transitions = roads + [edge], links + [allowed[0]]
            if edge.getToNode().getID() in nodes:
                pending.append((edge, trail, transitions))
            else:
                found.setdefault(edge.getID(), (trail, transitions))
    return [found[key] for key in sorted(found)], nodes


@st.cache_data(show_spinner=False)
def road_map_data(network_path, version, edge_id, labels, incoming_ids, radius):
    net = sumolib.net.readNet(network_path, withInternal=True)
    selected = net.getEdge(edge_id)
    center = list(selected.getShape()[-1])
    routes, _ = junction_exits(net, selected)
    outgoing = [roads[-1] for roads, _ in routes]
    context = []
    for edge in net.getEdges(withInternal=True):
        shape = edge.getShape()
        if len(shape) < 2 or not edge.allows('passenger'):
            continue
        if any(abs(x - center[0]) <= radius * 1.4 and abs(y - center[1]) <= radius * 1.4 for x, y in shape):
            context.append({'path_xy': [list(p) for p in shape], 'title': edge.getName() or 'Via da rede simulada',
                            'description': labels.get(edge.getID(), 'Trecho de ligação')})
    paths = []

    def append(edge, kind, reference, color, tail=False):
        path = short_path(edge.getShape(), min(radius * .85, 200), end=tail)
        total = sum(math.dist(a, b) for a, b in zip(path, path[1:]))
        position = point_at(path, total * (.22 if tail else .6))
        paths.append({'edge_id': edge.getID(), 'kind': kind, 'reference': reference, 'color': color,
                      'path_xy': path, 'position_xy': position, 'arrow_xy': arrow_polygon(path),
                      'title': reference, 'description': labels.get(edge.getID(), edge.getName() or 'Via da rede simulada')})

    append(selected, 'selected', labels[edge_id].split(' · ', 1)[0], BLUE, tail=True)
    for number, (roads, transitions) in enumerate(routes, 1):
        edge = roads[-1]
        append(edge, 'exit', f'Saída {number}', GREEN)
        connector = [center]
        for road, connection in zip(roads, transitions):
            if connection.getViaLaneID():
                connector.extend([list(p) for p in net.getLane(connection.getViaLaneID()).getShape()])
            if road != edge:
                connector.extend([list(p) for p in road.getShape()])
        paths[-1]['path_xy'] = connector + paths[-1]['path_xy']
        paths[-1]['via_edges'] = [road.getID() for road in roads]
    for other in incoming_ids:
        if other == edge_id or other in {e.getID() for e in outgoing}:
            continue
        edge = net.getEdge(other)
        point = edge.getShape()[-1]
        if math.dist(point, center) < radius:
            append(edge, 'other', labels[other].split(' · ', 1)[0], AMBER, tail=True)
    geo_error = None
    center_geo = None
    try:
        from pyproj import Proj
        location = ET.parse(network_path).getroot().find('location')
        if location is None or location.get('projParameter') in (None, '!', '-', '.'):
            raise ValueError('Rede sem projeção geográfica')
        projection = Proj(location.get('projParameter'))
        offset = tuple(map(float, location.get('netOffset').split(',')))

        def geographic(point):
            return list(projection(point[0] - offset[0], point[1] - offset[1], inverse=True))

        center_geo = geographic(center)
        for row in context + paths:
            row['path'] = [geographic(p) for p in row['path_xy']]
        for row in paths:
            row['position'] = geographic(row['position_xy'])
            row['polygon'] = [geographic(p) for p in row['arrow_xy']]
    except (RuntimeError, ImportError, ValueError) as error:
        center_geo = None
        geo_error = str(error)
    return {'center': center, 'center_geo': center_geo, 'context': context, 'paths': paths,
            'radius': radius, 'geo_error': geo_error, 'exit_count': len(outgoing)}


def road_deck(data, show_others=True, dark=False):
    paths = [row for row in data['paths'] if show_others or row['kind'] != 'other']
    labels = [row for row in paths if row['kind'] != 'other']
    return pdk.Deck(map_provider='carto', map_style='dark' if dark else 'light',
        initial_view_state=pdk.ViewState(longitude=data['center_geo'][0], latitude=data['center_geo'][1],
            zoom=17.3 if data['radius'] <= 200 else 16.3, pitch=0, bearing=0),
        tooltip={'text': '{title}\n{description}', 'style': {'fontSize': '13px', 'maxWidth': '360px'}},
        layers=[
            pdk.Layer('PathLayer', data['context'], id='road-context', get_path='path', get_color=[148, 163, 184, 110],
                      width_units="'pixels'", get_width=2, width_min_pixels=1, width_max_pixels=2, pickable=True),
            pdk.Layer('PathLayer', paths, id='selected-roads', get_path='path', get_color='color',
                      width_units="'pixels'", get_width=7, width_min_pixels=5, width_max_pixels=7, pickable=True, cap_rounded=True, joint_rounded=True),
            pdk.Layer('PolygonLayer', paths, id='direction-arrows', get_polygon='polygon', get_fill_color='color',
                      stroked=False, filled=True, pickable=True),
            pdk.Layer('ScatterplotLayer', labels, id='entrance-exit-markers', get_position='position',
                      get_fill_color='color', radius_units="'pixels'", get_radius=7, stroked=True,
                      get_line_color=[255, 255, 255], line_width_units="'pixels'", get_line_width=2, pickable=True),
            pdk.Layer('TextLayer', labels, id='entrance-exit-labels', get_position='position', get_text='reference',
                      get_color=[15, 23, 42], get_size=14, get_pixel_offset=[0, -22], background=True,
                      get_background_color=[255, 255, 255, 240], background_padding=[7, 4], character_set="'auto'", pickable=True),
        ])


def local_road_figure(data, show_others=True):
    fig = Figure(figsize=(10, 6), facecolor='#f8fafc')
    ax = fig.subplots()
    ax.set_facecolor('#f8fafc')
    for row in data['context']:
        ax.plot(*zip(*row['path_xy']), color='#cbd5e1', linewidth=2, zorder=1)
    for row in data['paths']:
        if row['kind'] == 'other' and not show_others:
            continue
        color = [v / 255 for v in row['color'][:3]]
        ax.plot(*zip(*row['path_xy']), color=color, linewidth=4 if row['kind'] != 'other' else 2, zorder=3)
        if row['arrow_xy']:
            from matplotlib.patches import Polygon
            ax.add_patch(Polygon(row['arrow_xy'], color=color, zorder=4))
        if row['kind'] != 'other':
            ax.scatter(*row['position_xy'], color=color, edgecolor='white', s=70, zorder=5)
            ax.annotate(row['reference'], row['position_xy'], xytext=(7, 10), textcoords='offset points',
                        fontsize=10, weight='bold', color=color, zorder=6,
                        bbox={'facecolor': 'white', 'edgecolor': '#e2e8f0', 'boxstyle': 'round,pad=.4'})
    cx, cy = data['center']
    radius = data['radius']
    ax.set(xlim=(cx - radius, cx + radius), ylim=(cy - radius, cy + radius))
    ax.set_aspect('equal')
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.annotate('N', xy=(.95, .95), xytext=(.95, .84), xycoords='axes fraction', ha='center', weight='bold',
                arrowprops={'arrowstyle': '-|>', 'color': '#334155'}, color='#334155')
    ax.plot([cx - radius * .85, cx - radius * .85 + 50], [cy - radius * .85] * 2, color='#334155', lw=3)
    ax.text(cx - radius * .85 + 25, cy - radius * .85 + 7, '50 m', ha='center', color='#334155', fontsize=9)
    fig.tight_layout(pad=1)
    return fig


def render_road_map(network_path, edge_id, labels, incoming_ids):
    from pathlib import Path
    key = f'road_map_{edge_id}'
    data = road_map_data(str(network_path), Path(network_path).stat().st_mtime_ns,
                         edge_id, labels, tuple(incoming_ids), 180)
    # A consulta de volumes destaca apenas a entrada que está sendo preenchida.
    data = dict(data, paths=[row for row in data['paths'] if row['kind'] == 'selected'])
    st.caption('🔵 Azul: entrada selecionada')
    if data['center_geo']:
        st.pydeck_chart(road_deck(data, show_others=False), height=480,
                        key=f'{key}_interactive')
        st.caption('Arraste para mover e use o zoom para aproximar. © OpenStreetMap, © CARTO.')
    else:
        st.pyplot(local_road_figure(data, show_others=False))
    with st.expander('Detalhes técnicos', expanded=False):
        st.dataframe([{'Referência': row['reference'], 'Via e sentido': row['description'],
                       'Código SUMO': row['edge_id']} for row in data['paths']],
                     hide_index=True, width='stretch')
