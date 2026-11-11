from streamlit.testing.v1 import AppTest


def test_flow_table_preserves_distribution_and_covers_duration():
    app = AppTest.from_string("""
import streamlit as st
from semaforos.apresentacao.fluxo import flow_profile_editor
st.session_state.profile = flow_profile_editor(600).to_dict('records')
""").run()
    assert not app.exception
    assert not app.select_slider
    assert not app.selectbox
    assert not app.number_input
    profile = app.session_state.profile
    assert profile[0]['begin'] == 0
    assert profile[-1]['end'] == 600
    masses = [(p['end'] - p['begin']) * p['multiplier'] for p in profile]
    assert masses == [25., 25., 25., 25.]
    assert profile[0]['end'] == profile[1]['begin']
