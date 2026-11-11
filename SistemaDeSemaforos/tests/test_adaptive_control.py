import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import traci

from semaforos.caminhos import PROJECT_ROOT
from semaforos.cenario.configuracao import read_config
from semaforos.cenario.experimental import prepare_experimental
from semaforos.simulacao.adaptativo import AdaptiveSignals, sensor_values
from semaforos.simulacao.ambiente import SemaforosEnv
from semaforos.experimentos.rl import train_rl, evaluate_rl


class AdaptiveControlTest(unittest.TestCase):
    def config(self):
        config = read_config(PROJECT_ROOT / 'config/cenario.json')
        config['ppo'].update(action_mode='adaptive_signals', decision_seconds=1)
        config['duration_seconds'] = 90
        return config

    def test_requested_green_skips_cycle_but_keeps_clearance_and_minimum(self):
        phases = [{'state': state, 'duration': seconds}
                  for state, seconds in [('Grr', 10), ('yrr', 3), ('rrr', 2),
                                         ('rGr', 10), ('ryr', 3), ('rrr', 2),
                                         ('rrG', 10), ('rry', 3), ('rrr', 2)]]
        spec = dict(tls_id='t', green_indices=[0, 3, 6], green_bounds={str(i): [5, 20] for i in (0, 3, 6)})
        state = {'index': 0, 'start': 0, 'now': 0}
        changes = []
        with patch('semaforos.simulacao.adaptativo.traci') as api:
            api.trafficlight.getPhase.side_effect = lambda tls: state['index']
            api.trafficlight.getSpentDuration.side_effect = lambda tls: state['now'] - state['start']
            def change(tls, index):
                changes.append((state['now'], index))
                state.update(index=index, start=state['now'])
            api.trafficlight.setPhase.side_effect = change
            controller = AdaptiveSignals([spec], {'t': phases}, 1)
            controller.request([2])
            for now in range(11):
                state['now'] = now
                controller.tick(now)
        self.assertEqual(changes, [(5, 1), (8, 2), (10, 6)])

    def test_sensor_observation_responds_to_presence_and_downstream_congestion(self):
        layout = [dict(lane_id='in', outgoing=['out'])]
        with patch('semaforos.simulacao.adaptativo.traci') as api:
            api.lane.getLength.return_value = 75
            api.lane.getMaxSpeed.return_value = 10
            api.lane.getLastStepMeanSpeed.return_value = 5
            api.lane.getLastStepVehicleNumber.return_value = 0
            api.lane.getLastStepHaltingNumber.return_value = 0
            api.lane.getLastStepOccupancy.return_value = 0
            empty = sensor_values(layout)
            api.lane.getLastStepVehicleNumber.return_value = 5
            api.lane.getLastStepHaltingNumber.return_value = 4
            api.lane.getLastStepOccupancy.side_effect = lambda lane: 90 if lane == 'out' else 50
            busy = sensor_values(layout)
        self.assertEqual(empty[0], 0)
        self.assertEqual(busy, [1., .5, .4, .5, .5, .9])

    def test_real_sumo_limits_and_reference_are_distinct(self):
        config = self.config()
        with tempfile.TemporaryDirectory() as folder:
            env = SemaforosEnv(config, Path(folder) / 'adaptive')
            try:
                observation, _ = env.reset(seed=11)
                self.assertTrue(env.observation_space.contains(observation))
                self.assertGreater(len(observation), 6)
                while True:
                    observation, _, done, _, _ = env.step([1])
                    self.assertTrue(env.observation_space.contains(observation))
                    if done:
                        break
                events = list(env.action_log)
            finally:
                env.close()
            self.assertEqual([e['phase_index'] for e in events[:3]], [1, 2, 3])
            self.assertEqual(events[0]['time_seconds'], 24)
            self.assertEqual(events[1]['time_seconds'] - events[0]['time_seconds'], 3)
            self.assertEqual(events[2]['time_seconds'] - events[1]['time_seconds'], 1)
            self.assertEqual(events[3]['previous_elapsed_seconds'], 58)
            env = SemaforosEnv(config, Path(folder) / 'reference')
            env.reference_mode = True
            try:
                env.reset(seed=11)
                for _ in range(42):
                    env.step([0])
                self.assertEqual(traci.trafficlight.getPhase('FAM_RONDON_PARANA'), 1)
                self.assertIsNone(env.adaptive)
            finally:
                env.close()

    def test_nine_intersections_train_save_load_and_reject_legacy_model_mode(self):
        with tempfile.TemporaryDirectory(prefix='test_adaptive_') as folder:
            folder = Path(folder)
            config, _ = prepare_experimental(read_config(PROJECT_ROOT / 'config/cenario_rede_corrigida.json'), folder / 'scenario')
            for section in ('control', 'ppo'):
                config[section]['action_mode'] = 'adaptive_signals'
            config['duration_seconds'] = 30
            config['ppo'].update(total_timesteps=4, n_steps=4, batch_size=4, n_epochs=1)
            train_rl(config, folder / 'train')
            manifest = json.loads((folder / 'train/manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(len(manifest['action_spec']), 17)
            self.assertTrue(manifest['sensor_layout'])
            evaluate_rl(config, folder / 'eval', folder / 'train/ppo_model.zip', seeds=[101])
            self.assertTrue((folder / 'eval/signals.csv').is_file())
            legacy = copy.deepcopy(config)
            legacy['control']['action_mode'] = 'phase_durations'
            with self.assertRaisesRegex(ValueError, 'modo de ação'):
                evaluate_rl(legacy, folder / 'reject', folder / 'train/ppo_model.zip', seeds=[101])


if __name__ == '__main__':
    unittest.main()
