"""Interface Streamlit do piloto PPO/SUMO.

Inicie com: streamlit run interface.py
"""
from semaforos.caminhos import PROJECT_ROOT

import json
import uuid
import io
from collections import deque
from pathlib import Path

import pandas as pd
import streamlit as st
import sumolib

from semaforos.cenario.configuracao import read_config
from semaforos.cenario.rede import network_programs, phase_action_spec
from semaforos.apresentacao.sinais import signal_presentation
from semaforos.arquivos import read_json
from semaforos.experimentos.tarefas import start_job as launch_job, saved_jobs, job_paths, job_state
from semaforos.apresentacao.diagnostico import render_diagnostics
from semaforos.apresentacao.layout import page_header, select_workflow_tab, preparation_summary, step_heading, section_label, readiness_panel, workflow_navigation
from semaforos.apresentacao.gargalos import render_study
from semaforos.apresentacao.resultados import result_overview, render_training_metrics
from semaforos.apresentacao.vias import identify_roads
from semaforos.apresentacao.estado import configuration_key, loaded_configuration_changed
from semaforos.apresentacao.layout import friendly_configuration_error
from semaforos.simulacao.janela import measurement_window
from semaforos.experimentos.repeticoes import study_plan
from semaforos.cenario.pedestres import crossing_routes
from semaforos.cenario.experimental import prepare_or_reuse, validate_experimental, preview_experimental, intersection_names
from semaforos.relatorios.catalogos import sumo_options, traci_getters, parameter_rows, metric_rows, training_workload
from semaforos.relatorios.legendas import parameter_legend, metric_legend, metric_column_label, metric_legend_rows, portuguese_metric_table, SUMO_CATEGORIES
from semaforos.algoritmos.registro import available_algorithms, get_algorithm


ROOT = PROJECT_ROOT
DEFAULT = ROOT / "config" / "cenario_rede_corrigida.json"
RESULTS = ROOT / "resultados"


@st.cache_data(show_spinner=False)
def installed_catalogs():
    version, options = sumo_options()
    return version, options, traci_getters()


def downloadable_table(rows, name, label):
    table = pd.DataFrame(rows)
    st.dataframe(table, hide_index=True, width="stretch", column_config={
        name: st.column_config.Column(metric_column_label(name), help=metric_legend(name)[1]) for name in table.columns})
    st.download_button(label, table.to_csv(index=False).encode("utf-8-sig"),
                       file_name=name, mime="text/csv", key=name)


def config_help(name):
    return parameter_legend(name)[1]


def render_result_metrics(path, key):
    try:
        table = pd.read_csv(path)
    except (pd.errors.EmptyDataError, pd.errors.ParserError, OSError):
        st.caption("A tabela está sendo gravada; aguarde a próxima atualização.")
        return
    st.dataframe(table, hide_index=True, width="stretch", column_config={
        name: st.column_config.Column(metric_column_label(name), help=metric_legend(name)[1])
        for name in table.columns})
    legend = pd.DataFrame(metric_legend_rows(table.columns))
    with st.expander(f"Legenda em português — {path.name}"):
        st.dataframe(legend, hide_index=True, width="stretch")
        st.download_button("Exportar legenda das colunas (.csv)", legend.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"{path.stem}_legenda_pt.csv", mime="text/csv", key=f"{key}_legend")
    st.download_button("Exportar métricas em português (.csv)",
                       portuguese_metric_table(table).to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"{path.stem}_pt.csv", mime="text/csv", key=f"{key}_pt")


@st.cache_data(show_spinner=False)
def road_options(network_path, target_ids):
    network_data = sumolib.net.readNet(network_path)
    edges = network_data.getEdges(withInternal=False)
    ids = sorted(edge.getID() for edge in edges if edge.allows("passenger")
                 and any(destination.allows('passenger') for destination in edge.getOutgoing()))
    exits = sorted(edge.getID() for edge in edges if not edge.getOutgoing() and edge.allows("passenger"))
    incoming = sorted({connection[0].getEdge().getID()
                       for light in network_data.getTrafficLights() if light.getID() in target_ids
                       for connection in light.getConnections()
                       if connection[0].getEdge().allows("passenger")})
    return ids, exits, incoming


@st.cache_data(show_spinner=False)
def road_details(network_path, targets, names_version=0):
    network_data = sumolib.net.readNet(network_path)
    names_file = ROOT / "dados/auditoria/nomes_vias_osm.json"
    osm_names = json.loads(names_file.read_text(encoding="utf-8"))["ways"] if names_file.exists() else {}
    details = identify_roads(network_data, targets, osm_names)
    return details


def road_labels(network_path, targets, names_version=0):
    return {edge: info['label'] for edge, info in road_details(network_path, targets, names_version).items()}


@st.cache_data(show_spinner=False)
def map_pedestrian_routes(network_path, version, targets):
    return crossing_routes(network_path, [{'tls_id': tls, 'name': name} for tls, name in targets])




def start_job(command, config, model=None):
    st.session_state.job = launch_job(config, command, RESULTS, model)
    select_workflow_tab('4 · Resultados')


st.set_page_config(page_title="Semáforos Rondon Norte", layout="wide")
page_header()
scenario_tab, demand_tab, training_tab, results_tab, advanced_tab = workflow_navigation()
with scenario_tab:
    step_heading(1, 'Rede da simulação', 'O mapa usa a rede completa, com os nove cruzamentos controlados em conjunto.')

with st.sidebar:
    with st.expander("Acompanhar ou recuperar uma execução", expanded=False):
        jobs = saved_jobs(RESULTS)
        current_folder = str(st.session_state['job']['folder']) if 'job' in st.session_state else ''
        if not current_folder:
            current_folder = next((str(j['folder']) for j in jobs if job_state(j)['status'] in ('starting', 'running')), '')
        choices = [''] + [str(j['folder']) for j in jobs]
        followed = st.selectbox('Execução para acompanhar', choices,
            index=choices.index(current_folder) if current_folder in choices else 0,
            format_func=lambda p: Path(p).name if p else 'Nenhuma execução selecionada', key=f'follow_{current_folder}')
        if followed:
            st.session_state.job = job_paths(followed)
            st.caption('O processo continua ao atualizar a página. Este seletor recupera o acompanhamento; não reinicia nem retoma um treinamento encerrado.')
            if st.button('Carregar configurações desta execução'):
                loaded = read_config(Path(followed) / 'cenario.json')
                loaded_configuration_changed()
                st.session_state.loaded_config = loaded
                if loaded.get('experimental'):
                    st.session_state.experimental_config = loaded
                    st.session_state.experimental_rows = validate_experimental(loaded)
                else:
                    st.session_state.pop('experimental_config', None)
                    st.session_state.pop('experimental_rows', None)
        else:
            st.session_state.pop('job', None)

