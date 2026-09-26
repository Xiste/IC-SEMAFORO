"""Verifica tipos, integridade e publicação dos resultados.

Entrada: métricas pequenas em pastas temporárias. Saída: assertions do unittest;
uso normal: make test, sem executar SUMO.
"""

import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from SistemaDeSemaforos.metrics.storage import metric_records, save_entities, save_episode, write_json


class StorageTests(unittest.TestCase):
    def test_types_are_preserved_and_invalid_values_rejected(self):
        records = metric_records({"enabled": True, "seed": 7, "speed": 2.5, "name": "random"})
        self.assertEqual({r["metric_name"]: r["data_type"] for r in records},
                         {"enabled": "bool", "seed": "int", "speed": "float", "name": "string"})
        for values, error in (({"bad-name": 1}, ValueError), ({"x": float("nan")}, ValueError),
                              ({"x": float("inf")}, ValueError), ({"x": None}, TypeError)):
            with self.assertRaises(error):
                metric_records(values)

    def test_export_keeps_ids_and_compresses_consolidated_entities(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            save_entities(directory, {"lanes": {"-via_ação_0": {"queue_max": 4.0}}})
            save_episode(directory, {"seed": 2}, {"status": "completed"})
            with gzip.open(directory / "entities.json.gz", "rt", encoding="utf-8") as stream:
                result = json.load(stream)
            self.assertEqual(result["entities"]["lanes"]["-via_ação_0"][0]["value"], 4.0)
            summary = json.loads((directory / "metrics.json").read_text())
            self.assertEqual(summary["entity_metrics_file"], "entities.json.gz")
            self.assertEqual(len(summary["metrics"]), 1)

    def test_invalid_json_preserves_previous_file_and_removes_temporary(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "metrics.json"
            path.write_text('{"previous": true}')
            with self.assertRaises(ValueError):
                write_json(path, {"invalid": float("nan")})
            self.assertEqual(json.loads(path.read_text()), {"previous": True})
            self.assertEqual(list(Path(temp).iterdir()), [path])


if __name__ == "__main__":
    unittest.main()
