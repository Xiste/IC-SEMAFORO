import copy
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from semaforos.arquivos import write_json, read_json
from semaforos.caminhos import PROJECT_ROOT
from semaforos.cenario.configuracao import read_config
from semaforos.cenario.calibracao import calibration_report
from semaforos.cenario.experimental import prepare_experimental, preview_experimental
from semaforos.cenario.grupos import audit_program, conflict_graph
from semaforos.cenario.rede import network_programs, phase_action_spec
from semaforos.cenario.calibracao import create_calibrated_demand
from semaforos.experimentos.referencia import run_reference


class PendingFixesTest(unittest.TestCase):
    def test_internal_counts_do_not_duplicate_vehicles(self):
        config = read_config(PROJECT_ROOT / 'config/cenario.json')
        config['demand'] = {'mode': 'observed_counts', 'edge_volumes': [
            {'from_edge': '1156717168', 'vehicles_per_hour': 600},
            {'from_edge': '154252437#1', 'vehicles_per_hour': 600}]}
        report = calibration_report(config)
        self.assertAlmostEqual(report['total_generated_vehicles_per_hour'], 600)
        self.assertTrue(all(abs(r['relative_error']) < 1e-6 for r in report['measurements']))
        config['duration_seconds'] = 60
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT / 'resultados') as temporary:
            output = Path(temporary) / 'reference'
            run_reference(config, output)
            self.assertTrue((output / 'flow_counts.csv').exists())
            self.assertTrue((output / 'summary.json').exists())
            self.assertTrue((output / 'comparison.png').exists())
            self.assertIn('intersection', (output / 'signals.csv').read_text(encoding='utf-8').splitlines()[0])
            detectors = list(output.glob('episodes/**/measurement_detectors.add.xml'))
            self.assertEqual(len(detectors), len(config['seeds']))

    def test_grouped_preview_profile_and_conflict_rejection(self):
        config = read_config(PROJECT_ROOT / 'config/cenario.json')
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT / 'resultados') as temporary:
            folder = Path(temporary)
            config, rows = prepare_experimental(config, folder / 'scenario')
            self.assertEqual(sum(r['controlado'] for r in rows), 17)
            self.assertTrue(all(r['conflitos_simultaneos'] == 0 for r in rows))
            limited = copy.deepcopy(config)
            limited['control']['maximum_cycle_seconds'] = 10
            with self.assertRaisesRegex(ValueError, 'máximo de ciclo'):
                phase_action_spec(limited, network_programs(config['network']))
            config['demand'] = {'mode': 'edge_volumes', 'edge_volumes': [
                {'from_edge': '1156717168', 'vehicles_per_hour': 600}],
                'time_profile': [{'begin': 0, 'end': config['duration_seconds'], 'multiplier': 1}]}
            original = copy.deepcopy(config)
            preview_experimental(config, folder / 'preview')
            self.assertEqual(config, original)
            config['demand']['time_profile'] = [{'begin': 0, 'end': 60, 'multiplier': 0},
                                               {'begin': 60, 'end': config['duration_seconds'], 'multiplier': 1}]
            info = preview_experimental(config, folder / 'preview_no_early_traffic')
            self.assertEqual(info['departed'], 0)
            root = ET.parse(config['network']).getroot()
            tls = config['targets'][0]['tls_id']
            graph = conflict_graph(root, tls)
            a, b = next((a, b) for a, foes in graph.items() for b in foes)
            phase = next(l for l in root.findall('tlLogic') if l.get('id') == tls).find('phase')
            phase.set('state', ''.join('G' if i in (a, b) else 'r' for i in range(len(graph))))
            with self.assertRaisesRegex(ValueError, 'conflitantes'):
                audit_program(root, tls)

    def test_inconsistent_counts_are_rejected(self):
        config = read_config(PROJECT_ROOT / 'config/cenario.json')
        config['demand'] = {'mode': 'observed_counts', 'calibration_tolerance': 0,
                           'edge_volumes': [{'from_edge': '152937010#0', 'vehicles_per_hour': 600},
                                           {'from_edge': '152937010#1', 'vehicles_per_hour': 0}]}
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, 'tolerância'):
                create_calibrated_demand(config, Path(temporary), 42)

    def test_progress_is_atomic(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'progress.json'
            write_json(path, {'step': 0})
            def writer():
                for step in range(80):
                    write_json(path, {'step': step, 'data': 'x' * 10000})
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(writer)
                for _ in range(250):
                    value = read_json(path)
                    if value is not None:
                        self.assertIn('step', value)
                future.result()
            self.assertEqual(read_json(path)['step'], 79)
            self.assertFalse(list(Path(temporary).glob('*.tmp')))