with scenario_tab:
    base = st.session_state.get('loaded_config') or read_config(DEFAULT)
    names = intersection_names()
    st.caption('Controle conjunto dos nove cruzamentos da rede.')
    joint = True
    experimental_ready = False
    if joint:
        prepared_names = {t['name'] for t in st.session_state.get('experimental_config', {}).get('targets', [])}
        if set(names) != prepared_names:
            try:
                with st.spinner('Carregando a rede completa do mapa...'):
                    prepared, rows, _ = prepare_or_reuse(base, RESULTS)
                    prepared['duration_seconds'] = base['duration_seconds']
                    st.session_state.experimental_config = prepared
                    st.session_state.experimental_rows = rows
            except Exception as error:
                st.error(friendly_configuration_error(error))
        st.caption("A rede experimental inclui os movimentos, as travessias e os tempos de segurança dos nove cruzamentos.")
        if st.button("Preparar simulação", type="primary"):
            try:
                with st.spinner("Preparando a simulação e verificando os movimentos..."):
                    prepared, rows, _ = prepare_or_reuse(base, RESULTS)
                    st.session_state.experimental_config = prepared
                    st.session_state.experimental_rows = rows
                st.success("Simulação dos nove cruzamentos pronta.")
            except Exception as error:
                st.error(friendly_configuration_error(error))
        prepared_names = {t['name'] for t in st.session_state.get('experimental_config', {}).get('targets', [])}
        wanted_names = set(names)
        if wanted_names <= prepared_names:
            base = st.session_state.experimental_config
            selected_rows = validate_experimental(base)
            experimental_ready = True
            st.caption(f"{len({t['name'] for t in base['targets']})} cruzamento(s) e {len(base['targets'])} controlador(es) selecionados. Verificação da simulação, sem certificação em campo.")
            timing_labels = road_labels(str(base['network']), tuple((t['tls_id'], t['name']) for t in base['targets']))
            with st.expander('Consultar os tempos iniciais e os movimentos no mapa'):
                preparation_summary(selected_rows, base['experimental'].get('external_repaired', []),
                                    signal_presentation(base, timing_labels))
            if base["experimental"]["method"] == "serial_links_v1":
                st.warning("Este cenário salvo usa atendimento serial antigo. Prepare um cenário novo para utilizar movimentos agrupados e correções externas.")
            st.caption("Para observar um ciclo completo de todos os controladores, use uma duração de simulação maior que o maior ciclo inicial da tabela.")
        else:
            if base.get('experimental'):
                base = read_config(DEFAULT)
            st.warning("Clique em Preparar simulação antes de iniciar o treinamento.")
    network = str(base["network"])
    plans = str(base["plans"])
    if not joint or experimental_ready:
        st.success('Cenário pronto. O próximo passo é informar os veículos e a duração da simulação.')
    st.caption('Rede experimental com tempos de sinais preparados para a pesquisa. As contagens da Settran ainda são aguardadas; os volumes informados por você representam hipóteses do estudo.')



with scenario_tab:
    st.divider()
    st.button('Continuar: configurar o tráfego', on_click=select_workflow_tab, args=('2 · Tráfego',), type='primary', disabled=joint and not experimental_ready)

import copy
limits_config = copy.deepcopy(base)
limits_config.setdefault('control', dict(base['ppo']))['action_mode'] = 'phase_durations'
programs = network_programs(network)
selected_specs = phase_action_spec(limits_config, programs)[1]
max_yellow = max(s['durations_seconds'][1] for s in selected_specs if s['kind'] == 'yellow')
max_clearance = max(s['durations_seconds'][1] for s in selected_specs if s['kind'] == 'all_red')
maximum_cycle = float(base.get('control', base['ppo']).get('maximum_cycle_seconds', 3600))

