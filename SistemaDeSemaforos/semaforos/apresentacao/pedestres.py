"""Identificação dos lados da travessia pela geometria e pelas conexões da rede."""
import math
from pathlib import Path
import xml.etree.ElementTree as ET

from matplotlib.figure import Figure
import pandas as pd
import streamlit as st


def pedestrian_route_details(network, routes):
    return _pedestrian_route_details(str(network), Path(network).stat().st_mtime_ns, routes)


@st.cache_data(show_spinner=False)
def _pedestrian_route_details(network, version, routes):
    root = ET.parse(network).getroot()
    edges = {e.get('id'): e for e in root.findall('edge')}
    connections = root.findall('connection')
    references = {crossing: f'Travessia {i}' for i, crossing in enumerate(sorted({r['crossing_id'] for r in routes}), 1)}
    compass = ['leste', 'nordeste', 'norte', 'noroeste', 'oeste', 'sudoeste', 'sul', 'sudeste']
    result = []
    for route in routes:
        crossing = route['crossing_id']
        lane = edges[crossing].find('lane')
        shape = [tuple(map(float, point.split(','))) for point in lane.get('shape').split()]
        upstream = {c.get('from') for c in connections if c.get('to') == crossing}
        downstream = {c.get('to') for c in connections if c.get('from') == crossing}
        access = {c.get('to') for c in connections if c.get('from') == route['from_edge']}
        if access & downstream and not access & upstream:
            shape.reverse()
        elif not access & upstream or access & downstream:
            raise ValueError(f"Não foi possível identificar o lado de partida da {references[crossing]}; confira as conexões de pedestres da rede.")
        start, end = shape[0], shape[-1]
        if start == end:
            origin, destination = 'A (ver mapa)', 'B (ver mapa)'
        else:
            angle = round(math.atan2(end[1] - start[1], end[0] - start[0]) / (math.pi / 4)) % 8
            origin, destination = compass[(angle + 4) % 8], compass[angle]
        result.append({**route, 'reference': references[crossing], 'origin_side': origin,
                       'destination_side': destination, 'shape': shape})
    return result


def pedestrian_map(network, route, local_routes):
    root = ET.parse(network).getroot()
    shape = route['shape']
    cx, cy = ((shape[0][i] + shape[-1][i]) / 2 for i in (0, 1))
    radius = max(18, math.dist(shape[0], shape[-1]) * 1.5 + 5)
    fig = Figure(figsize=(8, 5))
    ax = fig.subplots()
    for edge in root.findall('edge'):
        lane = edge.find('lane')
        if lane is None or not lane.get('shape'):
            continue
        points = [tuple(map(float, p.split(','))) for p in lane.get('shape').split()]
        if any(abs(x - cx) < radius and abs(y - cy) < radius for x, y in points):
            ax.plot(*zip(*points), color='#c4cbd2', linewidth=1, zorder=1)
    seen = set()
    for other in local_routes:
        if other['crossing_id'] in seen:
            continue
        seen.add(other['crossing_id'])
        points = other['shape']
        midpoint = tuple((points[0][i] + points[-1][i]) / 2 for i in (0, 1))
        if abs(midpoint[0] - cx) < radius and abs(midpoint[1] - cy) < radius:
            ax.plot(*zip(*points), color='#8b9aaa', linewidth=3, zorder=2)
            if other['crossing_id'] != route['crossing_id']:
                ax.annotate(other['reference'], midpoint, xytext=(5, 10), textcoords='offset points', fontsize=8,
                            bbox={'facecolor': 'white', 'edgecolor': 'none', 'alpha': .85}, zorder=5)
    ax.plot(*zip(*shape), color='#1565c0', linewidth=5, zorder=3)
    arrow_start = tuple(shape[0][i] + (shape[-1][i] - shape[0][i]) * .15 for i in (0, 1))
    arrow_end = tuple(shape[0][i] + (shape[-1][i] - shape[0][i]) * .85 for i in (0, 1))
    ax.annotate('', xy=arrow_end, xytext=arrow_start, arrowprops={'arrowstyle': '-|>', 'color': '#1565c0', 'lw': 2, 'mutation_scale': 18}, zorder=6)
    ax.scatter(*shape[0], color='#087f5b', s=70, label=f"Partida: lado {route['origin_side']}", zorder=5)
    ax.scatter(*shape[-1], color='#c92a2a', s=70, label=f"Chegada: lado {route['destination_side']}", zorder=5)
    ax.annotate('PARTIDA', shape[0], xytext=(-8, -15), ha='right', textcoords='offset points', color='#087f5b', weight='bold')
    ax.annotate('CHEGADA', shape[-1], xytext=(8, 2), textcoords='offset points', color='#c92a2a', weight='bold')
    ax.set(xlim=(cx - radius, cx + radius), ylim=(cy - radius, cy + radius),
           xlabel='Oeste ← → Leste (m)', ylabel='Sul ← → Norte (m)', title=f"{route['reference']} — {route['intersection']}")
    ax.set_aspect('equal')
    ax.legend(loc='lower left', fontsize=8)
    return fig


