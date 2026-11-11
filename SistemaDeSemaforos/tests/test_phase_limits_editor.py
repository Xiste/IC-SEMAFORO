from streamlit.testing.v1 import AppTest


def test_adaptive_limits_edit_entries_and_preserve_other_crossings(tmp_path):
    network = tmp_path / 'network.xml'
    network.write_text('''<net>
      <connection tl="a" from="roadA" to="outA" linkIndex="0" dir="s"/>
      <connection tl="b" from="roadB" to="outB" linkIndex="0" dir="l"/>
      <tlLogic id="a"><phase state="G" duration="20"/><phase state="y" duration="3"/><phase state="r" duration="2"/></tlLogic>
      <tlLogic id="b"><phase state="G" duration="20"/><phase state="y" duration="3"/><phase state="r" duration="2"/></tlLogic>
      </net>''', encoding='utf-8')
    source = f'''
import streamlit as st
from semaforos.apresentacao.treinamento import adaptive_limits_editor
config = {{'network': {str(network)!r}, 'targets': [{{'tls_id': 'a', 'name': 'Local A'}}, {{'tls_id': 'b', 'name': 'Local B'}}]}}
specs = [dict(tls_id=tls, phase_index=i, kind=kind, durations_seconds=bounds)
         for tls in ('a', 'b') for i, kind, bounds in [(0, 'green', [10, 20, 30]), (1, 'yellow', [3, 3, 6]), (2, 'all_red', [2, 2, 4])]]
st.session_state.result = adaptive_limits_editor(config, specs, {{'roadA': 'Entrada 1', 'roadB': 'Entrada 2'}}, 'adaptive').to_dict('records')
'''
    app = AppTest.from_string(source).run()
    assert not app.exception
    assert len(app.selectbox) == 1
    assert 'Entrada 1: seguir em frente' in app.dataframe[0].value.iloc[0]['entries']
    editor = next(k for k in app.session_state.filtered_state if k.endswith('_editor'))
    app.session_state[editor] = {'edited_rows': {0: {'minimum_seconds': 12}}, 'added_rows': [], 'deleted_rows': []}
    app.run()
    app.selectbox[0].select('Local B').run()
    assert app.session_state.result[0]['minimum_seconds'] == 12
    assert app.session_state.result[3]['minimum_seconds'] == 10
    assert app.session_state.result[1]['maximum_seconds'] == 3
    assert app.session_state.result[2]['maximum_seconds'] == 2
    app.selectbox[0].select('Local A').run()
    assert not app.exception
    assert app.dataframe[0].value.iloc[0]['minimum_seconds'] == 12


def test_filters_preserve_hidden_limits_and_edits():
    app = AppTest.from_string('''
import streamlit as st
from semaforos.apresentacao.treinamento import phase_limits_editor
rows = []
for crossing, controller in [('Local A', 'a'), ('Local B', 'b')]:
    for stage in range(1, 3):
        for offset, kind in enumerate(['Green', 'Yellow', 'Safety']):
            rows.append(dict(key=f'{controller}:{(stage-1)*3+offset}', crossing=crossing,
                signals=f'Entradas de {crossing}', stage=f'Etapa {stage}', type=kind,
                reference=20., minimum_seconds=10., maximum_seconds=30.))
st.session_state.result = phase_limits_editor(rows, 'test').to_dict('records')
''').run()
    assert not app.exception
    assert len(app.dataframe[0].value) == 3
    editor_key = next(key for key in app.session_state.filtered_state if '_editor_' in key)
    # Simula a edição enviada pelo componente de tabela do Streamlit.
    app.session_state[editor_key] = {'edited_rows': {0: {'minimum_seconds': 12.}}, 'added_rows': [], 'deleted_rows': []}
    app.run()
    assert app.session_state.result[0]['minimum_seconds'] == 12.
    app.selectbox[2].select('Etapa 2').run()
    assert app.dataframe[0].value['stage'].tolist() == ['Etapa 2'] * 3
    assert len(app.session_state.result) == 12
    assert app.session_state.result[0]['minimum_seconds'] == 12.
    app.selectbox[0].select('Local B').run()
    assert not app.exception
    assert app.dataframe[0].value['crossing'].tolist() == ['Local B'] * 3
    app.selectbox[0].select('Local A').run()
    app.selectbox[2].select('Etapa 1').run()
    assert app.dataframe[0].value.iloc[0]['minimum_seconds'] == 12.
    assert all(row['minimum_seconds'] == 10 for row in app.session_state.result[1:])