@st.fragment
def traffic_configuration():
    step_heading(2, 'Configure pelo mapa', 'Selecione semáforos, vias e travessias. Os ajustes aparecem no painel ao lado.')
    demand_mode = 'Volume por via'
    if base['demand']['mode'] != 'edge_volumes' and st.session_state.get('loaded_config'):
        st.caption('Informe os volumes por via no mapa. A quantidade total da execução antiga não é distribuída automaticamente entre as vias.')
    road_table = None
    profile_table = None
    pedestrian_table = None
    pedestrian_enabled = False
    pedestrian_speed = float(base.get('pedestrians', {}).get('walking_speed_meters_per_second', .8))
    phase_table = None
    if not joint or experimental_ready:
        try:
            edge_ids, exit_ids, incoming_ids = road_options(network, tuple(t['tls_id'] for t in base['targets']))
            by_edge = {row['from_edge']: row for row in base['demand'].get('edge_volumes', [])}
            initial = [by_edge.get(edge, {'from_edge': edge, 'vehicles_per_hour': 0., 'to_edge': ''}) for edge in edge_ids]
            names_file = ROOT / 'dados/auditoria/nomes_vias_osm.json'
            details = road_details(network, tuple((t['tls_id'], t['name']) for t in base['targets']),
                names_file.stat().st_mtime_ns if names_file.exists() else 0)
            ped_routes = map_pedestrian_routes(network, Path(network).stat().st_mtime_ns,
                tuple((t['tls_id'], t['name']) for t in base['targets']))
            saved_pedestrians = {(row['intersection'], row['from_edge'], row['to_edge']): row['persons_per_hour']
                                 for row in base.get('pedestrians', {}).get('flows', [])}
            defaults = [{**row, 'persons_per_hour': saved_pedestrians.get((row['intersection'], row['from_edge'], row['to_edge']), 0.)}
                        for row in ped_routes]
            from semaforos.apresentacao.mapa_configuracao import render_configuration_map
            road_table, pedestrian_table, phase_table, pedestrian_enabled, pedestrian_speed = render_configuration_map(
                base, initial, details, incoming_ids, selected_specs,
                {edge: info['reference'] + ' · ' + (info['street'] or 'Nome não cadastrado') for edge, info in details.items()}, defaults,
                volume_by_road=demand_mode == 'Volume por via')
        except Exception as error:
            st.error(friendly_configuration_error(error))
    else:
        st.info('Prepare o cenário selecionado para configurar os locais pelo mapa.')
    duration_options = {'300 s': 300, '600 s': 600, '900 s': 900}
    section_label('Duração de cada simulação')
    default_duration = next((label for label, seconds in duration_options.items() if seconds == int(base['duration_seconds'])), 'Personalizar')
    duration_choice = st.radio('Por quanto tempo simular?', list(duration_options) + ['Personalizar'],
        index=(list(duration_options) + ['Personalizar']).index(default_duration), horizontal=True, key=configuration_key('Por quanto tempo simular?'))
    if duration_choice == 'Personalizar':
        duration = st.number_input('Duração da simulação (segundos)', min_value=10,
            value=int(base['duration_seconds']), step=10, key=configuration_key('Duração da simulação (segundos)'))
    else:
        duration = duration_options[duration_choice]
    st.caption('Esse é o tempo de trânsito de cada simulação, não o tempo de espera no computador.')
    with st.expander('Avançado: precisão e aquecimento'):
        step_seconds = st.number_input("Passo do SUMO (s)", min_value=0.1,
            value=float(base["step_seconds"]), step=0.1,
            help='Quanto o relógio do simulador avança a cada atualização. Com 1 s, posições e filas são atualizadas a cada segundo simulado. Não é o tamanho do treinamento.', key=configuration_key('Passo do SUMO (s)'))
        st.caption('Passo do simulador: com 1 s, o trânsito é atualizado de segundo em segundo. Um passo menor faz mais atualizações e pode tornar a execução mais lenta.')
        warmup_seconds = st.number_input('Aquecimento sem atuação do algoritmo (s)', min_value=0.0, max_value=float(duration),
            value=min(float(base.get('measurement', {}).get('warmup_seconds', 0)), float(duration)), step=float(step_seconds),
            help='Tempo inicial para os veículos começarem a ocupar a rede. Os sinais seguem os tempos iniciais; o algoritmo ainda não atua e esse período fica fora dos indicadores.', key=configuration_key('Aquecimento sem atuação do algoritmo (s)'))
        st.caption('Aquecimento: período inicial para o trânsito se formar. Zero começa sem essa espera; 60 s deixa o trânsito circular por um minuto antes da atuação do algoritmo.')
        measurement_start, measurement_end = warmup_seconds, float(duration)
        st.info(f'A simulação dura {duration} s. Os indicadores são coletados do segundo {measurement_start:g} ao {measurement_end:g}: {max(0, measurement_end - measurement_start):g} s de medição. O aquecimento dura {warmup_seconds:g} s e não entra nessa medição.')
    if demand_mode == "Volume por via":
        vary_flow = st.toggle("Variar o fluxo ao longo da simula\u00e7\u00e3o?", value=bool(base["demand"].get("time_profile")), key=configuration_key('Variar o fluxo ao longo da simulação?'))
        if vary_flow:
            from semaforos.apresentacao.fluxo import flow_profile_editor
            profile_total = sum(int(float(v) * duration / 3600 + .5) for v in
                pd.to_numeric(road_table['vehicles_per_hour'], errors='coerce').fillna(0)) if road_table is not None else 0
            entry_counts = [int(float(v) * duration / 3600 + .5) for v in
                pd.to_numeric(road_table['vehicles_per_hour'], errors='coerce').fillna(0)] if road_table is not None else []
            profile_table = flow_profile_editor(duration, base["demand"].get("time_profile"),
                key=f"flow_{network}", planned_vehicles=profile_total, entry_counts=entry_counts)
    if road_table is not None:
        rates = pd.to_numeric(road_table["vehicles_per_hour"], errors="coerce").fillna(0)
        if rates.sum() == 0:
            st.warning("Todos os volumes estão em zero. Preencha pelo menos uma entrada para gerar tráfego neste cenário.")
    st.session_state['traffic_configuration_values'] = {
        'demand_mode': demand_mode,
        'road_table': road_table,
        'profile_table': profile_table,
        'phase_table': phase_table,
        'pedestrian_table': pedestrian_table,
        'pedestrian_enabled': pedestrian_enabled,
        'pedestrian_speed': pedestrian_speed,
        'duration': duration,
        'step_seconds': step_seconds,
        'warmup_seconds': warmup_seconds,
        'measurement_start': measurement_start,
        'measurement_end': measurement_end,
    }

with demand_tab:
    traffic_configuration()
traffic_values = st.session_state['traffic_configuration_values']
(demand_mode, road_table, profile_table, phase_table, pedestrian_table,
 pedestrian_enabled, pedestrian_speed, duration, step_seconds, warmup_seconds,
 measurement_start, measurement_end) = (
    traffic_values[name] for name in (
        'demand_mode', 'road_table', 'profile_table', 'phase_table', 'pedestrian_table',
        'pedestrian_enabled', 'pedestrian_speed', 'duration', 'step_seconds',
        'warmup_seconds', 'measurement_start', 'measurement_end'))

