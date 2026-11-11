import tempfile
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest
from semaforos.apresentacao.pedestres import pedestrian_route_details


class PedestrianLabelsTest(unittest.TestCase):
    def test_direction_uses_crossing_connections_and_handles_reverse_route(self):
        with tempfile.TemporaryDirectory() as temporary:
            network = Path(temporary) / 'network.xml'
            network.write_text('''<net>
                <edge id="cross" function="crossing"><lane shape="0,0 10,0"/></edge>
                <connection from="accessA" to="areaA"/><connection from="accessB" to="areaB"/>
                <connection from="areaA" to="cross"/><connection from="cross" to="areaB"/>
                </net>''', encoding='utf-8')
            routes = [dict(intersection='Local A', crossing_id='cross', from_edge='accessA', to_edge='accessB', persons_per_hour=120),
                      dict(intersection='Local A', crossing_id='cross', from_edge='accessB', to_edge='accessA', persons_per_hour=60)]
            details = pedestrian_route_details(network, routes)
            self.assertEqual((details[0]['origin_side'], details[0]['destination_side']), ('oeste', 'leste'))
            self.assertEqual((details[1]['origin_side'], details[1]['destination_side']), ('leste', 'oeste'))
            self.assertEqual(details[0]['reference'], details[1]['reference'])
            source = f'''from semaforos.apresentacao.pedestres import pedestrian_editor
import streamlit as st
table = pedestrian_editor({str(network)!r}, {routes!r}, 'pedestrians_test')
st.session_state.exported = table.to_dict('records')
'''
            app = AppTest.from_string(source).run()
            self.assertFalse(app.exception, str(app.exception))
            self.assertEqual(app.session_state['exported'], routes)
            app.selectbox[1].select_index(1).run()
            self.assertFalse(app.exception, str(app.exception))
            self.assertIn('leste -> oeste', app.selectbox[1].value)
            self.assertTrue(any('Verde: partida' in w.value for w in app.caption))
