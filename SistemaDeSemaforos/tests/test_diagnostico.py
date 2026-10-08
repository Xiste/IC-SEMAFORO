import tempfile
import unittest
from pathlib import Path

import pandas as pd

from semaforos.cenario.importacao import parse_counts, count_period
from semaforos.relatorios.diagnostico import export_diagnostics


class DiagnosticsTest(unittest.TestCase):
    def rows(self):
        rows = []
        for seed in (101, 102, 103):
            for controller in ('network_reference', 'queue_actuated'):
                better = controller == 'queue_actuated'
                rows.append({'controller': controller, 'seed': seed, 'episode_complete': True,
                    'simulated_seconds': 600, 'demand_sha256': f'demand_{seed}',
                    'global_halted_vehicle_seconds': 50 if better else 100,
                    'wait_vehicle_seconds': 40 if better else 80,
                    'arrived': 90, 'unfinished': 10, 'pending_departure': 0,
                    'collision_vehicles': 0, 'teleports_started': 0, 'planned_pedestrians': 0})
        return pd.DataFrame(rows)

    def diagnose(self, rows, config=None, flows=None):
        with tempfile.TemporaryDirectory() as folder:
            if flows is not None:
                pd.DataFrame(flows).to_csv(Path(folder) / 'flow_counts.csv', index=False)
            return export_diagnostics(folder, rows, {'evaluation_config': config or {'demand': {'mode': 'random'}},
                                                       'evaluation_seeds': [101, 102, 103]})

    def test_improvement_requires_paired_demand_service_and_confidence(self):
        rows = self.rows()
        report = self.diagnose(rows)
        self.assertTrue(report['conclusions'][0]['consistent_simulated_improvement'])
        queue = next(r for r in report['comparisons'] if r['metric'] == 'global_halted_vehicle_seconds')
        self.assertEqual(queue['improvement_percent'], 50)
        self.assertEqual(queue['benefit_ci95_low'], 50)
        rows.loc[rows.controller == 'queue_actuated', 'arrived'] = 89
        self.assertFalse(self.diagnose(rows)['conclusions'][0]['consistent_simulated_improvement'])
        rows = self.rows()
        rows.loc[(rows.controller == 'queue_actuated') & (rows.seed == 101), 'demand_sha256'] = 'other_routes'
        self.assertFalse(self.diagnose(rows)['conclusions'][0]['same_demand_and_horizon'])

    def test_partial_zero_reference_and_single_seed_are_not_proof(self):
        rows = self.rows()
        rows['mean_travel_time_seconds'] = None  # Nenhuma chegada em um teste curto.
        self.assertFalse(any(row['metric'] == 'mean_travel_time_seconds' for row in self.diagnose(rows)['comparisons']))
        rows.loc[rows.seed == 103, 'episode_complete'] = False
        self.assertFalse(self.diagnose(rows)['conclusions'][0]['complete_comparison'])
        rows = self.rows()[lambda r: r.seed == 101].copy()
        rows.loc[:, 'global_halted_vehicle_seconds'] = 0
        report = self.diagnose(rows)
        self.assertFalse(report['conclusions'][0]['consistent_simulated_improvement'])
        queue = next(r for r in report['comparisons'] if r['metric'] == 'global_halted_vehicle_seconds')
        self.assertIsNone(queue['improvement_percent'])
        self.assertIsNone(queue['benefit_ci95_low'])

    def test_mathematical_fit_does_not_certify_realized_flow(self):
        flows = [{'controller': 'network_reference', 'seed': seed, 'episode_complete': True, 'edge_id': 'a',
                  'measured_vehicles_per_hour': 600, 'fitted_vehicles_per_hour': 600,
                  'realized_vehicles_per_hour': 300} for seed in (101, 102, 103)]
        config = {'demand': {'mode': 'observed_counts', 'edge_volumes': [{'from_edge': 'a'}], 'calibration_tolerance': .2}}
        report = self.diagnose(self.rows(), config, flows)
        self.assertFalse(report['calibration_valid_in_reference'])
        self.assertFalse(report['conclusions'][0]['consistent_simulated_improvement'])
        for row in flows:
            row['realized_vehicles_per_hour'] = 600
        self.assertTrue(self.diagnose(self.rows(), config, flows)['calibration_valid_in_reference'])

    def test_period_keeps_complete_windows_without_scaling_boundary_counts(self):
        data = b'sensor_id,vehicles,hora_inicio,hora_fim\n5,10,2026-06-26 08:00:00,2026-06-26 08:01:00\n5,20,2026-06-26 08:01:00,2026-06-26 08:02:00\n5,40,2026-06-26 08:02:00,2026-06-26 08:03:00\n'
        start, end = '2026-06-26 08:00:30', '2026-06-26 08:02:30'
        rows = parse_counts(data, 'counts.csv', start, end)
        self.assertEqual(rows[0]['vehicles_per_hour'], 1200)
        _, period = count_period(data, 'counts.csv', start, end)
        self.assertEqual(period['selected_rows'], 1)
        self.assertEqual(period['boundary_windows_excluded'], 2)
        with self.assertRaisesRegex(ValueError, 'juntos'):
            parse_counts(data, 'counts.csv', start)
        with self.assertRaisesRegex(ValueError, 'Nenhuma janela'):
            parse_counts(data, 'counts.csv', '2026-06-27', '2026-06-28')

    def test_pedestrian_loss_and_missing_seed_prevent_favorable_conclusion(self):
        rows = self.rows()
        rows['planned_pedestrians'] = 10
        rows['pedestrians_arrived'] = 10
        rows['pedestrian_wait_person_seconds'] = 100
        rows.loc[rows.controller == 'queue_actuated', 'pedestrian_wait_person_seconds'] = 110
        self.assertFalse(self.diagnose(rows)['conclusions'][0]['service_and_events_ok'])
        rows = self.rows()[lambda r: r.seed != 103]
        self.assertFalse(self.diagnose(rows)['conclusions'][0]['complete_comparison'])

    def test_realized_flow_requires_all_configured_seeds(self):
        rows = self.rows()[lambda r: r.seed != 103]
        flows = [{'controller': 'network_reference', 'seed': seed, 'episode_complete': True, 'edge_id': 'a',
                  'measured_vehicles_per_hour': 600, 'fitted_vehicles_per_hour': 600,
                  'realized_vehicles_per_hour': 600} for seed in (101, 102)]
        config = {'demand': {'mode': 'observed_counts', 'edge_volumes': [{'from_edge': 'a'}], 'calibration_tolerance': .2}}
        self.assertFalse(self.diagnose(rows, config, flows)['calibration_valid_in_reference'])


if __name__ == '__main__':
    unittest.main()
