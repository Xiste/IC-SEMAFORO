import tempfile
import unittest
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest


class SpatialResultsTest(unittest.TestCase):
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
                f"from semaforos.apresentacao.resultados import result_overview\nresult_overview({str(output)!r}, 'spatial')"
            ).run()
            self.assertFalse(app.exception, str(app.exception))
            self.assertTrue(app.get('deck_gl_json_chart'))
            arrivals = next(metric for metric in app.metric if metric.label == 'Viagens concluídas na rede')
            self.assertEqual(arrivals.value, '14.0')
            detail = next(widget for widget in app.selectbox if widget.label == 'Cruzamento para detalhar')
            detail.select('Rondon x Paraná').run()
            self.assertFalse(app.exception, str(app.exception))
            change = next(metric for metric in app.metric if metric.label == 'Menos espera')
            self.assertEqual(change.value, '-25,0 veículo·s')
            detail.select('Rondon x Niterói').run()
            self.assertFalse(app.exception, str(app.exception))
            self.assertTrue(any('dados de espera' in item.value for item in app.info))