def pedestrian_street_map(network, route):
    import pydeck as pdk
    from pyproj import Proj
    location = ET.parse(network).getroot().find('location')
    if location is None or location.get('projParameter') in (None, '!', '-', '.'):
        return None
    projection = Proj(location.get('projParameter'))
    offset = tuple(map(float, location.get('netOffset').split(',')))
    points = [list(projection(x - offset[0], y - offset[1], inverse=True)) for x, y in route['shape']]
    ends = [{'position': points[0], 'color': [8, 127, 91], 'title': 'Partida'},
            {'position': points[-1], 'color': [201, 42, 42], 'title': 'Chegada'}]
    center = [(points[0][i] + points[-1][i]) / 2 for i in (0, 1)]
    return pdk.Deck(map_provider='carto', map_style='light',
        initial_view_state=pdk.ViewState(longitude=center[0], latitude=center[1], zoom=19, pitch=0, bearing=0),
        tooltip={'text': '{title}'}, layers=[
            pdk.Layer('PathLayer', [{'path': points, 'title': route['reference']}], get_path='path',
                      get_color=[37, 99, 235], width_units="'pixels'", get_width=6, pickable=True),
            pdk.Layer('ScatterplotLayer', ends, get_position='position', get_fill_color='color',
                      radius_units="'pixels'", get_radius=7, pickable=True),
            pdk.Layer('TextLayer', ends, get_position='position', get_text='title', get_size=14,
                      get_pixel_offset=[0, -22], get_color=[15, 23, 42], background=True,
                      get_background_color=[255, 255, 255, 240], character_set="'auto'")])


def pedestrian_editor(network, defaults, key, *, selected_crossing=None, selected_route=None, show_map=True, map_only=False):
    from semaforos.apresentacao.estado import configuration_key
    key = configuration_key(key)
    details = pedestrian_route_details(network, defaults)
    if not details:
        return pd.DataFrame(defaults)
    identity = lambda row: (row['intersection'], row['crossing_id'], row['from_edge'], row['to_edge'])
    state_key = f'{key}_values_{tuple(identity(row) for row in details)}'
    if state_key not in st.session_state:
        st.session_state[state_key] = {identity(row): float(row.get('persons_per_hour', 0)) for row in details}
    values = st.session_state[state_key]
    for number, row in enumerate(details, 1):
        row['entry_reference'] = f'Entrada {number}'
    crossings = list(dict.fromkeys(row['intersection'] for row in details))
    if (selected_crossing is not None or map_only) and selected_crossing not in crossings:
        result = pd.DataFrame([{**row, 'persons_per_hour': values[identity(row)]} for row in defaults])[
            ['intersection', 'crossing_id', 'from_edge', 'to_edge', 'persons_per_hour']]
        if any(v is None or not math.isfinite(v) or v < 0 for v in values.values()):
            result.attrs['validation_error'] = 'Confira os valores de pessoas por hora nas travessias dos outros cruzamentos.'
        return result
    crossing = selected_crossing if selected_crossing in crossings else st.selectbox('Cruzamento para preencher os pedestres', crossings,
                            key=f'{key}_crossing_{tuple(crossings)}')
    local = [row for row in details if row['intersection'] == crossing]
    if selected_route and any(r['crossing_id'] == selected_route for r in local):
        local = [r for r in local if r['crossing_id'] == selected_route]
    st.caption('Preencha as pessoas por hora deste cruzamento. Os valores dos outros cruzamentos são mantidos ao trocar a seleção. Zero não gera pedestres nesta entrada.')
    records = [{'Entrada': row['entry_reference'], 'Travessia': row['reference'],
                'Sai do lado': row['origin_side'], 'Chega ao lado': row['destination_side'],
                'persons_per_hour': values[identity(row)]} for row in local]
    edited = st.data_editor(pd.DataFrame(records), hide_index=True, num_rows='fixed', width='stretch',
        key=f'{state_key}_editor_{crossing}' + (f'_{selected_route}' if selected_route else ''),
        disabled=['Entrada', 'Travessia', 'Sai do lado', 'Chega ao lado'],
        column_config={'persons_per_hour': st.column_config.NumberColumn('Pessoas/h', min_value=0., step=10., required=True)})
    for row, value in zip(local, edited['persons_per_hour']):
        values[identity(row)] = float(value) if pd.notna(value) else None
    options = [f"{row['entry_reference']} - {row['reference']} - {row['origin_side']} -> {row['destination_side']}" for row in local]
    selected = st.selectbox('Entrada de pedestres a localizar', options,
        key=f'{key}_entry_{crossing}') if show_map else options[0]
    route = local[options.index(selected)]
    if selected_route:
        route = next((r for r in local if r['crossing_id'] == selected_route), route)
    deck = pedestrian_street_map(network, route) if show_map else None
    if show_map and deck is not None:
        st.pydeck_chart(deck, height=480, key=f'{key}_map_{crossing}_{selected}')
        st.caption('Arraste para mover e use o zoom para aproximar. \u00a9 OpenStreetMap, \u00a9 CARTO.')
    elif show_map:
        st.caption('Mapa de ruas indispon\u00edvel: esta rede n\u00e3o tem refer\u00eancia geogr\u00e1fica.')
        st.pyplot(pedestrian_map(network, route, local))
    if show_map:
        st.caption('Verde: partida. Vermelho: chegada. Azul: travessia.')
    result = pd.DataFrame([{**row, 'persons_per_hour': values[identity(row)]} for row in defaults])[
        ['intersection', 'crossing_id', 'from_edge', 'to_edge', 'persons_per_hour']]
    if any(v is None or not math.isfinite(v) or v < 0 for v in values.values()):
        result.attrs['validation_error'] = 'Preencha pessoas por hora com um número maior ou igual a zero em todas as entradas. Use zero para não gerar pedestres.'
        st.error(result.attrs['validation_error'])
    return result
