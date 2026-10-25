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
        selection = demand.resolve_contexts(
            day=kwargs["day"], start=kwargs["start"], sections=kwargs["sections"], variation=variation,
            master_seed=kwargs.get("master_seed"), variations=kwargs.get("variations"))
        metadata.update(
            seed=selection["seed"], variation=variation, contexts=selection["contexts"], vehicles_generated=2,
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
                        dict(demand_profile="random", spatial_scenario="local"),
                        dict(sections=57), dict(sections=2, variation=7),
                        dict(master_seed=-1), dict(master_seed=True), dict(master_seed=2**63),
                        dict(sections=2, variations=[7]), dict(sections=2, variations=[7, 26]),
                        dict(sections=2, variations=[7, True]), dict(variation=7, variations=[7]),
                        dict(demand_profile="random", master_seed=5),
                        dict(demand_profile="random", variations=[7])):
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
                      ["--sections", "2", "--variation", "7"], ["--master-seed", "-1"],
                      ["--sections", "2", "--variations", "7"],
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
                batch = self.run_batch(day=day, start=start, sections=2, variations=[7, 7])
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

    def test_master_seed_resolves_once_and_records_exact_choices_before_generation(self):
        batch = self.run_batch(day="tuesday", start="00:00", sections=7, master_seed=123456789)
        _, metrics, execution = self.results(batch)[0]
        selection = execution["context_selection"]
        chosen = [item["variation"] for item in selection["contexts"]]
        self.assertEqual(selection["master_seed"], 123456789)
        self.assertEqual(len(chosen), 7)
        self.assertTrue(all(1 <= item <= 25 for item in chosen))
        self.assertGreater(len(set(chosen)), 1)
        self.assertEqual(self.generate.call_args.kwargs["variations"], chosen)
        self.assertIsNone(self.generate.call_args.kwargs["variation"])
        self.assertEqual(metrics["seed"], selection["seed"])
        self.assertLess(metrics["seed"], 2**31)
        self.assertEqual(self.simulate.call_count, 1)
        self.assertEqual(self.simulate.call_args.kwargs["end"], 78300)

    def test_missing_master_seed_is_drawn_once_and_can_be_replayed(self):
        with patch.object(runner.secrets, "randbits", return_value=789) as entropy:
            first = self.run_batch(sections=8)
        entropy.assert_called_once_with(63)
        second = self.run_batch(sections=8, master_seed=789)
        selections = [self.results(batch)[0][2]["context_selection"] for batch in (first, second)]
        self.assertEqual(selections[0], selections[1])
        self.assertEqual(len(selections[0]["contexts"]), 8)

    def test_explicit_sequence_reproduces_master_selection_under_different_observation_profile(self):
        first = self.run_batch(day="sunday", start="21:00", sections=2, master_seed=456)
        _, first_metrics, first_execution = self.results(first)[0]
        chosen = [item["variation"] for item in first_execution["context_selection"]["contexts"]]
        second = self.run_batch(day="sunday", start="21:00", sections=2,
                                variations=chosen, metrics_profile="full")
        _, second_metrics, second_execution = self.results(second)[0]
        self.assertEqual(first_metrics["seed"], second_metrics["seed"])
        self.assertEqual(first_execution["context_selection"]["contexts"],
                         second_execution["context_selection"]["contexts"])
        self.assertEqual(first_execution["generation"]["routes_sha256"],
                         second_execution["generation"]["routes_sha256"])

    def test_long_selections_use_one_simulation_with_clearance_only_at_end(self):
        for sections, horizon in ((7, 78300), (8, 89100), (16, 175500), (56, 607500)):
            with self.subTest(sections=sections):
                previous = self.simulate.call_count
                batch = self.run_batch(day="monday", start="00:00", sections=sections, master_seed=42)
                _, metrics, execution = self.results(batch)[0]
                self.assertEqual(self.simulate.call_count, previous + 1)
                self.assertEqual(self.simulate.call_args.kwargs["end"], horizon)
                self.assertEqual(metrics["demand_duration_seconds"], sections * 10800)
                self.assertEqual(execution["generation"]["clearance_limit_seconds"], 2700)
                self.assertEqual(len(execution["context_selection"]["contexts"]), sections)

    def test_ten_multisection_epochs_have_recorded_reproducible_master_seeds(self):
        first = self.run_batch(sections=2, master_seed=31415, episodes=10)
        second = self.run_batch(sections=2, master_seed=31415, episodes=10)
        selections = [[execution["context_selection"] for _, _, execution in self.results(batch)]
                      for batch in (first, second)]
        self.assertEqual(selections[0], selections[1])
        self.assertEqual(selections[0][0]["master_seed"], 31415)
        self.assertEqual(len({item["master_seed"] for item in selections[0]}), 10)
        self.assertTrue(all(item["batch_master_seed"] == 31415 for item in selections[0]))
        self.assertEqual([item["batch_episode"] for item in selections[0]], list(range(1, 11)))

    def test_explicit_sequence_is_not_silently_changed_between_episodes(self):
        with patch.object(runner.secrets, "randbits", side_effect=AssertionError("explicit replay draws no entropy")):
            batch = self.run_batch(sections=2, variations=[25, 1], episodes=2)
        choices = [[item["variation"] for item in execution["context_selection"]["contexts"]]
                   for _, _, execution in self.results(batch)]
        self.assertEqual(choices, [[25, 1], [25, 1]])
        for _, _, execution in self.results(batch):
            self.assertIsNone(execution["context_selection"]["master_seed"])
            self.assertIsNone(execution["context_selection"]["batch_master_seed"])
            self.assertEqual(execution["context_selection"]["method"], "explicit_sequence")

    def test_master_seed_single_section_is_one_available_context_variation(self):
        batch = self.run_batch(master_seed=987654321)
        _, metrics, execution = self.results(batch)[0]
        selection = execution["context_selection"]
        self.assertEqual(len(selection["contexts"]), 1)
        chosen = selection["contexts"][0]["variation"]
        self.assertIn(chosen, range(1, 26))
        self.assertEqual(metrics["seed"], demand.effective_seed(chosen))
        self.assertEqual(self.generate.call_args.kwargs["variations"], [chosen])

    def test_multiple_section_choices_are_independent_of_signal_and_metrics_profiles(self):
        signal_selection = {"plan_id": "explicit-test-plan", "intersections": ["synthetic intersection"],
                            "tls_ids": ["synthetic_tls"], "current_tls_ids": [], "document_snapshot": {}}
        executions = []
        for signal, profile in (("current", "core"), ("settran", "full")):
            with self.subTest(signal=signal, profile=profile):
                with patch.object(runner, "_validate_signal_profile",
                                  return_value=signal_selection if signal == "settran" else None):
                    batch = self.run_batch(sections=2, master_seed=42, signal_profile=signal,
                                           metrics_profile=profile,
                                           settran_plan=signal_selection["plan_id"] if signal == "settran" else None)
                executions.append(self.results(batch)[0][2])
        self.assertEqual(executions[0]["context_selection"], executions[1]["context_selection"])
        self.assertEqual(executions[0]["generation"]["routes_sha256"],
                         executions[1]["generation"]["routes_sha256"])

    def test_free_groups_repeat_in_episode_order_with_their_own_results_and_clearance(self):
        selected = [55, 30, 0, 5, 29, 1, 4]
        choices = [4, 17, 9, 23, 2, 14, 6]
        groups = [
            ("monday", "12:00", 2, [4, 17],
             [{"day": "monday", "start": "12:00"}, {"day": "monday", "start": "15:00"}]),
            ("thursday", "15:00", 2, [9, 23],
             [{"day": "thursday", "start": "15:00"}, {"day": "thursday", "start": "18:00"}]),
            ("sunday", "21:00", 3, [2, 14, 6],
             [{"day": "sunday", "start": "21:00"}, {"day": "monday", "start": "00:00"},
              {"day": "monday", "start": "03:00"}]),
        ]
        with patch.object(runner.secrets, "randbits", side_effect=AssertionError("manual replay draws no entropy")):
            batch = self.run_batch(selected_sections=selected, consecutive_grouping_enabled=True,
                                   variations=choices, episodes=2, gui=True)
        results = self.results(batch)
        self.assertEqual(len(results), 6)
        self.assertEqual(self.generate.call_count, 6)
        self.assertEqual(self.simulate.call_count, 6)
        self.configuration.assert_called_once()
        for index, (directory, metrics, execution) in enumerate(results):
            repetition, group_index = divmod(index, 3)
            day, start, sections, variations, identities = groups[group_index]
            with self.subTest(repetition=repetition + 1, group=group_index + 1):
                self.assertTrue(directory.name.startswith(f"episode-{repetition + 1:04d}_group-{group_index + 1:02d}_"))
                self.assertEqual(directory.parent, batch)
                generated = self.generate.call_args_list[index].kwargs
                self.assertEqual({key: generated[key] for key in ("day", "start", "sections", "variations")},
                                 {"day": day, "start": start, "sections": sections, "variations": variations})
                simulated = self.simulate.call_args_list[index].kwargs
                self.assertTrue(simulated["gui"])
                self.assertEqual(simulated["end"], sections * 10800 + 2700)
                self.assertEqual(metrics["demand_duration_seconds"], sections * 10800)
                self.assertEqual(metrics["vehicles_requested"], 2)
                self.assertEqual(execution["selection_mode"], "free")
                self.assertIs(execution["consecutive_grouping_enabled"], True)
                self.assertEqual(execution["execution_type"], "consecutive_group")
                self.assertEqual(execution["selected_sections"], identities)
                self.assertEqual(execution["selection_group_index"], group_index + 1)
                self.assertEqual(execution["selection_group_count"], 3)
                context = execution["context_selection"]
                self.assertEqual(context["batch_episode"], repetition + 1)
                self.assertIsNone(context["master_seed"])
                self.assertIsNone(context["batch_master_seed"])
                self.assertEqual([item["variation"] for item in context["contexts"]], variations)

    def test_free_default_keeps_adjacent_sections_independent_including_week_boundary(self):
        batch = self.run_batch(selected_sections=[55, 1, 0], variations=[3, 11, 25])
        results = self.results(batch)
        self.assertEqual(len(results), 3)
        for index, (day, start, choice) in enumerate((
                ("monday", "00:00", 3), ("monday", "03:00", 11), ("sunday", "21:00", 25))):
            _, metrics, execution = results[index]
            self.assertEqual(execution["selection_mode"], "free")
            self.assertIs(execution["consecutive_grouping_enabled"], False)
            self.assertEqual(execution["execution_type"], "independent")
            self.assertEqual(execution["selected_sections"], [{"day": day, "start": start}])
            self.assertEqual(execution["context_selection"]["contexts"][0]["variation"], choice)
            self.assertEqual(metrics["simulation_end_requested_seconds"], 13500)
            self.assertEqual(self.generate.call_args_list[index].kwargs["sections"], 1)

    def test_free_grouping_checkbox_keeps_an_isolated_section_independent(self):
        batch = self.run_batch(selected_sections=[18], consecutive_grouping_enabled=True, variations=[8])
        _, _, execution = self.results(batch)[0]
        self.assertEqual(self.simulate.call_count, 1)
        self.assertEqual(execution["selection_mode"], "free")
        self.assertIs(execution["consecutive_grouping_enabled"], True)
        self.assertEqual(execution["execution_type"], "independent")
        self.assertEqual(execution["selected_sections"], [{"day": "wednesday", "start": "06:00"}])

    def test_free_day_and_full_week_only_form_one_process_when_grouping_is_enabled(self):
        for selected in (list(range(16, 24)), list(range(56))):
            for grouping in (False, True):
                with self.subTest(sections=len(selected), grouping=grouping):
                    with patch.object(runner, "_run_episode") as run:
                        self.run_batch(selected_sections=selected, consecutive_grouping_enabled=grouping,
                                       variations=[7] * len(selected))
                    self.assertEqual(run.call_count, 1 if grouping else len(selected))
                    options = [call.args[-1] for call in run.call_args_list]
                    contexts = [context for option in options for context in option["_context_selection"]["contexts"]]
                    self.assertEqual(len(contexts), len(selected))
                    identities = [(item["day"], item["start"]) for item in contexts]
                    self.assertEqual(len(set(identities)), len(selected))
                    first_day = "wednesday" if len(selected) == 8 else "monday"
                    self.assertEqual(identities[0], (first_day, "00:00"))
                    self.assertEqual([option["sections"] for option in options],
                                     [len(selected)] if grouping else [1] * len(selected))

    def test_invalid_free_selection_fails_before_outputs_or_entropy(self):
        invalid = [
            {"selected_sections": []}, {"selected_sections": [0, 0]},
            {"selected_sections": [-1]}, {"selected_sections": [56]},
            {"selected_sections": [True]}, {"selected_sections": ["0"]},
            {"selected_sections": "0,1"}, {"selected_sections": [0], "day": "monday"},
            {"selected_sections": [0], "start": "00:00"},
            {"selected_sections": [0], "sections": 1},
            {"selected_sections": [0], "variation": 7},
            {"selected_sections": [0, 1], "variations": [7]},
            {"selected_sections": [0, 1], "variations": [7, 8, 9]},
            {"selected_sections": [0], "variations": [0]},
            {"selected_sections": [0], "variations": [26]},
            {"selected_sections": [0], "variations": [True]},
            {"selected_sections": [0], "consecutive_grouping_enabled": "true"},
            {"selected_sections": [0], "demand_profile": "random"},
        ]
        with patch.object(runner.secrets, "randbits", side_effect=AssertionError("invalid input must not draw entropy")):
            for options in invalid:
                with self.subTest(options=options), self.assertRaises(ValueError):
                    self.run_batch(**options)
        self.assertFalse(self.output_root.exists())
        self.generate.assert_not_called()
        self.simulate.assert_not_called()
        self.configuration.assert_not_called()

    def test_free_automatic_choices_replay_across_signal_and_metrics_profiles(self):
        options = {"selected_sections": [2, 3, 20, 55, 0],
                   "consecutive_grouping_enabled": True, "episodes": 2}
        with patch.object(runner.secrets, "randbits", return_value=7823) as entropy:
            first = self.run_batch(**options)
        entropy.assert_called_once_with(63)
        signal_selection = {"plan_id": "explicit-test-plan", "intersections": ["synthetic intersection"],
                            "tls_ids": ["synthetic_tls"], "current_tls_ids": [], "document_snapshot": {}}
        with patch.object(runner, "_validate_signal_profile", return_value=signal_selection), \
                patch.object(runner.secrets, "randbits", side_effect=AssertionError("replay draws no entropy")):
            second = self.run_batch(**options, master_seed=7823, signal_profile="settran", metrics_profile="full",
                                    settran_plan=signal_selection["plan_id"])
        self.assertNotEqual(first, second)
        first_results, second_results = self.results(first), self.results(second)
        self.assertEqual(len(first_results), 6)
        self.assertEqual(len(second_results), 6)
        selections = []
        for (_, first_metrics, original), (_, second_metrics, replayed) in zip(first_results, second_results):
            self.assertEqual(original["context_selection"], replayed["context_selection"])
            self.assertEqual(original["selected_sections"], replayed["selected_sections"])
            self.assertEqual(original["generation"]["routes_sha256"], replayed["generation"]["routes_sha256"])
            self.assertEqual(first_metrics["seed"], second_metrics["seed"])
            self.assertEqual(first_metrics["simulation_end_requested_seconds"],
                             second_metrics["simulation_end_requested_seconds"])
            context = original["context_selection"]
            self.assertEqual(context["batch_master_seed"], 7823)
            self.assertTrue(all(1 <= item["variation"] <= 25 for item in context["contexts"]))
            selections.append(context)
        self.assertEqual([item["batch_episode"] for item in selections], [1, 1, 1, 2, 2, 2])
        self.assertEqual(len({item["master_seed"] for item in selections}), 6)

    def test_consecutive_mode_records_selection_without_changing_contexts(self):
        for sections in (1, 2):
            with self.subTest(sections=sections):
                batch = self.run_batch(day="sunday", start="21:00", sections=sections,
                                       variations=[7] * sections)
                _, _, execution = self.results(batch)[0]
                self.assertEqual(execution["selection_mode"], "consecutive")
                self.assertIs(execution["consecutive_grouping_enabled"], True)
                self.assertEqual(execution["execution_type"], "independent" if sections == 1 else "consecutive_group")
                identities = [{"day": item["day"], "start": item["start"]}
                              for item in execution["context_selection"]["contexts"]]
                self.assertEqual(execution["selected_sections"], identities)

    def test_resolved_master_and_sequence_survive_generation_failure(self):
        self.generate.side_effect = ValueError("native routing unavailable")
        with self.assertRaisesRegex(ValueError, "native routing unavailable"):
            self.run_batch(sections=2, master_seed=123)
        path, = self.output_dir.glob("*/*/metrics.json")
        document = json.loads(path.read_text())
        selection = document["execution"]["context_selection"]
        self.assertEqual(selection["master_seed"], 123)
        self.assertEqual(len(selection["contexts"]), 2)
        self.assertEqual(document["execution"]["status"], "failed")

    def test_cli_dispatches_master_and_explicit_sequence(self):
        with patch.object(runner, "run_episodes") as run:
            code = runner.main(["--demand-profile", "metasettran", "--day", "friday",
                                "--start", "21:00", "--sections", "2", "--master-seed", "123",
                                "--variations", "4", "17"])
        self.assertEqual(code, 0)
        self.assertEqual(run.call_args.kwargs["master_seed"], 123)
        self.assertEqual(run.call_args.kwargs["variations"], [4, 17])

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
