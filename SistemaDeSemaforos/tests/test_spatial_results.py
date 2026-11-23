import tempfile
import unittest
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest
from semaforos.apresentacao.resultados import signal_green_comparison


class SpatialResultsTest(unittest.TestCase):
    def test_green_seconds_compare_only_complete_pairs_and_keep_zero(self):
        rows = [
            [101, 'network_reference', True, 15, 8],
            [101, 'PPO', True, 19, 0],
            [102, 'network_reference', True, 14, 5],
            [102, 'PPO', False, 10, 5],
            [103, 'network_reference', True, 24, 9],
            [103, 'PPO', True, 30, 4],
            [104, 'network_reference', True, 17, 10],
            [104, 'PPO', True, 19, 8],
        ]
        signals = pd.DataFrame(rows, columns=['seed', 'controller', 'episode_complete', 'phase_0_seconds', 'phase_3_seconds'])
        signals['tls_id'] = 'signal'
        targets = [{'tls_id': 'signal', 'name': 'Cruzamento A'}]
        stages = {'signal': [(0, 'Rua A'), (3, 'Rua B')]}
        table = signal_green_comparison(signals, 'PPO', [101, 102, 104], targets, stages)
        self.assertEqual(table['Tempos iniciais (s)'].tolist(), [16., 9.])
        self.assertEqual(table['Controle avaliado (s)'].tolist(), [19., 4.])
        self.assertEqual(table['Diferença (s)'].tolist(), [3., -5.])

    def test_map_and_details_use_completed_pairs_with_matching_demand(self):
        def case(controller, seed, actual_demand, arrivals, complete=True):
            return {'controller': controller, 'seed': seed, 'demand_sha256': actual_demand,
                    'episode_complete': complete, 'arrived': arrivals}

        runs = [
            case('network_reference', 101, 'same', 12),
            case('PPO', 101, 'same', 14),
            case('network_reference', 102, 'same', 20),
            case('PPO', 102, 'same', 15, complete=False),
            case('network_reference', 103, 'different-base', 30),
            case('PPO', 103, 'different-candidate', 33),
            case('queue_actuated', 101, 'same', 40),
        ]
        # Local rows marked complete must still respect the global paired runs.
        intersections = [
            {'intersection': 'Rondon x Paraná', 'controller': run['controller'], 'seed': run['seed'],
             'episode_complete': True, 'wait_vehicle_seconds': wait}
            for run, wait in zip(runs, (75, 50, 90, 0, 110, 0))
        ]
        intersections.extend([
            {'intersection': 'Rondon x Niterói', 'controller': 'network_reference', 'seed': 101,
             'episode_complete': True, 'wait_vehicle_seconds': 25},
            {'intersection': 'Rondon x Niterói', 'controller': 'PPO', 'seed': 101,
             'episode_complete': True, 'wait_vehicle_seconds': None},
        ])
        coordinates = [
            {'intersection': 'Rondon x Paraná', 'latitude': -18.899, 'longitude': -48.265},
            {'intersection': 'Rondon x Niterói', 'latitude': -18.907, 'longitude': -48.267},
        ]
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            for file, rows in (('runs.csv', runs), ('intersections.csv', intersections), ('gargalos.csv', coordinates)):
                pd.DataFrame(rows).to_csv(output / file, index=False)
            app = AppTest.from_string(
                f"import streamlit as st\n"
                f"from semaforos.apresentacao.resultados import render_execution_results\n"
                "view = st.radio('Visualiza\\u00e7\\u00e3o', ['Resumo', 'M\\u00e9tricas'])\n"
                f"render_execution_results({str(output)!r}, 'spatial', view)"
            ).run()
            self.assertFalse(app.exception, str(app.exception))
            arrivals = next(metric for metric in app.metric if metric.label == 'Viagens concluídas na rede')
            self.assertEqual(arrivals.value, '14')
            self.assertFalse(app.get('deck_gl_json_chart'))
            self.assertFalse(app.get('download_button'))
            self.assertFalse(app.selectbox)
            app.radio[0].set_value('Métricas').run()
            self.assertFalse(app.exception, str(app.exception))
            self.assertTrue(app.get('deck_gl_json_chart'))
            self.assertEqual(len(app.get('download_button')), 1)
            detail = next(widget for widget in app.selectbox if widget.label == 'Cruzamento para detalhar')
            detail.select('Rondon x Paraná').run()
            self.assertFalse(app.exception, str(app.exception))
            change = next(metric for metric in app.metric if metric.label == 'Menos espera')
            self.assertEqual(change.value, '-25,0 veículo·s')
            detail.select('Rondon x Niterói').run()
            self.assertFalse(app.exception, str(app.exception))
            self.assertTrue(any('dados de espera' in item.value for item in app.info))