with training_tab:
    step_heading(3, 'Treinamento', 'Escolha o objetivo e a quantidade de prática do algoritmo.')
    algorithm_names = available_algorithms()
    if len(algorithm_names) == 1:
        selected_algorithm = algorithm_names[0]
        st.caption(f'Algoritmo: {selected_algorithm}')
    else:
        selected_algorithm = st.selectbox('Qual algoritmo usar?', algorithm_names,
            index=algorithm_names.index(base.get('algorithm', 'PPO')), key=configuration_key('Qual algoritmo usar?'))
    priorities = {'Equilibrar os resultados': {'waiting': 1.0, 'queues': 1.0, 'travel': 1.0},
                  'Diminuir a espera': {'waiting': 2.0, 'queues': 1.0, 'travel': 1.0},
                  'Diminuir as filas': {'waiting': 1.0, 'queues': 2.0, 'travel': 1.0}}
    current_objectives = base.get('objectives', priorities['Equilibrar os resultados'])
    custom_objectives = current_objectives not in list(priorities.values())
    default_priority = next((name for name, weights in priorities.items() if weights == current_objectives), 'Equilibrar os resultados')
    priority = st.selectbox('Objetivo do treinamento', list(priorities), index=list(priorities).index(default_priority), key=configuration_key('Objetivo do treinamento'))
    weights = current_objectives if custom_objectives else priorities[priority]
    w_wait, w_queue, w_travel = (float(weights.get(k, 1)) for k in ('waiting', 'queues', 'travel'))
    algorithm_budget = int(base.get(get_algorithm(selected_algorithm).config_key, {}).get('total_timesteps', 2048))
    total_steps = st.number_input('Quantidade de decisões para treinar', min_value=2,
        value=algorithm_budget, step=128, help=config_help('total_timesteps'), key=configuration_key('Quantidade de decisões para treinar'))
    st.caption('Mais decisões dão mais prática ao algoritmo e aumentam o tempo de treinamento.')
    gui = st.toggle('Ver simulação durante o treino', value=False, key=configuration_key('Ver simulação durante o treino'))
    gui_delay = int(base.get('control', base['ppo']).get('gui_delay_milliseconds', 0))
    if gui:
        gui_delay = st.number_input('Atraso da visualização (ms por passo)', min_value=0, max_value=2000,
            value=gui_delay, step=10, help='Zero executa o mais rápido possível. Aumente para observar os movimentos mais devagar.', key=configuration_key('Atraso da visualização (ms por passo)'))
    with st.expander("Configurações avançadas"):
        st.caption("Sementes tornam o estudo reproduzível. Use valores diferentes para treino e avaliação. Os pesos indicam quais objetivos o algoritmo prioriza.")
        seed = st.number_input("Semente", min_value=0, value=int(base["seeds"][0]), help=config_help("seeds"), key=configuration_key('Semente'))
        evaluation_seeds = st.text_input("Sementes de avaliação (separadas por vírgula)",
                                         value=", ".join(map(str, base.get("evaluation", {}).get("seeds", [101, 102, 103]))), help=config_help("evaluation.seeds"), key=configuration_key('Sementes de avaliação (separadas por vírgula)'))
        algorithm_parameters_text = "{}"
        if selected_algorithm != "PPO":
            algorithm_parameters_text = st.text_area("Parâmetros específicos do algoritmo (JSON)", value="{}",
                help="Objeto com parâmetros aceitos pelo adaptador do algoritmo. Épocas e minibatches abaixo são específicos do PPO.", key=configuration_key('Parâmetros específicos do algoritmo (JSON)'))
        custom_weights = st.checkbox('Personalizar pesos do objetivo', value=custom_objectives, key=configuration_key('Personalizar pesos do objetivo'))
        if not custom_weights:
            w_wait, w_queue, w_travel = (float(priorities[priority][k]) for k in ('waiting', 'queues', 'travel'))
        if custom_weights:
            w_wait = st.number_input("Prioridade: espera", min_value=0.0, value=w_wait, step=0.1, help=config_help("objectives.waiting"), key=configuration_key('Prioridade: espera'))
            w_queue = st.number_input("Prioridade: filas", min_value=0.0, value=w_queue, step=0.1, help=config_help("objectives.queues"), key=configuration_key('Prioridade: filas'))
            w_travel = st.number_input("Prioridade: tempo de viagem (aproximação)", min_value=0.0, value=w_travel, step=0.1, help=config_help("objectives.travel"), key=configuration_key('Prioridade: tempo de viagem (aproximação)'))
        decision = st.number_input("Intervalo de decisão (s)", min_value=1, value=int(base["ppo"]["decision_seconds"]), help=config_help("decision_seconds"), key=configuration_key('Intervalo de decisão (s)'))
        n_epochs = st.number_input("Épocas por lote", min_value=1, value=int(base["ppo"]["n_epochs"]), help=config_help("n_epochs"), disabled=selected_algorithm != "PPO", key=configuration_key('Épocas por lote'))
        n_steps = st.number_input("Passos por coleta", min_value=2, value=int(base["ppo"]["n_steps"]), help=config_help("n_steps"), disabled=selected_algorithm != "PPO", key=configuration_key('Passos por coleta'))
        batch_size = st.number_input("Tamanho do minibatch", min_value=2, value=int(base["ppo"]["batch_size"]), help=config_help("batch_size"), disabled=selected_algorithm != "PPO", key=configuration_key('Tamanho do minibatch'))
        detailed_analysis = st.checkbox('Coletar análise detalhada', value=False, key=configuration_key('Coletar análise detalhada'))
        with st.expander('Indicadores e critérios da análise detalhada'):
            collect_lane = st.checkbox("Velocidade e ocupação das faixas", value=True, help=config_help("collect_lane_details"), disabled=not detailed_analysis, key=configuration_key('Velocidade e ocupação das faixas'))
            collect_emissions = st.checkbox("CO₂, CO, HC, NOx, partículas, combustível e eletricidade", value=False, help=config_help("collect_emissions"), key=configuration_key('CO₂, CO, HC, NOx, partículas, combustível e eletricidade'))
            collect_events = st.checkbox("Teletransportes e colisões", value=True, help=config_help("collect_events"), key=configuration_key('Teletransportes e colisões'))
            collect_resources = st.checkbox("CPU e memória", value=True, help=config_help("collect_resources"), key=configuration_key('CPU e memória'))
            collect_extended = st.checkbox('Faixas, movimentos, filas em metros e bloqueios', value=base.get('metrics', {}).get('collect_extended', True), disabled=not detailed_analysis, key=configuration_key('Faixas, movimentos, filas em metros e bloqueios'))
            collect_dynamics = st.checkbox('Frenagens, paradas, velocidade e TTC exploratório', value=base.get('metrics', {}).get('collect_vehicle_dynamics', True), disabled=not collect_extended, key=configuration_key('Frenagens, paradas, velocidade e TTC exploratório'))
            collect_classes = st.checkbox('Separar indicadores por classe de veículo', value=base.get('metrics', {}).get('collect_vehicle_classes', True), disabled=not collect_extended, key=configuration_key('Separar indicadores por classe de veículo'))
            thresholds = dict(base.get('metrics', {}).get('thresholds', {}))
            thresholds['spillback_occupancy_percent'] = st.number_input('Ocupação para indicar transbordamento (%)', min_value=1.0, max_value=100.0, value=float(thresholds.get('spillback_occupancy_percent', 80)), key=configuration_key('Ocupação para indicar transbordamento (%)'))
            thresholds['downstream_occupancy_percent'] = st.number_input('Ocupação da saída para indicar bloqueio (%)', min_value=1.0, max_value=100.0, value=float(thresholds.get('downstream_occupancy_percent', 80)), key=configuration_key('Ocupação da saída para indicar bloqueio (%)'))
            thresholds['long_wait_seconds'] = st.number_input('Espera considerada longa (s)', min_value=1.0, value=float(thresholds.get('long_wait_seconds', 120)), key=configuration_key('Espera considerada longa (s)'))
            thresholds['hard_braking_meters_per_second_squared'] = st.number_input('Desaceleração para frenagem forte (m/s²)', min_value=0.1, value=float(thresholds.get('hard_braking_meters_per_second_squared', 4)), key=configuration_key('Desaceleração para frenagem forte (m/s²)'))
            thresholds['ttc_seconds'] = st.number_input('Limiar de TTC longitudinal exploratório (s)', min_value=0.1, value=float(thresholds.get('ttc_seconds', 1.5)), key=configuration_key('Limiar de TTC longitudinal exploratório (s)'))
            st.caption('Detalhes adicionais aumentam o custo de coleta. Bloqueio é um indicador baseado em verde, veículos parados e ocupação da saída; TTC não certifica risco de acidente. Limiares são configuráveis e ficam registrados.')
    st.caption('Os limites dos semáforos são configurados no mapa, na aba Tráfego.')
    collect_lane = detailed_analysis and collect_lane
    collect_extended = detailed_analysis and collect_extended
    collect_dynamics = collect_extended and collect_dynamics
    collect_classes = collect_extended and collect_classes



