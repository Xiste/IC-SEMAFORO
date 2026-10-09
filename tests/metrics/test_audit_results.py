"""Confere resultados publicados sem exigir entradas antigas para reproduzi-los."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from SistemaDeSemaforos.metrics.metrics_storage import (
    metric_records, save_entities, save_episode, write_json,
)
from scripts.audit_results import audit, episode_records_valid, records_valid


def episode_fixture(root, profile):
    directory = root / profile
    directory.mkdir()
    save_episode(directory, {
        "vehicles_completed": 2, "seed": 7, "simulation_seed": 23423,
        "status": "completed", "metrics_profile": profile,
    }, {"status": "completed", "sumo_version": "SUMO fixture",
        "collection": {"profile": profile}},
        include_entities=profile == "full")
    if profile == "full":
        save_entities(directory, {"vehicles": {"car0": {"trip_duration": 12.0}}})
    return directory


class AuditResultsTests(unittest.TestCase):
    def test_core_and_full_validate_without_archived_inputs_or_terminal_report(self):
        with TemporaryDirectory() as temporary, redirect_stdout(io.StringIO()) as terminal:
            root = Path(temporary)
            core = episode_fixture(root, "core")
            full = episode_fixture(root, "full")
            self.assertEqual({path.name for path in core.iterdir()}, {"metrics.json"})
            self.assertEqual({path.name for path in full.iterdir()}, {"metrics.json", "entities.json.gz"})
            result = audit(root)
        self.assertEqual(terminal.getvalue(), "")
        self.assertEqual(result["episodes_verified"], 2)
        self.assertEqual(result["typed_records_verified"], 11)

    def test_rejects_missing_directory_and_directory_without_episodes(self):
        with TemporaryDirectory() as temporary:
            for path in (Path(temporary), Path(temporary) / "missing"):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    audit(path)

    def test_entities_follow_profile_and_explicit_declaration(self):
        for variant in ("full_null", "full_missing", "core_omitted", "core_undeclared_file", "core_full"):
            with self.subTest(variant=variant), TemporaryDirectory() as temporary:
                profile = "full" if variant.startswith("full") else "core"
                root = Path(temporary)
                directory = episode_fixture(root, profile)
                document = json.loads((directory / "metrics.json").read_text())
                if variant == "core_omitted":
                    document.pop("entity_metrics_file")
                elif variant == "full_missing":
                    (directory / "entities.json.gz").unlink()
                elif variant == "core_full":
                    document["entity_metrics_file"] = "entities.json.gz"
                else:
                    document["entity_metrics_file"] = None
                if variant == "core_undeclared_file":
                    write_json(directory / "entities.json.gz", {"entities": {}})
                write_json(directory / "metrics.json", document)
                with self.assertRaises(ValueError):
                    audit(root)

    def test_rejects_missing_version_and_inconsistent_execution_state(self):
        for variant in ("sumo_version", "execution_status", "metric_status", "profile", "version"):
            with self.subTest(variant=variant), TemporaryDirectory() as temporary:
                root = Path(temporary)
                directory = episode_fixture(root, "core")
                document = json.loads((directory / "metrics.json").read_text())
                if variant == "sumo_version":
                    document["execution"].pop("sumo_version")
                elif variant == "execution_status":
                    document["execution"]["status"] = "failed"
                elif variant == "metric_status":
                    next(r for r in document["metrics"] if r["metric_name"] == "status")["value"] = "running"
                elif variant == "profile":
                    document["execution"]["collection"]["profile"] = "full"
                else:
                    document["schema_version"] = 2
                write_json(directory / "metrics.json", document)
                with self.assertRaises(ValueError):
                    audit(root)

    def test_rejects_invalid_global_types_and_entity_aggregates(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = episode_fixture(root, "full")
            document = json.loads((directory / "metrics.json").read_text())
            next(r for r in document["metrics"] if r["metric_name"] == "seed")["value"] = "7"
            write_json(directory / "metrics.json", document)
            with self.assertRaisesRegex(ValueError, "Tipo/chave inválido"):
                audit(root)
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = episode_fixture(root, "full")
            save_entities(directory, {"lanes": {"lane": {
                "speed_min": 2.0, "speed_mean": 1.0, "speed_max": 3.0,
            }}})
            with self.assertRaisesRegex(ValueError, "Agregados fora de ordem"):
                audit(root)

    def test_rejects_unknown_globals_and_duplicate_records(self):
        with self.assertRaisesRegex(ValueError, "sem apresentação"):
            episode_records_valid({"schema_version": 1,
                                   "metrics": metric_records({"unknown": 1.0})}, set())
        record = metric_records({"seed": 7})[0]
        with self.assertRaisesRegex(ValueError, "Tipo/chave inválido"):
            records_valid([record, record], set())


if __name__ == "__main__":
    unittest.main()
