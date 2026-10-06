"""A heurística usa as filas dos movimentos verdes, com ações válidas."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from semaforos.ppo import queue_actuated_action


class QueueBaselineTest(unittest.TestCase):
    def test_prefers_larger_incoming_queue(self):
        env = SimpleNamespace(
            targets=[{"tls_id": "T", "phase_indices": [0, 3]}],
            programs={"T": [{"state": "Gr"}, {"state": "yr"},
                            {"state": "rr"}, {"state": "rG"}]})
        links = [(('lane_a', 'out_a', ''),), (('lane_b', 'out_b', ''),)]
        with patch("semaforos.ppo.traci.trafficlight.getPhase", return_value=0), \
             patch("semaforos.ppo.traci.trafficlight.getControlledLinks", return_value=links), \
             patch("semaforos.ppo.traci.lane.getLastStepHaltingNumber",
                   side_effect=lambda lane: {"lane_a": 2, "lane_b": 5}[lane]):
            self.assertEqual(queue_actuated_action(env).tolist(), [0])
        with patch("semaforos.ppo.traci.trafficlight.getPhase", return_value=0), \
             patch("semaforos.ppo.traci.trafficlight.getControlledLinks", return_value=links), \
             patch("semaforos.ppo.traci.lane.getLastStepHaltingNumber",
                   side_effect=lambda lane: {"lane_a": 6, "lane_b": 1}[lane]):
            self.assertEqual(queue_actuated_action(env).tolist(), [2])


if __name__ == "__main__":
    unittest.main()
