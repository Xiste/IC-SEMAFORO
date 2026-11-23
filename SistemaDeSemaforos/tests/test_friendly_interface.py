import json
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
from test_interface_configuration_contract import pick_map


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
                self.assertFalse(any(w.label == 'Começar com um exemplo' for w in app.button))
                layers = json.loads(app.get('deck_gl_json_chart')[0].proto.json)['layers']
                roads = next(layer['data'] for layer in layers if layer['id'] == 'configuration-roads')
                entry = next(road['edge_id'] for road in roads if road['controllers'])
                next(w for w in app.selectbox if w.label == 'Buscar rua ou cruzamento no mapa').select(('roads', entry)).run()
                pick_map(app, 'configuration-roads', 'edge_id', entry)
                next(w for w in app.number_input if w.label == 'Veículos por hora').set_value(360.).run()
                next(w for w in app.button if w.label == 'Fechar ajustes').click().run()
                launch.assert_not_called()
                duration = next(w for w in app.number_input if w.label == 'Duração da simulação (segundos)')
                self.assertEqual(duration.value, 600)
                duration.set_value(901).run()
                self.assertFalse(any(w.label == 'Objetivo do treinamento' for w in app.selectbox))
                self.assertFalse(app.exception, str(app.exception))
                next(w for w in app.radio if w.label == 'Etapas do estudo').set_value('3 · Resultados').run()
                self.assertFalse(any(w.label == 'Modelo treinado' for w in app.selectbox))
                next(w for w in app.radio if w.label == 'Área dos resultados').set_value('Comparações').run()
                next(w for w in app.selectbox if w.label == 'Modelo treinado').select(str(model)).run()
                next(w for w in app.button if w.label == 'Comparar modelo com os tempos iniciais').click().run()
                config, command = launch.call_args.args[:2]
                self.assertEqual(command, 'rl-eval')
                self.assertEqual(config['duration_seconds'], 600)
                self.assertEqual(config['objectives'], saved_config['objectives'])
                self.assertEqual(launch.call_args.args[3], model)
                launch.reset_mock()
                next(w for w in app.radio if w.label == 'Etapas do estudo').set_value('2 · Treinamento').run()
                algorithm = next(w for w in app.selectbox if w.label == 'Algoritmo de treinamento')
                self.assertEqual(algorithm.value, 'PPO')
                self.assertEqual(algorithm.options, ['PPO', 'A2C'])
                algorithm.select('A2C').run()
                next(w for w in app.number_input if w.label == 'Passos por coleta').set_value(8).run()
                next(w for w in app.button if w.label == 'Iniciar treinamento').click().run()
                self.assertFalse(app.exception, str(app.exception))
                config, command = launch.call_args.args[:2]
                self.assertEqual(command, 'rl-train')
                self.assertEqual(config['algorithm'], 'A2C')
                self.assertEqual(config['a2c'], {'n_steps': 8, 'total_timesteps': 2048})
                self.assertFalse(any(w.label == 'Tamanho do minibatch' for w in app.number_input))
                self.assertEqual(config['duration_seconds'], 901)
                self.assertEqual(config['objectives'], {'waiting': 1.0, 'queues': 1.0, 'travel': 1.0})
                self.assertFalse(config['metrics']['collect_extended'])
                self.assertFalse(config['metrics']['collect_vehicle_dynamics'])
                self.assertFalse(config['metrics']['collect_lane_details'])
                next(w for w in app.radio if w.label == 'Etapas do estudo').set_value('1 · Cenário e tráfego').run()
                search = next(w for w in app.selectbox if w.label == 'Buscar rua ou cruzamento no mapa')
                search.select(('signals', config['targets'][0]['tls_id'])).run()
                pick_map(app, 'configuration-signals', 'tls_id', config['targets'][0]['tls_id'])
                self.assertTrue(any(w.label == 'Verde mínimo (s)' for w in app.number_input))
                self.assertFalse(any(w.label == 'Movimento no ciclo' for w in app.selectbox))
                self.assertFalse(any(w.label == 'Ver um ciclo completo no SUMO' for w in app.button))
                self.assertEqual(config['control']['action_mode'], 'adaptive_signals')
                launch.reset_mock()
                next(w for w in app.button if w.label == 'Fechar ajustes').click().run()
                next(w for w in app.radio if w.label == 'Etapas do estudo').set_value('2 · Treinamento').run()
                next(w for w in app.checkbox if w.label == 'Coletar análise detalhada').set_value(True).run()
                next(w for w in app.button if w.label == 'Iniciar treinamento').click().run()
                self.assertFalse(app.exception, str(app.exception))
                detailed = launch.call_args.args[0]
                self.assertTrue(detailed['metrics']['collect_extended'])
                self.assertTrue(detailed['metrics']['collect_vehicle_dynamics'])
                self.assertTrue(detailed['metrics']['collect_lane_details'])
                self.assertEqual(detailed['control']['phase_duration_bounds'], config['control']['phase_duration_bounds'])
