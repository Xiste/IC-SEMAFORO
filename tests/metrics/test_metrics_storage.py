"""Verifica tipos, integridade e publicação dos resultados.

Entrada: métricas pequenas em pastas temporárias. Saída: assertions do unittest;
uso normal: make test, sem executar SUMO.
"""

import gzip
import hashlib
import json
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from SistemaDeSemaforos.metrics.metrics_storage import (
    compress_file, describe_metric, metric_records, presentation_sort_key, read_json,
    result_sha256, save_entities, save_episode, verify_file, write_json,
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
            document = read_json(directory / "metrics.json.gz")
            self.assertEqual(document["schema_version"], 3)
            self.assertEqual(document["execution"], execution)
            self.assertEqual(execution, original)
            self.assertNotIn("batch_configuration_file", document)
            self.assertIsNone(document["entity_metrics_file"])
            self.assertEqual([path.name for path in directory.iterdir()], ["metrics.json.gz"])

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
            summary = read_json(directory / "metrics.json.gz")
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
            document = read_json(directory / "metrics.json.gz")
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
                document = read_json(directory / "metrics.json.gz")
                records = {r["metric_name"]: r for r in document["metrics"]}
                self.assertEqual(set(records), set(values))
                self.assertEqual(records["status"]["value"], status)
                self.assertEqual(document["execution"]["status"], status)
                self.assertEqual(episode_records_valid(document, set()), len(values))

    def test_auditor_rejects_incomplete_semantics_and_wrong_priority_order(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            save_episode(directory, {"vehicles_completed": 5, "seed": 3}, {})
            document = read_json(directory / "metrics.json.gz")
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

    def test_compressed_json_preserves_exact_plain_serialization_and_numbers(self):
        value = {"ação": [None, True, {"seed": 2**63 - 1,
                                      "tiny": 1.2345678901234567e-150,
                                      "signed_zero": -0.0, "text": "a\n\\\"b"}]}
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            plain, compressed = directory / "metrics.json", directory / "metrics.json.gz"
            write_json(plain, value)
            write_json(compressed, value)
            with gzip.open(compressed, "rb") as stream:
                recovered = stream.read()
            self.assertEqual(recovered, plain.read_bytes())
            self.assertEqual(hashlib.sha256(recovered).hexdigest(), result_sha256(compressed))
            plain.unlink()
            self.assertEqual(read_json(plain), value)

    def test_real_file_and_large_binary_round_trip_with_matching_sha256(self):
        real = Path(__file__).resolve().parents[2] / "docs" / "settran_programs.json"
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            for name, content in (("real.json", real.read_bytes()),
                                  ("large.xml", "<vehicle id='ação'/>\n".encode() * 150000)):
                with self.subTest(name=name):
                    source = directory / name
                    source.write_bytes(content)
                    compressed = compress_file(source)
                    verify_file(source, compressed)
                    self.assertEqual(result_sha256(compressed), hashlib.sha256(content).hexdigest())
                    self.assertEqual(gzip.decompress(compressed.read_bytes()), content)
                    self.assertEqual(source.read_bytes(), content)

    def test_failed_compression_or_corruption_never_removes_original(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            source = directory / "routes.xml"
            original = b"<routes>teste</routes>" * 5000
            source.write_bytes(original)
            with patch("SistemaDeSemaforos.metrics.metrics_storage._verify_gzip",
                       side_effect=ValueError("verificação falhou")):
                with self.assertRaisesRegex(ValueError, "verificação falhou"):
                    compress_file(source)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(list(directory.iterdir()), [source])
            compressed = compress_file(source)
            compressed.write_bytes(compressed.read_bytes()[:-8])
            with self.assertRaises((EOFError, OSError)):
                verify_file(source, compressed)
            self.assertEqual(source.read_bytes(), original)

    def test_invalid_compressed_json_keeps_previous_publication(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "metrics.json.gz"
            write_json(path, {"previous": 1})
            before = path.read_bytes()
            for failure in (ValueError("digest mismatch"), OSError("disk error")):
                with patch("SistemaDeSemaforos.metrics.metrics_storage._verify_gzip", side_effect=failure):
                    with self.assertRaises(type(failure)):
                        write_json(path, {"next": 2})
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(list(path.parent.iterdir()), [path])
            with self.assertRaises(ValueError):
                write_json(path, {"invalid": float("nan")})
            self.assertEqual(path.read_bytes(), before)

    def test_interrupted_process_preserves_original_and_previous_json(self):
        code = """
import sys
from pathlib import Path
from unittest.mock import patch
from SistemaDeSemaforos.metrics.metrics_storage import compress_file, write_json
def pause(*args):
    print('ready', flush=True)
    sys.stdin.readline()
with patch('SistemaDeSemaforos.metrics.metrics_storage._verify_gzip', side_effect=pause):
    if sys.argv[1] == 'file':
        compress_file(Path(sys.argv[2]))
    else:
        write_json(Path(sys.argv[2]), {'new': 2})
"""
        with TemporaryDirectory() as temp:
            source = Path(temp) / "route.xml"
            source.write_bytes(b"original route\n" * 10000)
            metrics = Path(temp) / "metrics.json.gz"
            write_json(metrics, {"previous": 1})
            original, previous = source.read_bytes(), metrics.read_bytes()
            for operation, path in (("file", source), ("json", metrics)):
                with self.subTest(operation=operation), subprocess.Popen(
                        [sys.executable, "-B", "-c", code, operation, str(path)],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        text=True) as child:
                    self.assertEqual(child.stdout.readline().strip(), "ready")
                    child.kill()
                    child.wait(timeout=10)
                self.assertEqual(source.read_bytes(), original)
                self.assertEqual(metrics.read_bytes(), previous)
                self.assertFalse(source.with_name(source.name + ".gz").exists())


class MetricPresentationTests(unittest.TestCase):
    def test_samples_and_exclusions_have_count_units_and_separate_priority(self):
        for base, unit in (("network_mean_speed_m_s", "m/s"),
                           ("vehicles_halting", "veículos"),
                           ("sumo_step_computation_ms", "ms")):
            with self.subTest(base=base):
                measured = describe_metric(base + "_mean")
                samples = describe_metric(base + "_samples")
                excluded = describe_metric(base + "_excluded_samples")
                self.assertEqual(measured["unit"], unit)
                self.assertEqual(samples["unit"], "amostras")
                self.assertEqual(excluded["unit"], "amostras")
                self.assertEqual(samples["priority"], 4)
                self.assertEqual(excluded["priority"], 3)
                self.assertEqual(excluded["category"], "integrity")

    def test_trip_status_and_aggregation_remain_explicit(self):
        for status, population in (("completed", "concluídas"),
                                   ("unfinished", "sem chegada registrada"),
                                   ("undeparted", "sem partida"),
                                   ("vaporized", "remoção excepcional")):
            mean = describe_metric(f"{status}_trip_waiting_time_mean")
            total = describe_metric(f"{status}_trip_waiting_time_sum")
            self.assertIn(population, mean["description_pt"])
            self.assertIn(population, total["description_pt"])
            self.assertIn("Média", mean["description_pt"])
            self.assertIn("Soma", total["description_pt"])
            self.assertEqual(mean["priority"], 1 if status == "completed" else 3)
        waiting = describe_metric("completed_trip_waiting_time_mean")
        self.assertIn("excluindo paradas programadas", waiting["description_pt"])
        delay = describe_metric("completed_trip_depart_delay_mean")
        self.assertIn("antes da entrada", delay["description_pt"])

    def test_emission_totals_rates_and_samples_have_distinct_units(self):
        for name, expected in (
            ("completed_emission_co2_abs_sum", "mg"),
            ("network_emission_co2_rate_mean", "mg/s"),
            ("completed_emission_fuel_abs_mean", "mg"),
            ("network_emission_fuel_rate_mean", "mg/s"),
            ("unfinished_emission_electricity_abs_sum", "Wh"),
            ("network_emission_electricity_rate_mean", "Wh/s"),
            ("completed_emission_n_ox_abs_samples", "amostras"),
        ):
            with self.subTest(name=name):
                self.assertEqual(describe_metric(name)["unit"], expected)
        self.assertIn("negativos indicando recuperação",
                      describe_metric("completed_emission_electricity_abs_mean")["description_pt"])

    def test_queue_coverage_and_halting_do_not_claim_queue_length(self):
        coverage = describe_metric("queue_observation_steps")
        self.assertEqual((coverage["kind"], coverage["priority"], coverage["unit"]),
                         ("diagnostic", 4, "passos"))
        self.assertIn("não mede comprimento de fila",
                      describe_metric("vehicles_halting_mean")["description_pt"])
        self.assertIn("toda a duração simulada",
                      describe_metric("completed_throughput_vehicles_per_hour")["description_pt"])
        queue = describe_metric("network_queueing_length_lane_sum_mean")
        self.assertEqual(queue["unit"], "m")
        self.assertIn("soma dos comprimentos", queue["description_pt"])
        self.assertIn("cada passo válido tem o mesmo peso", queue["description_pt"])
        self.assertIn("não representa uma fila física única", queue["description_pt"])
        self.assertEqual(describe_metric("network_queueing_length_lane_sum_samples")["unit"], "amostras")
        self.assertEqual(describe_metric("network_queueing_length_lane_sum_excluded_samples")["category"], "integrity")

    def test_demand_window_simulated_duration_and_wall_time_are_distinct(self):
        demand = describe_metric("demand_duration_seconds")
        simulation = describe_metric("simulation_duration_seconds")
        execution = describe_metric("execution_time_seconds")
        self.assertIn("partidas são solicitadas", demand["description_pt"])
        self.assertIn("Tempo simulado", simulation["description_pt"])
        self.assertIn("Tempo real", execution["description_pt"])
        self.assertIn("exclui a escrita final", execution["description_pt"])
        self.assertTrue(all(item["unit"] == "s" for item in (demand, simulation, execution)))

    def test_conditional_full_fields_and_hex_event_categories(self):
        for scope in ("edge", "lane"):
            self.assertEqual(describe_metric(f"{scope}_traffic_duration_seconds")["unit"], "s")
            self.assertEqual(describe_metric(f"{scope}_traffic_internal_included")["kind"], "context")
        reason = "strategic|urgent"
        prefix = "lane_change_reason_" + reason.encode().hex()
        self.assertIn(reason, describe_metric(prefix + "_count")["description_pt"])
        self.assertIn("seguir a rota; manobra urgente", describe_metric(prefix + "_count")["label_pt"])
        self.assertEqual(describe_metric(prefix + "_value")["kind"], "context")
        self.assertEqual(describe_metric("collision_victim_speed_mean")["priority"], 3)
        self.assertEqual(describe_metric("lane_change_follower_speed_mean")["unit"], "m/s")
        self.assertEqual(describe_metric("sumo_ride_statistics_aborted")["priority"], 3)
        self.assertIn("Duração média", describe_metric("sumo_pedestrian_statistics_duration")["description_pt"])

    def test_priority_and_headlines_are_independent_of_input_order(self):
        names = ["seed", "queue_observation_steps", "teleports", "vehicles_completed",
                 "network_mean_speed_m_s_mean", "completed_trip_waiting_time_mean",
                 "completed_throughput_vehicles_per_hour", "completed_trip_time_loss_mean",
                 "completed_trip_time_loss_samples", "execution_time_seconds"]
        records = [{"metric_name": n, **describe_metric(n)} for n in names]
        ordered = sorted(records, key=presentation_sort_key)
        self.assertEqual(ordered, sorted(reversed(records), key=presentation_sort_key))
        self.assertEqual([r["metric_name"] for r in ordered[:4]], [
            "completed_trip_time_loss_mean", "completed_trip_waiting_time_mean",
            "completed_throughput_vehicles_per_hour", "vehicles_completed",
        ])
        priorities = [r["priority"] for r in ordered]
        self.assertEqual(priorities, sorted(priorities))

    def test_unknown_metrics_are_not_given_invented_meaning(self):
        with self.assertRaisesRegex(ValueError, "sem apresentação cadastrada"):
            describe_metric("unknown_result")
        with self.assertRaisesRegex(ValueError, "Categoria de evento inválida"):
            describe_metric("lane_change_reason_ff_count")


if __name__ == "__main__":
    unittest.main()
