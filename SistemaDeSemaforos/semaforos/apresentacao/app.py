"""Interface Streamlit do piloto PPO/SUMO.

Inicie com: streamlit run interface.py
"""
from semaforos.caminhos import PROJECT_ROOT

import json
import io
from collections import deque
from pathlib import Path

import pandas as pd
import streamlit as st
import sumolib

from semaforos.cenario.configuracao import read_config, with_detailed_metrics
from semaforos.cenario.ciclos import adjusted_programs, include_adjusted_times, save_adjusted_network
from semaforos.cenario.demanda import planned_vehicle_count
from semaforos.cenario.rede import network_programs, phase_action_spec
from semaforos.apresentacao.sinais import signal_presentation
from semaforos.arquivos import read_json
from semaforos.experimentos.tarefas import start_job as launch_job, saved_jobs, job_state
from semaforos.apresentacao.diagnostico import render_diagnostics
from semaforos.apresentacao.layout import (
    RESULTS_TAB, TRAINING_TAB, configuration_summary, friendly_configuration_error, page_header,
    preparation_summary, select_workflow_tab, workflow_navigation, SETUP_TAB,
)
from semaforos.apresentacao.estudos import load_study_configuration
from semaforos.apresentacao.gargalos import render_study
from semaforos.apresentacao.resultados import (
    COMPARISONS, MODEL_COMPARISONS, TRAIN_RESULTS, duration_label, execution_label, execution_section, render_execution_results,
)
from semaforos.apresentacao.vias import identify_roads
from semaforos.apresentacao.estado import configuration_key
from semaforos.apresentacao.treinamento import adaptive_limits_editor
from semaforos.simulacao.janela import measurement_window
from semaforos.experimentos.repeticoes import study_plan
from semaforos.cenario.pedestres import crossing_routes
from semaforos.cenario.experimental import prepare_or_reuse, validate_experimental, intersection_names
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
    approaches = {connection[0].getEdge()
                  for light in network_data.getTrafficLights() if light.getID() in target_ids
                  for connection in light.getConnections()
                  if connection[0].getEdge().allows("passenger")}
    controlled_nodes = {edge.getToNode().getID() for edge in approaches}
    incoming = sorted(edge.getID() for edge in approaches if edge.getFromNode().getID() not in controlled_nodes)
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




def start_job(command, config, model=None, *, reference_model=None):
    config = with_detailed_metrics(config)
    options = {'reference_model': reference_model} if reference_model else {}
    st.session_state.job = launch_job(config, command, RESULTS, model, **options)
    st.session_state['results_next_section'] = execution_section(command, reference_model)
    select_workflow_tab(RESULTS_TAB)


st.set_page_config(page_title="Semáforos Rondon Norte", layout="wide")
page_header()
setup_tab, training_tab, results_tab, advanced_tab = workflow_navigation()
jobs = saved_jobs(RESULTS)
show_results = st.session_state.ui_default_tab == RESULTS_TAB

with results_tab:
    if show_results:
        current = st.session_state.get('job')
        if current and current['folder'] not in {entry['folder'] for entry in jobs} and (current['folder'] / 'job.json').is_file():
            jobs = [current, *jobs]
        states = {str(entry['folder']): read_json(entry['folder'] / 'job.json') or {} for entry in jobs}
        jobs = [entry for entry in jobs if states[str(entry['folder'])].get('command') != 'compare-baselines']
        by_path = {str(entry['folder']): entry for entry in jobs}
        sections = {path: execution_section(states[path].get('command'), states[path].get('reference_model'))
                    for path in by_path}
        execution_labels = {path: execution_label(path) for path in by_path}
        active_path = next((str(entry['folder']) for entry in jobs
                            if job_state(entry)['status'] in ('starting', 'running')), '')
        current_path = str(current['folder']) if current else active_path
        pending_section = st.session_state.pop('results_next_section', None)
        if pending_section or 'results_section' not in st.session_state:
            st.session_state['results_section'] = pending_section or sections.get(current_path, TRAIN_RESULTS)
        results_section = st.radio('Área dos resultados', [TRAIN_RESULTS, COMPARISONS, MODEL_COMPARISONS], horizontal=True,
                                   format_func=lambda area: 'Modelo × tempos iniciais' if area == COMPARISONS else area,
                                   label_visibility='collapsed', key='results_section')
        choices = {path: entry for path, entry in by_path.items() if sections[path] == results_section}
        if choices:
            saved_selections = st.session_state.setdefault('results_saved_selections', {})
            if current_path not in choices:
                previous = saved_selections.get(results_section)
                current_path = previous if previous in choices else next(iter(choices))
            execution_key = {
                TRAIN_RESULTS: 'results_training_execution',
                COMPARISONS: 'results_comparison_execution',
                MODEL_COMPARISONS: 'results_model_comparison_execution',
            }[results_section]
            # O Streamlit recria o seletor quando a lista muda. A execução
            # acompanhada continua sendo a escolhida pelo callback.
            st.session_state[execution_key] = current_path

            def follow_execution(key, entries):
                selected = entries.get(st.session_state.get(key))
                if selected is not None:
                    st.session_state.job = selected

            followed = st.selectbox('Execução', list(choices), format_func=execution_labels.__getitem__,
                                    key=execution_key, on_change=follow_execution, args=(execution_key, choices))
            st.session_state.job = choices[followed]
            saved_selections[results_section] = followed
        else:
            st.session_state.pop('job', None)
    current_results = st.container()
    if show_results and st.session_state.get('job'):
        job = st.session_state.job
        if (job['folder'] / 'cenario.json').is_file():
            def load_execution_draft(path):
                if error := load_study_configuration(path):
                    st.session_state['results_load_error'] = error
                else:
                    select_workflow_tab(SETUP_TAB)

            st.button('Carregar configurações desta execução',
                      help='Usa a configuração salva como um novo rascunho em Cenário e tráfego.',
                      on_click=load_execution_draft, args=(job['folder'] / 'cenario.json',))
            if error := st.session_state.pop('results_load_error', None):
                st.error(error)

