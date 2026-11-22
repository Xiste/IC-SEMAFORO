"""Escolhas para começar um rascunho a partir de um exemplo ou estudo salvo."""

from datetime import datetime
from pathlib import Path
from xml.etree.ElementTree import ParseError
from zoneinfo import ZoneInfo

import streamlit as st

from semaforos.apresentacao.estado import loaded_configuration_changed
from semaforos.apresentacao.layout import SETUP_TAB, select_workflow_tab
from semaforos.arquivos import read_json
from semaforos.cenario.configuracao import read_config
from semaforos.cenario.experimental import intersection_names, validate_experimental


def example_configuration(path):
    """Usa entradas reais da rede com volumes inteiramente ilustrativos."""
    import sumolib

    config = read_config(path)
    network = sumolib.net.readNet(str(config['network']))
    controller = network.getTLS(config['targets'][0]['tls_id'])
    entries = sorted({lane.getEdge().getID() for lane, _, _ in controller.getConnections()
                      if lane.getEdge().allows('passenger')
                      and any(outgoing.allows('passenger') for outgoing in lane.getEdge().getOutgoing())})
    if not entries:
        raise ValueError('A rede do exemplo não tem entradas disponíveis para veículos.')
    config['demand'] = {'mode': 'edge_volumes', 'synthetic': True, 'edge_volumes': [
        {'from_edge': edge, 'vehicles_per_hour': 360., 'to_edge': ''} for edge in entries]}
    return config


def activate_study_configuration(config, kind, label):
    rows = validate_experimental(config) if config.get('experimental') else None
    loaded_configuration_changed()
    st.session_state['loaded_config'] = config
    st.session_state['study_source'] = {'kind': kind, 'label': label}
    st.session_state.pop('configuration_focus', None)
    st.session_state.pop('configuration_focus_object', None)
    if rows is not None:
        st.session_state['experimental_config'] = config
        st.session_state['experimental_rows'] = rows
    else:
        st.session_state.pop('experimental_config', None)
        st.session_state.pop('experimental_rows', None)


def load_study_configuration(path, kind='recovered'):
    """Carrega um novo rascunho e deixa a execução acompanhada como está."""
    try:
        config = read_config(path)
        if kind == 'duplicate' and not can_duplicate(config, set(intersection_names())):
            raise ValueError('O cenário salvo não é compatível com os campos da interface atual.')
        activate_study_configuration(config, kind, Path(path).parent.name)
    except (ValueError, OSError, KeyError, TypeError, ParseError) as error:
        return f'Não foi possível carregar a configuração: {error}'
    return None


def can_duplicate(config, names):
    """Oferece cópia somente quando a interface pode representar o cenário."""
    from semaforos.algoritmos.registro import available_algorithms

    window = config.get('measurement', {})
    warmup = window.get('warmup_seconds', 0)
    duration = config.get('duration_seconds')
    return (
        config.get('experimental', {}).get('method') == 'compatible_groups_v2'
        and {target['name'] for target in config.get('targets', [])} == names
        and config.get('algorithm', 'PPO') in available_algorithms()
        and config.get('demand', {}).get('mode') == 'edge_volumes'
        and config.get('control', config.get('ppo', {})).get('action_mode') == 'adaptive_signals'
        and window.get('start_seconds', warmup) == warmup
        and window.get('end_seconds', duration) == duration
    )


@st.cache_data(show_spinner=False)
def duplicate_choice(config_path, file_version, names):
    try:
        config = read_json(config_path)
        if config and can_duplicate(config, set(names)):
            folder = Path(config_path).parent
            job = read_json(folder / 'job.json') or {}
            command = {
                'rl-train': 'Treinamento',
                'rl-eval': 'Avaliação',
                'run-reference': 'Simulação inicial',
                'compare-baselines': 'Comparação por filas',
                'run-study': 'Estudo com repetições',
            }.get(job.get('command'), 'Estudo')
            when = datetime.fromtimestamp(file_version / 1e9, ZoneInfo('America/Sao_Paulo'))
            return f'{command} · {when:%d/%m/%Y %H:%M} · {folder.name}'
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        pass
    return None


def render_study_starts(default_path, jobs):
    def start_example():
        try:
            config = example_configuration(default_path)
            activate_study_configuration(config, 'example', 'Exemplo ilustrativo')
        except (OSError, ValueError, KeyError, ParseError) as error:
            st.session_state['study_start_error'] = f'Não foi possível abrir o exemplo: {error}'
        else:
            st.session_state['configuration_focus'] = 'roads'
            st.session_state['configuration_focus_object'] = {'edge_id': config['demand']['edge_volumes'][0]['from_edge']}
            select_workflow_tab(SETUP_TAB)

    def duplicate():
        selected = st.session_state.get('study_duplicate_selection')
        if selected is None:
            return
        error = load_study_configuration(selected, kind='duplicate')
        if error:
            st.session_state['study_start_error'] = error
        else:
            select_workflow_tab(SETUP_TAB)

    source = st.session_state.get('study_source')
    with st.expander('Iniciar um estudo', expanded=not source or bool(st.session_state.get('study_start_error'))):
        st.caption('Cada opção troca os ajustes da tela por um novo rascunho editável.')
        st.button('Começar com um exemplo', on_click=start_example)
        st.caption('Dez minutos simulados, com volumes ilustrativos nas entradas de Rondon × Paraná.')
        choices = {}
        if jobs:
            names = tuple(intersection_names())
            for job in jobs:
                path = job['folder'] / 'cenario.json'
                try:
                    version = path.stat().st_mtime_ns
                except OSError:
                    continue
                label = duplicate_choice(str(path), version, names)
                if label:
                    choices[str(path)] = label
        if choices:
            st.selectbox('Estudo para duplicar', list(choices), index=None,
                         format_func=choices.__getitem__, key='study_duplicate_selection',
                         placeholder='Selecione uma configuração salva')
            st.button('Duplicar estudo anterior', on_click=duplicate,
                      disabled=st.session_state.get('study_duplicate_selection') not in choices)
        else:
            st.button('Duplicar estudo anterior', disabled=True)
            st.caption('Os estudos com a rede completa e o controle adaptativo aparecem aqui depois de executar.')
        error = st.session_state.pop('study_start_error', None)
        if error:
            st.error(error)
    if source:
        prefix = 'Cópia de ' if source['kind'] == 'duplicate' else ''
        st.caption(f"Rascunho: {prefix}{source['label']}")
