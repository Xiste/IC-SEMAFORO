"""Verifica a geração random sem exigir SUMO instalado ou executar simulação.

Usa redes temporárias e uma chamada simulada a randomTrips.py como entradas.
Confere os argumentos do SUMO, as viagens/rotas publicadas e os erros que
devem preservar uma demanda anterior. Executado pelo comando ``make test``.
"""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import call, patch
import xml.etree.ElementTree as ET

from SistemaDeSemaforos.demand import generator as demand


TRIPS_XML = '<routes><trip id="0" depart="0" from="a" to="b" /></routes>'
ROUTES_XML = (
    '<routes><vehicle id="0" depart="0">'
    '<route edges="a b" /></vehicle></routes>'
)


def option_value(command, option):
    """Obtém uma opção do comando sem exigir uma ordem específica."""
    return command[command.index(option) + 1]


def write_generated_files(command, **kwargs):
    """Simula os dois XMLs produzidos pelo randomTrips.py e pelo roteador."""
    Path(option_value(command, "--output-trip-file")).write_text(
        TRIPS_XML, encoding="utf-8"
    )
    Path(option_value(command, "--route-file")).write_text(
        ROUTES_XML, encoding="utf-8"
    )
    return subprocess.CompletedProcess(command, 0)


class RandomDemandTests(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.directory = Path(temporary_directory.name)
        self.net_file = self.directory / "network.net.xml"
        self.net_file.write_text("<net />", encoding="utf-8")
        self.output_dir = self.directory / "demand"
        self.random_trips = self.directory / "tools" / "randomTrips.py"
        script_patch = patch.object(
            demand, "_find_random_trips", return_value=self.random_trips
        )
        script_patch.start()
        self.addCleanup(script_patch.stop)

    def generate(self, **parameters):
        return demand.generate_random_demand(
            net_file=self.net_file,
            output_dir=self.output_dir,
            **parameters,
        )

    def create_previous_demand(self):
        self.output_dir.mkdir(exist_ok=True)
        files = {
            self.output_dir / "random.trips.xml": "viagens anteriores",
            self.output_dir / "random.rou.xml": "rotas anteriores",
        }
        for path, contents in files.items():
            path.write_text(contents, encoding="utf-8")
        return files

    def assert_previous_demand(self, files):
        for path, contents in files.items():
            self.assertEqual(path.read_text(encoding="utf-8"), contents)

    @patch.object(demand.subprocess, "run", side_effect=write_generated_files)
    def test_default_demand_builds_sumo_command_and_produces_routes(self, run):
        route_file = self.generate()

        self.assertEqual(route_file, self.output_dir / "random.rou.xml")
        self.assertEqual(len(ET.parse(route_file).getroot().findall("vehicle")), 1)
        trip_file = self.output_dir / "random.trips.xml"
        self.assertEqual(len(ET.parse(trip_file).getroot().findall("trip")), 1)
        run.assert_called_once()
        command = run.call_args.args[0]
        self.assertEqual(command[:2], [sys.executable, str(self.random_trips)])
        self.assertEqual(option_value(command, "--net-file"), str(self.net_file))
        self.assertEqual(float(option_value(command, "--begin")), 0)
        self.assertEqual(float(option_value(command, "--end")), 7200)
        self.assertEqual(float(option_value(command, "--period")), 1.5)
        self.assertEqual(option_value(command, "--vehicle-class"), "passenger")
        self.assertIn("--validate", command)
        self.assertIs(run.call_args.kwargs["check"], True)

    @patch.object(demand.subprocess, "run", side_effect=write_generated_files)
    def test_duration_period_and_output_directory_are_respected(self, run):
        self.output_dir = self.directory / "custom" / "demand"

        route_file = self.generate(duration=120, period=2)

        command = run.call_args.args[0]
        self.assertEqual(float(option_value(command, "--end")), 120)
        self.assertEqual(float(option_value(command, "--period")), 2)
        self.assertEqual(route_file, self.output_dir / "random.rou.xml")
        self.assertTrue(route_file.is_file())
        self.assertTrue((self.output_dir / "random.trips.xml").is_file())

    @patch.object(demand.random, "randint", side_effect=[17, 2147483647])
    @patch.object(demand.subprocess, "run", side_effect=write_generated_files)
    def test_each_generation_draws_and_passes_a_valid_seed(self, run, randint):
        self.generate()
        self.generate()

        seeds = [
            int(option_value(invocation.args[0], "--seed"))
            for invocation in run.call_args_list
        ]
        self.assertEqual(seeds, [17, 2147483647])
        for seed in seeds:
            self.assertGreaterEqual(seed, 0)
            self.assertLess(seed, 2**31)
        expected_call = call(0, 2**31 - 1)
        self.assertEqual(randint.call_args_list, [expected_call, expected_call])

    @patch.object(demand.subprocess, "run", side_effect=write_generated_files)
    def test_success_replaces_both_previous_files(self, run):
        self.create_previous_demand()

        self.generate()

        self.assertEqual(
            (self.output_dir / "random.trips.xml").read_text(encoding="utf-8"),
            TRIPS_XML,
        )
        self.assertEqual(
            (self.output_dir / "random.rou.xml").read_text(encoding="utf-8"),
            ROUTES_XML,
        )

    def test_subprocess_failure_preserves_previous_demand(self):
        previous = self.create_previous_demand()
        error = subprocess.CalledProcessError(1, ["randomTrips.py"])
        with patch.object(demand.subprocess, "run", side_effect=error):
            with self.assertRaises(subprocess.CalledProcessError):
                self.generate()

        self.assert_previous_demand(previous)

    def test_missing_or_invalid_generated_files_preserve_previous_demand(self):
        previous = self.create_previous_demand()
        cases = [
            (None, ROUTES_XML),
            (TRIPS_XML, None),
            ("", ROUTES_XML),
            (TRIPS_XML, ""),
            ("<routes>", ROUTES_XML),
            (TRIPS_XML, "<routes>"),
            ("<routes />", ROUTES_XML),
            (TRIPS_XML, "<routes />"),
            ("<other><trip /></other>", ROUTES_XML),
            (TRIPS_XML, "<other><vehicle /></other>"),
        ]
        for trips, routes in cases:
            with self.subTest(trips=trips, routes=routes):
                def write_invalid_files(command, **kwargs):
                    for option, contents in [
                        ("--output-trip-file", trips),
                        ("--route-file", routes),
                    ]:
                        if contents is not None:
                            Path(option_value(command, option)).write_text(
                                contents, encoding="utf-8"
                            )
                    return subprocess.CompletedProcess(command, 0)

                with patch.object(
                    demand.subprocess, "run", side_effect=write_invalid_files
                ):
                    with self.assertRaises(RuntimeError):
                        self.generate()
                self.assert_previous_demand(previous)

    @patch.object(demand.subprocess, "run")
    def test_duration_and_period_must_be_positive_and_finite(self, run):
        for name in ("duration", "period"):
            for value in (0, -1, float("inf"), float("-inf"), float("nan")):
                with self.subTest(parameter=name, value=value):
                    with self.assertRaises(ValueError):
                        self.generate(**{name: value})

        run.assert_not_called()

    @patch.object(demand.subprocess, "run")
    def test_missing_network_fails_before_calling_sumo(self, run):
        self.net_file.unlink()

        with self.assertRaises(FileNotFoundError):
            self.generate()

        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
