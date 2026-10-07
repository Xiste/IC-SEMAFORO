"""Integração das pendências de infraestrutura fora do algoritmo."""
import copy
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from semaforos.arquivos import read_json
from semaforos.caminhos import PROJECT_ROOT
from semaforos.cenario.configuracao import read_config
from semaforos.cenario.experimental import prepare_experimental
from semaforos.cenario.pedestres import crossing_routes
from semaforos.cenario.importacao import parse_counts, parse_od
from semaforos.simulacao.observacao import IntersectionMetrics
from semaforos.simulacao.ambiente import SemaforosEnv
from semaforos.simulacao.contagens import FlowCounts
from semaforos.experimentos.referencia import run_reference
from semaforos.experimentos.tarefas import start_job, saved_jobs, job_state, job_paths, LOCAL_PROCESSES
from semaforos.experimentos.rl import train_rl


class FunctionalRemainingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(dir=PROJECT_ROOT / 'resultados', prefix='test_funcional_')
        cls.folder = Path(cls.temporary.name)
        cls.config, _ = prepare_experimental(read_config(PROJECT_ROOT / 'config/cenario.json'), cls.folder / 'scenario')

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_shared_lanes_count_once_per_intersection(self):
        targets = [{'name': 'Cruzamento', 'tls_id': 'a'}, {'name': 'Cruzamento', 'tls_id': 'b'}]
        metrics = IntersectionMetrics(targets, {'a': ['l1'], 'b': ['l1', 'l2']}, 2)
        with patch('traci.lane.getLastStepHaltingNumber', side_effect=lambda lane: 2 if lane == 'l1' else 3), \
             patch('traci.lane.getLastStepVehicleIDs', return_value=['car']), \
             patch('traci.vehicle.getWaitingTime', return_value=10):
            metrics.sample(details=False)
        row = metrics.rows()[0]
        self.assertEqual(row['controller_count'], 2)
        self.assertEqual(row['unique_lane_count'], 2)
        self.assertEqual(row['queue_vehicle_seconds'], 10)
        self.assertEqual(row['peak_halted_vehicles'], 5)
        self.assertEqual(row['wait_vehicle_seconds'], 2)

    def test_imports_units_windows_and_excel(self):
        source = b'sensor_id,vehicles,window_seconds\n001,10,60\n001,30,120\n'
        result = parse_counts(source, 'counts.csv')
        self.assertEqual(result[0]['source_id'], '001')
        self.assertEqual(result[0]['vehicles_per_hour'], 800)
        self.assertEqual(result[0]['edge_id'], '')
        with self.assertRaisesRegex(ValueError, 'duração'):
            parse_counts(b'edge_id,vehicles\nx,20\n', 'no_units.csv')
        with self.assertRaisesRegex(ValueError, 'sobrepostas'):
            parse_counts(b'sensor_id,vehicles,hora_inicio,hora_fim\na,10,2026-01-01T10:00:00,2026-01-01T10:02:00\na,10,2026-01-01T10:01:00,2026-01-01T10:03:00\n', 'overlap.csv')
        buffer = io.BytesIO()
        pd.DataFrame([{'from_edge': '1156717168', 'to_edge': '154252437#1', 'vehicles_per_hour': 600}]).to_excel(buffer, index=False)
        od = parse_od(buffer.getvalue(), 'od.xlsx')
        self.assertEqual(od[0]['vehicles_per_hour'], 600)

    def test_pedestrians_intersections_live_and_partial(self):
        config = copy.deepcopy(self.config)
        config['duration_seconds'] = 120
        routes = crossing_routes(config['network'], config['targets'])
        self.assertGreater(len(routes), 0)
        config['pedestrians'] = {'enabled': True, 'flows': [{**routes[0], 'persons_per_hour': 120}]}
        output = self.folder / 'pedestrian_reference'
        run_reference(config, output)
        runs = pd.read_csv(output / 'runs.csv')
        self.assertGreater(runs['pedestrians_departed'].iloc[0], 0)
        self.assertGreater(runs['pedestrians_arrived'].iloc[0], 0)
        self.assertGreater(runs['crossing_passages'].iloc[0], 0)
        intersections = pd.read_csv(output / 'intersections.csv')
        self.assertEqual(intersections['intersection'].nunique(), 9)
        live = read_json(output / 'live.json')
        self.assertEqual(live['simulated_seconds'], 120)
        self.assertTrue(Path(live['episode_output'], 'live_history.csv').is_file())
        crossings = pd.read_csv(output / 'pedestrian_crossings.csv')
        self.assertGreater(crossings['crossing_passages'].sum(), 0)
        self.assertIn('pedestrian_wait_person_seconds', crossings)
        env = SemaforosEnv(config, self.folder / 'partial')
        try:
            env.reset(seed=42)
            env.step([1] * len(env.action_spec))
        finally:
            env.close()
        info = read_json(env.current_output / 'episode_metrics.json')
        self.assertFalse(info['episode_complete'])
        self.assertEqual(info['simulated_seconds'], 5)
        self.assertIn('tripinfo_unfinished', info)
        self.assertEqual(len(info['intersections']), 9)

    def test_job_reconnection_and_cancelled_reports(self):
        config = read_config(PROJECT_ROOT / 'config/cenario.json')
        config['duration_seconds'] = 60
        jobs_folder = self.folder / 'jobs'
        job = start_job(config, 'run-reference', jobs_folder)
        # Um novo objeto representa a página reaberta, sem reutilizar Popen/session_state.
        restored = job_paths(saved_jobs(jobs_folder)[0]['folder'])
        self.assertEqual(job['folder'], restored['folder'])
        (restored['folder'] / 'cancel.flag').touch()
        deadline = time.monotonic() + 70
        while job_state(restored)['status'] in ('starting', 'running') and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertEqual(job_state(restored)['status'], 'cancelled', restored['log'].read_text(encoding='utf-8', errors='replace'))
        runs = pd.read_csv(restored['output'] / 'runs.csv')
        self.assertFalse(runs['episode_complete'].iloc[0])
        self.assertEqual(read_json(restored['output'] / 'summary.json')['partial_runs'], 1)
        self.assertFalse((restored['output'] / 'comparison.png').exists())
        process = LOCAL_PROCESSES.pop(str(job['folder']), None)
        if process:
            process.wait(timeout=20)

    def test_training_budget_records_partial_episode(self):
        config = copy.deepcopy(self.config)
        config['duration_seconds'] = 120
        config['ppo'].update(total_timesteps=4, n_steps=4, batch_size=4, n_epochs=1)
        output = self.folder / 'partial_training'
        summary = train_rl(config, output)
        self.assertEqual(summary['episodes_completed'], 0)
        self.assertTrue(summary['partial_episode_saved'])
        episodes = pd.read_csv(output / 'training_episodes.csv')
        self.assertFalse(episodes['episode_complete'].iloc[0])
        self.assertEqual(episodes['simulated_seconds'].iloc[0], 20)
        self.assertTrue((output / 'partial_episode.json').exists())
        self.assertEqual(pd.read_csv(output / 'intersections.csv')['intersection'].nunique(), 9)

    def test_partial_flow_rate_uses_observed_time(self):
        # Regressão: ao interromper após 5 s, a conversão não pode usar os 600 s planejados.
        with tempfile.TemporaryDirectory() as folder:
            counts = FlowCounts({'duration_seconds': 600, 'demand': {'mode': 'random'}}, None, Path(folder))
            counts.target = {'measured_edge': 600}
            counts.fitted = {'measured_edge': 600}
            counts.passed = {'measured_edge': {'vehicle_1'}}
            row = counts.rows(observed_seconds=5)[0]
            self.assertEqual(row['observed_seconds'], 5)
            self.assertEqual(row['realized_vehicles_per_hour'], 720)
