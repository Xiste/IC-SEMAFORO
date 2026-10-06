"""Checks that unverified junctions cannot silently enter the PPO experiment."""

import tempfile
import unittest
from pathlib import Path

from semaforos.configuracao import read_config
from semaforos.mapeamento import audit_phase_kind, mapping_report, require_validated_targets
from semaforos.metricas import trip_summary


ROOT = Path(__file__).resolve().parents[1]


class MappingMetricsTest(unittest.TestCase):
    def test_audit_retains_unclassified_signal_states(self):
        self.assertEqual(audit_phase_kind("OOOOrrrr"), "other")

    def test_mapping_requires_external_validation(self):
        config = read_config(ROOT / "config" / "cenario.json")
        report = mapping_report(config, config["mapping_path"])
        self.assertEqual(report["total"], 9)
        self.assertEqual(report["validated_count"], 0)
        self.assertTrue(any("ciclos divergentes" in issue
                            for entry in report["intersections"] for issue in entry["issues"]))
        with self.assertRaisesRegex(ValueError, "mapeamento validado"):
            require_validated_targets(config, report)

    def test_completed_trips_exclude_unfinished_from_mean(self):
        content = ('<tripinfos><tripinfo id="a" arrival="20" duration="10" '
                   'waitingTime="2" timeLoss="3" waitingCount="1" '
                   'routeLength="100" departDelay="0"/>'
                   '<tripinfo id="b" arrival="-1" duration="100" '
                   'waitingTime="50"/></tripinfos>')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tripinfo.xml"
            path.write_text(content, encoding="utf-8")
            summary = trip_summary(path)
        self.assertEqual(summary["tripinfo_completed"], 1)
        self.assertEqual(summary["tripinfo_unfinished"], 1)
        self.assertEqual(summary["mean_travel_time_seconds"], 10)
        self.assertEqual(summary["mean_trip_waiting_seconds"], 2)

    def test_corrected_network_candidates_are_not_validated_targets(self):
        config = read_config(ROOT / "config" / "cenario_rede_corrigida.json")
        report = mapping_report(config, config["mapping_path"])
        candidates = [candidate for entry in report["intersections"]
                      for candidate in entry["candidate_controllers"]]
        self.assertEqual(len(candidates), 17)
        self.assertTrue(all(item["present_in_network"] for item in candidates))
        self.assertEqual(report["validated_count"], 0)


if __name__ == "__main__":
    unittest.main()
