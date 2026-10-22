"""Integração do contexto MetaSettran ao executor e à retenção existentes."""

from contextlib import redirect_stderr
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from SistemaDeSemaforos.demand import metasettran_demand_generator as demand
from SistemaDeSemaforos.metrics import episode_metrics_collector as collector
from SistemaDeSemaforos.simulation import episode_runner as runner


class MetaSettranRunnerTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.net = self.directory / "network.net.xml"
        self.net.write_text("<net />", encoding="utf-8")
        self.output_root = self.directory / "outputs"
        self.output_dir = self.output_root / "outputs-metasettran"
        self.start_patch(patch.object(runner, "OUTPUT_ROOT", self.output_root))
        self.start_patch(patch.object(runner.shutil, "which", return_value="/usr/bin/sumo"))
        self.configuration = self.start_patch(patch.object(runner, "read_sumo_configuration", return_value={
            "sumo_version": "SUMO synthetic test", "sumo_defaults": {"seed": "23423", "step-length": "1"},
        }))
        self.generate = self.start_patch(patch.object(demand, "generate_metasettran_demand",
                                                     side_effect=self.fake_generate))
        self.simulate = self.start_patch(patch.object(runner, "run_simulation", side_effect=self.fake_simulate))
        self.collect = self.start_patch(patch.object(collector, "collect_episode", side_effect=self.fake_collect))
        self.validate = self.start_patch(patch.object(collector, "collect_metasettran_validation",
                                                     side_effect=self.fake_validation))

    def start_patch(self, patcher):
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        return mocked

    def fake_generate(self, *, output_dir, variation, metadata, **kwargs):
        route = output_dir / "metasettran.rou.xml"
        duration = 10800.0 * kwargs.get("sections", 1)
        route.write_text('<routes><vehicle id="a" depart="0.5"/>'
                         f'<vehicle id="b" depart="{duration - 0.5}"/></routes>', encoding="utf-8")
        (output_dir / "metasettran.trips.xml").write_text("<routes />", encoding="utf-8")
        metadata.update(
            seed=demand.effective_seed(variation), variation=variation, vehicles_generated=2,
            trips_generated=2, duration=duration, duration_seconds=0.1, routes_file=str(route),
            routes_sha256=hashlib.sha256(route.read_bytes()).hexdigest(),
            spatial_model={"sensors": [{"candidates": [{"edge": "before"}, {"edge": "after"}]}]},
        )
        return route

    def fake_simulate(self, *, recording_dir, metadata, **kwargs):
        metadata.update(duration_seconds=0.2, seed=23423, step_length=1.0,
                        configuration_time_seconds=0.01)
        raw = recording_dir / "raw"
        raw.mkdir()
        for name in ("summary.xml.gz", "trips.xml.gz", "statistics.xml", "queues.xml.gz",
                     "metasettran_counts.xml.gz"):
            (raw / name).write_bytes(b"synthetic observation")
        (recording_dir / "sumo.log").write_text("synthetic native log", encoding="utf-8")

    def fake_collect(self, raw, net, profile="core"):
        return {"metrics": {"vehicles_completed": 2, "simulation_duration_seconds": 13500.0,
                            "vehicles_inserted": 2, "teleports": 0},
                "entities": {"vehicles": {"a": {}, "b": {}}} if profile == "full" else {}}

    def fake_validation(self, directory, generation, *, summary_metrics, vehicles=None):
        if vehicles is not None:
            vehicles["a"]["metasettran_trip_status"] = "completed_without_teleport"
        return {"metrics": {"vehicles_completed_without_teleport": 2, "vehicles_with_teleport": 0},
                "status": "conditional_on_unconfirmed_sensor_mapping", "ready_for_weekly_expansion": False}

    def run_batch(self, **kwargs):
        options = {"net_file": self.net, "output_dir": self.output_dir, "demand_profile": "metasettran"}
        options.update(kwargs)
        return runner.run_episodes(**options)

    def results(self, batch):
        results = []
        for path in sorted(batch.glob("*/metrics.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            metrics = {item["metric_name"]: item["value"] for item in document["metrics"]}
            results.append((path.parent, metrics, document["execution"]))
        return results

    def test_invalid_contexts_and_random_flags_fail_before_creating_outputs(self):
        for options in (dict(day="unknown"), dict(day=""), dict(start="18:30"), dict(start=""), dict(sections=0),
                        dict(variation=26), dict(variation=24, episodes=3), dict(drain_limit=-1),
                        dict(drain_limit=0.5), dict(drain_limit=float("nan")), dict(drain_limit=float("inf")),
                        dict(duration=10800), dict(period=2), dict(end=13500),
                        dict(demand_profile="random", day="tuesday"), dict(spatial_scenario="unknown"),
                        dict(demand_profile="random", spatial_scenario="local")):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.run_batch(**options)
        self.assertFalse(self.output_root.exists())
        self.generate.assert_not_called()
        self.simulate.assert_not_called()
        self.configuration.assert_not_called()

    def test_consecutive_episodes_use_variations_without_random_seed_or_wrap(self):
        with patch.object(runner.random, "randint", side_effect=AssertionError("MetaSettran não sorteia seed global")):
            batch = self.run_batch(episodes=3, variation=23)
        self.assertEqual([call.kwargs["variation"] for call in self.generate.call_args_list], [23, 24, 25])
        self.configuration.assert_called_once()
        results = self.results(batch)
        self.assertEqual(len(results), 3)
        for index, (_, metrics, execution) in enumerate(results, 23):
            self.assertEqual(metrics["seed"], demand.effective_seed(index))
            self.assertEqual(execution["generation"]["variation"], index)
            self.assertEqual(metrics["demand_model"], "metasettran")
            self.assertNotIn("demand_period_seconds", metrics)
            self.assertEqual(metrics["vehicles_requested"], 2)

    def test_clearance_changes_only_horizon_and_never_departure_window(self):
        for drain, expected_end in ((None, 13500.0), (900.0, 11700.0), (0.0, 10800.0)):
            with self.subTest(drain=drain):
                batch = self.run_batch(drain_limit=drain)
                arguments = self.simulate.call_args.kwargs
                self.assertEqual(arguments["end"], expected_end)
                self.assertEqual(arguments["metrics_profile"], "core")
                self.assertEqual(arguments["signal_profile"], "current")
                self.assertTrue(arguments["track_teleported_vehicles"])
                self.assertEqual(arguments["demand_observation_edges"], ("after", "before"))
                _, metrics, execution = self.results(batch)[0]
                self.assertEqual(metrics["demand_duration_seconds"], 10800.0)
                self.assertEqual(metrics["simulation_end_requested_seconds"], expected_end)
                self.assertEqual(execution["generation"]["clearance_limit_seconds"], expected_end - 10800)
                self.assertNotIn("duration", self.generate.call_args.kwargs)
                self.assertNotIn("period", self.generate.call_args.kwargs)

    def test_signal_and_metrics_axes_leave_demand_selection_and_artifact_unchanged(self):
        selection = {"plan_id": "explicit-test-plan", "intersections": ["synthetic intersection"],
                     "tls_ids": ["synthetic_tls"], "current_tls_ids": [], "document_snapshot": {}}
        hashes = []
        for signal, profile in (("current", "core"), ("settran", "full")):
            with self.subTest(signal=signal, profile=profile):
                with patch.object(runner, "_validate_signal_profile",
                                  return_value=selection if signal == "settran" else None):
                    batch = self.run_batch(variation=7, signal_profile=signal, metrics_profile=profile,
                                           settran_plan=selection["plan_id"] if signal == "settran" else None)
                arguments = self.simulate.call_args.kwargs
                self.assertEqual(arguments["signal_profile"], signal)
                self.assertEqual(arguments["metrics_profile"], profile)
                if signal == "settran":
                    self.assertEqual(arguments["settran_plan"], "explicit-test-plan")
                    self.assertEqual(arguments["settran_intersections"], ["synthetic intersection"])
                else:
                    self.assertNotIn("settran_plan", arguments)
                generated = self.generate.call_args.kwargs
                self.assertEqual({key: generated[key] for key in ("day", "start", "sections", "variation")},
                                 {"day": "tuesday", "start": "15:00", "sections": 1, "variation": 7})
                self.assertNotIn("signal_profile", generated)
                self.assertNotIn("metrics_profile", generated)
                _, _, execution = self.results(batch)[0]
                hashes.append(execution["generation"]["routes_sha256"])
        self.assertEqual(hashes[0], hashes[1])

    def test_current_does_not_require_settran_evidence_or_select_an_automatic_plan(self):
        with patch.object(runner, "SETTRAN_PROGRAMS_FILE", self.directory / "missing_settran.json"):
            self.run_batch()
            with self.assertRaisesRegex(ValueError, "explicitamente"):
                self.run_batch(signal_profile="settran")
        self.assertEqual(self.generate.call_count, 1)

    def test_core_and_full_retain_reusable_route_and_log_but_apply_existing_raw_policy(self):
        for profile in ("core", "full"):
            with self.subTest(profile=profile):
                batch = self.run_batch(metrics_profile=profile)
                directory, metrics, execution = self.results(batch)[0]
                retained = directory / "metasettran.rou.xml"
                self.assertTrue(retained.is_file())
                self.assertEqual(execution["generation"]["routes_file"], str(retained))
                self.assertEqual(self.simulate.call_args.kwargs["demand_file"], retained)
                self.assertTrue((directory / "sumo.log").is_file())
                self.assertFalse((directory / "inputs").exists())
                self.assertEqual((directory / "raw" / "metasettran_counts.xml.gz").is_file(), profile == "full")
                self.assertEqual((directory / "entities.json.gz").is_file(), profile == "full")
                self.assertEqual(metrics["vehicles_completed_without_teleport"], 2)
                self.assertFalse(execution["demand_validation"]["ready_for_weekly_expansion"])
                self.assertEqual(self.validate.call_args.kwargs["vehicles"] is not None, profile == "full")

    def test_validation_failure_retains_route_raw_and_inputs_for_investigation(self):
        self.validate.side_effect = ValueError("teleport log incomplete")
        with self.assertRaisesRegex(ValueError, "teleport log incomplete"):
            self.run_batch()
        paths = list(self.output_dir.glob("*/*/metrics.json"))
        self.assertEqual(len(paths), 1)
        directory = paths[0].parent
        self.assertTrue((directory / "metasettran.rou.xml").is_file())
        self.assertTrue((directory / "inputs" / "metasettran.trips.xml").is_file())
        self.assertTrue((directory / "raw" / "metasettran_counts.xml.gz").is_file())
        document = json.loads(paths[0].read_text())
        self.assertEqual(document["execution"]["status"], "failed")

    def test_cli_rejects_ambiguous_contexts_and_conflicting_window_flags(self):
        base = ["--demand-profile", "metasettran", "--net-file", str(self.net),
                "--output-dir", str(self.output_dir)]
        for extra in (["--day", "tomorrow"], ["--sections", "0"], ["--variation", "25", "--episodes", "2"],
                      ["--duration=7200"], ["--period", "1.5"], ["--end", "13500"]):
            with self.subTest(extra=extra), redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(runner.main(base + extra), 1)
                self.assertIn("Erro ao executar", errors.getvalue())
        self.assertFalse(self.output_root.exists())
        self.generate.assert_not_called()

    def test_contiguous_sections_and_midnight_use_one_process_and_one_clearance(self):
        for day, start in (("tuesday", "15:00"), ("friday", "21:00"), ("sunday", "21:00")):
            with self.subTest(day=day):
                previous = self.simulate.call_count
                batch = self.run_batch(day=day, start=start, sections=2, variation=7)
                self.assertEqual(self.simulate.call_count, previous + 1)
                self.assertEqual(self.simulate.call_args.kwargs["end"], 24300)
                _, metrics, execution = self.results(batch)[0]
                self.assertEqual(metrics["demand_duration_seconds"], 21600)
                self.assertEqual(metrics["demand_last_departure_seconds"], 21599.5)
                self.assertEqual(execution["generation"]["clearance_limit_seconds"], 2700)

    def test_ten_epochs_keep_ten_distinct_variations(self):
        batch = self.run_batch(episodes=10, variation=1)
        results = self.results(batch)
        self.assertEqual(len(results), 10)
        self.assertEqual([e["generation"]["variation"] for _, _, e in results], list(range(1, 11)))
        self.assertEqual(len({m["seed"] for _, m, _ in results}), 10)

    def test_cli_dispatches_independent_demand_signal_and_metrics_options(self):
        with patch.object(runner, "run_episodes") as run:
            code = runner.main(["--demand-profile", "metasettran", "--day", "tuesday",
                                "--start", "15:00", "--sections", "1", "--variation", "7",
                                "--drain-limit", "1200", "--signal-profile", "current",
                                "--spatial-scenario", "regional-integrated",
                                "--metrics-profile", "full"])
        self.assertEqual(code, 0)
        options = run.call_args.kwargs
        self.assertEqual(options["demand_profile"], "metasettran")
        self.assertEqual(options["signal_profile"], "current")
        self.assertEqual(options["metrics_profile"], "full")
        self.assertEqual(options["variation"], 7)
        self.assertEqual(options["drain_limit"], 1200)
        self.assertEqual(options["spatial_scenario"], "regional-integrated")


if __name__ == "__main__":
    unittest.main()
