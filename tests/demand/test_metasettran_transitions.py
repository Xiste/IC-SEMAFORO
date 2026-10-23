"""Continuidade, conservação e transporte de partidas sem sorteios adicionais."""

import copy
import math
import random
import unittest

from SistemaDeSemaforos.demand.metasettran_transitions import (
    _Curve,
    compose_rate_curves,
    transport_times,
)


def curve(begin, rates, step=900):
    return [dict(week_second=begin + index * step, rate_per_second=rate)
            for index, rate in enumerate(rates)]


def constant(begin, rate, duration=10800):
    return curve(begin, [rate, rate], duration)


class CurveIntegralTests(unittest.TestCase):
    def test_analytic_triangle_and_inverse_for_increasing_and_decreasing_rates(self):
        for rates in ([0, 2], [2, 0], [2, 2], [2, 2 + 1e-12]):
            reference = _Curve(curve(604800, rates, 900))
            self.assertAlmostEqual(reference.integral(604800, 605700), sum(rates) * 450)
            for seconds in (0, .001, 1, 450, 899, 900):
                absolute = 604800 + seconds
                self.assertAlmostEqual(reference.inverse(reference.cumulative(absolute)), absolute, places=7)

    def test_zero_plateau_inverse_skips_empty_interval(self):
        reference = _Curve(curve(0, [1, 0, 0, 1], 100))
        self.assertAlmostEqual(reference.mass[-1], 100)
        self.assertEqual(reference.inverse(50), 200)
        for mass in (0, 1, 49, 50, 51, 99, 100):
            self.assertAlmostEqual(reference.cumulative(reference.inverse(mass)), mass)

    def test_invalid_rates_and_support_rejected(self):
        for knots in (curve(0, [1]), curve(0, [1, -1]), curve(0, [1, float("nan")]),
                      curve(0, [1, 1], 0), curve(float("inf"), [1, 1])):
            with self.subTest(knots=knots), self.assertRaises(ValueError):
                _Curve(knots)
        reference = _Curve(constant(0, 1))
        for second in (-1, 10801, float("nan")):
            with self.assertRaises(ValueError):
                reference.rate(second)
        for mass in (-1, 10801, float("nan")):
            with self.assertRaises(ValueError):
                reference.inverse(mass)


