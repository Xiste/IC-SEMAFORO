from streamlit.testing.v1 import AppTest


def change(app, token, edits):
    key = next(k for k, value in app.session_state.filtered_state.items()
               if token in k and isinstance(value, dict) and 'edited_rows' in value)
    app.session_state[key] = {'edited_rows': edits, 'added_rows': [], 'deleted_rows': []}
    app.run()
    assert not app.exception


def test_vehicle_crossings_hidden_editor_and_loaded_configuration():
    source = '''
import streamlit as st
from semaforos.apresentacao.vias import edit_road_volumes
from semaforos.apresentacao.estado import loaded_configuration_changed
st.button('Carregar outra configuracao', on_click=loaded_configuration_changed)
if st.toggle('Mostrar editor', value=True):
    initial = [dict(from_edge=e, vehicles_per_hour=10., to_edge='') for e in ('a1','a2','b1')]
    details = {e: dict(crossing=e[0], reference='Entrada '+e, street='Rua '+e, approach='norte', label=e) for e in ('a1','a2','b1')}
    table = edit_road_volumes('network', initial, details, tuple(details), lambda *args: None)
    st.session_state.result = table.to_dict('records')
'''
    app = AppTest.from_string(source).run()
    change(app, 'volume_editor_', {0: {'vehicles_per_hour': 420.}, 1: {'vehicles_per_hour': 730.}})
    app.selectbox[0].select('b').run()
    change(app, 'volume_editor_', {0: {'vehicles_per_hour': 160.}})
    app.selectbox[0].select('a').run()
    assert [r['vehicles_per_hour'] for r in app.session_state.result] == [420., 730., 160.]
    app.toggle[0].set_value(False).run()
    app.toggle[0].set_value(True).run()
    assert [r['vehicles_per_hour'] for r in app.session_state.result] == [420., 730., 160.]
    app.button[0].click().run()
    assert [r['vehicles_per_hour'] for r in app.session_state.result] == [10., 10., 10.]


def test_pedestrian_crossings_keep_each_direction(tmp_path):
    network = tmp_path / 'network.xml'
    xml = '<net>'
    defaults = []
    for name, x in [('A', 0), ('B', 40)]:
        xml += f'''<edge id="cross{name}" function="crossing"><lane shape="{x},0 {x+10},0"/></edge>
        <connection from="access{name}1" to="area{name}1"/>
        <connection from="access{name}2" to="area{name}2"/>
        <connection from="area{name}1" to="cross{name}"/>
        <connection from="cross{name}" to="area{name}2"/>'''
        defaults.extend([dict(intersection=name, crossing_id=f'cross{name}', from_edge=f'access{name}{i}',
                              to_edge=f'access{name}{3-i}', persons_per_hour=10.) for i in (1, 2)])
    network.write_text(xml + '</net>', encoding='utf-8')
    source = f'''
import streamlit as st
from semaforos.apresentacao.pedestres import pedestrian_editor
if st.toggle('Mostrar editor', value=True):
    st.session_state.result = pedestrian_editor({str(network)!r}, {defaults!r}, 'ped').to_dict('records')
'''
    app = AppTest.from_string(source).run()
    assert not app.exception
    change(app, '_editor_', {0: {'persons_per_hour': 120.}, 1: {'persons_per_hour': 60.}})
    app.selectbox[0].select('B').run()
    change(app, '_editor_', {0: {'persons_per_hour': 90.}})
    app.selectbox[0].select('A').run()
    app.selectbox[1].select_index(1).run()
    assert [r['persons_per_hour'] for r in app.session_state.result] == [120., 60., 90., 10.]
    app.toggle[0].set_value(False).run()
    app.toggle[0].set_value(True).run()
    assert [r['persons_per_hour'] for r in app.session_state.result] == [120., 60., 90., 10.]