with setup_tab:
    source = st.session_state.get('study_source')
    if source and source['kind'] in ('duplicate', 'recovered'):
        prefix = 'Cópia de ' if source['kind'] == 'duplicate' else ''
        st.caption(f"Rascunho: {prefix}{source['label']}")
    base = st.session_state.get('loaded_config') or read_config(DEFAULT)
    wanted_names = set(intersection_names())
    joint = True
    experimental_ready = False
    preparation_status = st.empty()
    if st.session_state.get('configuration_focus') == 'scenario':
        st.session_state.pop('configuration_focus', None)
    try:
        prepared = st.session_state.get('experimental_config', {})
        if {t['name'] for t in prepared.get('targets', [])} != wanted_names:
            with preparation_status.container(), st.spinner('Preparando a rede…'):
                prepared, rows, _ = prepare_or_reuse(base, RESULTS)
                prepared['duration_seconds'] = base['duration_seconds']
                st.session_state.experimental_config = prepared
                st.session_state.experimental_rows = rows
        selected_rows = validate_experimental(prepared)
        base = prepared
        experimental_ready = True
    except Exception as error:
        with preparation_status.container():
            st.error(f'Não foi possível preparar a rede. {friendly_configuration_error(error)}')
            st.button('Tentar novamente', on_click=lambda: st.session_state.pop('experimental_config', None))
        if base.get('experimental'):
            base = read_config(DEFAULT)
    if experimental_ready and base['experimental']['method'] == 'serial_links_v1':
        st.warning('Este cenário salvo usa atendimento serial antigo. Abra um cenário novo para editar ciclos com movimentos agrupados.')
    network = str(base["network"])
    plans = str(base["plans"])

import copy
limits_config = copy.deepcopy(base)
limits_config.setdefault('control', dict(base['ppo']))['action_mode'] = 'phase_durations'
programs = network_programs(network)
selected_specs = phase_action_spec(limits_config, programs)[1]
max_yellow = max(s['durations_seconds'][1] for s in selected_specs if s['kind'] == 'yellow')
max_clearance = max(s['durations_seconds'][1] for s in selected_specs if s['kind'] == 'all_red')
maximum_cycle = float(base.get('control', base['ppo']).get('maximum_cycle_seconds', 3600))
warmup_seconds = float(base.get('measurement', {}).get('warmup_seconds', 0))

