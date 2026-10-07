import copy
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from semaforos.caminhos import PROJECT_ROOT
from semaforos.cenario.configuracao import read_config
from semaforos.cenario.experimental import prepare_experimental, validate_experimental
from semaforos.experimentos.rl import train_rl, evaluate_rl


class ExperimentalTest(unittest.TestCase):
    def test_joint_train_load_evaluate_and_tamper(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT / "resultados", prefix="test_nove_") as temporary:
            folder = Path(temporary)
            config, rows = prepare_experimental(read_config(PROJECT_ROOT / "config/cenario.json"), folder / "scenario")
            self.assertEqual(len(rows), 17)
            self.assertEqual(len({row["cruzamento"] for row in rows}), 9)
            source = ET.parse(PROJECT_ROOT / "dados/rede/uberlandia.rondon_norte_corrigida.net.xml").getroot()
            generated = ET.parse(config["network"]).getroot()
            targets = {item["tls_id"] for item in config["targets"]}
            original_times = {(logic.get("id"), logic.get("programID")): [p.get("duration") for p in logic.findall("phase")]
                              for logic in source.findall("tlLogic") if logic.get("id") not in targets}
            generated_times = {(logic.get("id"), logic.get("programID")): [p.get("duration") for p in logic.findall("phase")]
                               for logic in generated.findall("tlLogic") if logic.get("id") not in targets}
            self.assertEqual(original_times, generated_times)
            changed_mode = copy.deepcopy(config)
            changed_mode["control"]["action_mode"] = "green_extension"
            with self.assertRaises(ValueError):
                validate_experimental(changed_mode)
            config["duration_seconds"] = 20
            config["ppo"].update(total_timesteps=4, n_steps=4, batch_size=4, n_epochs=1)
            train_rl(config, folder / "train")
            evaluate_rl(config, folder / "eval", folder / "train/ppo_model.zip", seeds=[101])
            self.assertTrue((folder / "eval/signals.csv").is_file())
            changed = copy.deepcopy(config)
            changed["targets"] = changed["targets"][:-1]
            with self.assertRaises(ValueError):
                validate_experimental(changed)
            network = Path(config["network"])
            network.write_bytes(network.read_bytes() + b"\n")
            with self.assertRaises(ValueError):
                validate_experimental(config)


if __name__ == "__main__":
    unittest.main()