def configured():
    if phase_table is None:
        raise ValueError("Prepare o cenário e confira os ajustes dos semáforos no mapa antes de executar.")
    if joint and not experimental_ready:
        raise ValueError("Prepare o cenário selecionado antes de executar")
    config = dict(base)
    config["network"] = str(Path(network).resolve())
    config["plans"] = str(Path(plans).resolve())
    if demand_mode == "Volume por via":
        if road_table is None:
            raise ValueError("Selecione uma rede válida para preencher as vias")
        if road_table.attrs.get('validation_error'):
            raise ValueError(road_table.attrs['validation_error'])
        if profile_table is not None and profile_table.attrs.get('validation_error'):
            raise ValueError(profile_table.attrs['validation_error'])
        profile = profile_table.dropna(how="all").to_dict("records") if profile_table is not None else []
        vehicle_types = [dict(row) for row in base["demand"].get("vehicle_types", [])]
        entries = []
        for row in road_table.to_dict("records"):
            if not row.get("from_edge") or pd.isna(row["from_edge"]):
                continue
            entry = {"from_edge": row["from_edge"],
                            "vehicles_per_hour": float(row.get("vehicles_per_hour") or 0),
                            "to_edge": row.get("to_edge") or ""}
            entries.append(entry)
        config["demand"] = {"mode": "edge_volumes", "edge_volumes": entries}
        if profile:
            config["demand"]["time_profile"] = profile
        if vehicle_types:
            config["demand"]["vehicle_types"] = vehicle_types
    config["demand"]["synthetic"] = True
    if w_wait + w_queue + w_travel <= 0:
        raise ValueError("Escolha ao menos uma prioridade positiva")
    config["objectives"] = {"waiting": float(w_wait), "queues": float(w_queue), "travel": float(w_travel)}
    config["duration_seconds"] = int(duration)
    config['measurement'] = {'warmup_seconds': float(warmup_seconds), 'start_seconds': float(measurement_start), 'end_seconds': float(measurement_end)}
    if pedestrian_enabled:
        if pedestrian_table is None:
            raise ValueError('Prepare uma rede com travessias antes de ativar pedestres')
        if pedestrian_table.attrs.get('validation_error'):
            raise ValueError(pedestrian_table.attrs['validation_error'])
        ped_flows = [row for row in pedestrian_table.to_dict('records') if float(row.get('persons_per_hour', 0)) > 0]
        if not ped_flows or sum(int(row['persons_per_hour'] * duration / 3600 + 0.5) for row in ped_flows) == 0:
            raise ValueError('Preencha pessoas/h suficientes para gerar ao menos um pedestre no episódio')
        config['pedestrians'] = {'enabled': True, 'walking_speed_meters_per_second': pedestrian_speed,
                                'synthetic': True, 'flows': ped_flows}
    else:
        config['pedestrians'] = {'enabled': False}
    if config['demand']['mode'] == 'edge_volumes' and not config['pedestrians']['enabled']:
        planned_vehicles = sum(int(row['vehicles_per_hour'] * duration / 3600 + .5) for row in config['demand']['edge_volumes'])
        if planned_vehicles <= 0:
            raise ValueError('Informe veículos por hora em pelo menos uma entrada para gerar tráfego nesta duração de simulação')
    config["step_seconds"] = float(step_seconds)
    config["seeds"] = [int(seed)]
    try:
        parsed_seeds = [int(item.strip()) for item in evaluation_seeds.split(",") if item.strip()]
    except ValueError:
        raise ValueError('Informe sementes de avaliação como números inteiros separados por vírgulas') from None
    if not parsed_seeds or len(set(parsed_seeds)) != len(parsed_seeds) or int(seed) in parsed_seeds:
        raise ValueError("Informe sementes de avaliação distintas e diferentes da semente do treino")
    config["evaluation"] = {"seeds": parsed_seeds}
    config["metrics"] = {"collect_lane_details": collect_lane,
                         'collect_extended': collect_extended, 'collect_vehicle_dynamics': collect_dynamics,
                         'collect_vehicle_classes': collect_classes,
                         'thresholds': thresholds,
                         "collect_emissions": collect_emissions,
                         "collect_events": collect_events,
                         "collect_resources": collect_resources,
                         "collect_actions": True}
    config["ppo"] = {**base["ppo"], "decision_seconds": int(decision), "n_epochs": int(n_epochs),
                     "n_steps": int(n_steps), "batch_size": int(batch_size),
                     "total_timesteps": int(total_steps), "gui": bool(gui),
                     "action_mode": "adaptive_signals",
                     "phase_types": ["green", "yellow", "all_red"],
                     "duration_limits": {"yellow": {"maximum_seconds": float(max_yellow)},
                                         "all_red": {"maximum_seconds": float(max_clearance)}},
                     "phase_duration_bounds": {row["key"]: {"minimum_seconds": float(row["minimum_seconds"]),
                                                             "maximum_seconds": min(float(row["maximum_seconds"]), float(max_yellow) if row["type"] == "Amarelo" else float(max_clearance) if row["type"] == "Intervalo de segurança" else float(row["maximum_seconds"]))}
                                               for row in phase_table.to_dict("records")}, "maximum_cycle_seconds": float(maximum_cycle)}
    config["algorithm"] = selected_algorithm
    config["control"] = {key: config["ppo"][key] for key in (
        "decision_seconds", "gui", "action_mode", "phase_types", "duration_limits", "phase_duration_bounds", "maximum_cycle_seconds")}
    config['control']['gui_delay_milliseconds'] = int(gui_delay)
    if joint:
        # Os pisos geométricos não são removidos por ajustes avançados na interface.
        floors = base["experimental"]["minimum_durations"]
        for key, floor in base["experimental"]["green_floors"].items():
            bounds = config["control"]["phase_duration_bounds"].setdefault(key, {})
            bounds["minimum_seconds"] = max(floor, bounds.get("minimum_seconds", floor))
        largest_clearance = max(value for key, value in floors.items() if int(key.rsplit(":", 1)[1]) % 3 == 2)
        config["control"]["duration_limits"]["all_red"]["maximum_seconds"] = max(float(max_clearance), largest_clearance)
        config["ppo"].update(config["control"])
    if selected_algorithm != "PPO":
        parameters = json.loads(algorithm_parameters_text)
        if not isinstance(parameters, dict):
            raise ValueError("Parâmetros específicos devem ser um objeto JSON")
        key = get_algorithm(selected_algorithm).config_key
        config[key] = {**base.get(key, {}), **parameters, "total_timesteps": int(total_steps)}
    if joint:
        validate_experimental(config)
    measurement_window(config)
    phase_action_spec(config, programs)
    if demand_mode == "Volume por via":
        from semaforos.cenario.demanda import validate_time_profile, validate_vehicle_types
        validate_time_profile(config)
        validate_vehicle_types(config)
    return config


