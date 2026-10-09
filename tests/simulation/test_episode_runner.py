"""Testa a execução do SUMO e a sequência de episódios random.

As entradas são arquivos temporários e os processos externos são simulados.
O arquivo verifica os comandos construídos e uma demanda nova por episódio.
"""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

from SistemaDeSemaforos.simulation import episode_runner as simulation


def option_value(command, option):
    """Retorna o valor que aparece depois de uma opção do comando."""
    return command[command.index(option) + 1]


def configuration_result(command, xml="<configuration />"):
    """Simula a saída de configuração SUMO em stdout ou arquivo temporário."""
    if "--save-configuration" in command:
        destination = option_value(command, "--save-configuration")
        if destination != "-":
            Path(destination).write_text(xml, encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout=xml)
    return subprocess.CompletedProcess(command, 0, stdout="")


def synthetic_cesario_document():
    """Suplemento deliberadamente sintético; não aprova o plano real da SETTRAN."""
    document = json.loads(simulation.SETTRAN_PROGRAMS_FILE.read_text(encoding="utf-8"))
    intersection = "Av. Cesário Alvin x Rua Paraná"
    program = next(p for p in document["programs"]
                   if p["intersection"] == intersection and p["plan_id"] == "2")
    reference = "SYNTHETIC_TEST_FIXTURE_NOT_SETTRAN"
    tls = "FAM_CESARIO_PARANA"
    phases = []
    for stage in program["stages"]:
        indices = stage["sumo_links"][0]["link_indices"]
        for transition, field, signal in (("green", "green_seconds", "G"),
                                          ("yellow", "yellow_seconds", "y"),
                                          ("clearance_red", "clearance_red_seconds", "r")):
            state = ["r"] * 8
            for index in indices:
                state[index] = signal
            phases.append({"stage_id": stage["stage_id"], "transition": transition,
                           "duration_seconds": stage[field], "states": {tls: "".join(state)},
                           "source_reference": reference})
    program["operational"] = {
        "network_sha256": sha256(simulation.DEFAULT_NET_FILE.read_bytes()).hexdigest(),
        "tls_ids": [tls], "current_tls_ids": [],
        "stage_links": {s["stage_id"]: s["sumo_links"] for s in program["stages"]},
        "phases": phases,
        "evidence": {field: {"status": "CONFIRMADO", "source_reference": reference}
                     for field in ("movement_mapping", "control_scope", "permissions", "sequence",
                                   "transitions", "offset_reference")},
        "offset_reference": {"reference_type": "clock", "reference_id": "synthetic-clock",
                             "reference_time_seconds": 0, "direction": "delay",
                             "target_phase_index": 0, "source_reference": reference},
    }
    return document, intersection


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

    def test_native_configuration_is_read_without_creating_snapshot_files(self):
        commands = []

        def fake_sumo(command, **kwargs):
            commands.append(command)
            output = ('<configuration><time><begin value="0"/><end value="-1"/>'
                      '<step-length value="1"/></time><random_number>'
                      '<seed value="23423"/></random_number></configuration>'
                      if "--save-template" in command else "SUMO test version\n")
            return subprocess.CompletedProcess(command, 0, stdout=output)

        before = sorted(self.directory.iterdir())
        with patch.object(simulation.subprocess, "run", side_effect=fake_sumo):
            configuration = simulation.read_sumo_configuration("/usr/bin/sumo")
        self.assertIn("SUMO test version", configuration["sumo_version"])
        self.assertEqual(configuration["sumo_defaults"], {
            "begin": "0", "end": "-1", "step-length": "1", "seed": "23423"})
        self.assertEqual(sorted(self.directory.iterdir()), before)
        template_commands = [command for command in commands if "--save-template" in command]
        self.assertEqual(len(template_commands), 1)
        self.assertEqual(option_value(template_commands[0], "--save-template"), "-")

    def test_recording_preserves_run_options_and_stores_sumo_configuration(self):
        binary = self.directory / "sumo-gui"
        binary.write_text("SUMO simulado", encoding="utf-8")
        recording = self.directory / "episode"
        (recording / "inputs").mkdir(parents=True)
        metadata = {}
        commands = []

        def fake_sumo(command, **kwargs):
            commands.append(command)
            return configuration_result(command,
                '<configuration><output><precision value="8" /></output></configuration>')

        with patch.object(simulation.shutil, "which", return_value=str(binary)):
            with patch.object(simulation.subprocess, "run", side_effect=fake_sumo):
                simulation.run_simulation(
                    net_file=self.net_file, demand_file=self.demand_file,
                    gui=True, end=60, recording_dir=recording, metadata=metadata,
                    sumo_defaults={"seed": "23423", "step-length": "1"},
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
        self.assertFalse((recording / "inputs" / "observations.add.xml").exists())
        self.assertNotIn("--additional-files", command)
        self.assertTrue((recording / "sumo.log").is_file())

    def test_metrics_profile_preserves_native_timing_and_termination(self):
        def fake_sumo(command, **kwargs):
            return configuration_result(command)

        for profile in ("core", "full"):
            with self.subTest(profile=profile):
                recording = self.directory / profile
                (recording / "inputs").mkdir(parents=True)
                metadata = {}
                with patch.object(simulation.shutil, "which", return_value="/usr/bin/sumo"):
                    with patch.object(simulation.subprocess, "run", side_effect=fake_sumo):
                        simulation.run_simulation(
                            net_file=self.net_file, demand_file=self.demand_file,
                            recording_dir=recording, metrics_profile=profile, metadata=metadata,
                            sumo_defaults={"seed": "23423", "step-length": "1", "end": "-1"})
                command = metadata["command"]
                self.assertEqual(option_value(command, "--begin"), "0")
                self.assertEqual(option_value(command, "--route-files"), str(self.demand_file))
                self.assertNotIn("--end", command)
                self.assertNotIn("--step-length", command)
                self.assertNotIn("--time-to-teleport", command)
                self.assertNotIn("--collision.action", command)
                self.assertNotIn("--seed", command)
                self.assertEqual(metadata["step_length"], 1.0)
                self.assertEqual(metadata["seed"], 23423)

    def test_ready_local_fixture_preserves_observations_and_records_exact_scope(self):
        document, intersection = synthetic_cesario_document()
        recording = self.directory / "episode"
        recording.mkdir()
        source = Mock()
        source.read_text.return_value = json.dumps(document)
        metadata = {}
        commands = []

        def fake_sumo(command, **kwargs):
            commands.append(command)
            return configuration_result(command,
                '<configuration><output><precision value="8" /></output></configuration>')

        with patch.object(simulation, "SETTRAN_PROGRAMS_FILE", source):
            with patch.object(simulation.shutil, "which", return_value="/usr/bin/sumo"):
                with patch.object(simulation.subprocess, "run", side_effect=fake_sumo):
                    simulation.run_simulation(
                        net_file=simulation.DEFAULT_NET_FILE, demand_file=self.demand_file,
                        end=60, recording_dir=recording, metadata=metadata,
                        signal_profile="settran", settran_plan="2", metrics_profile="full",
                        settran_intersections=[intersection], sumo_defaults={"seed": "23423", "step-length": "1"})
        for command in commands:
            self.assertEqual(command.count("--additional-files"), 1)
            additions = option_value(command, "--additional-files").split(",")
            self.assertEqual([Path(a).name for a in additions],
                             ["settran.add.xml", "observations.add.xml"])
            self.assertNotIn("--seed", command)
        self.assertEqual(metadata["seed"], 23423)
        scope = metadata["signal_configuration"]
        self.assertEqual(scope["intersections"], [intersection])
        self.assertEqual(scope["tls_ids"], ["FAM_CESARIO_PARANA"])
        self.assertEqual(len(scope["current_tls_ids"]), 35)
        self.assertFalse((recording / "inputs/settran_programs.json").exists())
        logics = ET.parse(recording / "inputs/settran.add.xml").getroot().findall("tlLogic")
        self.assertEqual([logic.get("id") for logic in logics], ["FAM_CESARIO_PARANA"])
        self.assertEqual(logics[0].get("programID"), "settran_2")
        self.assertEqual(sum(float(p.get("duration")) for p in logics[0]), 70)
        self.assertEqual(scope["programs"], [{
            **logic.attrib, "phases": [phase.attrib for phase in logic.findall("phase")],
            "parameters": [param.attrib for param in logic.findall("param")]} for logic in logics])
        self.assertNotIn("source", scope)
        self.assertNotIn("additional", scope)

    def test_ready_local_core_fixture_adds_only_settran_programs(self):
        document, intersection = synthetic_cesario_document()
        recording = self.directory / "episode"
        recording.mkdir()
        commands = []

        def fake_sumo(command, **kwargs):
            commands.append(command)
            return configuration_result(command)

        with patch.object(simulation.shutil, "which", return_value="/usr/bin/sumo"):
            with patch.object(simulation.subprocess, "run", side_effect=fake_sumo):
                simulation.run_simulation(
                    net_file=simulation.DEFAULT_NET_FILE, demand_file=self.demand_file,
                    recording_dir=recording, metrics_profile="core", signal_profile="settran",
                    settran_plan="2", settran_intersections=[intersection],
                    _settran_document=document, sumo_defaults={"seed": "23423", "step-length": "1"})
        self.assertEqual(len(commands), 2)
        for command in commands:
            self.assertEqual(command.count("--additional-files"), 1)
            self.assertEqual(option_value(command, "--additional-files"),
                             str(recording / "inputs/settran.add.xml"))
            self.assertNotIn("--end", command)
        self.assertFalse((recording / "inputs/observations.add.xml").exists())

    def test_ready_fixture_without_recording_uses_temporary_program_then_removes_it(self):
        document, intersection = synthetic_cesario_document()
        additions = []

        def fake_sumo(command, **kwargs):
            additions.append(Path(option_value(command, "--additional-files")))
            self.assertTrue(additions[-1].is_file())
            return subprocess.CompletedProcess(command, 0)

        with patch.object(simulation.shutil, "which", return_value="/usr/bin/sumo"):
            with patch.object(simulation.subprocess, "run", side_effect=fake_sumo):
                simulation.run_simulation(net_file=simulation.DEFAULT_NET_FILE,
                    demand_file=self.demand_file, end=60, signal_profile="settran",
                    settran_plan="2", settran_intersections=[intersection],
                    _settran_document=document)
        self.assertEqual(len(additions), 1)
        self.assertFalse(additions[0].exists())


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
        self.configuration_mock = self.start_patch(patch.object(
            simulation, "read_sumo_configuration", return_value={
                "sumo_version": "SUMO test version",
                "sumo_defaults": {"seed": "23423", "step-length": "1", "end": "-1"}}))
        self.start_patch(patch.object(simulation.shutil, "which", return_value="/usr/bin/sumo"))
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
        raw = parameters["recording_dir"] / "raw"
        raw.mkdir()
        for name in ("summary.xml.gz", "trips.xml.gz", "statistics.xml", "queues.xml.gz"):
            (raw / name).write_bytes(b"<output />")

    def collect(self, raw, net_file, profile="core"):
        self.workflow.append("collect")
        return {
            "metrics": {"vehicles_completed": 2, "network_mean_speed_m_s_mean": 8.25,
                        "simulation_duration_seconds": 7462.0},
            "entities": {"lanes": {"via_ação_0": {"queue_length_max": 1}}}
                        if profile == "full" else {},
        }

    def episode_directories(self):
        return sorted(path.parent for path in self.output_dir.rglob("metrics.json"))

    def episode_results(self, directory):
        document = json.loads((directory / "metrics.json").read_text(encoding="utf-8"))
        execution = document["execution"]
        records = {item["metric_name"]: item for item in document["metrics"]}
        return records, execution

    def run_episodes(self, **parameters):
        arguments = {"net_file": self.net_file, "output_dir": self.output_dir}
        arguments.update(parameters)
        with redirect_stdout(io.StringIO()) as output:
            simulation.run_random_episodes(**arguments)
        return output.getvalue()

    def test_each_episode_generates_runs_and_collects_in_order(self):
        with patch.object(simulation.random, "randint", side_effect=[17, 42]) as randint:
            self.run_episodes(episodes=2, gui=True, duration=120, period=2, end=60)

        self.assertEqual(self.workflow, ["generate", "run", "collect"] * 2)
        self.assertEqual(randint.call_count, 2)
        self.configuration_mock.assert_called_once()
        self.assertEqual(len(list(self.output_dir.iterdir())), 1)
        self.assertEqual(len(self.episode_directories()), 2)
        self.assertEqual(list(self.output_dir.rglob("configuracao.json")), [])
        self.assertFalse((self.output_root / "baselines").exists())
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
            self.assertEqual(executed["sumo_defaults"], {
                "seed": "23423", "step-length": "1", "end": "-1"})
            self.assertEqual(executed["net_file"], generated["net_file"])
            self.assertEqual(executed["demand_file"], generated["output_dir"] / "random.rou.xml")
            self.assertEqual(executed["recording_dir"], episode_dir)
            self.assertTrue(episode_dir.is_relative_to(self.output_dir))
            self.assertEqual(generated["net_file"].read_bytes(), self.net_file.read_bytes())
            records, execution = self.episode_results(episode_dir)
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
            self.assertEqual(execution["generation"]["seed"], (17, 42)[index])
            self.assertEqual(execution["signal_profile"], "current")
            self.assertEqual(execution["sumo_version"], "SUMO test version")
            self.assertEqual(execution["status"], "completed")
            self.assertIn("started_at_utc", records)
            self.assertIn("finished_at_utc", records)
            self.assertFalse((episode_dir / "manifest.json").exists())
            self.assertFalse((episode_dir / "inputs").exists())
            self.assertEqual(execution["collection"]["profile"], "core")

    def test_both_profiles_keep_original_demand_window_and_simulation_defaults(self):
        for profile in ("core", "full"):
            with self.subTest(profile=profile):
                self.run_episodes(metrics_profile=profile)
                generated = self.generate_mock.call_args.kwargs
                executed = self.run_mock.call_args.kwargs
                self.assertEqual(generated["duration"], 7200.0)
                self.assertEqual(generated["period"], 1.5)
                self.assertIsNone(executed["end"])
                records, _ = self.episode_results(generated["output_dir"].parent)
                self.assertEqual(records["demand_duration_seconds"]["value"], 7200.0)
                self.assertEqual(records["demand_period_seconds"]["value"], 1.5)
                self.assertEqual(records["simulation_duration_seconds"]["value"], 7462.0)
                self.assertEqual(records["simulation_step_length_seconds"]["value"], 1.0)
                self.assertEqual(records["simulation_end_limited"]["value"], False)
                self.assertNotIn("simulation_end_requested_seconds", records)
                self.assertGreater(records["execution_time_seconds"]["value"], 0)
                self.assertLess(records["execution_time_seconds"]["value"], 7200.0)

    def test_core_removes_generated_inputs_and_observations_after_publishing_metrics(self):
        self.run_episodes()
        directory = self.episode_directories()[0]
        document = json.loads((directory / "metrics.json").read_text())
        _, execution = self.episode_results(directory)
        self.assertIsNone(document["entity_metrics_file"])
        self.assertFalse((directory / "entities.json.gz").exists())
        self.assertEqual(list((directory / "raw").glob("*")), [])
        self.assertFalse((directory / "inputs").exists())
        self.assertFalse((directory / "manifest.json").exists())
        self.assertNotIn("files", execution)
        self.assertNotIn("baseline", execution)

    def test_core_cleanup_preserves_unrecognized_file(self):
        def simulate_with_note(**parameters):
            self.simulate(**parameters)
            (parameters["recording_dir"] / "raw/nota.txt").write_text("observação manual")

        self.run_mock.side_effect = simulate_with_note
        self.run_episodes()
        directory = self.episode_directories()[0]
        _, execution = self.episode_results(directory)
        self.assertEqual([path.name for path in (directory / "raw").iterdir()], ["nota.txt"])
        self.assertEqual((directory / "raw/nota.txt").read_text(), "observação manual")

    def test_full_retains_entities_and_native_observations(self):
        self.run_episodes(metrics_profile="full")
        directory = self.episode_directories()[0]
        document = json.loads((directory / "metrics.json").read_text())
        _, execution = self.episode_results(directory)
        self.assertEqual(document["entity_metrics_file"], "entities.json.gz")
        self.assertTrue((directory / "entities.json.gz").is_file())
        self.assertEqual(len(list((directory / "raw").iterdir())), 4)
        self.assertFalse((directory / "inputs").exists())
        self.assertFalse((directory / "manifest.json").exists())

    def test_core_collection_failure_preserves_native_observations(self):
        self.collector.collect_episode.side_effect = ValueError("observação incompleta")
        with self.assertRaisesRegex(ValueError, "observação incompleta"):
            self.run_episodes()
        directory = self.episode_directories()[0]
        records, execution = self.episode_results(directory)
        self.assertEqual(records["status"]["value"], "failed")
        self.assertEqual(len(list((directory / "raw").iterdir())), 4)
        self.assertTrue((directory / "inputs/random.rou.xml").is_file())

    def test_core_export_failure_preserves_native_observations(self):
        save_episode = simulation.save_episode

        def failing_save(directory, metrics, execution, **options):
            if metrics["status"] == "completed":
                raise OSError("disco indisponível")
            return save_episode(directory, metrics, execution, **options)

        with patch.object(simulation, "save_episode", side_effect=failing_save):
            with self.assertRaisesRegex(OSError, "disco indisponível"):
                self.run_episodes()
        directory = self.episode_directories()[0]
        self.assertEqual(len(list((directory / "raw").iterdir())), 4)

    def test_core_cleanup_failure_keeps_published_result_consistent(self):
        unlink = Path.unlink

        def fail_during_cleanup(path, *args, **kwargs):
            if path.parent.name == "raw" and path.name == "trips.xml.gz":
                raise OSError("limpeza interrompida")
            return unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", autospec=True, side_effect=fail_during_cleanup):
            with self.assertRaisesRegex(OSError, "limpeza interrompida"):
                self.run_episodes()
        directory = self.episode_directories()[0]
        records, execution = self.episode_results(directory)
        self.assertEqual(records["status"]["value"], "completed")
        self.assertEqual(execution["status"], "completed")
        self.assertEqual(records["vehicles_completed"]["value"], 2)
        self.assertFalse((directory / "raw/summary.xml.gz").exists())
        self.assertTrue((directory / "raw/trips.xml.gz").is_file())

    def test_episode_files_preserve_seeds_and_three_times_without_summary_csv(self):
        with patch.object(simulation.random, "randint", side_effect=[17, 42]):
            output = self.run_episodes(episodes=2)
        directories = self.episode_directories()
        self.assertEqual(len(directories), 2)
        self.assertEqual(list(self.output_dir.rglob("resumo.csv")), [])
        for index, directory in enumerate(directories, start=1):
            records, execution = self.episode_results(directory)
            self.assertEqual(records["episode_index"]["value"], index)
            self.assertEqual(records["seed"]["value"], (17, 42)[index - 1])
            self.assertEqual(records["simulation_seed"]["value"], 23423)
            self.assertEqual(records["demand_duration_seconds"]["value"], 7200.0)
            self.assertEqual(records["demand_period_seconds"]["value"], 1.5)
            self.assertEqual(records["simulation_duration_seconds"]["value"], 7462.0)
            self.assertGreater(records["execution_time_seconds"]["value"], 0)
            self.assertEqual(records["vehicles_completed"]["value"], 2)
            self.assertNotIn("completed_trip_waiting_time_mean", records)
            self.assertEqual(execution["status"], "completed")
            self.assertEqual(execution["collection"]["profile"], "core")
        self.assertEqual(output, "")

    def test_same_seed_and_timestamp_never_overwrite_previous_episode(self):
        fixed_time = datetime(2026, 9, 25, 20, 0, tzinfo=timezone.utc)
        with patch.object(simulation, "datetime") as clock:
            clock.now.return_value = fixed_time
            with patch.object(simulation.random, "randint", return_value=17):
                with patch.object(simulation, "uuid4", side_effect=[
                    SimpleNamespace(hex="11111111aaaaaaaa"),
                    SimpleNamespace(hex="22222222bbbbbbbb"),
                    SimpleNamespace(hex="33333333cccccccc"),
                    SimpleNamespace(hex="44444444dddddddd"),
                ]):
                    self.run_episodes()
                    first = self.episode_directories()[0]
                    previous_metrics = (first / "metrics.json").read_bytes()
                    self.run_episodes()

        self.assertEqual(len(list(self.output_dir.iterdir())), 2)
        self.assertEqual((first / "metrics.json").read_bytes(), previous_metrics)

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

    def test_settran_fails_before_seed_configuration_or_episode_creation(self):
        with patch.object(simulation.random, "randint") as seed:
            for options, message in (
                ({"signal_profile": "settran"}, "Escolha explicitamente --settran-plan"),
                ({"signal_profile": "settran", "settran_plan": "1"}, "2/4/16/24"),
                ({"signal_profile": "settran", "settran_plan": "2"}, "quadro veicular de intervalos"),
                ({"signal_profile": "current", "settran_plan": "2"}, "exige"),
            ):
                with self.subTest(options=options), self.assertRaisesRegex(ValueError, message):
                    self.run_episodes(net_file=simulation.DEFAULT_NET_FILE, **options)
        seed.assert_not_called()
        self.configuration_mock.assert_not_called()
        self.generate_mock.assert_not_called()
        self.run_mock.assert_not_called()
        self.assertFalse(self.output_dir.exists())

    def test_real_plans_report_vehicle_requirements_without_pedestrian_blockers(self):
        for plan in ("2", "4", "16", "24"):
            with self.subTest(plan=plan), self.assertRaises(ValueError) as error:
                self.run_episodes(net_file=simulation.DEFAULT_NET_FILE,
                                  signal_profile="settran", settran_plan=plan)
            message = str(error.exception)
            self.assertIn(f"Plano {plan};", message)
            self.assertEqual(message.count(f"Plano {plan};"), 9)
            self.assertIn("quadro veicular de intervalos", message)
            self.assertIn("referência da defasagem", message)
            self.assertIn("FAM_RONDON_ANSELMO", message)
            self.assertIn("FAM_RONDON_NITEROI", message)
            self.assertIn("Agenda ausente não impede plano fixo", message)
            for cell in ("R115", "R116", "R117"):
                self.assertNotIn(cell, message)
            self.assertNotIn("conversor", message)
        self.configuration_mock.assert_not_called()
        self.generate_mock.assert_not_called()
        self.run_mock.assert_not_called()
        self.assertFalse(self.output_dir.exists())

    def test_removing_source_plans_cannot_bypass_validation(self):
        document = json.loads(simulation.SETTRAN_PROGRAMS_FILE.read_text(encoding="utf-8"))
        document["programs"] = [program for program in document["programs"]
                                if program["plan_id"] == "4"]
        source = Mock()
        source.read_text.return_value = json.dumps(document)
        with patch.object(simulation, "SETTRAN_PROGRAMS_FILE", source):
            with self.assertRaisesRegex(ValueError, "fonte|extração|originais"):
                self.run_episodes(signal_profile="settran", settran_plan="2")
        self.generate_mock.assert_not_called()
        self.assertFalse(self.output_dir.exists())

    def test_ready_label_cannot_bypass_missing_operational_evidence(self):
        document = json.loads(simulation.SETTRAN_PROGRAMS_FILE.read_text(encoding="utf-8"))
        document["status"] = "ready"
        source = Mock()
        source.read_text.return_value = json.dumps(document)
        with patch.object(simulation, "SETTRAN_PROGRAMS_FILE", source):
            with patch.object(simulation.random, "randint") as seed:
                with self.assertRaisesRegex(ValueError, "fonte|origem|extração|originais"):
                    self.run_episodes(signal_profile="settran", settran_plan="2")
        seed.assert_not_called()
        self.configuration_mock.assert_not_called()
        self.generate_mock.assert_not_called()
        self.run_mock.assert_not_called()
        self.assertFalse(self.output_dir.exists())

    def test_explicit_intersection_reports_only_its_missing_requirements(self):
        with self.assertRaises(ValueError) as error:
            self.run_episodes(net_file=simulation.DEFAULT_NET_FILE, signal_profile="settran",
                              settran_plan="2",
                              settran_intersections=["Av. Cesário Alvin x Rua Paraná"])
        message = str(error.exception)
        self.assertIn("FAM_CESARIO_PARANA", message)
        self.assertIn("quadro veicular de intervalos", message)
        self.assertNotIn("FAM_RONDON_ROTARY_CLUB", message)
        self.assertNotIn("Niterói", message)
        self.assertFalse(self.output_dir.exists())
        self.generate_mock.assert_not_called()

    def test_ready_local_selection_keeps_random_arguments_and_records_signal_scope(self):
        document, intersection = synthetic_cesario_document()
        source = Mock()
        source.read_text.return_value = json.dumps(document)
        with patch.object(simulation, "SETTRAN_PROGRAMS_FILE", source):
            with patch.object(simulation.random, "randint", return_value=17):
                self.run_episodes(net_file=simulation.DEFAULT_NET_FILE, duration=30, period=5,
                                  end=60, signal_profile="settran", settran_plan="2",
                                  settran_intersections=[intersection])
        generated = self.generate_mock.call_args.kwargs
        self.assertEqual((generated["duration"], generated["period"], generated["seed"]), (30, 5, 17))
        self.assertNotIn("signal_profile", generated)
        self.assertNotIn("settran_plan", generated)
        executed = self.run_mock.call_args.kwargs
        self.assertEqual(executed["_settran_document"], document)
        self.assertEqual(executed["settran_intersections"], [intersection])
        _, execution = self.episode_results(self.episode_directories()[0])
        self.assertEqual(execution["signal_configuration"]["tls_ids"], ["FAM_CESARIO_PARANA"])
        self.assertEqual(len(execution["signal_configuration"]["current_tls_ids"]), 35)

    def test_cli_settran_returns_actionable_error_without_fallback(self):
        error = io.StringIO()
        with redirect_stderr(error), redirect_stdout(io.StringIO()):
            result = simulation.main(["--signal-profile", "settran"])
        self.assertEqual(result, 1)
        self.assertIn("docs/GUIA_DE_FUNCIONAMENTO.md", error.getvalue())
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
        directory = self.episode_directories()[0]
        records, execution = self.episode_results(directory)
        self.assertEqual(records["status"]["value"], "failed")
        self.assertEqual(records["seed"]["value"], 42)
        self.assertEqual(records["demand_model"]["value"], "random")
        self.assertGreater(records["execution_time_seconds"]["value"], 0)
        self.assertIn("CalledProcessError", records["error"]["value"])
        self.assertEqual(execution["status"], "failed")
        self.assertFalse((self.output_root / "baselines").exists())
        self.assertEqual(list(self.output_dir.rglob("resumo.csv")), [])
        self.assertNotIn("simulation_duration_seconds", records)
        self.assertNotIn("vehicles_completed", records)

    def test_simulation_failure_preserves_generation_and_stops_batch(self):
        self.run_mock.side_effect = subprocess.CalledProcessError(1, ["sumo"])

        with self.assertRaises(subprocess.CalledProcessError):
            self.run_episodes(episodes=3)

        self.generate_mock.assert_called_once()
        self.run_mock.assert_called_once()
        self.collector.collect_episode.assert_not_called()
        records, execution = self.episode_results(self.episode_directories()[0])
        self.assertEqual(records["status"]["value"], "failed")
        self.assertEqual(records["vehicles_generated"]["value"], 2)
        self.assertEqual(execution["generation"]["vehicles_generated"], 2)
        self.assertTrue((self.episode_directories()[0] / "inputs/random.rou.xml").is_file())

    def test_keyboard_interrupt_preserves_interrupted_status(self):
        self.run_mock.side_effect = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.run_episodes(episodes=2)
        records, execution = self.episode_results(self.episode_directories()[0])
        self.assertEqual(records["status"]["value"], "interrupted")
        self.assertEqual(execution["status"], "interrupted")
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
        self.assertIsNone(options["settran_intersections"])

    @patch.object(simulation, "run_random_episodes")
    def test_cli_forwards_signal_profile_separately(self, run_random_episodes):
        with redirect_stdout(io.StringIO()):
            result = simulation.main(["--signal-profile", "settran", "--settran-plan", "16",
                                      "--metrics-profile", "full", "--settran-intersection", "A",
                                      "--settran-intersection", "B"])
        self.assertEqual(result, 0)
        self.assertEqual(run_random_episodes.call_args.kwargs["signal_profile"], "settran")
        self.assertEqual(run_random_episodes.call_args.kwargs["settran_plan"], "16")
        self.assertEqual(run_random_episodes.call_args.kwargs["metrics_profile"], "full")
        self.assertEqual(run_random_episodes.call_args.kwargs["settran_intersections"], ["A", "B"])

    def test_cli_recognizes_fixed_plan_and_reports_missing_operational_data(self):
        error = io.StringIO()
        with redirect_stderr(error), redirect_stdout(io.StringIO()):
            result = simulation.main(["--signal-profile", "settran", "--settran-plan", "2"])
        self.assertEqual(result, 1)
        self.assertIn("Plano 2;", error.getvalue())
        self.assertIn("quadro veicular de intervalos", error.getvalue())
        self.assertIn("referência da defasagem", error.getvalue())
        self.assertNotIn("conversor", error.getvalue())
        self.generate_mock.assert_not_called()
        self.run_mock.assert_not_called()
        self.assertFalse(self.output_dir.exists())


if __name__ == "__main__":
    unittest.main()
