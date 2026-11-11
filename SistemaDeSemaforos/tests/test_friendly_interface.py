import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from semaforos.arquivos import write_json
from semaforos.caminhos import PROJECT_ROOT
from semaforos.cenario.configuracao import read_config
from semaforos.experimentos.tarefas import job_paths
from semaforos.apresentacao.resultados import comparison_table


class FriendlyInterfaceTest(unittest.TestCase):
    def test_comparison_excludes_partial_runs_and_keeps_missing_values(self):
        runs = pd.DataFrame([
            {'controller': 'network_reference', 'seed': 101, 'episode_complete': True, 'arrived': 10, 'unfinished': 2, 'pending_departure': 1, 'mean_trip_waiting_seconds': 8},
            {'controller': 'PPO', 'seed': 101, 'episode_complete': True, 'arrived': 12, 'unfinished': 0, 'pending_departure': 1, 'mean_trip_waiting_seconds': 6},
            {'controller': 'network_reference', 'seed': 102, 'episode_complete': True, 'arrived': 100},
            {'controller': 'PPO', 'seed': 102, 'episode_complete': False, 'arrived': 0},
        ])
        table, pairs = comparison_table(runs, 'PPO')
        self.assertEqual(pairs, 1)
        self.assertEqual(table.iloc[0]['Diferença'], -2)
        self.assertEqual(table.iloc[2]['Controle avaliado'], 12)
        self.assertTrue(pd.isna(table.iloc[1]['Controle avaliado']))
        self.assertEqual(table.iloc[4]['Controle avaliado'], 1)

    def test_minutes_priority_and_comparison_use_correct_configs(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT / 'resultados', prefix='ui_friendly_') as temporary:
            folder = Path(temporary)
            paths = job_paths(folder)
            paths['output'].mkdir()
            model = paths['output'] / 'ppo_model.zip'
            model.write_bytes(b'mocked-model')
            saved_config = read_config(PROJECT_ROOT / 'config/cenario_rede_corrigida.json')
            write_json(folder / 'cenario.json', saved_config)
            write_json(folder / 'job.json', {'status': 'completed', 'command': 'rl-train', 'exit_code': 0})
            write_json(paths['output'] / 'summary.json', {'model': str(model), 'episodes_completed': 2, 'timesteps': 2048})
            with patch('semaforos.experimentos.tarefas.start_job', return_value=paths) as launch:
                app = AppTest.from_file(str(PROJECT_ROOT / 'interface.py'), default_timeout=90)
                app.session_state['job'] = paths
                app.run()
                self.assertFalse(app.exception, str(app.exception))
                self.assertEqual(next(w for w in app.radio if w.label == 'Por quanto tempo simular?').value, '600 s')
                next(w for w in app.radio if w.label == 'Por quanto tempo simular?').set_value('900 s').run()
                next(w for w in app.selectbox if w.label == 'Objetivo do treinamento').select('Diminuir as filas').run()
                self.assertFalse(app.exception, str(app.exception))
                next(w for w in app.button if w.label == 'Comparar este modelo com os tempos iniciais').click().run()
                config, command = launch.call_args.args[:2]
                self.assertEqual(command, 'rl-eval')
                self.assertEqual(config['duration_seconds'], 600)
                self.assertEqual(config['objectives'], saved_config['objectives'])
                self.assertEqual(launch.call_args.args[3], model)
                launch.reset_mock()
                next(w for w in app.button if w.label == 'Iniciar treinamento').click().run()
                self.assertFalse(app.exception, str(app.exception))
                config, command = launch.call_args.args[:2]
                self.assertEqual(command, 'rl-train')
                self.assertEqual(config['duration_seconds'], 900)
                self.assertEqual(config['objectives'], {'waiting': 1.0, 'queues': 2.0, 'travel': 1.0})
                self.assertFalse(config['metrics']['collect_extended'])
                self.assertFalse(config['metrics']['collect_vehicle_dynamics'])
                self.assertFalse(config['metrics']['collect_lane_details'])
                self.assertFalse(any(w.label == 'Qual algoritmo usar?' for w in app.selectbox))
                limits = next(item.value for item in app.dataframe if 'entries' in item.value.columns)
                self.assertNotIn('stage', limits.columns)
                self.assertTrue(all(limits['entries']))
                self.assertEqual(config['control']['action_mode'], 'adaptive_signals')
                launch.reset_mock()
                next(w for w in app.checkbox if w.label == 'Coletar análise detalhada').set_value(True).run()
                next(w for w in app.button if w.label == 'Iniciar treinamento').click().run()
                self.assertFalse(app.exception, str(app.exception))
                detailed = launch.call_args.args[0]
                self.assertTrue(detailed['metrics']['collect_extended'])
                self.assertTrue(detailed['metrics']['collect_vehicle_dynamics'])
                self.assertTrue(detailed['metrics']['collect_lane_details'])
                self.assertEqual(detailed['control']['phase_duration_bounds'], config['control']['phase_duration_bounds'])
