import copy

import pytest
from streamlit.testing.v1 import AppTest

from semaforos.caminhos import PROJECT_ROOT
from semaforos.cenario.ciclos import adjusted_programs, include_adjusted_times, save_adjusted_network
from semaforos.cenario.configuracao import read_config
from semaforos.cenario.experimental import digest, prepare_or_reuse, validate_experimental
from semaforos.cenario.rede import network_programs, phase_action_spec


def test_adjusted_timing_keeps_phase_states_and_original_network(tmp_path):
    original = read_config(PROJECT_ROOT / 'config/cenario_rede_corrigida.json')
    config, _, _ = prepare_or_reuse(original, PROJECT_ROOT / 'resultados')
    source = config['network']
    before = digest(source)
    programs = network_programs(source)
    controller = 'FAM_RONDON_PARANA'
    edits = {f'{controller}:{index}': programs[controller][index]['duration'] + 1 for index in range(3)}
    edits[f'{controller}:1'] = max(edits[f'{controller}:1'], 4.)
    effective = adjusted_programs(config, programs, edits)
    original_params = copy.deepcopy(config['control'])
    include_adjusted_times(config['control'], effective, edits)
    phase_action_spec(config, effective)
    save_adjusted_network(config, edits, tmp_path)
    validate_experimental(config)
    assert digest(source) == before
    assert network_programs(config['network']) == effective
    assert [p['state'] for p in effective[controller]] == [p['state'] for p in programs[controller]]
    assert config['control']['phase_duration_bounds'][f'{controller}:1']['maximum_seconds'] == edits[f'{controller}:1']
    assert config['control']['maximum_cycle_seconds'] == original_params['maximum_cycle_seconds']
    with pytest.raises(ValueError, match='pelo menos'):
        adjusted_programs(config, programs, {f'{controller}:1': 1.})


def test_apply_times_stores_green_yellow_and_all_red(tmp_path):
    network = tmp_path / 'cycle.net.xml'
    network.write_text('''<net><edge id="road" name="Rua A"/><edge id="exit"/>
        <connection from="road" to="exit" tl="control" linkIndex="0" dir="s"/>
        <tlLogic id="control"><phase duration="24" state="G"/><phase duration="3" state="y"/>
        <phase duration="3" state="r"/></tlLogic></net>''', encoding='utf-8')
    app = AppTest.from_string(f'''
import streamlit as st
from semaforos.apresentacao.mapa_configuracao import cycle_edit_key, edit_initial_cycle
base = {{
    'network': {str(network)!r}, 'targets': [{{'tls_id': 'control', 'name': 'Local A', 'phase_indices': [0]}}],
    'step_seconds': 1, 'training': {{'minimum_green_seconds': 8, 'minimum_yellow_seconds': 3, 'minimum_all_red_seconds': 3}},
    'ppo': {{'maximum_cycle_seconds': 60}},
    'experimental': {{'method': 'compatible_groups_v2', 'green_floors': {{'control:0': 8}},
                       'minimum_durations': {{'control:1': 3, 'control:2': 3}}}}
}}
edit_initial_cycle(base, 'control', {{}}, 'test')
st.session_state['edits'] = st.session_state.get(cycle_edit_key(base['network']), {{}})
''').run()
    values = {'Verde (s)': 27., 'Amarelo (s)': 4., 'Todos em vermelho (s)': 5.}
    for widget in app.number_input:
        widget.set_value(values[widget.label])
    app.button[0].click().run()
    assert not app.exception
    assert app.session_state['edits'] == {'control:0': 27., 'control:1': 4., 'control:2': 5.}
