"""Apresentação do fluxo de trabalho, sem alterar configuração ou execução."""
import re

import streamlit as st


SETUP_TAB = '1 · Cenário e tráfego'
TRAINING_TAB = '2 · Treinamento'
RESULTS_TAB = '3 · Resultados'


def select_workflow_tab(label):
    st.session_state.ui_default_tab = label
    st.session_state.ui_next_tab = label


def workflow_navigation():
    """Navegação controlada; os botões mudam a etapa visível."""
    options = [SETUP_TAB, TRAINING_TAB, RESULTS_TAB, 'Referência técnica']
    pending = st.session_state.pop('ui_next_tab', None)
    if pending in options:
        st.session_state.ui_workflow_selection = pending
    if st.session_state.get('ui_workflow_selection') not in options:
        previous = st.session_state.get('ui_default_tab')
        if previous not in options:
            previous = {'3 · Treinamento': TRAINING_TAB, '4 · Resultados': RESULTS_TAB}.get(previous, SETUP_TAB)
        st.session_state.ui_workflow_selection = previous
    selected = st.radio('Etapas do estudo', options, horizontal=True,
                        key='ui_workflow_selection', label_visibility='collapsed')
    st.session_state.ui_default_tab = selected
    names = ['traffic', 'training', 'results', 'reference']
    hidden = [f'.st-key-view_{name}' for index, name in enumerate(names) if options[index] != selected]
    st.markdown('<style>' + ','.join(hidden) + '{display:none!important;}</style>', unsafe_allow_html=True)
    return tuple(st.container(key=f'view_{name}') for name in names)


def preparation_summary(rows, external_repaired=(), timings=None):
    import pandas as pd

    if timings:
        st.markdown('**Quanto tempo cada sinal fica aberto ou fechado?**')
        crossings = list(dict.fromkeys(row['cruzamento'] for row in timings))
        crossing_key = f'signal_timing_crossing_{tuple(crossings)}'
        if st.session_state.get(crossing_key) not in crossings:
            st.session_state[crossing_key] = crossings[0]
        crossing = st.selectbox('Ver tempos do cruzamento', crossings, key=crossing_key)
        local = [row for row in timings if row['cruzamento'] == crossing]
        controllers = list(dict.fromkeys(row['controlador'] for row in local))
        durations = pd.DataFrame(local)
        if len(controllers) > 1:
            durations.insert(0, 'Conjunto', durations['controlador'].map({value: f'Conjunto {index + 1}' for index, value in enumerate(controllers)}))
        durations = durations.drop(columns=[c for c in durations if c.startswith('_') or c in ('Grupo', 'cruzamento', 'controlador', 'Limpeza após amarelo (s)', 'Intervalo de segurança (s)')])
        st.dataframe(durations, hide_index=True, width='stretch', column_config={
            'Movimentos liberados': st.column_config.TextColumn(width='large', help='Entradas e movimentos compatíveis que podem receber verde juntos.'),
            'Vermelho total (s)': st.column_config.NumberColumn('Tempo de vermelho (s)', help='Tempo em que o sinal permanece vermelho durante um ciclo, enquanto outros movimentos passam e durante os intervalos de segurança.'),
        })
        st.caption('Tempos iniciais da simulação, antes do treinamento. O tempo de vermelho já inclui os intervalos de segurança. O algoritmo pode ajustar os tempos durante a execução.')


def page_header():
    from pathlib import Path
    styles = Path(__file__).with_name('interface.css').read_text(encoding='utf-8')
    st.markdown(f'<style>{styles}</style>', unsafe_allow_html=True)
    st.title('Rondon Norte · 9 cruzamentos')


def configuration_issue(error):
    text = str(error or '').casefold()
    if re.search(r'limites de [^ ]+ excedem', text):
        return 'green_limits', TRAINING_TAB, 'Ajustar os limites de verde'
    rules = (
        (('prepare', 'rede válida', 'rede experimental'), 'scenario', SETUP_TAB, 'Preparar a rede'),
        (('duração da simulação', 'aquecimento', 'warmup', 'medição', 'measurement'), 'duration', SETUP_TAB, 'Ajustar a duração'),
        (('decision_seconds',), 'ppo', TRAINING_TAB, 'Ajustar o intervalo entre decisões'),
        (('step_seconds', 'passo da simulação', 'passo sumo'), 'scenario', SETUP_TAB, 'Conferir o cenário'),
        (('pessoas', 'pedestre', 'travessia'), 'pedestrians', SETUP_TAB, 'Ajustar a demanda de pedestres'),
        (('limites ppo', 'limites de verde'), 'green_limits', TRAINING_TAB, 'Ajustar os limites de verde'),
        (('fase', 'semáforo', 'máximo de ciclo', 'maximum_cycle', 'phase_duration'), 'signals', SETUP_TAB, 'Ajustar os semáforos'),
        (('veículo', 'entrada', 'fluxo', 'volume', 'tráfego'), 'roads', SETUP_TAB, 'Ajustar o fluxo nas vias'),
        (('semente',), 'seeds', TRAINING_TAB, 'Ajustar as sementes'),
        (('prioridade', 'pesos', 'objetivo'), 'objectives', TRAINING_TAB, 'Ajustar o objetivo'),
    )
    for terms, group, destination, action in rules:
        if any(term in text for term in terms):
            return group, destination, action
    return 'ppo', TRAINING_TAB, 'Abrir as configurações avançadas do treinamento'


