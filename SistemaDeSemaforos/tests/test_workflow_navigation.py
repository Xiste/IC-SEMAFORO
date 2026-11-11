from streamlit.testing.v1 import AppTest

from semaforos.apresentacao.layout import configuration_guidance


def test_continue_back_and_manual_navigation_choose_the_visible_section():
    app = AppTest.from_string(r'''
import streamlit as st
from semaforos.apresentacao.layout import workflow_navigation, select_workflow_tab
sections = workflow_navigation()
with sections[0]:
    st.button('Continue', on_click=select_workflow_tab, args=('2 \u00b7 Tr\u00e1fego',))
with sections[1]:
    st.button('Back', on_click=select_workflow_tab, args=('1 \u00b7 Cen\u00e1rio',))
''').run()
    app.button[0].click().run()
    assert app.radio[0].value == '2 · Tráfego'
    assert '.st-key-view_traffic' not in app.markdown[0].value
    assert '.st-key-view_scenario' in app.markdown[0].value
    app.button[1].click().run()
    assert app.radio[0].value == '1 · Cenário'
    app.radio[0].set_value('4 · Resultados').run()
    assert app.session_state.ui_default_tab == '4 · Resultados'
    assert '.st-key-view_results' not in app.markdown[0].value
    assert not app.exception


def test_validation_points_to_the_relevant_step():
    assert configuration_guidance('Prepare o cenário')[0] == '1 · Cenário'
    assert configuration_guidance('Aquecimento inválido')[0] == '2 · Tráfego'
    assert configuration_guidance('Informe veículos por hora')[0] == '2 · Tráfego'
    assert configuration_guidance('Limites PPO inválidos')[0] == '3 · Treinamento'