@st.fragment
def traffic_configuration():
    focus = st.session_state.get('configuration_focus')
    focus_object = None
    if focus in ('roads', 'pedestrians', 'signals', 'duration'):
        st.session_state.pop('configuration_focus', None)
        focus_object = st.session_state.pop('configuration_focus_object', None)
    duration_column, pedestrian_controls, filter_controls = st.columns(3)
    default_duration = int(base['duration_seconds'])
    entered_duration = duration_column.number_input('Duração da simulação (segundos)', min_value=1,
        value=default_duration, step=1, key=configuration_key('Duração da simulação (segundos)'))
    duration_incomplete = entered_duration is None
    duration = default_duration if duration_incomplete else entered_duration
    duration_error = None
    if duration_incomplete:
        duration_error = 'Preencha a duração da simulação em segundos.'
    elif duration <= warmup_seconds:
        duration_error = f'A duração da simulação precisa superar os {warmup_seconds:g} s de aquecimento do cenário.'
    if duration_error:
        st.warning(duration_error)
    if base['demand']['mode'] != 'edge_volumes' and st.session_state.get('loaded_config'):
        st.caption('Informe os volumes por via no mapa. A quantidade total da execução antiga não é distribuída automaticamente entre as vias.')
    if base['demand'].get('time_profile'):
        st.caption('O estudo salvo usava uma distribuição por período. Novas execuções deste rascunho usam o volume por hora de cada via durante todo o episódio.')
    road_table = None
    pedestrian_table = None
    pedestrian_enabled = False
    if not joint or experimental_ready:
        try:
            edge_ids, _, incoming_ids = road_options(network, tuple(t['tls_id'] for t in base['targets']))
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
            road_table, pedestrian_table, pedestrian_enabled = render_configuration_map(
                base, initial, details, incoming_ids, defaults,
                duration=None if duration_incomplete else duration, focus=focus, focus_object=focus_object,
                pedestrian_controls=pedestrian_controls, filter_controls=filter_controls)
        except Exception as error:
            st.error(friendly_configuration_error(error))
    if road_table is not None:
        rates = pd.to_numeric(road_table["vehicles_per_hour"], errors="coerce").fillna(0)
        active_entries = int(rates.gt(0).sum())
        status = 'pedestres ativados' if pedestrian_enabled else 'pedestres desativados'
        entries_label = 'entrada com fluxo' if active_entries == 1 else 'entradas com fluxo'
        shown_duration = f'{duration:g} s' if not duration_error else 'duração a conferir'
        st.caption(f'{shown_duration} · {active_entries} {entries_label} · {status}')
        if not active_entries and not pedestrian_enabled:
            st.caption('Preencha o volume de pelo menos uma entrada para simular.')
    st.session_state['traffic_configuration_values'] = {
        'road_table': road_table,
        'pedestrian_table': pedestrian_table,
        'pedestrian_enabled': pedestrian_enabled,
        'duration': duration,
        'duration_error': duration_error,
    }

with setup_tab:
    traffic_configuration()
traffic_values = st.session_state['traffic_configuration_values']
(road_table, pedestrian_table,
 pedestrian_enabled, duration, duration_error) = (
    traffic_values[name] for name in (
        'road_table', 'pedestrian_table',
        'pedestrian_enabled', 'duration', 'duration_error'))

