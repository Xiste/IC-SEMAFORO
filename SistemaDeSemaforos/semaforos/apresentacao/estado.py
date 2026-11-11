"""Separa edições de configurações carregadas, sem alterar o estado das execuções."""
import streamlit as st


def configuration_key(name):
    return f'configuration_{st.session_state.get("configuration_revision", 0)}_{name}'


def loaded_configuration_changed():
    st.session_state['configuration_revision'] = st.session_state.get('configuration_revision', 0) + 1