with advanced_tab:
    st.subheader("Referência técnica")
    st.caption("Consulta opcional. Você não precisa alterar estes catálogos para iniciar um treino.")
    with st.expander('Dicionário rápido: o que significam os termos?'):
        st.markdown('**Simulação:** uma execução que representa o trânsito durante o período escolhido.\n\n**Treinamento:** repetição de simulações para o algoritmo aprender.\n\n**Decisão:** escolha feita pelo algoritmo para controlar os sinais.\n\n**Etapa:** movimentos que recebem verde juntos.\n\n**Ciclo:** sequência completa das etapas de um conjunto de semáforos.\n\n**Avaliação:** comparação do modelo treinado com os tempos iniciais, em simulações reservadas para esse fim.')
    tab_options, tab_parameters, tab_metrics = st.tabs(["Opções SUMO", "Parâmetros de treinamento", "Dicionário de métricas"])
configuration_error = None

try:
    current_config = configured()
except (ValueError, TypeError, KeyError) as error:
    current_config = None
    configuration_error = friendly_configuration_error(error)

with tab_options:
    version, options, queries = installed_catalogs()
    st.caption(f"{version}: {len(options)} opções CLI em {len({row['categoria'] for row in options})} categorias. Catálogo gerado pelo executável instalado.")
    st.info("Esta tabela inclui todas as opções do executável SUMO. Atributos XML de redes, veículos e modelos e opções de outras ferramentas têm catálogos próprios. Apenas os campos da interface são editáveis aqui; o catálogo não aplica opções automaticamente.")
    category = st.selectbox("Categoria SUMO", ["Todas"] + sorted({row["categoria"] for row in options}),
                            format_func=lambda name: SUMO_CATEGORIES.get(name, name))
    with st.expander("Legenda das categorias e tipos SUMO"):
        st.dataframe(pd.DataFrame([{"categoria técnica": name, "significado em português": label}
                                  for name, label in SUMO_CATEGORIES.items()]), hide_index=True)
        st.write("BOOL = verdadeiro/falso; INT = inteiro; FLOAT = número decimal; TIME = tempo; STR = texto; FILE = arquivo. O nome da opção e a descrição original SUMO são preservados para consulta técnica.")
    search = st.text_input("Pesquisar opção ou descrição SUMO")
    selected = [row for row in options if (category == "Todas" or row["categoria"] == category)
                and search.casefold() in " ".join(str(value) for value in row.values()).casefold()]
    st.dataframe(pd.DataFrame(selected), hide_index=True, width="stretch")
    st.download_button("Baixar catálogo completo SUMO", pd.DataFrame(options).to_csv(index=False).encode("utf-8-sig"),
                       "sumo_options.csv", "text/csv")

with tab_parameters:
    st.caption("A coluna ‘legenda em português’ explica cada configuração. Passe o mouse no ícone de ajuda dos campos para ver seu significado.")
    st.write("`n_epochs=10` faz dez passagens de otimização por coleta. Episódios são execuções do SUMO; `total_timesteps` determina o orçamento do treino.")
    if current_config is not None:
        try:
            workload = training_workload(current_config)
            st.dataframe(pd.DataFrame([{"quantidade": name, "valor": value} for name, value in workload.items()]), hide_index=True)
            st.caption("Previsão para um ambiente, sem cancelamento ou interrupção por KL. Passos são arredondados para coletas completas; episódios dependem do horizonte e intervalo de decisão.")
        except ValueError as error:
            st.error(friendly_configuration_error(error))
        downloadable_table(parameter_rows(current_config), "effective_parameters.csv", "Baixar todos os parâmetros atuais")
        st.download_button("Baixar cenário atual", json.dumps(current_config, ensure_ascii=False, indent=2, default=str),
                           "cenario.json", "application/json")
        st.caption("Inclui cada campo do cenário, todos os argumentos do construtor PPO e opções enviadas ao SUMO. O comando e a semente reais de cada episódio ficam em run_config.json; manifest.json registra versões e hashes.")
    benchmark_path = ROOT / "dados/auditoria/benchmark_ppo_10_epocas.json"
    if benchmark_path.is_file():
        st.write("Medição local de viabilidade computacional")
        st.json(json.loads(benchmark_path.read_text(encoding="utf-8")))
    st.warning("Tempo de execução viável não demonstra convergência. Use demanda representativa e avaliação independente. O cenário conjunto usa programas sintéticos, sem reproduzir os planos reais.")

