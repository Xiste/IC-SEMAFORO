"""A heurística usa as filas dos movimentos verdes, com ações válidas."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from semaforos.algoritmos.heuristicas import queue_actuated_action


class QueueBaselineTest(unittest.TestCase):
    def test_duration_mode_prepares_next_green_during_clearance(self):
        env = SimpleNamespace(action_mode="phase_durations",
            targets=[{"tls_id": "T", "phase_indices": [0, 3]}],
            programs={"T": [{"state": "Gr"}, {"state": "yr"}, {"state": "rr"}, {"state": "rG"}]},
            action_spec=[{"tls_id": "T", "phase_index": i, "kind": kind}
                         for i, kind in enumerate(["green", "yellow", "all_red", "green"])])
        links = [(('lane_a', 'out_a', ''),), (('lane_b', 'out_b', ''),)]
        with patch("semaforos.algoritmos.heuristicas.traci.trafficlight.getPhase", return_value=2), \
             patch("semaforos.algoritmos.heuristicas.traci.trafficlight.getControlledLinks", return_value=links), \
             patch("semaforos.algoritmos.heuristicas.traci.lane.getLastStepHaltingNumber",
                   side_effect=lambda lane: {"lane_a": 2, "lane_b": 5}[lane]):
            self.assertEqual(queue_actuated_action(env).tolist(), [0, 1, 1, 2])

    def test_prefers_larger_incoming_queue(self):
        env = SimpleNamespace(
            targets=[{"tls_id": "T", "phase_indices": [0, 3]}],
            programs={"T": [{"state": "Gr"}, {"state": "yr"},
                            {"state": "rr"}, {"state": "rG"}]})
        links = [(('lane_a', 'out_a', ''),), (('lane_b', 'out_b', ''),)]
        with patch("semaforos.algoritmos.heuristicas.traci.trafficlight.getPhase", return_value=0), \
             patch("semaforos.algoritmos.heuristicas.traci.trafficlight.getControlledLinks", return_value=links), \
             patch("semaforos.algoritmos.heuristicas.traci.lane.getLastStepHaltingNumber",
                   side_effect=lambda lane: {"lane_a": 2, "lane_b": 5}[lane]):
            self.assertEqual(queue_actuated_action(env).tolist(), [0])
        with patch("semaforos.algoritmos.heuristicas.traci.trafficlight.getPhase", return_value=0), \
             patch("semaforos.algoritmos.heuristicas.traci.trafficlight.getControlledLinks", return_value=links), \
             patch("semaforos.algoritmos.heuristicas.traci.lane.getLastStepHaltingNumber",
                   side_effect=lambda lane: {"lane_a": 6, "lane_b": 1}[lane]):
            self.assertEqual(queue_actuated_action(env).tolist(), [2])


if __name__ == "__main__":
    unittest.main()
