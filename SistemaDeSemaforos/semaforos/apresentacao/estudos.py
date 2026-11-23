"""Recuperação de configurações salvas como rascunhos."""

from pathlib import Path
from xml.etree.ElementTree import ParseError

import streamlit as st

from semaforos.apresentacao.estado import loaded_configuration_changed
from semaforos.cenario.configuracao import read_config
from semaforos.cenario.experimental import validate_experimental


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


def load_study_configuration(path):
    """Carrega um novo rascunho e deixa a execução acompanhada como está."""
    try:
        config = read_config(path)
        activate_study_configuration(config, 'recovered', Path(path).parent.name)
    except (ValueError, OSError, KeyError, TypeError, ParseError) as error:
        return f'Não foi possível carregar a configuração: {error}'
    return None