def configuration_guidance(error):
    _, destination, action = configuration_issue(error)
    return destination, action


def focus_configuration_issue(error):
    group, destination, _ = configuration_issue(error)
    st.session_state['configuration_focus'] = group
    st.session_state.pop('configuration_focus_object', None)
    if group in ('signals', 'green_limits'):
        match = re.search(r'Limites (?:PPO inválidos para|de)\s+([^\s:;]+)(?=:\d|\s+excedem)', str(error), re.IGNORECASE)
        if match:
            st.session_state['configuration_focus_object'] = {'tls_id': match.group(1)}
    select_workflow_tab(destination)


def friendly_configuration_error(error):
    """Mantém o detalhe técnico nos arquivos, com uma ação clara na tela."""
    text = str(error or '')
    lowered = text.casefold()
    if any(t in lowered for t in ('pessoas/h', 'ao menos um pedestre', 'zero pedestres')):
        return 'Preencha pessoas por hora em pelo menos uma travessia do mapa ou desative a opção de incluir pedestres. Se necessário, aumente o volume ou a duração.'
    if 'step_seconds' in lowered and ('duraç' in lowered or 'múltipl' in lowered):
        return 'Os tempos dos semáforos precisam ser múltiplos do passo definido no cenário. Confira a configuração do estudo.'
    if 'decision_seconds' in lowered:
        return 'Nos ajustes avançados do treinamento, use um intervalo entre decisões igual ou maior que o passo definido no cenário.'
    if lowered.startswith('a duração da simulação precisa superar'):
        return text
    if any(t in lowered for t in ('measurement', 'warmup', 'medição', 'aquecimento', '0 ≤')):
        return 'Escolha uma duração compatível com o aquecimento e o passo definidos no cenário.'
    if any(t in lowered for t in ('limites ppo', 'mínimo', 'máximo de ciclo', 'phase_duration', 'maximum_cycle')):
        return 'Confira os tempos iniciais e os limites de verde em Treinamento → Configurações avançadas.'
    if any(t in lowered for t in ('n_steps', 'batch_size', 'minibatch', 'parâmetros ppo')):
        return 'Nos ajustes avançados do treinamento, a coleta precisa ser múltipla do tamanho do lote, e o lote não pode ser maior que a coleta.'
    if 'semente' in lowered:
        return 'Use números inteiros diferentes para as sementes de treino e avaliação, separados por vírgulas no campo de avaliação.'
    if any(t in lowered for t in ('sumo não encontrado', 'sumo nao encontrado')):
        return 'O simulador não foi encontrado. Confira a instalação do SUMO e sua configuração no computador.'
    if isinstance(error, (ValueError, TypeError)) and ('invalid literal' in lowered or 'could not convert' in lowered):
        return 'Confira os campos numéricos: preencha somente números válidos, sem letras ou campos vazios.'
    if 'prepare' in lowered or 'rede válida' in lowered:
        return 'Abra Cenário e tráfego. Se a rede apresentar erro de preparação, use Tentar novamente.'
    if any(t in lowered for t in ('zero veículos', 'gerar tráfego', 'veículos por hora')):
        return 'No mapa, preencha o volume de pelo menos uma via. Se necessário, aumente o volume ou a duração para gerar veículos.'
    return text or 'Confira os valores preenchidos antes de iniciar.'


