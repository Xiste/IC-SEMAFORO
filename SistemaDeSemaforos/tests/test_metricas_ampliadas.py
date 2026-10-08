"""Verificações sem executar SUMO ou modelos: dados artificiais e TraCI substituído."""
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd

from semaforos.simulacao.janela import measurement_window
from semaforos.simulacao.detalhes import DetailedMetrics, metric_settings
from semaforos.cenario.volumes import distribute_volumes
from semaforos.experimentos.repeticoes import study_plan, aggregate_repetitions, run_study
from semaforos.relatorios.metricas import trip_summary
from semaforos.relatorios.gargalos import bottleneck_rows
from semaforos.relatorios.episodios import export_extended_details
from semaforos.arquivos import write_json


class ExtendedMetricsTest(unittest.TestCase):
    def test_environment_reset_warms_up_and_measures_only_selected_steps(self):
        from semaforos.simulacao.ambiente import SemaforosEnv
        from contextlib import ExitStack
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            network = Path(folder) / 'network.xml'
            network.write_text('<net/>')
            routes = Path(folder) / 'routes.xml'
            routes.write_text('<routes><vehicle id="v" depart="0"/></routes>')
            config = {'network': network, 'duration_seconds': 6, 'step_seconds': 1,
                      'targets': [{'tls_id': 't', 'name': 'A', 'phase_indices': [0]}],
                      'control': {'decision_seconds': 1}, 'demand': {'mode': 'random'},
                      'measurement': {'warmup_seconds': 2, 'start_seconds': 3, 'end_seconds': 5},
                      'metrics': {'collect_extended': False, 'collect_events': False, 'collect_resources': False},
                      'objectives': {'waiting': 1, 'queues': 1, 'travel': 1},
                      'training': {'unfinished_penalty_seconds': 0, 'minimum_green_seconds': 5}}
            api = stack.enter_context(patch('semaforos.simulacao.ambiente.traci'))
            stack.enter_context(patch('semaforos.simulacao.ambiente.load_scenario', return_value=(None, MagicMock(), {'t': [{'state': 'G', 'duration': 10}]})))
            stack.enter_context(patch('semaforos.simulacao.ambiente.phase_action_spec', return_value=('green_extension', [{'tls_id': 't'}])))
            stack.enter_context(patch('semaforos.simulacao.ambiente.create_demand', return_value=routes))
            stack.enter_context(patch('semaforos.simulacao.ambiente.create_pedestrian_demand', return_value=(None, 0)))
            stack.enter_context(patch('semaforos.simulacao.ambiente.sumo_executable', return_value=Path('fake-sumo')))
            flow = stack.enter_context(patch('semaforos.simulacao.ambiente.FlowCounts')).return_value
            flow.file = None
            flow.rows.return_value = []
            intersection = stack.enter_context(patch('semaforos.simulacao.ambiente.IntersectionMetrics')).return_value
            intersection.rows.return_value = []
            people = stack.enter_context(patch('semaforos.simulacao.ambiente.PedestrianMetrics')).return_value
            people.summary.return_value = {}
            people.rows.return_value = []
            stack.enter_context(patch('semaforos.simulacao.ambiente.LiveMetrics'))
            clock = [0]
            api.simulation.getTime.side_effect = lambda: clock[0]
            api.simulationStep.side_effect = lambda: clock.__setitem__(0, clock[0] + 1)
            api.simulation.getDepartedNumber.return_value = 1
            api.simulation.getArrivedNumber.return_value = 0
            api.simulation.getPendingVehicles.return_value = ['delayed']
            api.vehicle.getIDList.return_value = ['v']
            api.vehicle.getSpeed.return_value = 0
            api.vehicle.getWaitingTime.side_effect = lambda _: clock[0]
            api.trafficlight.getControlledLanes.return_value = ['a_0']
            api.trafficlight.getPhase.return_value = 0
            api.trafficlight.getNextSwitch.return_value = 10
            api.lane.getLastStepHaltingNumber.return_value = 1
            api.lane.getLastStepVehicleNumber.return_value = 1
            api.lane.getLastStepMeanSpeed.return_value = 0
            api.lane.getLastStepOccupancy.return_value = 10
            env = SemaforosEnv(config, Path(folder) / 'episodes')
            env.reset(seed=11)
            self.assertEqual(clock[0], 2)
            self.assertEqual(env.wait_seconds, 0)
            self.assertEqual(env.action_log, [])
            for _ in range(4):
                _, _, done, _, info = env.step([1])
            self.assertTrue(done)
            self.assertEqual(info['measured_seconds'], 2)
            self.assertEqual(info['wait_vehicle_seconds'], 2)
            self.assertEqual(info['departed'], 2)
            self.assertEqual(info['total_departed'], 6)
            self.assertEqual(info['vehicles_at_window_start'], 1)
            self.assertEqual(info['pending_departure'], 1)
            self.assertEqual(flow.step.call_count, 2)
            api.close.side_effect = lambda: (env.current_output / 'tripinfo.xml').write_text('<tripinfos/>')
            env.close()
            self.assertTrue((env.current_output / 'episode_metrics.json').is_file())
            api.start.assert_called_once()  # substituído: nenhum processo SUMO é iniciado

    def test_window_excludes_warmup_and_stops_at_end(self):
        config = {'duration_seconds': 60, 'step_seconds': 1,
                  'measurement': {'warmup_seconds': 10, 'start_seconds': 20, 'end_seconds': 40}}
        window = measurement_window(config)
        self.assertFalse(window.contains_step(19, 20))
        self.assertTrue(window.contains_step(20, 21))
        self.assertTrue(window.contains_step(39, 40))
        self.assertFalse(window.contains_step(40, 41))
        self.assertEqual(window.elapsed(60), 20)
        self.assertFalse(window.metadata(39)['measurement_complete'])
        for settings in ({'warmup_seconds': 60}, {'start_seconds': 2.5}, {'end_seconds': 61}, {'warmup_seconds': -1}):
            with self.assertRaises(ValueError):
                measurement_window({**config, 'measurement': settings})

    def test_total_distribution_keeps_direction_and_zero(self):
        totals = [{'intersection': 'A', 'vehicles_per_hour': 1000}]
        shares = [{'intersection': 'A', 'edge_id': 'east', 'percent': 75},
                  {'intersection': 'A', 'edge_id': 'west', 'percent': 25}]
        result = distribute_volumes(totals, shares, {'A': ['east', 'west']})
        self.assertEqual([r['vehicles_per_hour'] for r in result], [750, 250])
        self.assertEqual([r['from_edge'] for r in result], ['east', 'west'])
        with self.assertRaises(ValueError):
            distribute_volumes(totals, shares[:1], {'A': ['east', 'west']})
        result = distribute_volumes(totals, [{**shares[0], 'percent': 100}, {**shares[1], 'percent': 0}], {'A': ['east', 'west']})
        self.assertTrue(result[1]['zero_measured'])

    def test_collector_detects_queue_and_blocked_green_without_simulation(self):
        root = ET.fromstring('''<net><edge id="a"><lane id="a_0" length="100"/></edge>
          <edge id="b"><lane id="b_0" length="100"/></edge>
          <edge id=":t" function="internal"><lane id=":t_0" length="10"/></edge>
          <connection from="a" to="b" fromLane="0" toLane="0" tl="t" linkIndex="0" via=":t_0" dir="s"/></net>''')
        config = {'duration_seconds': 60, 'targets': [{'tls_id': 't', 'name': 'A'}]}
        with tempfile.TemporaryDirectory() as folder, patch('semaforos.simulacao.detalhes.traci') as api:
            metrics = DetailedMetrics(config, folder, root)
            api.lane.getLastStepVehicleIDs.return_value = ['v']
            api.lane.getLastStepOccupancy.return_value = 90
            api.lane.getLastStepHaltingNumber.return_value = 1
            api.lanearea.getJamLengthMeters.return_value = 95
            api.lanearea.getJamLengthVehicle.return_value = 1
            api.vehicle.getNextTLS.return_value = [('t', 0, 5, 'G')]
            api.trafficlight.getRedYellowGreenState.return_value = 'G'
            api.inductionloop.getVehicleData.return_value = [('warmup', 5, 9, 10, 'car'), ('v', 5, 11, 12, 'car')]
            api.vehicle.getAcceleration.return_value = -5
            api.vehicle.getAllowedSpeed.return_value = 10
            api.vehicle.getLeader.return_value = None
            api.vehicle.getVehicleClass.return_value = 'passenger'
            metrics.prime({'v': 5})
            metrics.sample(1, {'v': 0}, {'v': 1}, 10)
            lanes, movements = metrics.rows()
            self.assertEqual(lanes[0]['spillback_seconds'], 1)
            self.assertEqual(lanes[0]['mean_density_vehicles_per_kilometer'], 10)
            self.assertEqual(movements[0]['green_with_blocked_downstream_seconds'], 1)
            self.assertEqual(movements[0]['passed_vehicles'], 1)
            self.assertEqual(metrics.global_summary()['stop_events'], 1)
            self.assertEqual(metrics.global_summary()['hard_braking_vehicle_seconds'], 1)
            self.assertEqual(metrics.class_rows()[0]['observed_unique_vehicles'], 1)
            self.assertEqual(len(ET.parse(metrics.file).getroot()), 2)
            api.trafficlight.getRedYellowGreenState.return_value = 'r'
            metrics.sample(1, {'v': 0}, {'v': 2}, 10)
            metrics.sample(1, {'v': 0}, {'v': 3}, 10)
            self.assertEqual(metrics.rows()[1][0]['maximum_continuous_red_seconds'], 2)

    def test_thresholds_reject_invalid_and_collection_can_be_disabled(self):
        with self.assertRaises(ValueError):
            metric_settings({'metrics': {'thresholds': {'downstream_occupancy_percent': 101}}})
        with tempfile.TemporaryDirectory() as folder:
            collector = DetailedMetrics({'metrics': {'collect_extended': False}}, folder, ET.Element('net'))
            collector.sample(1, {}, {}, 0)
            self.assertIsNone(collector.file)
            self.assertEqual(collector.rows(), ([], []))
            self.assertEqual(collector.global_summary(), {})

    def test_arrival_cohort_in_window_keeps_full_trip_duration(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'trip.xml'
            path.write_text('<tripinfos><tripinfo depart="0" arrival="5" duration="5"/>'
                            '<tripinfo depart="5" arrival="15" duration="10"/>'
                            '<tripinfo depart="15" arrival="25" duration="10"/>'
                            '<tripinfo depart="21" arrival="-1"/></tripinfos>')
            result = trip_summary(path, 10, 20)
            self.assertEqual(result['tripinfo_completed'], 1)
            self.assertEqual(result['tripinfo_unfinished'], 1)
            self.assertEqual(result['p99_travel_time_seconds'], 10)

    def test_extended_export_preserves_controller_and_seed(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            episode = output / 'episodes' / 'one'
            episode.mkdir(parents=True)
            write_json(episode / 'episode_metrics.json', {'episode_number': 1, 'seed': 101, 'episode_complete': True,
                       'lanes': [{'lane_id': 'a_0', 'intersection': 'A'}], 'vehicle_classes': [{'vehicle_class': 'bus'}]})
            pd.DataFrame([{'episode_number': 1, 'controller': 'PPO', 'seed': 101, 'episode_complete': True}]).to_csv(output / 'intersections.csv', index=False)
            export_extended_details(output)
            self.assertEqual(pd.read_csv(output / 'lanes.csv').controller.iloc[0], 'PPO')
            self.assertEqual(pd.read_csv(output / 'vehicle_classes.csv').seed.iloc[0], 101)

    def test_bottleneck_pairing_and_warning_priority(self):
        rows = pd.DataFrame([{'intersection': 'A', 'controller': c, 'seed': 1, 'episode_complete': True,
                             'queue_vehicle_seconds': q, 'wait_vehicle_seconds': q, 'peak_halted_vehicles': 2}
                            for c, q in [('network_reference', 100), ('PPO', 50)]])
        with patch('semaforos.relatorios.gargalos.intersection_locations', return_value={}):
            result = bottleneck_rows({}, rows)
            self.assertEqual(result[0]['queue_improvement_percent'], 50)
            self.assertEqual(result[0]['status'], 'Melhorou')
            blocked = pd.DataFrame([{'intersection': 'A', 'controller': 'PPO', 'episode_complete': True,
                                    'green_with_blocked_downstream_seconds': 5}])
            self.assertEqual(bottleneck_rows({}, rows, movements=blocked)[0]['status'], 'Bloqueio a jusante observado')

    def test_repetitions_are_independent_and_use_reserved_evaluation_seeds(self):
        config = {'seeds': [11], 'study': {'training_seeds': [11, 22]}, 'evaluation': {'seeds': [101, 102]}}
        self.assertEqual(study_plan(config)['evaluation_episodes'], 12)
        with self.assertRaises(ValueError):
            study_plan({**config, 'evaluation': {'seeds': [11]}})
        result = {'cancelled': False, 'comparison_complete': True, 'diagnostico': {'conclusions': [],
                  'comparisons': [{'controller': 'PPO', 'metric': 'wait', 'label': 'Espera', 'benefit_mean': 5}]}}
        with tempfile.TemporaryDirectory() as folder, patch('semaforos.experimentos.rl.train_rl', return_value={'model': 'fake-model'}) as train, patch('semaforos.experimentos.rl.evaluate_rl', return_value=result) as evaluate:
            summary = run_study(config, Path(folder) / 'study')
            self.assertEqual([call.args[0]['seeds'] for call in train.call_args_list], [[11], [22]])
            self.assertEqual(evaluate.call_count, 2)
            self.assertEqual(evaluate.call_args.kwargs['seeds'], [101, 102])
            self.assertEqual(summary['aggregate'][0]['independent_training_repetitions'], 2)
            self.assertTrue(summary['comparison_complete'])
            self.assertEqual(summary['aggregate'][0]['benefit_ci95_low'], 5)

    def test_cancellation_during_warmup_still_writes_study_summary(self):
        config = {'seeds': [11], 'evaluation': {'seeds': [101]}}
        with tempfile.TemporaryDirectory() as folder, patch('semaforos.experimentos.rl.train_rl', side_effect=InterruptedError('cancelled')), patch('semaforos.experimentos.repeticoes.cancellation_requested', side_effect=[False, True]):
            output = Path(folder) / 'study'
            summary = run_study(config, output)
            self.assertTrue(summary['cancelled'])
            self.assertFalse(summary['comparison_complete'])
            self.assertEqual(summary['completed_count'], 0)
            self.assertTrue((output / 'summary.json').is_file())

    def test_diagnostic_rejects_different_measurement_windows(self):
        from semaforos.relatorios.diagnostico import export_diagnostics
        rows = pd.DataFrame([{'controller': c, 'seed': 101, 'episode_complete': True,
                 'simulated_seconds': 60, 'demand_sha256': 'same', 'measurement_start_seconds': start,
                 'measurement_end_seconds': 60, 'measured_seconds': 60-start, 'measurement_complete': True,
                 'wait_vehicle_seconds': wait, 'global_halted_vehicle_seconds': wait,
                 'arrived': 10, 'unfinished': 0, 'pending_departure': 0}
                 for c, start, wait in [('network_reference', 0, 100), ('PPO', 30, 1)]])
        with tempfile.TemporaryDirectory() as folder:
            report = export_diagnostics(folder, rows, {'evaluation_config': {'demand': {'mode': 'random'}}})
            self.assertFalse(report['conclusions'][0]['same_demand_and_horizon'])


if __name__ == '__main__':
    unittest.main()
