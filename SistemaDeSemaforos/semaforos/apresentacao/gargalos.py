"""Mapa e filtros de gargalos por cruzamento."""
import pandas as pd
import streamlit as st
import pydeck as pdk


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
