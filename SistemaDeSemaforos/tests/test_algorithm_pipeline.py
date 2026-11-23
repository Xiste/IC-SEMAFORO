"""Treino, salvamento e avaliação reais para PPO e A2C."""

import json
import tempfile
import unittest
from pathlib import Path

from semaforos.caminhos import PROJECT_ROOT
from semaforos.cenario.configuracao import read_config
from semaforos.cenario.experimental import prepare_or_reuse
from semaforos.experimentos.rl import train_rl, evaluate_rl


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
        self.assertEqual([row["controller"] for row in result["runs"]], ["network_reference", name])
        self.assertTrue(result["same_planned_demand_per_seed"])
        self.assertTrue((folder / "evaluation/comparison.png").is_file())

    def test_ppo_migrated_train_save_load_and_evaluate(self):
        with tempfile.TemporaryDirectory() as folder:
            self.check_cycle(self.config(), "PPO", Path(folder))

    def test_a2c_trains_and_evaluates_the_nine_intersections(self):
        base = read_config(PROJECT_ROOT / "config/cenario_rede_corrigida.json")
        config, _, _ = prepare_or_reuse(base, PROJECT_ROOT / 'resultados')
        config.update(algorithm="A2C", a2c={"n_steps": 2, "total_timesteps": 4}, duration_seconds=20)
        config["control"] = {**config["control"], "action_mode": "adaptive_signals", "gui": False}
        config["demand"] = {"mode": "edge_volumes", "edge_volumes": [
            {"from_edge": "1156717168", "vehicles_per_hour": 540.}
        ]}
        with tempfile.TemporaryDirectory() as folder:
            self.check_cycle(config, "A2C", Path(folder))
            manifest = json.loads((Path(folder) / "train/manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["action_mode"], "adaptive_signals")
            self.assertEqual(len(manifest["action_spec"]), 17)


if __name__ == "__main__":
    unittest.main()
