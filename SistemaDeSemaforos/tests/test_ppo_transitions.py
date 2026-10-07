"""Teste de integração das transições do piloto PPO com SUMO real."""

import tempfile
import unittest
from pathlib import Path

import traci

from semaforos.simulacao.ambiente import SemaforosEnv
from semaforos.cenario.configuracao import read_config
from semaforos.cenario.rede import network_programs, phase_action_spec


ROOT = Path(__file__).resolve().parents[1]


class TransitionTest(unittest.TestCase):
    def transitions(self, action):
        config = read_config(ROOT / "config" / "cenario.json")
        config["duration_seconds"] = 75
        config["ppo"]["decision_seconds"] = 1
        config["ppo"]["action_mode"] = "green_extension"
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

    def test_ppo_changes_yellow_and_clearance_between_decisions(self):
        config = read_config(ROOT / "config" / "cenario.json")
        config["duration_seconds"] = 75
        config["ppo"]["decision_seconds"] = 5
        with tempfile.TemporaryDirectory() as folder:
            env = SemaforosEnv(config, folder)
            try:
                env.reset(seed=11)
                self.assertEqual(len(env.action_spec), 6)
                for _ in range(15):
                    env.step([2] * 6)
                logs = env.action_log
            finally:
                env.close()
        self.assertEqual([row["phase_index"] for row in logs[:4]], [0, 1, 2, 3])
        self.assertEqual(logs[1]["phase_started_seconds"] - logs[0]["phase_started_seconds"], 58)
        self.assertEqual(logs[2]["phase_started_seconds"] - logs[1]["phase_started_seconds"], 6)
        self.assertEqual(logs[3]["phase_started_seconds"] - logs[2]["phase_started_seconds"], 3)
        self.assertEqual([row["selected_total_duration_seconds"] for row in logs[:3]], [58, 6, 3])

    def test_original_duration_choices_preserve_reference(self):
        config = read_config(ROOT / "config" / "cenario.json")
        config["duration_seconds"] = 50
        with tempfile.TemporaryDirectory() as folder:
            env = SemaforosEnv(config, folder)
            try:
                env.reset(seed=11)
                for _ in range(10):
                    env.step([1] * 6)
                logs = env.action_log
            finally:
                env.close()
        self.assertEqual([row["phase_started_seconds"] for row in logs[:4]], [0, 41, 44, 45])

    def test_yellow_below_network_duration_is_rejected(self):
        config = read_config(ROOT / "config" / "cenario.json")
        config["ppo"]["duration_limits"]["yellow"]["minimum_seconds"] = 2
        with self.assertRaisesRegex(ValueError, "Limites PPO inválidos"):
            phase_action_spec(config, network_programs(config["network"]))


if __name__ == "__main__":
    unittest.main()
