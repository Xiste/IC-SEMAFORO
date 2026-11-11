import copy
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from semaforos.caminhos import PROJECT_ROOT
from semaforos.cenario.configuracao import read_config
from semaforos.cenario.experimental import prepare_experimental, validate_experimental, intersection_names, select_intersection, preview_experimental, prepare_or_reuse
from semaforos.experimentos.rl import train_rl, evaluate_rl


class ExperimentalTest(unittest.TestCase):
    def test_individual_intersections(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT / 'resultados', prefix='test_individual_') as temporary:
            folder = Path(temporary)
            config, _ = prepare_experimental(read_config(PROJECT_ROOT / 'config/cenario_rede_corrigida.json'), folder / 'cenario_nove_cache')
            current = read_config(PROJECT_ROOT / 'config/cenario_rede_corrigida.json')
            current['demand']['vehicles_per_hour'] = 720
            current['ppo']['total_timesteps'] = 4096
            with patch('semaforos.cenario.experimental.prepare_experimental') as create:
                reused_config, _, reused = prepare_or_reuse(current, folder)
                self.assertTrue(reused)
                create.assert_not_called()
                self.assertEqual(reused_config['demand']['vehicles_per_hour'], 720)
                self.assertEqual(reused_config['ppo']['total_timesteps'], 4096)
            saved_path = folder / 'cenario_nove_cache/cenario.json'
            saved = json.loads(saved_path.read_text(encoding='utf-8'))
            saved['experimental']['source_sha256'] = 'outdated'
            saved_path.write_text(json.dumps(saved), encoding='utf-8')
            with patch('semaforos.cenario.experimental.prepare_experimental', return_value=(config, [])) as create:
                _, _, reused = prepare_or_reuse(current, folder)
                self.assertFalse(reused)
                create.assert_called_once()
            self.assertEqual(len(intersection_names()), 9)
            multiple = None
            for name in intersection_names():
                selected = select_intersection(config, name)
                expected = [t for t in config['targets'] if t['name'] == name]
                self.assertEqual(selected['targets'], expected)
                self.assertEqual(len(validate_experimental(selected)), len(expected))
                ids = {t['tls_id'] for t in expected}
                self.assertTrue(all(k.rsplit(':', 1)[0] in ids for k in selected['control']['phase_duration_bounds']))
                if len(expected) > 1:
                    multiple = selected
            self.assertEqual(len(config['targets']), 17)
            self.assertIsNotNone(multiple)
            changed = copy.deepcopy(multiple)
            changed['targets'].pop()
            with self.assertRaises(ValueError):
                validate_experimental(changed)
            multiple['control']['gui'] = False
            preview_experimental(multiple, folder / 'preview')
            self.assertTrue((folder / 'preview/preview.json').is_file())

    def test_joint_train_load_evaluate_and_tamper(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT / "resultados", prefix="test_nove_") as temporary:
            folder = Path(temporary)
            config, rows = prepare_experimental(read_config(PROJECT_ROOT / "config/cenario.json"), folder / "scenario")
            controlled = [row for row in rows if row["controlado"]]
            self.assertEqual(len(controlled), 17)
            self.assertEqual(len({row["cruzamento"] for row in controlled}), 9)
            source = ET.parse(PROJECT_ROOT / "dados/rede/uberlandia.rondon_norte_corrigida.net.xml").getroot()
            generated = ET.parse(config["network"]).getroot()
            targets = {item["tls_id"] for item in config["targets"]}
            targets.update(config["experimental"]["external_repaired"])
            self.assertEqual(len(config["experimental"]["external_repaired"]), 4)
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