with tab_metrics:
    st.info("1 veículo·s equivale a um veículo durante um segundo. Exemplo: 10 veículos parados durante 30 s = 300 veículo·s. P95 é o percentil 95; uma célula vazia significa ausência de valor válido, não zero.")
    if current_config is not None:
        downloadable_table(metric_rows(current_config), "metrics_catalog.csv", "Baixar tabela de métricas coletadas")
    st.caption("A avaliação exporta runs.csv, signals.csv, aggregate.csv, comparison.png, report.md e summary.json. Viagens incompletas são contadas, mas ficam fora das estatísticas de viagem; std de viagens é populacional e std entre execuções é amostral.")
    with st.expander(f"Todas as consultas TraCI disponíveis na instalação ({len(queries)})"):
        st.write("Inventário da API, incluindo identificadores, geometria e estruturas. A disponibilidade de uma consulta não significa que ela esteja no relatório; detectores e pedestres dependem dos elementos da rede.")
        domain = st.selectbox("Domínio TraCI", ["Todos"] + sorted({row["domínio"] for row in queries}))
        st.dataframe(pd.DataFrame([row for row in queries if domain == "Todos" or row["domínio"] == domain]), hide_index=True)
        st.download_button("Baixar catálogo completo TraCI", pd.DataFrame(queries).to_csv(index=False).encode("utf-8-sig"),
                           "traci_queries.csv", "text/csv")

active = any(job_state(job)['status'] in ('starting', 'running') for job in saved_jobs(RESULTS))
readiness_panel(current_config, configuration_error, active)
with demand_tab:
    section_label('Conferir antes de treinar')
    st.caption('Opcional: observe o cenário ou simule com os tempos iniciais. Para treinar diretamente, use Continuar abaixo.')
    if st.button("Simular com os tempos iniciais", disabled=active, type="primary"):
        try:
            start_job("run-reference", configured())
            st.rerun()
        except Exception as error:
            st.error(friendly_configuration_error(error))
    if st.button("Ver uma prévia de 30 segundos", disabled=active):
        try:
            with st.spinner("Executando teste curto no SUMO…"):
                preview_config = configured()
                preview_config['control'] = {**preview_config['control'], 'gui': True, 'gui_delay_milliseconds': 100}
                preview = preview_experimental(preview_config, RESULTS / f"preview_nove_{uuid.uuid4().hex[:12]}")
            st.success("Prévia concluída. Ela confere o funcionamento, sem medir melhora do trânsito nem percorrer necessariamente todos os ciclos.")
            with st.expander("Detalhes técnicos da prévia"):
                st.json({key: value for key, value in preview.items() if key != "signals"})
        except Exception as error:
            st.error(friendly_configuration_error(error))

with demand_tab:
    st.divider()
    navigation_left, navigation_right = st.columns(2)
    with navigation_left:
        st.button('Voltar: escolher o cenário', on_click=select_workflow_tab, args=('1 · Cenário',))
    with navigation_right:
        st.button('Continuar: preparar o treinamento', on_click=select_workflow_tab, args=('3 · Treinamento',), type='primary')

with results_tab:
    step_heading(4, 'Acompanhe e compare os resultados', 'Observe a execução e, ao concluir o treino, compare o modelo com os tempos iniciais.')
    st.caption('A referência são os tempos iniciais da rede simulada. A comparação usa o mesmo tráfego e as mesmas sementes de avaliação para os controles comparados.')

with training_tab:
    if active:
        st.info('Já existe uma execução em andamento. Aguarde a conclusão ou interrompa na etapa Resultados para iniciar outra.')
    if current_config is None:
        st.error(f'Não foi possível iniciar: {configuration_error}')
    if st.button("Iniciar treinamento", disabled=active or current_config is None, type="primary"):
        try:
            start_job("rl-train", configured())
            st.rerun()
        except Exception as error:
            st.error(friendly_configuration_error(error))

    with st.expander('Treinamentos independentes e avaliações automáticas'):
        training_seed_text = st.text_input('Sementes dos treinamentos independentes (separadas por vírgula)',
            value=', '.join(map(str, base.get('study', {}).get('training_seeds', [11, 22, 33]))))
        planned_study = None
        try:
            study_config = configured()
            study_config['study'] = {'training_seeds': [int(s.strip()) for s in training_seed_text.split(',') if s.strip()]}
            planned_study = study_plan(study_config)
            st.write(f"{planned_study['repetitions']} treinos independentes; {planned_study['evaluation_episodes']} episódios de avaliação; {planned_study['requested_training_timesteps']} passos de treino solicitados no total.")
            st.caption('Cada modelo é treinado com uma semente diferente e avaliado nas sementes reservadas acima. O agregado separa variação entre treinamentos de variação entre sementes de avaliação. Só começa ao clicar no botão.')
        except (ValueError, TypeError) as error:
            st.caption(f'Plano de repetições indisponível: {error}')
        if st.button('Executar treinos e avaliações repetidos', disabled=active or planned_study is None):
            try:
                start_job('run-study', study_config)
                st.rerun()
            except Exception as error:
                st.error(friendly_configuration_error(error))


