"""Apresentação do fluxo de trabalho, sem alterar configuração ou execução."""
import streamlit as st


def select_workflow_tab(label):
    st.session_state.ui_default_tab = label


def page_header():
    st.markdown('''<style>
    .block-container {max-width: 1360px; padding-top: 2rem; padding-bottom: 3rem;}
    h1 {letter-spacing: -.035em;}
    h2, h3 {letter-spacing: -.02em;}
    [data-testid="stMetric"] {background: rgba(100,140,160,.07); border: 1px solid rgba(100,140,160,.18); border-radius: 14px; padding: 16px;}
    [data-testid="stMetricLabel"] {font-size: .85rem;}
    [data-baseweb="tab-list"] {gap: .5rem; overflow-x: auto;}
    [data-baseweb="tab"] {padding: .8rem 1rem; white-space: nowrap;}
    [data-baseweb="tab"][aria-selected="true"] {background: rgba(15,118,110,.10); border-radius: 10px 10px 0 0;}
    [data-testid="stExpander"] {border-radius: 12px;}
    [data-testid="stSidebar"] {border-right: 1px solid rgba(100,140,160,.15);}
    .project-label {color: #0f9188; font-size: .8rem; font-weight: 700; letter-spacing: .16em; margin-bottom: .4rem;}
    @media (max-width: 700px) {.block-container {padding: 1rem;} [data-baseweb="tab"] {padding: .6rem .7rem;}}
    </style><div class="project-label">RONDON NORTE · MOBILIDADE URBANA</div>''', unsafe_allow_html=True)
    st.title('Laboratório de trânsito')
    st.caption('Configure o tráfego, treine o controle dos semáforos e compare os resultados com a referência.')
    with st.sidebar:
        st.subheader('Seu estudo de trânsito')
        st.caption('Siga as abas da esquerda para a direita.')
        st.markdown('**1. Cenário** — escolha os cruzamentos.\n\n**2. Tráfego** — informe volumes e período.\n\n**3. Treinamento** — configure e execute.\n\n**4. Resultados** — acompanhe e compare.')
        st.divider()


def configuration_summary(config, error=None):
    st.subheader('Confira antes de executar')
    if config is None:
        st.error(f'A configuração precisa de um ajuste: {error}')
        st.caption('Revise as abas Cenário e Tráfego. Os botões de execução ficam disponíveis quando a configuração estiver válida.')
        return
    count = len({target['name'] for target in config['targets']})
    window = config['measurement']
    algorithm = config.get('algorithm', 'PPO')
    from semaforos.algoritmos.registro import get_algorithm
    budget = config.get(get_algorithm(algorithm).config_key, {}).get('total_timesteps', 2048)
    columns = st.columns(4)
    columns[0].metric('Cruzamentos no estudo', count)
    columns[1].metric('Duração do episódio', f"{config['duration_seconds']:g} s")
    columns[2].metric('Tempo de medição', f"{window['end_seconds'] - window['start_seconds']:g} s")
    columns[3].metric('Passos de treinamento', f'{budget:,}'.replace(',', '.'))
    modes = {'random': 'Taxa total da rede', 'edge_volumes': 'Entradas por via',
             'observed_counts': 'Contagens observadas com calibração', 'flows': 'Origens e destinos'}
    st.caption(f"{algorithm} · {modes[config['demand']['mode']]} · Aquecimento: {window['warmup_seconds']:g} s · Medição: {window['start_seconds']:g}–{window['end_seconds']:g} s")
    if config['demand']['mode'] == 'observed_counts':
        st.info('Antes do treino, confira o ajuste em Tráfego e valide as passagens no SUMO. O ajuste das rotas, sozinho, não comprova calibração.')
