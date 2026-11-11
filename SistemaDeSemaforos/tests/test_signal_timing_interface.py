import unittest

from streamlit.testing.v1 import AppTest


class SignalTimingInterfaceTest(unittest.TestCase):
    def test_switching_crossings_does_not_keep_another_controller(self):
        app = AppTest.from_string(r'''
import streamlit as st
from semaforos.apresentacao.layout import preparation_summary
single = st.toggle('Somente B')
if st.toggle('Simular estado antigo'):
    st.session_state["signal_timing_controller_B_('b1',)"] = 'a2'
rows, timings = [], []
for crossing, controller, seconds in [('A', 'a1', 24), ('A', 'a2', 30), ('B', 'b1', 40), ('C', 'c1', 50)]:
    if single and crossing != 'B':
        continue
    rows.append({'cruzamento': crossing, 'controlador': controller, 'ciclo_inicial_s': 77})
    timings.append({'cruzamento': crossing, 'controlador': controller, 'Grupo': 'Grupo 1',
                    'Verde (s)': seconds, 'Amarelo (s)': 3, 'Vermelho total (s)': 74 - seconds,
                    'Limpeza ap\u00f3s amarelo (s)': 8, 'Movimentos liberados': controller})
preparation_summary(rows, timings=timings)
''').run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.selectbox), 1)
        self.assertEqual(app.dataframe[0].value['Verde (s)'].tolist(), [24, 30])
        self.assertNotIn('Etapa', app.dataframe[0].value.columns)
        for crossing, expected in [('B', [40]), ('C', [50]), ('A', [24, 30]), ('B', [40])]:
            app.selectbox[0].set_value(crossing).run()
            self.assertFalse(app.exception, str(app.exception))
            self.assertEqual(app.dataframe[0].value['Verde (s)'].tolist(), expected)
        app.toggle[1].set_value(True).run()
        self.assertFalse(app.exception, str(app.exception))
        self.assertEqual(app.dataframe[0].value['Verde (s)'].tolist(), [40])
        app.toggle[0].set_value(True).run()
        self.assertFalse(app.exception, str(app.exception))
        self.assertEqual(app.dataframe[0].value['Verde (s)'].tolist(), [40])