@st.fragment(run_every="2s")
def progress_panel():
    job = st.session_state.get("job")
    if not job:
        return
    state = job_state(job)
    running = state['status'] in ('starting', 'running')
    st.subheader("Acompanhamento da simulação")
    statuses = {'starting': 'iniciando', 'running': 'em andamento', 'completed': 'concluída', 'failed': 'falhou',
                'cancelled': 'interrompida pelo usuário', 'interrupted': 'processo encerrado sem conclusão', 'unknown': 'estado indisponível'}
    st.write("Estado:", statuses[state['status']])
    if state.get('error'):
        st.error(friendly_configuration_error(state['error']))
    if running and st.button("Interromper execução"):
        (job["folder"] / "cancel.flag").touch()
        st.info("Cancelamento solicitado; a execução será encerrada ao concluir o passo atual.")
    progress = read_json(job['output'] / 'progress.json') or {}
    saved_summary = read_json(job['output'] / 'summary.json') or {}
    completed_episodes = progress.get('episodes_completed', saved_summary.get('episodes_completed'))
    if completed_episodes is not None:
        st.metric('Simulações de treino concluídas', completed_episodes)
    stages = {'rl-train': 'Treinamento do modelo', 'rl-eval': 'Comparação do modelo com os tempos iniciais',
              'run-reference': 'Simulação com os tempos iniciais', 'compare-baselines': 'Comparação com o controle por filas',
              'validate-demand': 'Conferência das contagens', 'run-study': 'Treinos e comparações repetidos'}
    st.caption(stages.get(state.get('command'), 'Execução do estudo'))
    if state.get('command') == 'rl-train':
        try:
            execution_config = read_config(job['folder'] / 'cenario.json')
            algorithm = execution_config.get('algorithm', 'PPO')
            target_steps = execution_config.get(get_algorithm(algorithm).config_key, {}).get('total_timesteps', 2048)
            done_steps = progress.get('timesteps', saved_summary.get('timesteps', 0))
            st.progress(min(1.0, done_steps / target_steps), text=f'{done_steps:,} de {target_steps:,} decisões de treino')
            model = Path(saved_summary['model']) if saved_summary.get('model') else None
            if state['status'] == 'completed' and model and model.is_file() and not saved_summary.get('cancelled'):
                st.success('Treinamento concluído. Compare o modelo para verificar o efeito no trânsito.')
                comparison_busy = any(job_state(saved)['status'] in ('starting', 'running') for saved in saved_jobs(RESULTS))
                if st.button('Comparar este modelo com os tempos iniciais', disabled=comparison_busy, type='primary', key=f"compare_completed_{job['folder'].name}"):
                    start_job('rl-eval', execution_config, model)
                    st.rerun()
        except (OSError, ValueError, KeyError, TypeError) as error:
            st.caption(f'A comparação deste modelo ainda não está disponível: {error}')
    live_output = job['output']
    if progress.get('active_output'):
        live_output = Path(progress['active_output'])
        stages = {'training': 'treinamento', 'evaluation': 'avaliação'}
        st.caption(f"Repetição {progress['repetition']} / {progress['total_repetitions']} — {stages.get(progress['stage'], progress['stage'])}; semente de treino {progress['training_seed']}.")
    live = read_json(live_output / 'live.json')
    if live:
        a, b, c, d = st.columns(4)
        a.metric('Tempo simulado no episódio (s)', round(live['simulated_seconds'], 1))
        b.metric('Fila atual nas entradas', live['queue_vehicles_now'])
        c.metric('Veículos que chegaram', live['arrived'])
        d.metric('Pedestres que chegaram', live.get('pedestrians_arrived', 0))
    result_overview(job['output'], 'current_result')
    render_training_metrics(live_output, 'current_training', running=running)



with results_tab:
    if not st.session_state.get("job"):
        with st.container(border=True):
            st.markdown('### Seu resultado aparecerá aqui')
            st.write('Depois de iniciar uma simulação ou treinamento, você verá o progresso, as filas e as chegadas nesta etapa.')
            st.button('Ir para o treinamento', on_click=select_workflow_tab, args=('3 · Treinamento',))
            st.caption('Já executou antes? Recupere uma execução na barra lateral ou abra os relatórios anteriores abaixo.')
    progress_panel()

    with st.expander("Comparar outro modelo treinado"):
        st.caption("Depois do treinamento, atualize a lista e escolha o modelo que será comparado com a referência.")
        st.button("Atualizar lista de modelos treinados", help="Após o treino, atualiza os modelos disponíveis para avaliação.")
        models = sorted(RESULTS.glob("**/*_model.zip"), key=lambda p: p.stat().st_mtime, reverse=True) if RESULTS.exists() else []
        selected_model = st.selectbox("Selecionar modelo treinado", [""] + [str(p) for p in models], format_func=lambda p: str(Path(p).relative_to(RESULTS)) if p else "Escolher depois do treinamento")
        model_path = selected_model
        if not model_path:
            st.caption('Para comparar o treino recém-concluído, use o botão no acompanhamento. Este seletor permite avaliar outros modelos com a configuração atual.')
        if st.button(f"Comparar {selected_algorithm} com os tempos iniciais", disabled=active or current_config is None or not model_path):
            try:
                model = Path(model_path).resolve()
                if not model.is_file():
                    raise ValueError("Informe um arquivo ppo_model.zip existente")
                start_job("rl-eval", configured(), model)
                st.rerun()
            except Exception as error:
                st.error(friendly_configuration_error(error))

    with st.expander("Comparar controles sem aprendizado"):
        if st.button('Comparar tempos iniciais com controle por filas', disabled=active or current_config is None):
            try:
                start_job('compare-baselines', configured())
                st.rerun()
            except Exception as error:
                st.error(friendly_configuration_error(error))
        st.caption('As comparações usam as sementes de avaliação, verificam viagens e horários idênticos e mostram percentuais, intervalos e perdas de atendimento. A avaliação do modelo inclui também essa comparação.')

with results_tab:
    with st.expander("Abrir relatórios de execuções anteriores"):
        summaries = sorted(RESULTS.glob("**/summary.json"), key=lambda path: path.stat().st_mtime, reverse=True) if RESULTS.exists() else []
        if summaries:
            chosen = st.selectbox("Resultado salvo", [str(path.parent.relative_to(RESULTS)) for path in summaries])
            folder = RESULTS / chosen
            result_overview(folder, 'saved_result')
            render_training_metrics(folder, 'saved_training')
        else:
            st.caption("Nenhuma execução concluída encontrada.")
