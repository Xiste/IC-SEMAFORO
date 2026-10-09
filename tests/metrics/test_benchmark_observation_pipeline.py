"""Confere comparação científica e retenção do benchmark sem executar SUMO."""

from contextlib import redirect_stdout
import gzip
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import benchmark_observation_pipeline as benchmark


class BenchmarkTests(unittest.TestCase):
    def test_signature_ignores_only_devices_and_xml_order(self):
        with TemporaryDirectory() as temporary:
            paths = [Path(temporary) / f"{i}.xml.gz" for i in range(3)]
            documents = [
                '<tripinfos><tripinfo id="b" duration="2" devices="tripinfo"/>'
                '<tripinfo id="a" duration="1"/></tripinfos>',
                '<tripinfos><tripinfo duration="1" id="a"/>'
                '<tripinfo devices="emissions tripinfo" duration="2" id="b"/></tripinfos>',
                '<tripinfos><tripinfo id="b" duration="3"/>'
                '<tripinfo id="a" duration="1"/></tripinfos>',
            ]
            for path, document in zip(paths, documents):
                with gzip.open(path, "wt") as stream:
                    stream.write(document)
            first, second, changed = map(benchmark.trip_signature, paths)
            self.assertEqual(first, second)
            self.assertNotEqual(first, changed)
            self.assertEqual(first[0], 2)

    def test_comparison_excludes_observer_diagnostics_but_requires_every_core_result(self):
        core = {"vehicles_completed": 4, "teleports": 0, "simulation_duration_seconds": 7205.0,
                "metrics_profile": "core", "collection_trips_time_seconds": 1.0}
        full = {**core, "metrics_profile": "full", "collection_trips_time_seconds": 3.0,
                "emissions": 7}
        result = benchmark.compare_traffic_metrics(core, full)
        self.assertTrue(result["equal"])
        self.assertEqual(result["count"], 3)
        del full["teleports"]
        self.assertFalse(benchmark.compare_traffic_metrics(core, full)["equal"])
        full["teleports"] = 1
        self.assertEqual(benchmark.compare_traffic_metrics(core, full)["differences"],
                         {"teleports": {"core": 0, "full": 1}})
        self.assertFalse(benchmark.compare_traffic_metrics({}, {})["equal"])

    def test_profile_retention_and_timings_keep_simulated_time_separate(self):
        def fake_run(**arguments):
            destination = arguments["recording_dir"]
            (destination / "raw").mkdir()
            (destination / "sumo.log").write_text("complete")
            for name in ("summary.xml.gz", "statistics.xml", "queues.xml.gz"):
                (destination / "raw" / name).write_bytes(b"xml")
            with gzip.open(destination / "raw/trips.xml.gz", "wt") as stream:
                stream.write('<tripinfos><tripinfo id="one" duration="7200"/></tripinfos>')
            arguments["metadata"].update(duration_seconds=0.1, configuration_time_seconds=0.01)
            self.assertNotIn("end", arguments)

        metrics = {"simulation_duration_seconds": 7300.0, "vehicles_completed": 1}
        entities = {"vehicles": {"one": {"trip_duration": 7200.0}}}
        with TemporaryDirectory() as temporary:
            for profile in ("core", "full"):
                with self.subTest(profile=profile):
                    directory = Path(temporary) / profile
                    with patch.object(benchmark, "run_simulation", side_effect=fake_run), \
                            patch.object(benchmark, "collect_episode", return_value={
                                "metrics": metrics, "entities": entities if profile == "full" else {}}):
                        result = benchmark._measure_profile(directory, profile, "sumo", Path("net"),
                                                            Path("routes"), {})
                    self.assertEqual(result["simulation_duration_seconds"], 7300.0)
                    self.assertEqual(result["simulation_seconds"], 0.1)
                    self.assertEqual(result["trips"], 1)
                    self.assertEqual((directory / "raw").exists(), profile == "full")
                    self.assertEqual((directory / "entities.json.gz").exists(), profile == "full")
                    observation = json.loads((directory / "observation.json").read_text())
                    self.assertEqual(observation["metrics"], metrics)
                    self.assertEqual(result["produced"]["files"] - result["retained"]["files"],
                                     4 if profile == "core" else 0)
                    self.assertEqual(result["raw_produced"]["files"], 4)

    def test_failed_core_collection_preserves_raw_evidence(self):
        def fake_run(**arguments):
            raw = arguments["recording_dir"] / "raw"
            raw.mkdir()
            (raw / "trips.xml.gz").write_bytes(b"incomplete")

        with TemporaryDirectory() as temporary:
            destination = Path(temporary) / "core"
            with patch.object(benchmark, "run_simulation", side_effect=fake_run), \
                    patch.object(benchmark, "collect_episode", side_effect=ValueError("incomplete")):
                with self.assertRaisesRegex(ValueError, "incomplete"):
                    benchmark._measure_profile(destination, "core", "sumo", Path("net"), Path("routes"), {})
            self.assertEqual((destination / "raw/trips.xml.gz").read_bytes(), b"incomplete")

    def test_completed_benchmark_saves_data_without_inputs_snapshots_or_terminal_summary(self):
        def generate(**arguments):
            directory = arguments["output_dir"]
            routes = directory / "random.rou.xml"
            routes.write_text("<routes />")
            arguments["metadata"].update(seed=arguments["seed"], vehicles_generated=1)
            return routes

        def measure(destination, profile, binary, network, routes, defaults):
            self.assertEqual(network, original_network)
            self.assertEqual(defaults, {"seed": "23423", "step-length": "1"})
            self.assertTrue(routes.is_file())
            destination.mkdir()
            return {"profile": profile, "trip_signature": "same-trips", "total_seconds": 1.0,
                    "retained": {"bytes": 30}, "traffic_metrics": {
                        "simulation_duration_seconds": 7300.0, "vehicles_completed": 1}}

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            original_network = root / "original.net.xml"
            original_network.write_text("<net />")
            configuration = {"sumo_version": "test", "sumo_defaults": {
                "seed": "23423", "step-length": "1"}}
            with patch.object(benchmark, "ROOT", root), \
                    patch.object(benchmark, "DEFAULT_NET_FILE", original_network), \
                    patch.object(benchmark.shutil, "which", return_value="sumo"), \
                    patch.object(benchmark, "read_sumo_configuration", return_value=configuration), \
                    patch.object(benchmark, "generate_random_demand", side_effect=generate), \
                    patch.object(benchmark, "_isolated_measurement", side_effect=measure), \
                    redirect_stdout(io.StringIO()) as stdout:
                result = benchmark.benchmark(duration=7200, period=1.5, seed=17, repetitions=1)
            report = json.loads(result.read_text())
            self.assertEqual(report["status"], "completed")
            self.assertEqual(report["seed"], 17)
            self.assertEqual(report["parameters"]["demand_duration_seconds"], 7200)
            self.assertEqual(report["configuration"], configuration)
            self.assertTrue(report["metric_comparisons"][0]["equal"])
            self.assertFalse((result.parent / "inputs").exists())
            self.assertFalse((root / "outputs/baselines").exists())
            self.assertNotIn("baseline", report)
            self.assertNotIn("inputs", report)
            self.assertEqual(original_network.read_text(), "<net />")
            self.assertEqual(stdout.getvalue(), "")

    def test_output_directory_cannot_escape_outputs_or_replace_existing_folder(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(benchmark, "ROOT", root), patch.object(benchmark.shutil, "which", return_value="sumo"):
                for directory in (root, root / "outputs", root / "outputs" / ".." / "outside"):
                    with self.subTest(directory=directory), self.assertRaises(ValueError):
                        benchmark.benchmark(output_dir=directory)
                (root / "outputs/existing").mkdir(parents=True)
                with self.assertRaises(FileExistsError):
                    benchmark.benchmark(output_dir=root / "outputs/existing")


if __name__ == "__main__":
    unittest.main()