with training_tab:
    training_focus = st.session_state.get('configuration_focus')
    training_focus_object = {}
    if training_focus in ('seeds', 'ppo', 'objectives', 'green_limits'):
        st.session_state.pop('configuration_focus', None)
        training_focus_object = st.session_state.pop('configuration_focus_object', {})
    restored_study = st.session_state.get('study_source', {}).get('kind') in ('duplicate', 'recovered')
    algorithm_names = sorted(available_algorithms(), key=lambda name: name != 'PPO')
    saved_algorithm = get_algorithm(base.get('algorithm', 'PPO')).name
    selected_algorithm = st.selectbox('Algoritmo de treinamento', algorithm_names,
        index=algorithm_names.index(saved_algorithm), key=configuration_key('Algoritmo de treinamento'))
    algorithm_key = get_algorithm(selected_algorithm).config_key
    default_weights = {'waiting': 1.0, 'queues': 1.0, 'travel': 1.0}
    weights = {**default_weights, **base.get('objectives', {})}
    w_wait, w_queue, w_travel = 1.0, 1.0, 1.0
    algorithm_budget = int(base.get(algorithm_key, {}).get('total_timesteps', 2048))
    total_steps = st.number_input('Quantidade de decisões para treinar', min_value=2,
        value=algorithm_budget, step=128, help=config_help('total_timesteps'),
        key=configuration_key(f'Quantidade de decisões para treinar_{selected_algorithm}'))
    start_training_controls = st.container()
    phase_table = None
    with st.expander("Configurações avançadas", expanded=training_focus in ('seeds', 'ppo', 'objectives', 'green_limits')):
        gui = st.toggle('Ver simulação durante o treino', value=restored_study and bool(base.get('control', base['ppo']).get('gui', False)),
                        key=configuration_key('Ver simulação durante o treino'))
        gui_delay = int(base.get('control', base['ppo']).get('gui_delay_milliseconds', 0))
        if gui:
            gui_delay = st.number_input('Atraso da visualização (ms por passo)', min_value=0, max_value=2000,
                value=gui_delay, step=10, help='Zero executa o mais rápido possível. Aumente para observar os movimentos mais devagar.', key=configuration_key('Atraso da visualização (ms por passo)'))
        if experimental_ready:
            with st.expander('Limites de verde do treinamento', expanded=training_focus == 'green_limits'):
                target_names = {t['tls_id']: t['name'] for t in base['targets']}
                crossing_key = configuration_key('green_limits_crossing')
                focused_crossing = target_names.get(training_focus_object.get('tls_id'))
                if focused_crossing:
                    st.session_state[crossing_key] = focused_crossing
                crossing = st.selectbox('Cruzamento para ajustar limites', list(dict.fromkeys(target_names.values())),
                                        key=crossing_key)
                names_file = ROOT / 'dados/auditoria/nomes_vias_osm.json'
                details = road_details(network, tuple(target_names.items()),
                    names_file.stat().st_mtime_ns if names_file.exists() else 0)
                labels = {edge: info['reference'] + ' · ' + (info['street'] or 'Nome não cadastrado')
                          for edge, info in details.items()}
                phase_table = adaptive_limits_editor(base, selected_specs, labels, key=f'adaptive_limits_{network}',
                                                     selected_crossing=crossing, map_only=True)
        st.caption("Sementes tornam o estudo reproduzível. Use valores diferentes para treino e avaliação. Os pesos indicam quais objetivos o algoritmo prioriza.")
        seed = st.number_input("Semente", min_value=0, value=int(base["seeds"][0]), help=config_help("seeds"), key=configuration_key('Semente'))
        evaluation_seeds = st.text_input("Sementes de avaliação (separadas por vírgula)",
                                         value=", ".join(map(str, base.get("evaluation", {}).get("seeds", [101, 102, 103]))), help=config_help("evaluation.seeds"), key=configuration_key('Sementes de avaliação (separadas por vírgula)'))
        custom_weights = st.checkbox('Personalizar pesos do objetivo', value=weights != default_weights, key=configuration_key('Personalizar pesos do objetivo'))
        if custom_weights:
            w_wait = st.number_input("Prioridade: espera", min_value=0.0, value=float(weights['waiting']), step=0.1, help=config_help("objectives.waiting"), key=configuration_key('Prioridade: espera'))
            w_queue = st.number_input("Prioridade: filas", min_value=0.0, value=float(weights['queues']), step=0.1, help=config_help("objectives.queues"), key=configuration_key('Prioridade: filas'))
            w_travel = st.number_input("Prioridade: tempo de viagem (aproximação)", min_value=0.0, value=float(weights['travel']), step=0.1, help=config_help("objectives.travel"), key=configuration_key('Prioridade: tempo de viagem (aproximação)'))
        decision = st.number_input("Intervalo de decisão (s)", min_value=1, value=int(base["ppo"]["decision_seconds"]), help=config_help("decision_seconds"), key=configuration_key('Intervalo de decisão (s)'))
        algorithm_parameters = {}
        algorithm_parameters_text = None
        if selected_algorithm == "PPO":
            algorithm_parameters['n_epochs'] = st.number_input("Épocas por coleta", min_value=1,
                value=int(base["ppo"]["n_epochs"]), help=config_help("n_epochs"), key=configuration_key('Épocas por lote'))
            algorithm_parameters['n_steps'] = st.number_input("Passos por coleta", min_value=2,
                value=int(base["ppo"]["n_steps"]), help=config_help("n_steps"), key=configuration_key('Passos por coleta'))
            algorithm_parameters['batch_size'] = st.number_input("Tamanho do minibatch", min_value=2,
                value=int(base["ppo"]["batch_size"]), help=config_help("batch_size"), key=configuration_key('Tamanho do minibatch'))
        elif selected_algorithm == "A2C":
            from semaforos.algoritmos.a2c import DEFAULT_N_STEPS

            algorithm_parameters['n_steps'] = st.number_input("Passos por coleta", min_value=1,
                value=int(base.get(algorithm_key, {}).get('n_steps', DEFAULT_N_STEPS)),
                help='Decisões coletadas antes de cada atualização do A2C.', key=configuration_key('Passos por coleta A2C'))
        else:
            algorithm_parameters_text = st.text_area("Parâmetros específicos do algoritmo (JSON)", value="{}",
                help="Objeto com parâmetros aceitos pelo adaptador.", key=configuration_key('Parâmetros específicos do algoritmo (JSON)'))
        with st.expander('Indicadores e critérios da análise detalhada'):
            st.markdown(
                'Coleta automática em todas as execuções:\n'
                '- Velocidade e ocupação das faixas\n'
                '- CO₂, CO, HC, NOx, partículas, combustível e eletricidade\n'
                '- Teletransportes e colisões\n'
                '- CPU e memória\n'
                '- Faixas, movimentos, filas em metros e bloqueios\n'
                '- Frenagens, paradas, velocidade e TTC explorat?rio\n'
                '- Indicadores por classe de veículo'
            )
            thresholds = dict(base.get('metrics', {}).get('thresholds', {}))
            thresholds['spillback_occupancy_percent'] = st.number_input('Ocupação para indicar transbordamento (%)', min_value=1.0, max_value=100.0, value=float(thresholds.get('spillback_occupancy_percent', 80)), key=configuration_key('Ocupação para indicar transbordamento (%)'))
            thresholds['downstream_occupancy_percent'] = st.number_input('Ocupação da saída para indicar bloqueio (%)', min_value=1.0, max_value=100.0, value=float(thresholds.get('downstream_occupancy_percent', 80)), key=configuration_key('Ocupação da saída para indicar bloqueio (%)'))
            thresholds['long_wait_seconds'] = st.number_input('Espera considerada longa (s)', min_value=1.0, value=float(thresholds.get('long_wait_seconds', 120)), key=configuration_key('Espera considerada longa (s)'))
            thresholds['hard_braking_meters_per_second_squared'] = st.number_input('Desaceleração para frenagem forte (m/s²)', min_value=0.1, value=float(thresholds.get('hard_braking_meters_per_second_squared', 4)), key=configuration_key('Desaceleração para frenagem forte (m/s²)'))
            thresholds['ttc_seconds'] = st.number_input('Limiar de TTC longitudinal exploratório (s)', min_value=0.1, value=float(thresholds.get('ttc_seconds', 1.5)), key=configuration_key('Limiar de TTC longitudinal exploratório (s)'))
            st.caption('Detalhes adicionais aumentam o custo de coleta. Bloqueio é um indicador baseado em verde, veículos parados e ocupação da saída; TTC não certifica risco de acidente. Limiares são configuráveis e ficam registrados.')


