"""Confere a unidade das contagens sem presumir associação com vias SUMO."""

import tempfile
import unittest
from pathlib import Path

from semaforos.cenario.medicoes import measurement_report


class MeasurementsTest(unittest.TestCase):
    def test_rates_use_only_complete_minute_windows(self):
        csv_text = ("hora_inicio,hora_fim,vlink_id,descricao_linha,car,bike,motorcycle,bus,truck,person,vehicle_total,speed_pxm,speed_pxm_max\n"
                    "2026-06-26 21:00:00,2026-06-26 21:01:00,5,Niteroi,4,1,2,0,0,3,4,0,0\n"
                    "2026-06-26 21:01:00,2026-06-26 21:03:00,5,Niteroi,8,0,1,0,0,0,8,0,0\n"
                    "2026-06-26 21:03:00,2026-06-26 21:04:00,5,Niteroi,6,0,0,0,0,0,6,0,0\n")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "measurements.csv"
            path.write_text(csv_text, encoding="utf-8")
            sensor = measurement_report(path)["sensors"][0]
        self.assertEqual(sensor["observed_vehicle_total"], 18)
        self.assertEqual(sensor["observed_motorcycle"], 3)
        self.assertEqual(sensor["complete_minute_rows"], 2)
        self.assertEqual(sensor["mean_vehicles_per_hour_in_observed_minutes"], 300)
        self.assertEqual(sensor["window_seconds"], {60: 2, 120: 1})


if __name__ == "__main__":
    unittest.main()
