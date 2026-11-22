"""Mapa e filtros de gargalos por cruzamento."""
from math import isfinite

import pandas as pd
import pydeck as pdk
import streamlit as st


def _formatted_wait(value, signed=False):
    return format(value, '+,.1f' if signed else ',.1f').translate(str.maketrans(',.', '.,'))


def _wait_marks(rows, locations):
    marks = []
    for row in rows:
        name = row['intersection']
        status, symbol, color = 'Sem dados pareados', '?', [71, 85, 105]
        change = row['difference']
        details = 'Nenhum par válido'
        if change is not None:
            details = f"{_formatted_wait(row['before'])} → {_formatted_wait(row['after'])} veículo·s"
            if round(change, 1) < 0:
                status, symbol, color = 'Menos espera', '↓', [15, 118, 95]
            elif round(change, 1) > 0:
                status, symbol, color = 'Mais espera', '↑', [171, 60, 56]
            else:
                status, symbol = 'Sem diferença visível', '='
        location = {key: value for key, value in locations.get(name, {}).items()
                    if value is not None and isfinite(value)}
        marks.append({**row, **location, 'status': status, 'symbol': symbol, 'color': color, 'details': details})
    return marks


def render_wait_comparison(rows, locations, key):
    st.subheader('Espera por cruzamento')
    st.caption('Espera acumulada nas faixas de entrada, em veículo·s. Por exemplo, 10 veículos esperando 5 s somam 50 veículo·s.')
    marks = _wait_marks(rows, locations)
    by_name = {row['intersection']: row for row in marks}
    selection_key = f'{key}_intersection'
    georeferenced = [row for row in marks if {'longitude', 'latitude'} <= set(row)]
    if georeferenced:
        map_key = f'{key}_map'

        def select_intersection():
            selection = st.session_state.get(map_key, {}).get('selection', {})
            for item in selection.get('objects', {}).get('intersection-wait', []):
                if item.get('intersection') in by_name:
                    st.session_state[selection_key] = item['intersection']

        map_data = pd.DataFrame(georeferenced)
        deck = pdk.Deck(map_provider='carto', map_style='light',
            initial_view_state=pdk.ViewState(latitude=float(map_data.latitude.mean()),
                longitude=float(map_data.longitude.mean()), zoom=12.8),
            layers=[
                pdk.Layer('ScatterplotLayer', map_data, id='intersection-wait',
                    get_position='[longitude, latitude]', get_fill_color='color',
                    radius_units="'pixels'", get_radius=16, pickable=True, auto_highlight=True),
                pdk.Layer('TextLayer', map_data, id='intersection-wait-status',
                    get_position='[longitude, latitude]', get_text='symbol', get_color=[255, 255, 255],
                    get_size=16, character_set="'auto'"),
            ], tooltip={'text': '{intersection}\n{status}\n{details}'})
        st.pydeck_chart(deck, key=map_key, height=365, on_select=select_intersection, selection_mode='single-object')
        st.caption('↓ Menos espera · ↑ Mais espera · = Sem diferença visível · ? Sem dados pareados')
        if len(georeferenced) < len(marks):
            st.caption('Outros cruzamentos estão disponíveis na lista abaixo.')
    else:
        local = [row for row in marks if {'x_meters', 'y_meters'} <= set(row)]
        if local:
            st.scatter_chart(pd.DataFrame(local).rename(columns={'x_meters': 'Leste (m)', 'y_meters': 'Norte (m)'}),
                x='Leste (m)', y='Norte (m)', color='status', height=340)
        else:
            st.caption('As coordenadas deste relatório não estão disponíveis. Consulte a espera pela lista de cruzamentos.')
    crossing = st.selectbox('Cruzamento para detalhar', list(by_name), key=selection_key)
    selected = by_name[crossing]
    if selected['pairs']:
        before, after, change = st.columns(3)
        before.metric('Tempos iniciais', f"{_formatted_wait(selected['before'])} veículo·s")
        after.metric('Controle avaliado', f"{_formatted_wait(selected['after'])} veículo·s")
        delta = round(selected['difference'], 1) or 0
        change.metric(selected['status'], f"{_formatted_wait(delta, signed=bool(delta))} veículo·s")
        st.caption(f"Média de {selected['pairs']} par(es) com dados neste cruzamento. Posições aproximadas das entradas.")
    else:
        st.info('Não há simulações completas dos dois controles com dados de espera para este cruzamento.')


def render_bottlenecks(report, key):
    rows = report.get('bottlenecks', [])
    if not rows:
        return
    st.write('**Mapa de gargalos**')
    controllers = sorted({row['controller'] for row in rows})
    controller = st.selectbox('Controle exibido no mapa', controllers, key=f'{key}_map_controller')
    table = pd.DataFrame([row for row in rows if row['controller'] == controller])
    positions = table.dropna(subset=['longitude', 'latitude']) if {'longitude', 'latitude'} <= set(table) else pd.DataFrame()
    if not positions.empty:
        deck = pdk.Deck(layers=[pdk.Layer('ScatterplotLayer', positions, get_position='[longitude, latitude]',
            get_fill_color='color', get_radius=55, pickable=True)],
            initial_view_state=pdk.ViewState(latitude=float(positions.latitude.mean()), longitude=float(positions.longitude.mean()), zoom=13),
            tooltip={'text': '{intersection}\n{status}\nFila média: {mean_queue_vehicle_seconds} veículo·s\nPico: {peak_halted_vehicles} veículos'})
        st.pydeck_chart(deck, key=f'{key}_map')
    elif {'x_meters', 'y_meters'} <= set(table):
        st.scatter_chart(table, x='x_meters', y='y_meters', color='status')
        st.caption('Rede sem conversão geográfica disponível: exibindo coordenadas locais em metros.')
    st.caption('Verde: redução média de fila. Vermelho: aumento. Laranja/amarelo: indicador de bloqueio/transbordamento. Cinza: referência ou sem diferença. Posições aproximadas das entradas; as cores não comprovam significância estatística. O mapa pode exigir internet para carregar o fundo.')
    st.dataframe(table.drop(columns=['color'], errors='ignore'), hide_index=True)


def render_study(output, summary, key):
    if summary.get('kind') != 'repeated_study':
        return
    st.subheader('Treinamentos independentes e avaliações repetidas')
    st.metric('Repetições completas', f"{summary['completed_count']} / {summary['plan']['repetitions']}")
    st.caption(summary['scope'])
    if not summary['comparison_complete']:
        st.warning('Estudo incompleto. Repetições parciais não entram no agregado.')
    if summary.get('aggregate'):
        st.dataframe(pd.DataFrame(summary['aggregate']), hide_index=True)
    for name in ('study_plan.json', 'study_comparisons.csv', 'study_aggregate.csv', 'study_completed.json'):
        path = output / name
        if path.is_file():
            st.download_button(f'Exportar {name}', path.read_bytes(), file_name=name, key=f'{key}_{name}')