def configured():
    if duration_error:
        raise ValueError(duration_error)
    if joint and not experimental_ready:
        raise ValueError("Prepare o cenário selecionado antes de executar")
    config = dict(base)
    config["network"] = str(Path(network).resolve())
    config["plans"] = str(Path(plans).resolve())
    if road_table is None:
        raise ValueError("Selecione uma rede válida para preencher as vias")
    if road_table.attrs.get('validation_error'):
        raise ValueError(road_table.attrs['validation_error'])
    vehicle_types = [dict(row) for row in base["demand"].get("vehicle_types", [])]
    entries = []
    for row in road_table.to_dict("records"):
        if not row.get("from_edge") or pd.isna(row["from_edge"]):
            continue
        entry = {"from_edge": row["from_edge"],
                 "vehicles_per_hour": float(row.get("vehicles_per_hour") or 0),
                 "to_edge": row.get("to_edge") or ""}
        if isinstance(row.get('destinations'), list):
            entry['destinations'] = row['destinations']
        entries.append(entry)
    config["demand"] = {"mode": "edge_volumes", "edge_volumes": entries, "synthetic": True}
    if vehicle_types:
        config["demand"]["vehicle_types"] = vehicle_types
    if w_wait + w_queue + w_travel <= 0:
        raise ValueError("Escolha ao menos uma prioridade positiva")
    config["objectives"] = {"waiting": float(w_wait), "queues": float(w_queue), "travel": float(w_travel)}
    config["duration_seconds"] = int(duration)
    config['measurement'] = {'warmup_seconds': warmup_seconds, 'start_seconds': warmup_seconds, 'end_seconds': float(duration)}
    if pedestrian_enabled:
        if pedestrian_table is None:
            raise ValueError('Prepare uma rede com travessias antes de ativar pedestres')
        if pedestrian_table.attrs.get('validation_error'):
            raise ValueError(pedestrian_table.attrs['validation_error'])
        ped_flows = [row for row in pedestrian_table.to_dict('records') if float(row.get('persons_per_hour', 0)) > 0]
        if not ped_flows or sum(int(row['persons_per_hour'] * duration / 3600 + 0.5) for row in ped_flows) == 0:
            raise ValueError('Preencha pessoas/h suficientes para gerar ao menos um pedestre no episódio')
        speed = float(base.get('pedestrians', {}).get('walking_speed_meters_per_second', .8))
        config['pedestrians'] = {'enabled': True, 'walking_speed_meters_per_second': speed,
                                'synthetic': True, 'flows': ped_flows}
    else:
        config['pedestrians'] = {'enabled': False}
    if not config['pedestrians']['enabled']:
        planned_vehicles = sum(planned_vehicle_count(row['vehicles_per_hour'], duration) for row in entries)
        if planned_vehicles <= 0:
            raise ValueError('Informe veículos por hora em pelo menos uma entrada para gerar tráfego nesta duração de simulação')
    config["seeds"] = [int(seed)]
    try:
        parsed_seeds = [int(item.strip()) for item in evaluation_seeds.split(",") if item.strip()]
    except ValueError:
        raise ValueError('Informe sementes de avaliação como números inteiros separados por vírgulas') from None
    if not parsed_seeds or len(set(parsed_seeds)) != len(parsed_seeds) or int(seed) in parsed_seeds:
        raise ValueError("Informe sementes de avaliação distintas e diferentes da semente do treino")
    config["evaluation"] = {"seeds": parsed_seeds}
    config["metrics"] = {"thresholds": thresholds}
    config = with_detailed_metrics(config)
    config["ppo"] = {**base["ppo"], "decision_seconds": int(decision), "gui": bool(gui),
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
    parameters = algorithm_parameters
    if algorithm_parameters_text is not None:
        parameters = json.loads(algorithm_parameters_text)
        if not isinstance(parameters, dict):
            raise ValueError("Parâmetros específicos devem ser um objeto JSON")
    config[algorithm_key] = {**config.get(algorithm_key, {}), **parameters,
                             "total_timesteps": int(total_steps)}
    if joint:
        validate_experimental(config)
    measurement_window(config)
    from semaforos.apresentacao.mapa_configuracao import cycle_edit_key

    cycle_edits = st.session_state.get(cycle_edit_key(network), {})
    effective_programs = adjusted_programs(config, programs, cycle_edits)
    if cycle_edits:
        include_adjusted_times(config['control'], effective_programs, cycle_edits)
        config['ppo'].update(config['control'])
    phase_action_spec(config, effective_programs)
    from semaforos.cenario.demanda import validate_vehicle_types
    validate_vehicle_types(config)
    if cycle_edits:
        save_adjusted_network(config, cycle_edits, RESULTS / 'redes_ajustadas')
        validate_experimental(config)
    return config


with advanced_tab:
    st.subheader("Referência técnica")
    st.caption("Consulta opcional. Você não precisa alterar estes catálogos para iniciar um treino.")
    if experimental_ready and st.session_state.get('ui_default_tab') == 'Referência técnica':
        with st.expander('Programas iniciais da rede'):
            timing_labels = road_labels(network, tuple((t['tls_id'], t['name']) for t in base['targets']))
            preparation_summary(selected_rows, base['experimental'].get('external_repaired', []),
                                signal_presentation(base, timing_labels))
    with st.expander('Dicionário rápido: o que significam os termos?'):
        st.markdown('**Simulação:** uma execução que representa o trânsito durante o período escolhido.\n\n**Treinamento:** repetição de simulações para o algoritmo aprender.\n\n**Decisão:** escolha feita pelo algoritmo para controlar os sinais.\n\n**Etapa:** movimentos que recebem verde juntos.\n\n**Ciclo:** sequência completa das etapas de um conjunto de semáforos.\n\n**Avaliação:** comparação do modelo treinado com os tempos iniciais, em simulações reservadas para esse fim.')
    tab_options, tab_parameters, tab_metrics = st.tabs(["Opções SUMO", "Parâmetros de treinamento", "Dicionário de métricas"])
configuration_error = None
raw_configuration_error = None

try:
    current_config = configured()
except (ValueError, TypeError, KeyError) as error:
    current_config = None
    raw_configuration_error = error
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
    st.write("Episódios são execuções do SUMO. O parâmetro `total_timesteps` determina o orçamento do treino.")
    if selected_algorithm == "PPO":
        st.caption("No PPO, `n_epochs=10` faz dez passagens de otimização por coleta.")
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
        st.caption("Inclui os campos do cenário, os argumentos do algoritmo e as opções enviadas ao SUMO. O comando e a semente de cada episódio ficam em run_config.json. O manifest.json registra versões e hashes.")
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
with setup_tab:
    simulate, continue_training = st.columns(2)
    if simulate.button("Simular com os tempos iniciais", disabled=active, type='primary'):
        try:
            start_job("run-reference", configured())
            st.rerun()
        except Exception as error:
            st.error(friendly_configuration_error(error))
    continue_training.button('Continuar: preparar o treinamento', on_click=select_workflow_tab, args=(TRAINING_TAB,))

with start_training_controls:
    if active:
        st.info('Já existe uma execução em andamento. Aguarde a conclusão ou interrompa na etapa Resultados para iniciar outra.')
    configuration_summary(current_config, configuration_error, baseline=base, raw_error=raw_configuration_error)
    if st.button("Iniciar treinamento", disabled=active or current_config is None, type="primary"):
        try:
            start_job("rl-train", configured())
            st.rerun()
        except Exception as error:
            st.error(friendly_configuration_error(error))

with training_tab:
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


results_job = st.session_state.get('job') if show_results else None
was_running = bool(results_job and job_state(results_job)['status'] in ('starting', 'running'))


def progress_panel():
    job = st.session_state.get("job")
    if not job:
        return
    state = job_state(job)
    running = state['status'] in ('starting', 'running')
    if was_running and not running:
        st.rerun()
    status = {'starting': 'Iniciando', 'running': 'Em andamento', 'completed': 'Concluída', 'failed': 'Falhou',
              'cancelled': 'Interrompida', 'interrupted': 'Processo encerrado sem conclusão'}
    st.caption(status.get(state['status'], 'Estado indisponível'))
    if state.get('error'):
        st.error(friendly_configuration_error(state['error']))
    if running and st.button("Interromper execução"):
        (job["folder"] / "cancel.flag").touch()
        st.info("Cancelamento solicitado; a execução será encerrada ao concluir o passo atual.")
    progress = read_json(job['output'] / 'progress.json') or {}
    execution_config = read_json(job['folder'] / 'cenario.json') or {}
    if running:
        if state.get('command') == 'rl-train' and execution_config:
            algorithm = execution_config.get('algorithm', 'PPO')
            target_steps = execution_config.get(get_algorithm(algorithm).config_key, {}).get('total_timesteps', 2048)
            done_steps = progress.get('timesteps', 0)
            st.progress(min(1.0, done_steps / target_steps), text=f'{done_steps} de {target_steps} decisões de treino')
        live_output = job['output']
        if progress.get('active_output'):
            live_output = Path(progress['active_output'])
            stage = {'training': 'treino', 'evaluation': 'avaliação'}.get(progress['stage'], progress['stage'])
            st.caption(f"Repetição {progress['repetition']} de {progress['total_repetitions']} · {stage}")
        live = read_json(live_output / 'live.json')
        if live:
            metrics = [
                ('Tempo simulado', duration_label(live['simulated_seconds'])),
                ('Fila atual nas entradas', live['queue_vehicles_now']),
                ('Veículos que chegaram', live['arrived']),
            ]
            if execution_config.get('pedestrians', {}).get('enabled') or live.get('pedestrians_arrived'):
                metrics.append(('Pedestres que chegaram', live.get('pedestrians_arrived', 0)))
            for column, (label, value) in zip(st.columns(len(metrics)), metrics):
                column.metric(label, value)
        return

    if results_section != TRAIN_RESULTS:
        download_label = 'Baixar Excel desta comparação'
    elif state.get('command') == 'rl-train' or (job['output'] / 'training_episodes.csv').is_file():
        download_label = 'Baixar Excel deste treino'
    else:
        download_label = 'Baixar Excel desta simulação'
    evaluation = None
    if state.get('command') == 'rl-train':
        model = (read_json(job['output'] / 'summary.json') or {}).get('model')
        if model:
            for entry in jobs:
                candidate = read_json(entry['folder'] / 'job.json') or {}
                if (candidate.get('command') == 'rl-eval' and candidate.get('status') == 'completed'
                        and not candidate.get('reference_model')
                        and candidate.get('model') and Path(candidate['model']) == Path(model)):
                    evaluation = entry['output']
                    break
    render_execution_results(job['output'], f"results_{job['folder']}", 'Métricas',
                             download_label=download_label, evaluation=evaluation)



if show_results:
    with current_results:
        if not st.session_state.get("job"):
            if results_section == TRAIN_RESULTS:
                st.info('Inicie uma simulação ou um treinamento para ver os resultados aqui.')
                st.button('Ir para o treinamento', on_click=select_workflow_tab, args=(TRAINING_TAB,))
        if was_running:
            st.fragment(run_every='2s')(progress_panel)()
        else:
            progress_panel()

def render_new_comparison(compare_models):
    with results_tab, st.expander('Nova comparação', expanded=results_job is None):
        models = sorted(RESULTS.glob('**/*_model.zip'), key=lambda p: p.stat().st_mtime, reverse=True)
        if len(models) < (2 if compare_models else 1):
            if compare_models and models:
                st.info('Você tem 1 modelo salvo. Treine mais um no mesmo cenário para comparar os dois.')
                if st.button('Comparar o modelo salvo com os tempos iniciais'):
                    st.session_state['results_next_section'] = COMPARISONS
                    st.rerun()
            else:
                st.info('Nenhum modelo salvo. Conclua dois treinos no mesmo cenário para comparar os modelos.'
                        if compare_models else 'Nenhum modelo salvo. Conclua um treino para compará-lo com os tempos iniciais.')
            st.button('Ir para o treinamento', on_click=select_workflow_tab, args=(TRAINING_TAB,))
            return

        model_jobs = {entry['output']: str(entry['folder']) for entry in jobs}
        model_names = {
            str(model): execution_labels[model_jobs[model.parent]] if model.parent in model_jobs else str(model.relative_to(RESULTS))
            for model in models
        }
        if compare_models:
            st.caption('Escolha o modelo que quer avaliar (A) e o que vai servir de referência (B).')
        selected_model = st.selectbox('Modelo A' if compare_models else 'Modelo treinado', list(model_names), index=None,
                                      format_func=model_names.__getitem__, placeholder='Selecione um treino salvo')
        if not selected_model:
            return
        reference_model = None
        comparison_seeds = ''
        if compare_models:
            reference_model = st.selectbox('Modelo B (referência)', [path for path in model_names if path != selected_model],
                                           index=None, format_func=model_names.__getitem__,
                                           placeholder='Selecione outro treino salvo')
            if not reference_model:
                return
            st.caption('Os dois modelos usarão o mesmo cenário, demanda e sementes de avaliação.')
        use_current_config = False
        if not compare_models or st.toggle('Personalizar a avaliação'):
            use_current_config = st.checkbox('Usar o cenário atual',
                                             help='Por padrão, a avaliação usa a configuração salva no treino.')
            if compare_models:
                comparison_seeds = st.text_input('Sementes de avaliação para os dois modelos', placeholder='Ex.: 101, 102, 103',
                                                 help='Deixe em branco para usar as sementes do cenário. Use sementes diferentes das usadas nos dois treinos.')
        if st.button('Comparar os dois modelos' if compare_models else 'Comparar modelo com os tempos iniciais', type='primary',
                     disabled=active or (use_current_config and current_config is None)):
            try:
                model = Path(selected_model).resolve()
                if not model.is_file():
                    raise ValueError("Selecione um arquivo de modelo treinado que esteja disponível")
                manifest = read_json(model.parent / 'manifest.json') or {}
                if use_current_config:
                    comparison_config = configured()
                elif model.parent in model_jobs:
                    comparison_config = read_config(Path(model_jobs[model.parent]) / 'cenario.json')
                else:
                    comparison_config = manifest.get('config')
                    if not comparison_config:
                        raise ValueError("A configuração do treino não está disponível. Use o cenário atual para comparar este modelo.")
                algorithm = manifest.get('algorithm', comparison_config.get('algorithm', 'PPO'))
                if algorithm.upper() != comparison_config.get('algorithm', 'PPO').upper():
                    raise ValueError(f'Este modelo usa {algorithm}. Escolha o mesmo algoritmo em Treinamento.')
                if comparison_seeds.strip():
                    try:
                        seeds = [int(seed.strip()) for seed in comparison_seeds.split(',')]
                    except ValueError as error:
                        raise ValueError('Informe sementes inteiras separadas por vírgulas.') from error
                    if min(seeds) < 0 or len(set(seeds)) != len(seeds):
                        raise ValueError('Use sementes distintas e não negativas.')
                    comparison_config = {**comparison_config, 'evaluation': {
                        **comparison_config.get('evaluation', {}), 'seeds': seeds}}
                if reference_model:
                    seeds = comparison_config.get('evaluation', {}).get('seeds') or comparison_config['seeds']
                    baseline_manifest = read_json(Path(reference_model).parent / 'manifest.json') or {}
                    if any(saved.get('training_seed') in seeds for saved in (manifest, baseline_manifest)):
                        raise ValueError('Uma das sementes de avaliação foi usada no treinamento. Escolha sementes diferentes das usadas nos dois treinos.')
                start_job('rl-eval', comparison_config, model, reference_model=reference_model)
                st.rerun()
            except Exception as error:
                st.error(friendly_configuration_error(error))


if show_results and results_section != TRAIN_RESULTS:
    render_new_comparison(results_section == MODEL_COMPARISONS)
