"""Verifica exposição, separação temporal e interpolação do piloto MetaSettran."""

import csv
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from SistemaDeSemaforos.demand import metasettran_calibration as calibration


FIELDS = ["hora_inicio", "hora_fim", "vlink_id", "descricao_linha", *calibration.COUNTS,
          "speed_pxm", "speed_pxm_max"]


class SourceTimeTests(unittest.TestCase):
    def test_explicit_utc_conversion_changes_day_and_weekday(self):
        source = datetime(2026, 8, 25, 0, 30)
        civil = calibration._source_to_civil(source, "utc")
        self.assertEqual(civil, datetime(2026, 8, 24, 21, 30))
        self.assertEqual(civil.weekday(), 0)
        self.assertEqual(calibration._source_to_civil(datetime(2026, 8, 25, 9), "utc").hour, 6)
        self.assertEqual(calibration._source_to_civil(source, "legacy_civil"), source)
        with self.assertRaises(ValueError):
            calibration._source_to_civil(source.replace(tzinfo=timezone.utc), "utc")

    def test_midnight_interval_is_split_by_civil_date_without_changing_source(self):
        begin, end = datetime(2026, 8, 24, 2, 59), datetime(2026, 8, 24, 3, 1)
        records = {"5": [(begin, end, 12, 120)], "6": []}
        bins = calibration._aggregate(records, source_time_convention="utc")
        self.assertEqual(bins["5"][datetime(2026, 8, 23, 23, 45)], [60, 6])
        self.assertEqual(bins["5"][datetime(2026, 8, 24)], [60, 6])
        self.assertLess(datetime(2026, 8, 23).date(), calibration.TRAIN_BEFORE)
        self.assertEqual(records["5"][0][0], begin)
        with self.assertRaises(ValueError):
            calibration._aggregate(records, -3, source_time_convention="utc")


class MetaSettranCalibrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.csv_file = Path(temporary.name) / "measurements.csv"
        self.rows = []
        for day, cars in (("2026-06-30", 10), ("2026-07-07", 20), ("2026-07-21", 30),
                          ("2026-08-11", 40), ("2026-08-18", 50),
                          ("2026-08-25", 60), ("2026-09-01", 70)):
            begin = datetime.fromisoformat(day + "T14:45:00")
            for minute in range(210):
                start = begin + timedelta(minutes=minute)
                for sensor in calibration.SENSORS:
                    count = cars * (1 if sensor == "5" else 2)
                    self.rows.append({
                        "hora_inicio": str(start), "hora_fim": str(start + timedelta(minutes=1)),
                        "vlink_id": sensor, "descricao_linha": "fixture " + sensor,
                        "car": count, "bike": 2, "motorcycle": 3, "bus": 4,
                        "truck": 5, "person": 6, "vehicle_total": count + 9,
                        "speed_pxm": 0, "speed_pxm_max": 0,
                    })
        self.write_rows()

    def write_rows(self):
        with self.csv_file.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(self.rows)

    def test_car_only_baseline_has_explicit_civil_clock_and_valid_json(self):
        result = calibration.calibrate(self.csv_file)
        self.assertEqual(result["time"]["timezone"], "America/Sao_Paulo")
        self.assertEqual(result["time"]["offset_applied_hours"], 0)
        self.assertEqual(result["time"]["interpretation"], "brasilia")
        self.assertEqual(result["validation_dates"], ["2026-08-25"])
        self.assertEqual(result["post_validation_dates"], ["2026-09-01"])
        self.assertEqual(len(result["training_dates"]), 5)
        self.assertEqual(len(result["source"]["sha256"]), 64)
        for sensor, multiplier in (("5", 1), ("6", 2)):
            profile = result["sensors"][sensor]
            self.assertEqual(len(profile["knots"]), 14)
            self.assertAlmostEqual(profile["expected_cars_15_18"], 5400 * multiplier)
            self.assertAlmostEqual(sum(profile["target_counts"]), 5400 * multiplier)
            self.assertAlmostEqual(profile["knots"][0]["rate_per_second"], 0.5 * multiplier)
            self.assertEqual(profile["knots"][0]["n_dates"], 5)
            self.assertEqual(profile["validation"]["primary"]["daily_counts"][0]["exposure_seconds"], [900.0] * 12)
            self.assertAlmostEqual(profile["validation"]["primary"]["mae_cars_per_15min"], 450 * multiplier)
            self.assertAlmostEqual(profile["validation"]["primary"]["wape"], 0.5)
        json.dumps(result, allow_nan=False)
        self.assertEqual(result, calibration.calibrate(self.csv_file))

    def test_validation_values_never_change_training_or_dispersion(self):
        original = calibration.calibrate(self.csv_file)
        for row in self.rows:
            if row["hora_inicio"][:10] >= "2026-08-25":
                row["car"] = 9000
                row["vehicle_total"] = 9009
        self.write_rows()
        changed = calibration.calibrate(self.csv_file)
        self.assertNotEqual(original["source"]["sha256"], changed["source"]["sha256"])
        for sensor in calibration.SENSORS:
            for field in ("knots", "training_curves", "expected_cars_15_18", "target_counts", "training_cars_15_18_dispersion", "daily_fraction_15_18"):
                self.assertEqual(original["sensors"][sensor][field], changed["sensors"][sensor][field])
            self.assertNotEqual(original["sensors"][sensor]["validation"], changed["sensors"][sensor]["validation"])

    def test_gap_excludes_the_training_date_from_both_sensors_without_zero_filling(self):
        self.rows = [row for row in self.rows if not (
            row["vlink_id"] == "6" and row["hora_inicio"] in
            ("2026-08-18 15:00:00", "2026-08-18 15:01:00")
        )]
        self.write_rows()
        result = calibration.calibrate(self.csv_file)
        self.assertEqual(result["excluded_training_dates"], ["2026-08-18"])
        self.assertEqual(len(result["training_dates"]), 4)
        self.assertEqual(result["quality"]["gaps"]["6"]["n"], 7)
        self.assertAlmostEqual(result["sensors"]["5"]["expected_cars_15_18"], 25 * 180)
        self.assertEqual(result["sensors"]["6"]["knots"][1]["n_dates"], 4)

    def test_long_interval_is_removed_from_counts_and_exposure(self):
        long = dict(next(row for row in self.rows if row["vlink_id"] == "6" and row["hora_inicio"] == "2026-08-18 15:00:00"))
        long.update(hora_fim="2026-08-18 15:03:00", car=90000, vehicle_total=90009)
        self.rows = [row for row in self.rows if not (
            row["vlink_id"] == "6" and "2026-08-18 15:00:00" <= row["hora_inicio"] < "2026-08-18 15:03:00"
        )]
        self.rows.append(long)
        self.write_rows()
        result = calibration.calibrate(self.csv_file)
        self.assertEqual(result["quality"]["excluded_long_intervals"], 1)
        self.assertEqual(result["excluded_training_dates"], ["2026-08-18"])
        self.assertAlmostEqual(result["sensors"]["6"]["expected_cars_15_18"], 50 * 180)

    def test_absent_holdout_bin_is_unknown_and_is_not_scored_as_zero(self):
        self.rows = [row for row in self.rows if not (
            row["vlink_id"] == "5" and "2026-08-25 15:00:00" <= row["hora_inicio"] < "2026-08-25 15:15:00"
        )]
        self.write_rows()
        primary = calibration.calibrate(self.csv_file)["sensors"]["5"]["validation"]["primary"]
        self.assertEqual(primary["n_windows"], 11)
        self.assertEqual(primary["excluded_windows"], 1)
        self.assertIsNone(primary["daily_counts"][0]["counts"][0])
        self.assertFalse(primary["daily_counts"][0]["eligible"][0])
        self.assertEqual(primary["daily_counts"][0]["exposure_seconds"][0], 0)
        self.assertAlmostEqual(primary["wape"], 0.5)

    def test_partial_holdout_exposure_is_explicit_and_raw_counts_are_not_expanded(self):
        # Thirty missing seconds remain eligible; validation explicitly records
        # raw exposure/count and the separately named normalized estimate.
        row = next(row for row in self.rows if row["vlink_id"] == "5" and row["hora_inicio"] == "2026-08-25 15:00:00")
        row.update(hora_inicio="2026-08-25 15:00:30", car=30, vehicle_total=39)
        self.write_rows()
        primary = calibration.calibrate(self.csv_file)["sensors"]["5"]["validation"]["primary"]
        observation = primary["observations"][0]
        self.assertEqual(observation["exposure_seconds"], 870)
        self.assertEqual(observation["observed_cars"], 870)
        self.assertEqual(observation["observed_cars_normalized_15min"], 900)
        self.assertEqual(primary["daily_counts"][0]["counts"][0], 870)

    def test_coverage_threshold_is_inclusive_at_exactly_95_percent(self):
        row = next(row for row in self.rows if row["vlink_id"] == "6" and row["hora_inicio"] == "2026-08-18 15:00:00")
        row.update(hora_inicio="2026-08-18 15:00:45", car=25, vehicle_total=34)
        self.write_rows()
        included = calibration.calibrate(self.csv_file)
        self.assertIn("2026-08-18", included["training_dates"])
        row.update(hora_inicio="2026-08-18 15:00:46", car=24, vehicle_total=33)
        self.write_rows()
        excluded = calibration.calibrate(self.csv_file)
        self.assertNotIn("2026-08-18", excluded["training_dates"])
        self.assertEqual(excluded["excluded_training_dates"], ["2026-08-18"])

    def test_intervals_crossing_quarter_boundaries_conserve_uniform_flow(self):
        for row in self.rows:
            row["hora_inicio"] = str(datetime.fromisoformat(row["hora_inicio"]) + timedelta(seconds=30))
            row["hora_fim"] = str(datetime.fromisoformat(row["hora_fim"]) + timedelta(seconds=30))
        self.write_rows()
        result = calibration.calibrate(self.csv_file)
        self.assertEqual(len(result["training_dates"]), 5)
        for sensor, multiplier in (("5", 1), ("6", 2)):
            profile = result["sensors"][sensor]
            self.assertAlmostEqual(profile["expected_cars_15_18"], 5400 * multiplier)
            self.assertEqual(profile["validation"]["primary"]["daily_counts"][0]["counts"], [900 * multiplier] * 12)

    def test_duplicates_overlap_and_invalid_count_conventions_are_rejected(self):
        self.rows.append(dict(self.rows[0]))
        self.write_rows()
        with self.assertRaisesRegex(ValueError, "Duplicata ou sobreposição"):
            calibration.calibrate(self.csv_file)
        self.rows.pop()
        self.rows[0]["vehicle_total"] += 1
        self.write_rows()
        with self.assertRaisesRegex(ValueError, "vehicle_total"):
            calibration.calibrate(self.csv_file)

    def test_insufficient_training_cannot_create_a_calibrated_profile(self):
        self.rows = [row for row in self.rows if row["hora_inicio"][:10] not in
                     ("2026-06-30", "2026-07-07", "2026-07-21")]
        self.write_rows()
        with self.assertRaisesRegex(ValueError, "pelo menos três terças"):
            calibration.calibrate(self.csv_file)

    def test_linear_interpolation_preserves_continuity_and_integrates_peaks(self):
        knots = [{"week_second": 0, "rate_per_second": 0},
                 {"week_second": 900, "rate_per_second": 2},
                 {"week_second": 1800, "rate_per_second": 0}]
        self.assertAlmostEqual(calibration.interpolate_rate(knots, 450), 1)
        self.assertAlmostEqual(calibration.interpolate_rate(knots, 900), 2)
        self.assertAlmostEqual(calibration.interpolate_rate(knots, 900 - 1e-5),
                               calibration.interpolate_rate(knots, 900 + 1e-5))
        self.assertAlmostEqual(calibration.integrate_rate(knots, 0, 1800), 1800)
        self.assertAlmostEqual(calibration.integrate_rate(knots, 450, 1350), 1350)
        with self.assertRaises(ValueError):
            calibration.interpolate_rate(knots, -1)
        with self.assertRaises(ValueError):
            calibration.integrate_rate(knots, 900, 0)

    def test_daily_transfer_requires_whole_days_and_separates_car_from_motorized(self):
        day = datetime.fromisoformat("2026-07-07").date()
        midnight = datetime.combine(day, datetime.min.time())
        bins = {midnight + timedelta(minutes=15 * i): (900, 10) for i in range(96)}
        classes = {str(day): {"car": 960, "motorcycle": 120, "bus": 60, "truck": 60}}
        result = calibration._daily_fraction(bins, [day], classes)
        self.assertEqual(result["median"], .125)
        self.assertEqual(result["car_fraction_motorized_median"], .8)
        bins[midnight] = (899, 10)
        incomplete = calibration._daily_fraction(bins, [day], classes)
        self.assertIsNone(incomplete["median"])
        self.assertEqual(incomplete["dates"], [])

    def test_class_composition_is_prorated_at_midnight_like_car_exposure(self):
        self.rows = [dict(self.rows[0], vlink_id=sensor,
                          hora_inicio="2026-07-06 23:59:30", hora_fim="2026-07-07 00:00:30")
                     for sensor in calibration.SENSORS]
        self.write_rows()
        _, quality, _ = calibration._read_measurements(self.csv_file)
        for sensor in calibration.SENSORS:
            classes = quality["training_tuesday_class_sums"][sensor]["2026-07-07"]
            self.assertEqual(classes["car"], 5)
            self.assertEqual(classes["motorcycle"], 1.5)

    def test_utc_sensitivity_prorates_classes_on_the_shifted_civil_day(self):
        template = self.rows[0]
        self.rows = [dict(template, vlink_id=sensor, car=cars, vehicle_total=cars + 9,
                          hora_inicio=f"2026-07-{day:02} 02:59:30",
                          hora_fim=f"2026-07-{day:02} 03:00:30")
                     for sensor in calibration.SENSORS for day, cars in ((7, 10), (8, 20))]
        self.write_rows()
        records, quality, _ = calibration._read_measurements(self.csv_file, class_offset_hours=-3)
        for sensor in calibration.SENSORS:
            classes = quality["training_tuesday_class_sums"][sensor]
            self.assertEqual(list(classes), ["2026-07-07"])
            self.assertEqual(classes["2026-07-07"]["car"], 15)
            self.assertEqual(classes["2026-07-07"]["motorcycle"], 3)
            self.assertEqual(records[sensor][0][0], datetime(2026, 7, 7, 2, 59, 30))