class TransitionCompositionTests(unittest.TestCase):
    def assert_mass_preserved(self, originals, starts, combined, diagnostics):
        composed = _Curve(combined)
        expected = 0.0
        for knots, begin in zip(originals, starts):
            original = _Curve(knots)
            value = original.integral(begin, begin + 10800)
            expected += value
            self.assertAlmostEqual(composed.integral(begin, begin + 10800), value, places=7)
        self.assertAlmostEqual(composed.mass[-1], expected, places=7)
        self.assertAlmostEqual(diagnostics["expected_after"], expected, places=7)
        for row in diagnostics["boundaries"]:
            for side in ("left", "right"):
                self.assertAlmostEqual(row[f"expected_{side}_half_window_before"],
                                       row[f"expected_{side}_half_window_after"], places=7)
            self.assertEqual([window["seconds"] for window in row["windows"]], [300, 900])
        self.assertTrue(all(knot["rate_per_second"] >= 0 for knot in combined))
        self.assertTrue(all(right["week_second"] > left["week_second"]
                            for left, right in zip(combined, combined[1:])))

    def test_unequal_realizations_join_without_mass_inflation_or_input_mutation(self):
        starts = [0, 10800]
        originals = [curve(0, [1, 2, 3, 4, 2, 1, 2, 3, 5, 8, 6, 4, 2]),
                     curve(10800, [5, 4, 3, 6, 2, 1, 3, 4, 2, 1, 2, 1, 0])]
        saved = copy.deepcopy(originals)
        combined, diagnostics = compose_rate_curves(originals, starts)
        self.assertEqual(originals, saved)
        self.assert_mass_preserved(originals, starts, combined, diagnostics)
        result = _Curve(combined)
        self.assertAlmostEqual(result.rate(10800 - 1e-6), result.rate(10800 + 1e-6), places=6)
        self.assertNotAlmostEqual(diagnostics["boundaries"][0]["original_left_rate_per_second"],
                                  diagnostics["boundaries"][0]["original_right_rate_per_second"])
        for index, begin in enumerate(starts):
            reference = _Curve(originals[index])
            for second in range(begin + 900, begin + 9901, 137):
                self.assertAlmostEqual(result.rate(second), reference.rate(second), places=12)

    def test_continuous_original_is_not_deformed(self):
        originals = [curve(0, [1, 3, 2], 5400), curve(10800, [2, 4, 1], 5400)]
        combined, diagnostics = compose_rate_curves(originals, [0, 10800])
        self.assertEqual(combined, originals[0] + originals[1][1:])
        self.assertFalse(diagnostics["boundaries"][0]["changed"])

    def test_single_section_and_week_wrap_do_not_apply_modulo_or_change_rates(self):
        begin = 604800 - 10800
        original = curve(begin - 450, [index / 10 for index in range(14)])
        combined, diagnostics = compose_rate_curves([original], [begin])
        self.assertEqual(combined, _Curve(original).clip(begin, 604800))
        self.assertEqual(diagnostics["boundaries"], [])
        pair = [constant(begin, .1), constant(604800, 1)]
        combined, diagnostics = compose_rate_curves(pair, [begin, 604800])
        self.assertEqual(combined[-1]["week_second"], 615600)
        self.assert_mass_preserved(pair, [begin, 604800], combined, diagnostics)

    def test_extreme_constant_jump_has_bounded_and_reported_compensation(self):
        originals = [constant(0, 1), constant(10800, 100)]
        combined, diagnostics = compose_rate_curves(originals, [0, 10800])
        self.assert_mass_preserved(originals, [0, 10800], combined, diagnostics)
        row = diagnostics["boundaries"][0]
        self.assertLessEqual(row["peak_rate_after_per_second"], 100.000000001)
        self.assertAlmostEqual(row["peak_rate_ratio_after_before"], 1)
        self.assertAlmostEqual(row["peak_rate_ratio_after_before"],
                               row["peak_rate_after_per_second"] / 100)

    def test_empty_context_stays_empty_at_transition(self):
        for rates in ((0, 0),):
            originals = [constant(0, rates[0]), constant(10800, rates[1])]
            combined, diagnostics = compose_rate_curves(originals, [0, 10800])
            self.assert_mass_preserved(originals, [0, 10800], combined, diagnostics)
            for index, rate in enumerate(rates):
                if rate == 0:
                    self.assertEqual(_Curve(combined).integral(index * 10800, (index + 1) * 10800), 0)

    def test_impossible_zero_to_constant_transition_is_rejected_without_hidden_peak(self):
        # A constant positive half-window cannot both retain its full area and
        # join zero continuously without exceeding its own peak. Fail explicitly.
        for rates in ((0, 2), (2, 0)):
            with self.assertRaisesRegex(ValueError, "sem ponte contínua"):
                compose_rate_curves([constant(0, rates[0]), constant(10800, rates[1])], [0, 10800])

    def test_narrow_peak_uses_positive_bridge_when_fixed_midpoint_is_impossible(self):
        # Future support finer than 15 minutes must not turn a narrow pulse into
        # negative rates just to reconcile the endpoint with its small integral.
        left = curve(0, [0, 0], 10800)
        right = [dict(week_second=10800, rate_per_second=10),
                 dict(week_second=10801, rate_per_second=0),
                 dict(week_second=11699, rate_per_second=0),
                 dict(week_second=11700, rate_per_second=10),
                 dict(week_second=21600, rate_per_second=10)]
        combined, diagnostics = compose_rate_curves([left, right], [0, 10800])
        self.assert_mass_preserved([left, right], [0, 10800], combined, diagnostics)
        self.assertLessEqual(max(row["rate_per_second"] for row in combined), 10)

    def test_full_week_preserves_each_of_56_different_budgets(self):
        rng = random.Random(20261022)
        starts = [604800 + 10800 * index for index in range(56)]
        originals = [curve(begin, [rng.uniform(.001, 8) for _ in range(13)]) for begin in starts]
        combined, diagnostics = compose_rate_curves(originals, starts)
        self.assertEqual(len(diagnostics["boundaries"]), 55)
        self.assertEqual(len(diagnostics["sections"]), 56)
        self.assertEqual(combined[-1]["week_second"], 1209600)
        self.assert_mass_preserved(originals, starts, combined, diagnostics)

    def test_rejects_discontinuous_overlapping_or_invalid_selections(self):
        originals = [constant(0, 1), constant(10800, 2)]
        for starts in ([0], [0, 10799], [0, 10801], [10800, 0], [0, float("nan")]):
            with self.subTest(starts=starts), self.assertRaises(ValueError):
                compose_rate_curves(originals, starts)
        for duration, half_window in ((0, 900), (10800, 0), (10800, 6000), (float("nan"), 900)):
            with self.assertRaises(ValueError):
                compose_rate_curves(originals, [0, 10800], duration, half_window)


