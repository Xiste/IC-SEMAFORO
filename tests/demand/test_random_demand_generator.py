"""Verifica a geração random sem exigir SUMO instalado ou executar simulação.

Usa redes temporárias e uma chamada simulada a randomTrips.py como entradas.
Confere os argumentos do SUMO, as viagens/rotas publicadas e os erros que
devem preservar uma demanda anterior. Executado pelo comando ``make test``.
"""

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import call, patch
import xml.etree.ElementTree as ET

from SistemaDeSemaforos.demand import random_demand_generator as demand


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
        self.random_trips.parent.mkdir()
        self.random_trips.write_text("# ferramenta simulada\n", encoding="utf-8")
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

    @patch.object(demand.random, "randint")
    @patch.object(demand.subprocess, "run", side_effect=write_generated_files)
    def test_explicit_seed_is_passed_without_drawing_another(self, run, randint):
        for seed in (0, 2**31 - 1):
            with self.subTest(seed=seed):
                self.generate(seed=seed)
                self.assertEqual(option_value(run.call_args.args[0], "--seed"), str(seed))

        randint.assert_not_called()

    @patch.object(demand.random, "randint")
    @patch.object(demand.subprocess, "run")
    def test_invalid_seed_fails_before_generation(self, run, randint):
        for seed in (-1, 2**31, 1.5, True, False, "42"):
            with self.subTest(seed=seed):
                with self.assertRaises(ValueError):
                    self.generate(seed=seed)

        randint.assert_not_called()
        run.assert_not_called()

    @patch.object(demand.time, "perf_counter", side_effect=[10.0, 12.5])
    @patch.object(demand.random, "randint", return_value=17)
    @patch.object(demand.subprocess, "run", side_effect=write_generated_files)
    def test_metadata_records_inputs_actual_outputs_and_monotonic_duration(
        self, run, randint, perf_counter
    ):
        metadata = {}

        route_file = self.generate(duration=10.0, period=3.0, metadata=metadata)

        self.assertEqual(metadata["seed"], 17)
        self.assertEqual(metadata["demand_model"], "random")
        self.assertEqual(metadata["begin"], 0.0)
        self.assertEqual(metadata["duration"], 10.0)
        self.assertEqual(metadata["period"], 3.0)
        self.assertEqual(metadata["vehicle_class"], "passenger")
        self.assertIs(metadata["validate"], True)
        self.assertEqual(metadata["vehicles_requested"], 4)
        self.assertEqual(metadata["trips_generated"], 1)
        self.assertEqual(metadata["vehicles_generated"], 1)
        self.assertEqual(metadata["net_file"], str(self.net_file))
        self.assertEqual(metadata["trips_file"], str(self.output_dir / "random.trips.xml"))
        self.assertEqual(metadata["routes_file"], str(route_file))
        self.assertEqual(metadata["random_trips_file"], str(self.random_trips))
        self.assertEqual(
            metadata["random_trips_sha256"],
            hashlib.sha256(self.random_trips.read_bytes()).hexdigest(),
        )
        self.assertEqual(metadata["command"], run.call_args.args[0])
        self.assertEqual(metadata["duration_seconds"], 2.5)
        start = datetime.fromisoformat(metadata["started_at_utc"])
        finish = datetime.fromisoformat(metadata["finished_at_utc"])
        self.assertEqual(start.tzinfo, timezone.utc)
        self.assertEqual(finish.tzinfo, timezone.utc)
        self.assertGreaterEqual(finish, start)
        randint.assert_called_once_with(0, 2**31 - 1)

    def test_optional_log_captures_tool_output(self):
        log_file = self.directory / "logs" / "generation.log"

        def generate_with_log(command, **kwargs):
            kwargs["stdout"].write("mensagem da ferramenta\n")
            self.assertEqual(kwargs["stderr"], subprocess.STDOUT)
            return write_generated_files(command, **kwargs)

        with patch.object(demand.subprocess, "run", side_effect=generate_with_log):
            self.generate(log_file=log_file)

        self.assertEqual(log_file.read_text(encoding="utf-8"), "mensagem da ferramenta\n")

    @patch.object(demand.time, "perf_counter", side_effect=[10.0, 11.0])
    def test_failure_retains_generation_metadata_and_previous_demand(self, perf_counter):
        previous = self.create_previous_demand()
        metadata = {}
        error = subprocess.CalledProcessError(1, ["randomTrips.py"])

        with patch.object(demand.subprocess, "run", side_effect=error):
            with self.assertRaises(subprocess.CalledProcessError):
                self.generate(seed=42, metadata=metadata)

        self.assertEqual(metadata["seed"], 42)
        self.assertEqual(metadata["duration_seconds"], 1.0)
        self.assertIn("finished_at_utc", metadata)
        self.assertIn("command", metadata)
        self.assertNotIn("vehicles_generated", metadata)
        self.assert_previous_demand(previous)
        self.assertEqual(list(self.output_dir.glob(".random-*")), [])

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
