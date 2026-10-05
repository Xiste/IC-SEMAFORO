"""Testa a execução do SUMO e a sequência de episódios random.

As entradas são arquivos temporários e os processos externos são simulados.
O arquivo verifica os comandos construídos e uma demanda nova por episódio.
"""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from SistemaDeSemaforos.simulation import episode_runner as simulation


def option_value(command, option):
    """Retorna o valor que aparece depois de uma opção do comando."""
    return command[command.index(option) + 1]


class RunSimulationTests(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.directory = Path(temporary_directory.name)
        self.net_file = self.directory / "network.net.xml"
        self.demand_file = self.directory / "demand.rou.xml"
        self.net_file.write_text("<net />", encoding="utf-8")
        self.demand_file.write_text("<routes />", encoding="utf-8")

    @patch.object(simulation.subprocess, "run")
    @patch.object(simulation.shutil, "which", return_value="/usr/bin/sumo")
    def test_explicit_current_keeps_the_default_sumo_command(self, which, run):
        parameters = dict(net_file=self.net_file, demand_file=self.demand_file, end=60)
        source = Mock()
        source.read_text.side_effect = AssertionError("current não deve carregar SETTRAN")
        with patch.object(simulation, "SETTRAN_PROGRAMS_FILE", source):
            simulation.run_simulation(**parameters)
            default = run.call_args
            simulation.run_simulation(**parameters, signal_profile="current")
        self.assertEqual(run.call_args, default)
        source.read_text.assert_not_called()

    @patch.object(simulation.subprocess, "run")
    def test_settran_or_unknown_profile_never_starts_sumo(self, run):
        for profile, plan in (("settran", None), ("settran", "1"), ("settran", "2"),
                              ("current", "2"), ("unknown", None)):
            with self.subTest(profile=profile, plan=plan), self.assertRaises(ValueError):
                simulation.run_simulation(net_file=self.net_file, demand_file=self.demand_file,
                                          signal_profile=profile, settran_plan=plan)
        run.assert_not_called()

    @patch.object(simulation.subprocess, "run")
    @patch.object(simulation.shutil, "which", return_value="/usr/bin/sumo")
    def test_headless_command_uses_network_and_demand(self, which, run):
        simulation.run_simulation(
            net_file=self.net_file,
            demand_file=self.demand_file,
        )

        which.assert_called_once_with("sumo")
        command = run.call_args.args[0]
        self.assertEqual(command[0], "/usr/bin/sumo")
        self.assertEqual(option_value(command, "--net-file"), str(self.net_file))
        self.assertEqual(
            option_value(command, "--route-files"), str(self.demand_file)
        )
        self.assertNotIn("--end", command)
        self.assertNotIn("--start", command)
        self.assertEqual(option_value(command, "--aggregate-warnings"), "5")
        self.assertNotIn("--duration-log.statistics", command)
        self.assertTrue(run.call_args.kwargs["check"])

    @patch.object(simulation.subprocess, "run")
    @patch.object(simulation.shutil, "which", return_value="/usr/bin/sumo-gui")
    def test_gui_starts_closes_and_respects_end(self, which, run):
        simulation.run_simulation(
            net_file=self.net_file,
            demand_file=self.demand_file,
            gui=True,
            end=60,
        )

        which.assert_called_once_with("sumo-gui")
        command = run.call_args.args[0]
        self.assertIn("--start", command)
        self.assertIn("--quit-on-end", command)
        self.assertEqual(option_value(command, "--end"), "60")

    @patch.object(simulation.subprocess, "run")
    def test_invalid_inputs_do_not_start_sumo(self, run):
        with self.assertRaises(ValueError):
            simulation.run_simulation(
                net_file=self.net_file,
                demand_file=self.demand_file,
                end=0,
            )
        with self.assertRaises(FileNotFoundError):
            simulation.run_simulation(
                net_file=self.directory / "missing.net.xml",
                demand_file=self.demand_file,
            )
        with self.assertRaises(FileNotFoundError):
            simulation.run_simulation(
                net_file=self.net_file,
                demand_file=self.directory / "missing.rou.xml",
            )

        run.assert_not_called()

    @patch.object(simulation.subprocess, "run")
    @patch.object(simulation.shutil, "which", return_value=None)
    def test_missing_sumo_binary_does_not_start_process(self, which, run):
        with self.assertRaisesRegex(FileNotFoundError, "sumo"):
            simulation.run_simulation(
                net_file=self.net_file,
                demand_file=self.demand_file,
            )

        which.assert_called_once_with("sumo")
        run.assert_not_called()

    def test_recording_preserves_run_options_and_stores_sumo_configuration(self):
        binary = self.directory / "sumo-gui"
        binary.write_text("SUMO simulado", encoding="utf-8")
        recording = self.directory / "episode"
        (recording / "inputs").mkdir(parents=True)
        metadata = {}
        commands = []

        def fake_sumo(command, **kwargs):
            commands.append(command)
            if "--save-template" in command:
                Path(option_value(command, "--save-template")).write_text(
                    '<configuration><random_number><seed value="23423" />'
                    '</random_number><time><step-length value="1" />'
                    '</time></configuration>', encoding="utf-8",
                )
            if "--save-configuration" in command:
                Path(option_value(command, "--save-configuration")).write_text(
                    '<configuration><output><precision value="8" /></output></configuration>',
                    encoding="utf-8",
                )
            return subprocess.CompletedProcess(command, 0, stdout="SUMO test version\n")

        with patch.object(simulation.shutil, "which", return_value=str(binary)):
            with patch.object(simulation.subprocess, "run", side_effect=fake_sumo):
                simulation.run_simulation(
                    net_file=self.net_file, demand_file=self.demand_file,
                    gui=True, end=60, recording_dir=recording, metadata=metadata,
                    baseline={"manifest": {"sumo_defaults": {"seed": "23423", "step-length": "1"}}},
                )

        command = metadata["command"]
        self.assertEqual(commands[-1], command)
        self.assertEqual(len(commands), 2)
        self.assertEqual(option_value(command, "--net-file"), str(self.net_file))
        self.assertEqual(option_value(command, "--route-files"), str(self.demand_file))
        self.assertEqual(option_value(command, "--end"), "60")
        self.assertIn("--start", command)
        self.assertIn("--quit-on-end", command)
        self.assertNotIn("--seed", command)
        self.assertEqual(metadata["seed"], 23423)
        self.assertEqual(metadata["step_length"], 1.0)
        self.assertEqual(metadata["configured_options"]["precision"], "8")
        self.assertGreaterEqual(metadata["duration_seconds"], 0)
        self.assertGreaterEqual(metadata["configuration_time_seconds"], 0)
        self.assertNotIn("--fcd-output", command)
        self.assertTrue((recording / "inputs" / "observations.add.xml").is_file())
        self.assertTrue((recording / "sumo.log").is_file())


class RandomEpisodeTests(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.directory = Path(temporary_directory.name)
        self.net_file = self.directory / "network.net.xml"
        self.net_file.write_text("<net />", encoding="utf-8")
        self.output_root = self.directory / "outputs"
        self.output_dir = self.output_root / "outputs-random"
        self.workflow = []

        self.collector = ModuleType("SistemaDeSemaforos.metrics.episode_metrics_collector")
        self.collector.collect_episode = Mock(side_effect=self.collect)
        self.start_patch(patch.dict(sys.modules, {self.collector.__name__: self.collector}))
        self.start_patch(patch.object(simulation, "OUTPUT_ROOT", self.output_root))
        baseline_dir = self.output_root / "baselines" / "fixture"
        baseline_dir.mkdir(parents=True)
        (baseline_dir / "network.net.xml").write_bytes(self.net_file.read_bytes())
        (baseline_dir / "baseline.json").write_text('{"baseline_id": "fixture"}')
        self.baseline_mock = self.start_patch(patch.object(
            simulation, "prepare_baseline", return_value={
                "directory": baseline_dir, "manifest": {"baseline_id": "fixture"}}))
        self.generate_mock = self.start_patch(
            patch.object(simulation, "generate_random_demand", side_effect=self.generate)
        )
        self.run_mock = self.start_patch(
            patch.object(simulation, "run_simulation", side_effect=self.simulate)
        )
        self.start_patch(patch.object(
            simulation.subprocess, "run",
            return_value=subprocess.CompletedProcess(["git"], 0, stdout="test_commit\n"),
        ))

    def start_patch(self, patcher):
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        return mocked

    def generate(self, *, output_dir, seed, metadata, **parameters):
        self.workflow.append("generate")
        metadata.update(seed=seed, trips_generated=2, vehicles_generated=2, duration_seconds=0.1)
        routes = output_dir / "random.rou.xml"
        routes.write_text("<routes />", encoding="utf-8")
        (output_dir / "random.trips.xml").write_text("<routes />", encoding="utf-8")
        return routes

    def simulate(self, *, metadata, **parameters):
        self.workflow.append("run")
        metadata.update(duration_seconds=0.2, seed=23423, step_length=1.0,
                        configuration_time_seconds=0.01)

    def collect(self, raw, net_file, profile="core"):
        self.workflow.append("collect")
        return {
            "metrics": {"vehicles_completed": 2, "network_mean_speed_m_s_mean": 8.25},
            "entities": {"lanes": {"via_ação_0": {"queue_length_max": 1}}},
        }

    def episode_results(self, directory):
        document = json.loads((directory / "metrics.json").read_text(encoding="utf-8"))
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        records = {item["metric_name"]: item for item in document["metrics"]}
        return records, manifest

    def run_episodes(self, **parameters):
        arguments = {"net_file": self.net_file, "output_dir": self.output_dir}
        arguments.update(parameters)
        with redirect_stdout(io.StringIO()):
            simulation.run_random_episodes(**arguments)

    def test_each_episode_generates_runs_and_collects_in_order(self):
        with patch.object(simulation.random, "randint", side_effect=[17, 42]) as randint:
            self.run_episodes(episodes=2, gui=True, duration=120, period=2, end=60)

        self.assertEqual(self.workflow, ["generate", "run", "collect"] * 2)
        self.assertEqual(randint.call_count, 2)
        self.baseline_mock.assert_called_once()
        self.assertEqual(len(list(self.output_dir.iterdir())), 2)
        for index, (generation, run) in enumerate(zip(
            self.generate_mock.call_args_list, self.run_mock.call_args_list
        )):
            generated = generation.kwargs
            executed = run.kwargs
            episode_dir = generated["output_dir"].parent
            self.assertEqual(generated["seed"], (17, 42)[index])
            self.assertEqual(generated["duration"], 120)
            self.assertEqual(generated["period"], 2)
            self.assertEqual(executed["gui"], True)
            self.assertEqual(executed["end"], 60)
            self.assertEqual(executed["net_file"], generated["net_file"])
            self.assertEqual(executed["demand_file"], generated["output_dir"] / "random.rou.xml")
            self.assertEqual(executed["recording_dir"], episode_dir)
            self.assertTrue(episode_dir.is_relative_to(self.output_dir))
            self.assertEqual(generated["net_file"].read_bytes(), self.net_file.read_bytes())
            records, manifest = self.episode_results(episode_dir)
            for name, expected_type, value in (
                ("seed", "int", (17, 42)[index]), ("demand_model", "string", "random"),
                ("gui", "bool", True), ("demand_duration_seconds", "float", 120.0),
                ("demand_period_seconds", "float", 2.0),
                ("simulation_end_requested_seconds", "float", 60.0),
                ("vehicles_requested", "int", 60), ("vehicles_generated", "int", 2),
                ("vehicles_completed", "int", 2), ("network_mean_speed_m_s_mean", "float", 8.25),
                ("status", "string", "completed"),
            ):
                self.assertEqual({key: records[name][key] for key in ("metric_name", "data_type", "value")}, {
                    "metric_name": name, "data_type": expected_type, "value": value,
                })
            self.assertGreater(records["execution_time_seconds"]["value"], 0)
            self.assertEqual(manifest["seed"], (17, 42)[index])
            self.assertEqual(manifest["signal_profile"], "current")
            self.assertEqual(manifest["status"], "completed")
            self.assertIn("started_at_utc", manifest)
            self.assertIn("finished_at_utc", manifest)
            self.assertNotIn("inputs/network.net.xml", manifest["files"])
            self.assertEqual(manifest["baseline"]["id"], "fixture")
            self.assertEqual(manifest["collection"]["profile"], "core")
            self.assertIn("inputs/random.rou.xml", manifest["files"])

    def test_same_seed_and_timestamp_never_overwrite_previous_episode(self):
        fixed_time = datetime(2026, 9, 25, 20, 0, tzinfo=timezone.utc)
        with patch.object(simulation, "datetime") as clock:
            clock.now.return_value = fixed_time
            with patch.object(simulation.random, "randint", return_value=17):
                with patch.object(simulation, "uuid4", side_effect=[
                    SimpleNamespace(hex="11111111aaaaaaaa"),
                    SimpleNamespace(hex="22222222bbbbbbbb"),
                ]):
                    self.run_episodes()
                    first = next(self.output_dir.iterdir())
                    previous_metrics = (first / "metrics.json").read_bytes()
                    previous_manifest = (first / "manifest.json").read_bytes()
                    self.run_episodes()

        self.assertEqual(len(list(self.output_dir.iterdir())), 2)
        self.assertEqual((first / "metrics.json").read_bytes(), previous_metrics)
        self.assertEqual((first / "manifest.json").read_bytes(), previous_manifest)

    def test_invalid_batch_parameters_stop_before_generation(self):
        invalid_values = {
            "episodes": (0, -1, 1.5, True),
            "end": (0, -1, float("inf"), float("nan")),
            "duration": (0, -1, float("inf"), float("nan")),
            "period": (0, -1, float("inf"), float("nan")),
            "metrics_profile": ("unknown", ""),
            "signal_profile": ("unknown", "", "settran"),
            "settran_plan": ("2", "", 2, False),
        }
        for name, values in invalid_values.items():
            for value in values:
                with self.subTest(parameter=name, value=value):
                    with self.assertRaises(ValueError):
                        self.run_episodes(**{name: value})

        self.generate_mock.assert_not_called()
        self.run_mock.assert_not_called()

    def test_settran_fails_before_seed_baseline_or_episode_creation(self):
        with patch.object(simulation.random, "randint") as seed:
            for options, message in (
                ({"signal_profile": "settran"}, "Escolha explicitamente --settran-plan"),
                ({"signal_profile": "settran", "settran_plan": "1"}, "2/4/16/24"),
                ({"signal_profile": "settran", "settran_plan": "2"}, "conversor"),
                ({"signal_profile": "current", "settran_plan": "2"}, "exige"),
            ):
                with self.subTest(options=options), self.assertRaisesRegex(ValueError, message):
                    self.run_episodes(**options)
        seed.assert_not_called()
        self.baseline_mock.assert_not_called()
        self.generate_mock.assert_not_called()
        self.run_mock.assert_not_called()
        self.assertFalse(self.output_dir.exists())

    def test_selected_plan_reports_only_its_source_anomalies(self):
        red_cells = {"2": None, "4": "R115", "16": "R116", "24": "R117"}
        for plan, expected_cell in red_cells.items():
            with self.subTest(plan=plan), self.assertRaises(ValueError) as error:
                self.run_episodes(signal_profile="settran", settran_plan=plan)
            message = str(error.exception)
            self.assertIn(f"Plano SETTRAN {plan} selecionado para teste fixo", message)
            self.assertIn("9 definições de interseção", message)
            self.assertIn("9 definições não possuem sumo_phases", message)
            self.assertIn("A144/B158", message)
            self.assertIn("Anselmo", message)
            self.assertIn("A agenda ausente não impede esta escolha explícita", message)
            for cell in ("R115", "R116", "R117"):
                self.assertEqual(cell in message, cell == expected_cell)
            if plan == "2":
                self.assertNotIn("Niterói", message)
        self.baseline_mock.assert_not_called()
        self.generate_mock.assert_not_called()
        self.run_mock.assert_not_called()
        self.assertFalse(self.output_dir.exists())

    def test_available_plan_ids_come_from_the_normalized_source(self):
        document = json.loads(simulation.SETTRAN_PROGRAMS_FILE.read_text(encoding="utf-8"))
        document["programs"] = [program for program in document["programs"]
                                if program["plan_id"] == "4"]
        source = Mock()
        source.read_text.return_value = json.dumps(document)
        with patch.object(simulation, "SETTRAN_PROGRAMS_FILE", source):
            with self.assertRaisesRegex(ValueError, "Planos disponíveis na fonte: 4\\."):
                self.run_episodes(signal_profile="settran", settran_plan="2")
        self.generate_mock.assert_not_called()
        self.assertFalse(self.output_dir.exists())

    def test_editing_intermediate_phases_cannot_enable_an_unimplemented_converter(self):
        document = json.loads(simulation.SETTRAN_PROGRAMS_FILE.read_text(encoding="utf-8"))
        document["status"] = "ready"
        for program in document["programs"]:
            program["sumo_phases"] = [{"duration": 70, "state": "G"}]
        source = Mock()
        source.read_text.return_value = json.dumps(document)
        with patch.object(simulation, "SETTRAN_PROGRAMS_FILE", source):
            with patch.object(simulation.random, "randint") as seed:
                with self.assertRaisesRegex(ValueError, "conversor .* não está implementado"):
                    self.run_episodes(signal_profile="settran", settran_plan="2")
        seed.assert_not_called()
        self.baseline_mock.assert_not_called()
        self.generate_mock.assert_not_called()
        self.run_mock.assert_not_called()
        self.assertFalse(self.output_dir.exists())

    def test_cli_settran_returns_actionable_error_without_fallback(self):
        error = io.StringIO()
        with redirect_stderr(error), redirect_stdout(io.StringIO()):
            result = simulation.main(["--signal-profile", "settran"])
        self.assertEqual(result, 1)
        self.assertIn("docs/settran/settran_audit.csv", error.getvalue())
        self.generate_mock.assert_not_called()
        self.run_mock.assert_not_called()

    def test_current_selection_does_not_change_demand_arguments(self):
        source = Mock()
        source.read_text.side_effect = AssertionError("current não deve carregar SETTRAN")
        with patch.object(simulation, "SETTRAN_PROGRAMS_FILE", source):
            with patch.object(simulation.random, "randint", return_value=17):
                self.run_episodes(duration=30, period=5, end=60)
                self.run_episodes(duration=30, period=5, end=60, signal_profile="current")
        source.read_text.assert_not_called()
        calls = [call.kwargs for call in self.generate_mock.call_args_list]
        for key in ("net_file", "duration", "period", "seed"):
            self.assertEqual(calls[0][key], calls[1][key])
        self.assertNotIn("signal_profile", calls[0])
        self.assertNotIn("signal_profile", calls[1])
        self.assertNotIn("settran_plan", calls[0])
        self.assertNotIn("settran_plan", calls[1])

    def test_output_outside_random_results_is_rejected(self):
        for invalid in (self.directory / "elsewhere", self.output_root / "outputs-other"):
            with self.subTest(directory=invalid):
                with self.assertRaises(ValueError):
                    self.run_episodes(output_dir=invalid)
        self.generate_mock.assert_not_called()

    def test_generation_failure_preserves_context_and_stops_batch(self):
        self.generate_mock.side_effect = subprocess.CalledProcessError(1, ["randomTrips.py"])
        with patch.object(simulation.random, "randint", return_value=42):
            with self.assertRaises(subprocess.CalledProcessError):
                self.run_episodes(episodes=3)

        self.generate_mock.assert_called_once()
        self.run_mock.assert_not_called()
        self.collector.collect_episode.assert_not_called()
        directory = next(self.output_dir.iterdir())
        records, manifest = self.episode_results(directory)
        self.assertEqual(records["status"]["value"], "failed")
        self.assertEqual(records["seed"]["value"], 42)
        self.assertEqual(records["demand_model"]["value"], "random")
        self.assertGreater(records["execution_time_seconds"]["value"], 0)
        self.assertIn("CalledProcessError", records["error"]["value"])
        self.assertEqual(manifest["status"], "failed")
        self.assertEqual(manifest["baseline"]["id"], "fixture")

    def test_simulation_failure_preserves_generation_and_stops_batch(self):
        self.run_mock.side_effect = subprocess.CalledProcessError(1, ["sumo"])

        with self.assertRaises(subprocess.CalledProcessError):
            self.run_episodes(episodes=3)

        self.generate_mock.assert_called_once()
        self.run_mock.assert_called_once()
        self.collector.collect_episode.assert_not_called()
        records, manifest = self.episode_results(next(self.output_dir.iterdir()))
        self.assertEqual(records["status"]["value"], "failed")
        self.assertEqual(records["vehicles_generated"]["value"], 2)
        self.assertEqual(manifest["generation"]["vehicles_generated"], 2)
        self.assertIn("inputs/random.rou.xml", manifest["files"])

    def test_keyboard_interrupt_preserves_interrupted_status(self):
        self.run_mock.side_effect = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.run_episodes(episodes=2)
        records, manifest = self.episode_results(next(self.output_dir.iterdir()))
        self.assertEqual(records["status"]["value"], "interrupted")
        self.assertEqual(manifest["status"], "interrupted")
        self.generate_mock.assert_called_once()

    @patch.object(simulation, "run_random_episodes")
    def test_cli_forwards_options(self, run_random_episodes):
        with redirect_stdout(io.StringIO()):
            result = simulation.main(
                [
                    "--net-file",
                    str(self.net_file),
                    "--output-dir",
                    str(self.output_dir),
                    "--episodes",
                    "2",
                    "--gui",
                    "--duration",
                    "120",
                    "--period",
                    "2",
                    "--end",
                    "60",
                    "--metrics-profile",
                    "full",
                ]
            )

        self.assertEqual(result, 0)
        options = run_random_episodes.call_args.kwargs
        self.assertEqual(options["episodes"], 2)
        self.assertTrue(options["gui"])
        self.assertEqual(options["duration"], 120)
        self.assertEqual(options["period"], 2)
        self.assertEqual(options["end"], 60)
        self.assertEqual(options["metrics_profile"], "full")
        self.assertEqual(options["signal_profile"], "current")
        self.assertIsNone(options["settran_plan"])

    @patch.object(simulation, "run_random_episodes")
    def test_cli_forwards_signal_profile_separately(self, run_random_episodes):
        with redirect_stdout(io.StringIO()):
            result = simulation.main(["--signal-profile", "settran", "--settran-plan", "16",
                                      "--metrics-profile", "full"])
        self.assertEqual(result, 0)
        self.assertEqual(run_random_episodes.call_args.kwargs["signal_profile"], "settran")
        self.assertEqual(run_random_episodes.call_args.kwargs["settran_plan"], "16")
        self.assertEqual(run_random_episodes.call_args.kwargs["metrics_profile"], "full")

    def test_cli_recognizes_fixed_plan_and_reports_compilation_limit(self):
        error = io.StringIO()
        with redirect_stderr(error), redirect_stdout(io.StringIO()):
            result = simulation.main(["--signal-profile", "settran", "--settran-plan", "2"])
        self.assertEqual(result, 1)
        self.assertIn("Plano SETTRAN 2 selecionado para teste fixo", error.getvalue())
        self.assertIn("conversor", error.getvalue())
        self.assertNotIn("Niterói", error.getvalue())
        self.generate_mock.assert_not_called()
        self.run_mock.assert_not_called()
        self.assertFalse(self.output_dir.exists())


if __name__ == "__main__":
    unittest.main()
