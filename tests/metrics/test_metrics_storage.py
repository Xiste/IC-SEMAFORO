"""Verifica tipos, integridade e publicação dos resultados.

Entrada: métricas pequenas em pastas temporárias. Saída: assertions do unittest;
uso normal: make test, sem executar SUMO.
"""

import gzip
import json
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from SistemaDeSemaforos.metrics.metrics_storage import (
    metric_records, save_entities, save_episode, write_json,
)
from scripts.audit_results import episode_records_valid, records_valid


class StorageTests(unittest.TestCase):
    def test_core_keeps_context_in_one_json_without_archived_inputs(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            execution = {"status": "completed", "collection": {"profile": "core"},
                         "simulation": {"seed": 23423, "step_length": 1.0}}
            original = deepcopy(execution)
            save_episode(directory, {"vehicles_completed": 3}, execution, include_entities=False)
            document = json.loads((directory / "metrics.json").read_text())
            self.assertEqual(document["schema_version"], 3)
            self.assertEqual(document["execution"], execution)
            self.assertEqual(execution, original)
            self.assertNotIn("batch_configuration_file", document)
            self.assertIsNone(document["entity_metrics_file"])
            self.assertEqual([path.name for path in directory.iterdir()], ["metrics.json"])

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
            self.assertEqual(summary["schema_version"], 3)
            self.assertEqual(result["schema_version"], 1)
            self.assertEqual(set(result["entities"]["lanes"]["-via_ação_0"][0]),
                             {"metric_name", "data_type", "value"})

    def test_episode_presentation_preserves_all_canonical_values_and_input(self):
        values = {
            "seed": 42, "gui": False, "status": "completed",
            "execution_time_seconds": 0.5, "vehicles_completed": 7,
            "completed_trip_waiting_time_mean": 12.84,
            "completed_trip_time_loss_mean": 23.125,
            "completed_throughput_vehicles_per_hour": 140.0,
            "network_mean_speed_m_s_mean": 5.0, "teleports": 2,
            "trip_records_unfinished": 3,
            "completed_emission_electricity_abs_sum": -0.25,
        }
        original = deepcopy(values)
        legacy = metric_records(values)
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            save_episode(directory, values, {"status": "completed"})
            document = json.loads((directory / "metrics.json").read_text())
        records = document["metrics"]
        projected = [{key: r[key] for key in ("metric_name", "data_type", "value")}
                     for r in records]
        self.assertEqual(sorted(projected, key=lambda r: r["metric_name"]), legacy)
        self.assertEqual(values, original)
        self.assertEqual([r["metric_name"] for r in records[:4]], [
            "completed_trip_time_loss_mean", "completed_trip_waiting_time_mean",
            "completed_throughput_vehicles_per_hour", "vehicles_completed",
        ])
        for record in records:
            self.assertTrue(record["label_pt"].strip())
            self.assertTrue(record["description_pt"].strip())
            self.assertIn("unit", record)
        by_name = {r["metric_name"]: r for r in records}
        self.assertEqual(by_name["seed"]["kind"], "context")
        self.assertEqual(by_name["vehicles_completed"]["kind"], "result")
        self.assertEqual(by_name["execution_time_seconds"]["kind"], "diagnostic")
        self.assertEqual(by_name["teleports"]["category"], "integrity")
        self.assertEqual(by_name["completed_trip_waiting_time_mean"]["unit"], "s")
        # O leitor anterior continua aceitando os campos extras e a nova ordem.
        observed = set()
        self.assertEqual(records_valid(records, observed), len(values))
        self.assertEqual(observed, set(values))
        self.assertEqual(episode_records_valid(document, set()), len(values))
        self.assertEqual(episode_records_valid(
            {"schema_version": 1, "metrics": legacy}, set()), len(values))

    def test_initial_and_failed_episodes_do_not_invent_absent_measurements(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            for status in ("running", "failed", "interrupted"):
                values = {"status": status, "seed": 4}
                if status != "running":
                    values["error"] = "RuntimeError: ferramenta indisponível"
                save_episode(directory, values, {"status": status})
                document = json.loads((directory / "metrics.json").read_text())
                records = {r["metric_name"]: r for r in document["metrics"]}
                self.assertEqual(set(records), set(values))
                self.assertEqual(records["status"]["value"], status)
                self.assertEqual(document["execution"]["status"], status)
                self.assertEqual(episode_records_valid(document, set()), len(values))

    def test_auditor_rejects_incomplete_semantics_and_wrong_priority_order(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            save_episode(directory, {"vehicles_completed": 5, "seed": 3}, {})
            document = json.loads((directory / "metrics.json").read_text())
        for field, invalid in (("label_pt", ""), ("description_pt", None),
                               ("unit", []), ("kind", "unknown"),
                               ("priority", True), ("category", "unknown")):
            with self.subTest(field=field):
                broken = deepcopy(document)
                broken["metrics"][0][field] = invalid
                with self.assertRaises(ValueError):
                    episode_records_valid(broken, set())
        document["metrics"].reverse()
        with self.assertRaises(ValueError):
            episode_records_valid(document, set())

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