class DepartureTransportTests(unittest.TestCase):
    def test_transport_retains_count_order_context_and_cdf_with_exterior_unchanged(self):
        originals = [constant(0, 1), constant(10800, 4)]
        combined, _ = compose_rate_curves(originals, [0, 10800])
        for index, begin in enumerate((0, 10800)):
            times = sorted([begin, begin + .001, begin + 900, begin + 9899,
                            begin + 10300, begin + 10799.999] +
                           [begin + number * 13.7 for number in range(1, 788)])
            moved = transport_times(times, originals[index], combined, begin, 10800)
            self.assertEqual(len(moved), len(times))
            self.assertEqual(moved, sorted(moved))
            self.assertGreaterEqual(min(moved), begin)
            self.assertLess(max(moved), begin + 10800)
            old, new = _Curve(originals[index]), _Curve(_Curve(combined).clip(begin, begin + 10800))
            for before, after in zip(times, moved):
                self.assertAlmostEqual(old.cumulative(before), new.cumulative(after), places=7)
                if begin + 900 <= before <= begin + 9900:
                    self.assertAlmostEqual(before, after, places=7)
            self.assertEqual(moved, transport_times(times, originals[index], combined, begin, 10800))

    def test_round_trip_recovers_original_schedule_including_absolute_week_clock(self):
        starts = [604800, 615600]
        originals = [constant(starts[0], .02), constant(starts[1], .08)]
        combined, _ = compose_rate_curves(originals, starts)
        for index, begin in enumerate(starts):
            times = [begin + offset for offset in (.001, 100, 449, 900, 3000, 9900, 10350, 10799.999)]
            moved = transport_times(times, originals[index], combined, begin, 10800)
            recovered = transport_times(moved, combined, originals[index], begin, 10800)
            for expected, actual in zip(times, recovered):
                self.assertAlmostEqual(expected, actual, places=7)

    def test_noop_transport_preserves_exact_float_values_and_accepts_empty_zero_curve(self):
        reference = constant(0, 1)
        times = [0, math.pi, 10800 - 1e-9]
        self.assertEqual(transport_times(times, reference, reference, 0, 10800), times)
        self.assertEqual(transport_times([], constant(0, 0), constant(0, 0), 0, 10800), [])
        with self.assertRaises(ValueError):
            transport_times([1], constant(0, 0), constant(0, 0), 0, 10800)

    def test_invalid_schedule_or_nonconservative_target_rejected(self):
        reference = constant(0, 1)
        for times in ([-1], [10800], [float("nan")], [2, 1]):
            with self.subTest(times=times), self.assertRaises(ValueError):
                transport_times(times, reference, reference, 0, 10800)
        with self.assertRaises(ValueError):
            transport_times([1], reference, constant(0, 2), 0, 10800)


if __name__ == "__main__":
    unittest.main()
