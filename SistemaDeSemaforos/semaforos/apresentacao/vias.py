"""Referências legíveis para localizar entradas sem inventar nomes de ruas."""
import math
import re


def identify_roads(network, targets, osm_names=None):
    osm_names = osm_names or {}
    owners = {}
    names = dict(targets)
    for light in network.getTrafficLights():
        if light.getID() in names:
            for connection in light.getConnections():
                edge = connection[0].getEdge()
                owners.setdefault(edge.getID(), set()).add(names[light.getID()])
    entries = sorted(edge.getID() for edge in network.getEdges(withInternal=False)
                     if edge.getID() in owners and edge.allows('passenger'))
    references = {edge: f'Entrada {number}' for number, edge in enumerate(entries, 1)}
    directions = ['leste', 'nordeste', 'norte', 'noroeste', 'oeste', 'sudoeste', 'sul', 'sudeste']
    details = {}
    for number, edge in enumerate(sorted(network.getEdges(withInternal=False), key=lambda e: e.getID()), 1):
        edge_id = edge.getID()
        match = re.match(r'^-?(\d+)(?:#|$)', edge_id)
        name = edge.getName() or (osm_names.get(match.group(1), {}).get('name', '') if match else '')
        if name.startswith(':'):
            name = ''
        shape = edge.getShape()
        # A direção é a do trecho final de chegada, inclusive em vias curvas.
        end = shape[-1]
        previous = next((point for point in reversed(shape[:-1]) if point != end), None)
        if previous:
            angle = round(math.atan2(end[1] - previous[1], end[0] - previous[0]) / (math.pi / 4)) % 8
            direction, origin = directions[angle], directions[(angle + 4) % 8]
            approach = f'chega pelo {origin}, segue para {direction}'
        else:
            approach = 'sentido a conferir no mapa'
        reference = references.get(edge_id, f'Trecho de ligação {number}')
        crossing = ' / '.join(sorted(owners.get(edge_id, [])))
        parts = [reference, crossing, name, approach]
        details[edge_id] = {'label': ' · '.join(part for part in parts if part),
                            'reference': reference, 'crossing': crossing, 'street': name,
                            'approach': approach}
    return details


def edit_road_volumes(network, initial, details, incoming_ids, render_map, *, selected_crossing=None, selected_edge=None, show_map=True, map_only=False):
    """Edita um cruzamento mantendo volumes dos demais na mesma configuração."""
    import pandas as pd
    import streamlit as st
    from semaforos.apresentacao.estado import configuration_key

    signature = tuple(row['from_edge'] for row in initial)
    if map_only:
        from hashlib import sha256
        signature = sha256(repr(signature).encode()).hexdigest()[:20]
    scope = configuration_key(f'{network}_{signature}')
    state_key = f'road_volume_values_{scope}'
    if state_key not in st.session_state:
        st.session_state[state_key] = {row['from_edge']: float(row.get('vehicles_per_hour', 0)) for row in initial}
    values = st.session_state[state_key]
    if map_only:
        if selected_edge in values:
            info = details[selected_edge]
            st.markdown('**' + (info['street'] or 'Via sem nome cadastrado') + '**')
            st.caption(info['reference'] + ' · ' + info['approach'])
            input_key = f'road_rate_{scope}_{selected_edge}'
            if input_key not in st.session_state:
                st.session_state[input_key] = values[selected_edge]
            values[selected_edge] = st.number_input('Veículos por hora', min_value=0., step=10.,
                key=input_key, help='Quantidade de veículos inseridos por hora neste trecho e neste sentido. Zero não insere veículos.')
            st.caption('A alteração é guardada ao confirmar o campo. Clique em outra via para continuar.')
        result = pd.DataFrame([dict(row, vehicles_per_hour=values[row['from_edge']], to_edge='') for row in initial])
        if any(v is None or not math.isfinite(v) or v < 0 for v in values.values()):
            result.attrs['validation_error'] = 'Confira os volumes das vias: use números maiores ou iguais a zero.'
        return result
    crossings = list(dict.fromkeys(details[row['from_edge']]['crossing'] or 'Outras entradas' for row in initial))
    crossing = selected_crossing if selected_crossing in crossings else st.selectbox('Cruzamento para preencher os volumes', crossings, key=f'volume_crossing_{scope}')
    visible = [row['from_edge'] for row in initial if (details[row['from_edge']]['crossing'] or 'Outras entradas') == crossing]
    if selected_edge in visible:
        visible = [selected_edge]
    st.caption('Preencha os veículos por hora deste cruzamento. Os valores dos outros cruzamentos são mantidos ao trocar a seleção. As saídas são escolhidas automaticamente.')
    records = [{'Entrada': details[edge]['reference'], 'Via': details[edge]['street'] or 'Nome não cadastrado',
                'Sentido de chegada': details[edge]['approach'], 'vehicles_per_hour': values[edge]} for edge in visible]
    edited = st.data_editor(pd.DataFrame(records), hide_index=True, num_rows='fixed', width='stretch',
        disabled=['Entrada', 'Via', 'Sentido de chegada'], key=f'volume_editor_{scope}_{crossing}' + (f'_{selected_edge}' if selected_edge else ''),
        column_config={'vehicles_per_hour': st.column_config.NumberColumn('Veículos/h', min_value=0., step=10., required=True),
                       'Via': st.column_config.TextColumn(width='large'),
                       'Sentido de chegada': st.column_config.TextColumn(width='large')})
    for edge, value in zip(visible, edited['vehicles_per_hour']):
        values[edge] = float(value) if pd.notna(value) else None
    if selected_edge in visible:
        st.info(f"{details[selected_edge]['reference']} · {details[selected_edge]['street'] or 'Nome não cadastrado'} · {details[selected_edge]['approach']}")
    if show_map:
        selected = st.selectbox('Entrada a localizar', visible,
            format_func=lambda edge: f"{details[edge]['reference']} · {details[edge]['street'] or 'Nome não cadastrado'} · {details[edge]['approach']}",
            key=f'volume_map_entry_{scope}_{crossing}')
        render_map(network, selected, {edge: info['label'] for edge, info in details.items()}, incoming_ids)
    result = pd.DataFrame([dict(row, vehicles_per_hour=values[row['from_edge']], to_edge='') for row in initial])
    if any(v is None or not math.isfinite(v) or v < 0 for v in values.values()):
        result.attrs['validation_error'] = 'Preencha um volume válido, maior ou igual a zero, em todas as entradas. Use zero quando não houver veículos.'
        st.error(result.attrs['validation_error'])
    return result
