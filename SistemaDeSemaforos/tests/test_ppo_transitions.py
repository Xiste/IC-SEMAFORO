"""Teste de integração das transições do piloto PPO com SUMO real."""

import tempfile
import unittest
from pathlib import Path

import traci

from semaforos.ambiente_ppo import SemaforosEnv
from semaforos.configuracao import read_config


ROOT = Path(__file__).resolve().parents[1]


class TransitionTest(unittest.TestCase):
    def transitions(self, action):
        config = read_config(ROOT / "config" / "cenario.json")
        config["duration_seconds"] = 75
        config["ppo"]["decision_seconds"] = 1
        with tempfile.TemporaryDirectory() as folder:
            env = SemaforosEnv(config, folder)
            try:
                env.reset(seed=11)
                phases = []
                for _ in range(65):
                    env.step([action])
                    phases.append(traci.trafficlight.getPhase("FAM_RONDON_PARANA"))
            finally:
                env.close()
        return [(step + 1, phase) for step, phase in enumerate(phases)
                if step == 0 or phase != phases[step - 1]]

    def test_short_green_keeps_clearance(self):
        changes = self.transitions(0)
        self.assertEqual([phase for _, phase in changes[:4]], [0, 1, 2, 3])
        self.assertGreaterEqual(changes[1][0], 24)
        self.assertLess(changes[1][0], 41)
        self.assertEqual(changes[2][0] - changes[1][0], 3)
        self.assertEqual(changes[3][0] - changes[2][0], 1)

    def test_extended_green_respects_maximum(self):
        changes = self.transitions(2)
        self.assertGreater(changes[1][0], 41)
        self.assertLessEqual(changes[1][0], 58)
        self.assertEqual(changes[2][0] - changes[1][0], 3)
        self.assertEqual(changes[3][0] - changes[2][0], 1)


if __name__ == "__main__":
    unittest.main()
