"""O esquema de cruzamentos aceita vários controladores sem validar candidatos por engano."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from semaforos.cenario.configuracao import read_config
from semaforos.cenario.mapeamento import mapping_report


ROOT = Path(__file__).resolve().parents[1]


class MultiControllerMappingTest(unittest.TestCase):
    def test_audit_lists_four_controllers_for_porto_alegre(self):
        config = read_config(ROOT / "config" / "cenario_rede_corrigida.json")
        mapping = json.loads(config["mapping_path"].read_text(encoding="utf-8"))
        entry = mapping["intersections"][3]
        entry["controllers"] = [{"tls_id": tls_id, "stage_to_phase": {}}
                                for tls_id in entry["candidate_tls_ids"]]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "mapping.json"
            path.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
            report = mapping_report(config, path)
        crossing = report["intersections"][3]
        self.assertEqual(len(crossing["controllers"]), 4)
        self.assertEqual(report["validated_count"], 0)
        self.assertTrue(all(controller["controlled_links"] for controller in crossing["controllers"]))

    def test_candidate_subset_cannot_be_declared_complete(self):
        config = read_config(ROOT / "config" / "cenario_rede_corrigida.json")
        mapping = json.loads(config["mapping_path"].read_text(encoding="utf-8"))
        entry = mapping["intersections"][3]
        entry["controllers"] = [{"tls_id": entry["candidate_tls_ids"][0], "stage_to_phase": {}}]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "mapping.json"
            path.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
            report = mapping_report(config, path)
        self.assertTrue(any("IDs candidatos sem atribuição completa" in issue
                            for issue in report["intersections"][3]["issues"]))

    def test_validated_mapping_expands_controllers_into_targets(self):
        source = ROOT / "config" / "cenario_rede_corrigida.json"
        config = read_config(source)
        mapping = json.loads(config["mapping_path"].read_text(encoding="utf-8"))
        for entry in mapping["intersections"]:
            entry["controllers"] = [{"tls_id": entry["candidate_tls_ids"][0],
                                     "stage_to_phase": {"A": 0}}]
        porto = mapping["intersections"][3]
        porto["controllers"].append({"tls_id": porto["candidate_tls_ids"][1],
                                      "stage_to_phase": {"B": 3}})
        scenario = json.loads(source.read_text(encoding="utf-8"))
        scenario.update(network=str(config["network"]), plans=str(config["plans"]),
                        targets_from_mapping=True)
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            mapping_path = folder / "mapping.json"
            mapping_path.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
            scenario["mapping_path"] = str(mapping_path)
            scenario_path = folder / "scenario.json"
            scenario_path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")
            with patch("semaforos.cenario.mapeamento.mapping_report", return_value={"validated_count": 9}):
                loaded = read_config(scenario_path)
        self.assertEqual(len(loaded["targets"]), 10)
        self.assertIn({"name": porto["name"], "tls_id": porto["candidate_tls_ids"][1],
                       "phase_indices": [3]}, loaded["targets"])


if __name__ == "__main__":
    unittest.main()