def configuration_changes(config, baseline, *, restored_study=True):
    """Descreve edições do rascunho em relação à configuração que abriu os campos."""
    if baseline is None:
        return []
    def active_entries(source):
        return {
            row['from_edge']: (row['vehicles_per_hour'], row.get('to_edge') or '')
            for row in source.get('demand', {}).get('edge_volumes', []) if row['vehicles_per_hour'] > 0
        }

    def pedestrian_settings(source):
        settings = source.get('pedestrians', {})
        if not settings.get('enabled'):
            return False,
        flows = {(row['from_edge'], row['to_edge']): row['persons_per_hour']
                 for row in settings.get('flows', []) if row['persons_per_hour'] > 0}
        return True, settings.get('walking_speed_meters_per_second', .8), flows

    def green_limits(source):
        control = source.get('control', source.get('ppo', {}))
        bounds = control.get('phase_duration_bounds', {})
        greens = source.get('experimental', {}).get('green_floors', bounds)
        return {key: bounds[key] for key in greens if key in bounds}

    def optional_metrics(source, use_saved):
        metrics = source.get('metrics', {}) if use_saved else {}
        details = bool(metrics.get('collect_lane_details') or metrics.get('collect_extended'))
        extended = details and metrics.get('collect_extended', True)
        return (
            details and metrics.get('collect_lane_details', True), extended,
            extended and metrics.get('collect_vehicle_dynamics', True),
            extended and metrics.get('collect_vehicle_classes', True),
            metrics.get('collect_emissions', False),
            metrics.get('collect_events', True), metrics.get('collect_resources', True),
        )

    def visualization(source, use_saved):
        control = source.get('control', source.get('ppo', {}))
        gui = use_saved and control.get('gui', False)
        return gui, control.get('gui_delay_milliseconds', 0) if gui else 0

    changes = []
    before, after = active_entries(baseline), active_entries(config)
    roads = sum(before.get(edge) != after.get(edge) for edge in before.keys() | after.keys())
    if roads:
        changes.append('Fluxo alterado em 1 via' if roads == 1 else f'Fluxo alterado em {roads} vias')
    before_duration, after_duration = baseline['duration_seconds'], config['duration_seconds']
    if before_duration != after_duration:
        changes.append(f'Duração de {before_duration:g} para {after_duration:g} s')
    before_warmup = baseline.get('measurement', {}).get('warmup_seconds', 0)
    after_warmup = config.get('measurement', {}).get('warmup_seconds', 0)
    if before_warmup != after_warmup:
        changes.append(f'Aquecimento de {before_warmup:g} para {after_warmup:g} s')
    if baseline['step_seconds'] != config['step_seconds']:
        changes.append(f'Passo da simulação de {baseline["step_seconds"]:g} para {config["step_seconds"]:g} s')
    if baseline['demand'].get('time_profile') and not config['demand'].get('time_profile'):
        changes.append('Volume por hora constante ao longo da simulação')
    if pedestrian_settings(baseline) != pedestrian_settings(config):
        changes.append('Configuração de pedestres alterada')
    if green_limits(baseline) != green_limits(config):
        changes.append('Limites de verde alterados')
    if baseline.get('experimental', {}).get('network_sha256') != config.get('experimental', {}).get('network_sha256'):
        changes.append('Tempos do ciclo inicial alterados')
    if baseline.get('objectives') != config.get('objectives'):
        changes.append('Prioridades do treinamento alteradas')
    if baseline.get('seeds') != config.get('seeds') or baseline.get('evaluation') != config.get('evaluation'):
        changes.append('Sementes do estudo alteradas')
    from semaforos.algoritmos.registro import get_algorithm

    before_algorithm = get_algorithm(baseline.get('algorithm', 'PPO'))
    after_algorithm = get_algorithm(config.get('algorithm', 'PPO'))
    before_params = baseline.get(before_algorithm.config_key, {})
    after_params = config.get(after_algorithm.config_key, {})
    if before_algorithm.name != after_algorithm.name:
        changes.append(f'Algoritmo alterado de {before_algorithm.name} para {after_algorithm.name}')
    old, new = before_params.get('total_timesteps', 2048), after_params.get('total_timesteps', 2048)
    if old != new:
        changes.append(f'Decisões solicitadas de {old:,} para {new:,}'.replace(',', '.'))
    before_control = baseline.get('control', baseline.get('ppo', {}))
    after_control = config.get('control', config.get('ppo', {}))
    if (before_control.get('decision_seconds') != after_control.get('decision_seconds')
            or (before_algorithm.name == after_algorithm.name and any(
                before_params.get(key) != after_params.get(key) for key in ('n_epochs', 'n_steps', 'batch_size')
            ))):
        changes.append('Parâmetros avançados de treinamento alterados')
    if visualization(baseline, restored_study) != visualization(config, True):
        changes.append('Visualização durante o treino alterada')
    from semaforos.simulacao.detalhes import metric_settings

    try:
        thresholds_changed = metric_settings(baseline) != metric_settings(config)
    except (TypeError, ValueError):
        thresholds_changed = (baseline.get('metrics', {}).get('thresholds')
                              != config.get('metrics', {}).get('thresholds'))
    if optional_metrics(baseline, restored_study) != optional_metrics(config, True) or thresholds_changed:
        changes.append('Coleta de indicadores ou limiares alterados')
    return changes


def configuration_summary(config, error=None, *, baseline=None, raw_error=None):
    """Mostra somente as alterações e o atalho da primeira pendência."""
    if config is None:
        st.error(f'Não foi possível iniciar: {error}')
        issue = raw_error or error
        _, _, action = configuration_issue(issue)
        st.button(action, on_click=focus_configuration_issue, args=(issue,), key='fix_configuration')
        return
    restored = st.session_state.get('study_source', {}).get('kind') in ('duplicate', 'recovered')
    changes = configuration_changes(config, baseline, restored_study=restored)
    if changes:
        label = 'Ver 1 alteração antes de executar' if len(changes) == 1 else f'Ver {len(changes)} alterações antes de executar'
        with st.expander(label):
            st.markdown('\n'.join('- ' + change for change in changes))
