import tempfile
import unittest
from pathlib import Path

from semaforos.cenario.rede import initial_signal_timings


class SignalTimingTest(unittest.TestCase):
    def test_red_includes_other_groups_and_all_clearance_intervals(self):
        with tempfile.TemporaryDirectory() as temporary:
            network = Path(temporary) / 'network.xml'
            network.write_text('''<net>
              <edge id="a" name="Avenida A"/><edge id="b" name="Rua B"/>
              <connection tl="signal" from="a" to="b" dir="s" linkIndex="0"/>
              <connection tl="signal" from="b" to="a" dir="l" linkIndex="1"/>
              <tlLogic id="signal">
                <phase duration="24" state="Gr"/><phase duration="3" state="yr"/>
                <phase duration="8" state="rr"/><phase duration="30" state="rG"/>
                <phase duration="3" state="ry"/><phase duration="9" state="rr"/>
              </tlLogic></net>''', encoding='utf-8')
            rows = initial_signal_timings({'network': network, 'targets': [
                {'name': 'Cruzamento A', 'tls_id': 'signal', 'phase_indices': [0, 3]}]})
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]['Verde (s)'], 24)
            self.assertEqual(rows[0]['Amarelo (s)'], 3)
            self.assertEqual(rows[0]['Vermelho total (s)'], 50)
            self.assertEqual(rows[0]['Limpeza após amarelo (s)'], 8)
            self.assertEqual(rows[1]['Vermelho total (s)'], 44)
            self.assertEqual(rows[1]['Limpeza após amarelo (s)'], 9)
            for row in rows:
                self.assertEqual(sum(row[key] for key in ('Verde (s)', 'Amarelo (s)', 'Vermelho total (s)')), 77)
            self.assertIn('Avenida A', rows[0]['Movimentos liberados'])
            self.assertIn('esquerda', rows[1]['Movimentos liberados'])
