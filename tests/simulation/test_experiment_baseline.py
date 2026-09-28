"""Verifica deduplicação e integridade das entradas estáticas compartilhadas."""

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from SistemaDeSemaforos.simulation import experiment_baseline as baseline


class BaselineTests(unittest.TestCase):
    def test_reuse_changed_network_and_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            network = root / "net.xml"
            network.write_text("<net />")
            binary = root / "sumo"
            binary.write_text("fake binary")

            def run(command, **kwargs):
                if "--save-template" in command:
                    Path(command[-1]).write_text(
                        '<configuration><time><step-length value="1" /></time>'
                        '<random_number><seed value="23423" /></random_number></configuration>')
                return subprocess.CompletedProcess(command, 0, stdout="SUMO fixture")

            with patch.object(baseline.subprocess, "run", side_effect=run) as process:
                first = baseline.prepare_baseline(network, str(binary), root / "outputs")
                again = baseline.prepare_baseline(network, str(binary), root / "outputs")
                self.assertEqual(first["directory"], again["directory"])
                self.assertEqual(sum(call.args[0][0] == str(binary)
                                     for call in process.call_args_list), 2)
                self.assertEqual(first["manifest"]["sumo_defaults"]["seed"], "23423")
                network.write_text('<net><location netOffset="0,0" /></net>')
                changed = baseline.prepare_baseline(network, str(binary), root / "outputs")
                self.assertNotEqual(first["directory"], changed["directory"])
                self.assertEqual((first["directory"] / "network.net.xml").read_text(), "<net />")
                (changed["directory"] / "network.net.xml").write_text("tampered")
                with self.assertRaisesRegex(ValueError, "Baseline modificado"):
                    baseline.prepare_baseline(network, str(binary), root / "outputs")
