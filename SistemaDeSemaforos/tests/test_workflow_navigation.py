from streamlit.testing.v1 import AppTest

from semaforos.apresentacao.layout import configuration_guidance


def test_continue_back_and_manual_navigation_choose_the_visible_section():
    app = AppTest.from_string(r'''
import streamlit as st
from semaforos.apresentacao.layout import workflow_navigation, select_workflow_tab
sections = workflow_navigation()
with sections[0]:
    st.button('Continue', on_click=select_workflow_tab, args=('2 \u00b7 Treinamento',))
with sections[1]:
    st.button('Back', on_click=select_workflow_tab, args=('1 \u00b7 Cen\u00e1rio e tr\u00e1fego',))
''').run()
    assert app.radio[0].value == '1 · Cenário e tráfego'
    app.button[0].click().run()
    assert app.radio[0].value == '2 · Treinamento'
    assert '.st-key-view_training' not in app.markdown[0].value
    assert '.st-key-view_traffic' in app.markdown[0].value
    app.button[1].click().run()
    assert app.radio[0].value == '1 · Cenário e tráfego'
    app.radio[0].set_value('3 · Resultados').run()
    assert app.session_state.ui_default_tab == '3 · Resultados'
    assert '.st-key-view_results' not in app.markdown[0].value
    assert not app.exception


def test_validation_points_to_the_relevant_step():
    for error in ('Prepare o cenário', 'Aquecimento inválido', 'Informe veículos por hora'):
        assert configuration_guidance(error)[0] == '1 · Cenário e tráfego'
    assert configuration_guidance('Limites PPO inválidos')[0] == '2 · Treinamento'


def test_fix_button_opens_training_limits_with_affected_controller():
    app = AppTest.from_string(r'''
from semaforos.apresentacao.layout import configuration_summary, workflow_navigation
sections = workflow_navigation()
with sections[1]:
    configuration_summary(None, 'Confira o verde do semaforo',
                          raw_error=ValueError('Limites PPO inv\u00e1lidos para FAM_RONDON_PARANA:0'))
''').run()
    app.radio[0].set_value('2 · Treinamento').run()
    app.button[0].click().run()
    assert app.radio[0].value == '2 · Treinamento'
    assert app.session_state['configuration_focus'] == 'green_limits'
    assert app.session_state['configuration_focus_object'] == {'tls_id': 'FAM_RONDON_PARANA'}
    assert not app.exception