class MetaSettranWeeklyCalibrationTests(unittest.TestCase):
    """A agregação/leitura já é exercitada acima; aqui isolamos o modelo semanal."""

    def setUp(self):
        self.bins = {sensor: {} for sensor in calibration.SENSORS}
        for monday, factor in (("2026-07-06", 1), ("2026-07-13", 2), ("2026-07-20", 4),
                               ("2026-08-24", 10), ("2026-08-31", 20)):
            for weekday in range(7):
                midnight = datetime.fromisoformat(monday) + timedelta(days=weekday)
                for quarter in range(96):
                    stamp = midnight + timedelta(minutes=quarter * 15)
                    count = factor * (weekday + 1) * (1 + quarter // 12)
                    for sensor in calibration.SENSORS:
                        self.bins[sensor][stamp] = (900, count * (1 if sensor == "5" else 2))
        self.read_patch = patch.object(calibration, "_read_measurements", return_value=({}, {}, "fixture"))
        self.aggregate_patch = patch.object(calibration, "_aggregate", side_effect=lambda *_, **__: self.bins)
        self.read_patch.start()
        self.aggregate_patch.start()
        self.addCleanup(self.read_patch.stop)
        self.addCleanup(self.aggregate_patch.stop)

    def test_week_is_cyclic_and_all_contexts_have_distinct_observed_support(self):
        result = calibration.calibrate_weekly()
        self.assertEqual(result["time"]["offset_applied_hours"], -3)
        self.assertEqual(len(result["training_dates"]), 21)
        for sensor in calibration.SENSORS:
            knots = result["sensors"][sensor]["knots"]
            self.assertEqual(len(knots), 674)
            self.assertEqual(knots[0]["week_second"], -450)
            self.assertEqual(knots[-1]["week_second"], calibration.WEEK_SECONDS + 450)
            self.assertEqual(knots[0]["rate_per_second"], knots[-2]["rate_per_second"])
            self.assertAlmostEqual(calibration.interpolate_rate(knots, 0),
                                   calibration.interpolate_rate(knots, calibration.WEEK_SECONDS))
            self.assertTrue(all(knot["n_dates"] == 3 for knot in knots))
        totals = []
        for weekday in range(7):
            for section in range(8):
                result_window = calibration.weekly_window(result, weekday * 86400 + section * 10800, 10800)
                profile = result_window["sensors"]["5"]
                self.assertEqual(len(profile["target_counts"]), 12)
                self.assertAlmostEqual(sum(profile["target_counts"]), profile["expected_cars"])
                totals.append(profile["expected_cars"])
        self.assertEqual(len(totals), 56)
        self.assertGreater(len(set(totals)), 30)

    def test_training_support_excludes_holdout_and_partial_windows(self):
        missing = datetime(2026, 7, 7, 15)
        del self.bins["5"][missing]
        result = calibration.calibrate_weekly()
        selected = calibration.weekly_window(result, calibration.START_WEEK_SECOND, 10800)
        support = selected["sensors"]["5"]["training_support"]
        self.assertEqual(support["complete_observed_windows"], 2)
        self.assertEqual(support["eligible_observed_quarters"], 35)
        self.assertEqual(support["joint_training_dates_per_quarter_min"], 2)
        self.assertEqual(support["joint_training_dates_per_quarter_max"], 3)
        self.assertEqual(support["normalized_car_count_statistics"]["n_dates"], 2)

    def test_clock_anomaly_is_reported_without_changing_hours_or_counts(self):
        for sensor in calibration.SENSORS:
            for timestamp in self.bins[sensor]:
                if timestamp.hour == 6:
                    self.bins[sensor][timestamp] = (900, .1)
        result = calibration.calibrate_weekly()
        evidence = result["training_clock_evidence"]["sensors"]["6"]
        self.assertTrue(all(day["morning_minimum_requires_civil_context_review"] for day in evidence))
        self.assertTrue(all(day["median_hourly_minimum_hour"] == 6 for day in evidence))
        self.assertEqual(result["time"]["offset_applied_hours"], -3)
        knot = next(k for k in result["sensors"]["6"]["knots"] if k["week_second"] == 6*3600+450)
        self.assertAlmostEqual(knot["rate_per_second"], .1/900)
        json.dumps(result, allow_nan=False)

    def test_validation_is_reserved_before_fitting_and_before_resampling(self):
        original = calibration.calibrate_weekly(variation=7)
        for sensor in calibration.SENSORS:
            for stamp, (exposure, cars) in list(self.bins[sensor].items()):
                if stamp.date() >= calibration.TRAIN_BEFORE:
                    self.bins[sensor][stamp] = (exposure, cars * 100)
        changed = calibration.calibrate_weekly(variation=7)
        self.assertEqual(original["realization"], changed["realization"])
        for sensor in calibration.SENSORS:
            for field in ("knots", "realization_knots", "baseline_reference_cars_15_18"):
                self.assertEqual(original["sensors"][sensor][field], changed["sensors"][sensor][field])
        before_window = calibration.weekly_window(original, calibration.START_WEEK_SECOND, 10800)
        after_window = calibration.weekly_window(changed, calibration.START_WEEK_SECOND, 10800)
        self.assertNotEqual(before_window["sensors"]["5"]["validation"],
                            after_window["sensors"]["5"]["validation"])
        self.assertTrue(set(original["training_dates"]).isdisjoint(original["validation_dates"]))

    def test_joint_full_day_bootstrap_preserves_sensor_and_time_dependence(self):
        result = calibration.calibrate_weekly(variation=7)
        for item in result["realization"]["sampled_days"]:
            self.assertEqual(item["joint_observed_bins"], 96)
            self.assertEqual(item["baseline_fallback_bins"], 0)
        for first, second in zip(result["sensors"]["5"]["realization_knots"],
                                 result["sensors"]["6"]["realization_knots"]):
            self.assertEqual(first["source_date"], second["source_date"])
            self.assertAlmostEqual(second["rate_per_second"], 2 * first["rate_per_second"])
            stamp = datetime.fromisoformat(first["source_date"]) + timedelta(
                seconds=(first["week_second"] % 86400) - 450)
            self.assertEqual(first["rate_per_second"], self.bins["5"][stamp][1] / 900)
        repeated = calibration.calibrate_weekly(variation=7)
        self.assertEqual(result, repeated)

    def test_twenty_five_ids_and_explicit_seed_are_deterministic(self):
        results = [calibration.calibrate_weekly(variation=index) for index in range(1, 26)]
        self.assertEqual(len({result["realization"]["seed"] for result in results}), 25)
        self.assertGreater(len({tuple(item["date"] for item in result["realization"]["sampled_days"])
                                for result in results}), 1)
        first = calibration.calibrate_weekly(variation=1, seed=42)
        second = calibration.calibrate_weekly(variation=25, seed=42)
        self.assertEqual(first["realization"]["sampled_days"], second["realization"]["sampled_days"])
        for invalid in (0, 26, True, 1.5):
            with self.assertRaises(ValueError):
                calibration.calibrate_weekly(variation=invalid)

    def test_gap_excludes_the_observation_not_as_zero_and_fallback_is_flagged(self):
        missing = datetime(2026, 7, 7, 15)
        del self.bins["6"][missing]
        result = calibration.calibrate_weekly()
        knot = next(knot for knot in result["sensors"]["5"]["knots"]
                    if knot["week_second"] == calibration.START_WEEK_SECOND + 450)
        self.assertEqual(knot["n_dates"], 2)
        self.assertEqual(knot["donor_dates"], ["2026-07-14", "2026-07-21"])
        self.assertGreater(knot["rate_per_second"], 0)
        chosen = result["realization"]["sampled_days"][1]
        self.assertNotIn("2026-07-07", chosen["complete_candidate_dates"])
        for sensor in calibration.SENSORS:
            for stamp in list(self.bins[sensor]):
                if stamp.weekday() == 0 and stamp.date() < calibration.TRAIN_BEFORE:
                    del self.bins[sensor][stamp]
        fallback = calibration.calibrate_weekly()
        self.assertEqual(fallback["sensors"]["5"]["knots"][1]["status"],
                         "hypothesis_other_weekdays_same_clock")
        self.assertEqual(fallback["realization"]["sampled_days"][0]["baseline_fallback_bins"], 96)

    def test_consecutive_sections_and_week_wrap_share_the_same_realization(self):
        result = calibration.calibrate_weekly(variation=7)
        for begin in (86400 + 15 * 3600, 4 * 86400 + 21 * 3600, 6 * 86400 + 21 * 3600):
            combined = calibration.weekly_window(result, begin, 21600)
            left = calibration.weekly_window(result, begin, 10800)
            right = calibration.weekly_window(result, begin + 10800, 10800)
            self.assertEqual(combined["selection"]["end_week_second"], begin + 21600)
            for sensor in calibration.SENSORS:
                profile = combined["sensors"][sensor]
                self.assertEqual(len(profile["target_counts"]), 24)
                for field in ("knots", "realization_knots"):
                    boundary = begin + 10800
                    self.assertAlmostEqual(calibration.interpolate_rate(left["sensors"][sensor][field], boundary),
                                           calibration.interpolate_rate(right["sensors"][sensor][field], boundary))
                for field in ("target_counts", "realized_target_counts"):
                    self.assertEqual(profile[field], left["sensors"][sensor][field] + right["sensors"][sensor][field])

    def test_holdout_window_crosses_real_dates_without_synthetic_day_pairing(self):
        result = calibration.calibrate_weekly()
        begin = 4 * 86400 + 21 * 3600
        friday = calibration.weekly_window(result, begin, 21600)["sensors"]["5"]["validation"]["primary"]
        self.assertEqual(friday["daily_counts"][0]["start"], "2026-08-28T21:00:00")
        self.assertEqual(friday["daily_counts"][0]["end"], "2026-08-29T03:00:00")
        self.assertEqual(friday["daily_counts"][0]["counts"], [400] * 12 + [60] * 12)
        self.assertEqual(friday["n_windows"], 24)
        sunday = calibration.weekly_window(result, 6 * 86400 + 21 * 3600, 21600)
        primary = sunday["sensors"]["5"]["validation"]["primary"]
        self.assertEqual(primary["daily_counts"][0]["eligible"], [True] * 12 + [False] * 12)
        self.assertEqual(primary["n_windows"], 12)
        del self.bins["5"][datetime(2026, 8, 28, 21)]
        changed = calibration.weekly_window(calibration.calibrate_weekly(), begin, 21600)
        primary = changed["sensors"]["5"]["validation"]["primary"]
        self.assertIsNone(primary["daily_counts"][0]["counts"][0])
        self.assertEqual(primary["n_windows"], 23)


if __name__ == "__main__":
    unittest.main()
