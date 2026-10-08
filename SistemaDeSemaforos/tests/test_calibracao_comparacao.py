import tempfile
import unittest
from pathlib import Path

from semaforos.cenario.configuracao import read_config
from semaforos.experimentos.rl import evaluate_rl
from semaforos.caminhos import PROJECT_ROOT


class CalibratedComparisonTest(unittest.TestCase):
    def test_relative_output_actual_flows_and_identical_routes(self):
        config = read_config(PROJECT_ROOT / 'config/cenario.json')
        config['duration_seconds'] = 20
        config['evaluation'] = {'seeds': [101]}
        config['demand'] = {'mode': 'observed_counts', 'calibration_tolerance': .2,
                            'edge_volumes': [{'from_edge': '1156717168', 'vehicles_per_hour': 600}]}
        # A saída relativa exercita a resolução dos nomes nos detectores additional.
        with tempfile.TemporaryDirectory(dir='resultados', prefix='test_comparacao_') as folder:
            output = Path(folder) / 'comparacao'
            result = evaluate_rl(config, output)
            self.assertEqual({row['controller'] for row in result['runs']}, {'network_reference', 'queue_actuated'})
            self.assertEqual(len({row['demand_sha256'] for row in result['runs']}), 1)
            self.assertTrue(all(Path(row['episode_output']).is_absolute() for row in result['runs']))
            conclusion = result['diagnostico']['conclusions'][0]
            self.assertTrue(conclusion['same_demand_and_horizon'])
            self.assertTrue(conclusion['complete_comparison'])
            self.assertFalse(conclusion['consistent_simulated_improvement'])
            self.assertEqual(len(result['diagnostico']['calibration']), 2)
            self.assertTrue((output / 'validacao_demanda.csv').is_file())
            self.assertTrue((output / 'melhorias.csv').is_file())
            self.assertTrue((output / 'diagnostico.json').is_file())


if __name__ == '__main__':
    unittest.main()
