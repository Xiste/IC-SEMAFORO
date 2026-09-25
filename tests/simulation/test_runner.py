"""Testa a execução do SUMO e a sequência de episódios random.

As entradas são arquivos temporários e os processos externos são simulados.
O arquivo verifica os comandos construídos e uma demanda nova por episódio.
"""

from contextlib import redirect_stdout
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, call, patch

from SistemaDeSemaforos.simulation import runner as simulation


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


class RandomEpisodeTests(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.directory = Path(temporary_directory.name)
        self.net_file = self.directory / "network.net.xml"
        self.output_dir = self.directory / "episodes"

    def run_episodes(self, **parameters):
        arguments = {"net_file": self.net_file, "output_dir": self.output_dir}
        arguments.update(parameters)
        with redirect_stdout(io.StringIO()):
            simulation.run_random_episodes(**arguments)

    @patch.object(simulation, "run_simulation")
    @patch.object(simulation, "generate_random_demand")
    def test_each_episode_generates_before_running_sumo(self, generate, run):
        first = self.output_dir / "episodio_001" / "random.rou.xml"
        second = self.output_dir / "episodio_002" / "random.rou.xml"
        generate.side_effect = [first, second]
        workflow = Mock()
        workflow.attach_mock(generate, "generate")
        workflow.attach_mock(run, "run")

        self.run_episodes(
            episodes=2,
            gui=True,
            duration=120,
            period=2,
            end=60,
        )

        self.assertEqual(
            workflow.mock_calls,
            [
                call.generate(
                    net_file=self.net_file,
                    output_dir=first.parent,
                    duration=120,
                    period=2,
                ),
                call.run(
                    net_file=self.net_file,
                    demand_file=first,
                    gui=True,
                    end=60,
                ),
                call.generate(
                    net_file=self.net_file,
                    output_dir=second.parent,
                    duration=120,
                    period=2,
                ),
                call.run(
                    net_file=self.net_file,
                    demand_file=second,
                    gui=True,
                    end=60,
                ),
            ],
        )

    @patch.object(simulation, "run_simulation")
    @patch.object(simulation, "generate_random_demand")
    def test_invalid_batch_parameters_stop_before_generation(self, generate, run):
        invalid_values = {
            "episodes": (0, -1, 1.5, True),
            "end": (0, -1, float("inf"), float("nan")),
        }
        for name, values in invalid_values.items():
            for value in values:
                with self.subTest(parameter=name, value=value):
                    with self.assertRaises(ValueError):
                        self.run_episodes(**{name: value})

        generate.assert_not_called()
        run.assert_not_called()

    @patch.object(simulation, "run_simulation")
    @patch.object(simulation, "generate_random_demand")
    def test_simulation_failure_stops_remaining_episodes(self, generate, run):
        route_file = self.output_dir / "episodio_001" / "random.rou.xml"
        generate.return_value = route_file
        run.side_effect = subprocess.CalledProcessError(1, ["sumo"])

        with self.assertRaises(subprocess.CalledProcessError):
            self.run_episodes(episodes=3)

        generate.assert_called_once()
        run.assert_called_once()

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
                ]
            )

        self.assertEqual(result, 0)
        options = run_random_episodes.call_args.kwargs
        self.assertEqual(options["episodes"], 2)
        self.assertTrue(options["gui"])
        self.assertEqual(options["duration"], 120)
        self.assertEqual(options["period"], 2)
        self.assertEqual(options["end"], 60)


if __name__ == "__main__":
    unittest.main()
