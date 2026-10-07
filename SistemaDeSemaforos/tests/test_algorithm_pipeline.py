"""Treino e avaliação reais verificam o contrato de extensão e o PPO migrado."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from semaforos.caminhos import PROJECT_ROOT
from semaforos.cenario.configuracao import read_config
from semaforos.algoritmos.registro import Algorithm, get_algorithm, register_algorithm
from semaforos.experimentos.rl import train_rl, evaluate_rl
from stable_baselines3 import A2C


class AlgorithmPipelineTest(unittest.TestCase):
    def config(self):
        config = read_config(PROJECT_ROOT / "config/cenario.json")
        config["duration_seconds"] = 40
        config["ppo"].update(n_steps=8, batch_size=4, n_epochs=2, total_timesteps=8, gui=False)
        config["control"] = {**config["ppo"], "decision_seconds": 5}
        return config

    def check_cycle(self, config, name, folder):
        output = folder / "train"
        summary = train_rl(config, output)
        self.assertEqual(summary["algorithm"], name)
        self.assertTrue(Path(summary["model"]).is_file())
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["algorithm"], name)
        self.assertTrue(manifest["algorithm_parameters"])
        result = evaluate_rl(config, folder / "evaluation", summary["model"], seeds=[101])
        self.assertEqual({row["controller"] for row in result["runs"]}, {name, "network_reference", "queue_actuated"})
        self.assertTrue(result["same_planned_demand_per_seed"])
        self.assertTrue((folder / "evaluation/comparison.png").is_file())

    def test_ppo_migrated_train_save_load_and_evaluate(self):
        with tempfile.TemporaryDirectory() as folder:
            self.check_cycle(self.config(), "PPO", Path(folder))

    def test_second_registered_algorithm_reuses_pipeline(self):
        get_algorithm("PPO")

        def parameters(config):
            return dict(policy="MlpPolicy", n_steps=config["a2c_test"]["n_steps"], seed=config["seeds"][0], verbose=0)

        # A2C é uma prova do adaptador neste teste, não um algoritmo publicado na UI.
        with patch.dict("semaforos.algoritmos.registro._ALGORITHMS"):
            register_algorithm(Algorithm("A2C_TEST", A2C, "a2c_test", parameters))
            config = self.config()
            config.update(algorithm="A2C_TEST", a2c_test={"n_steps": 4, "total_timesteps": 8})
            with tempfile.TemporaryDirectory() as folder:
                self.check_cycle(config, "A2C_TEST", Path(folder))
        with self.assertRaisesRegex(ValueError, "desconhecido"):
            get_algorithm("A2C_TEST")


if __name__ == "__main__":
    unittest.main()
