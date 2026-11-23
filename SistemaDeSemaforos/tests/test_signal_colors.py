import unittest

from semaforos.simulacao.cores import colors_from_trace, programmed_color_times


class SignalColorsTest(unittest.TestCase):
    def test_red_spans_multiple_phases_and_wraps_the_cycle(self):
        phases = [{'state': color, 'duration': seconds}
                  for color, seconds in [('r', 2), ('G', 10), ('y', 3), ('r', 5)]]
        expected = {'green': 10., 'yellow': 3., 'red': 7.}
        self.assertEqual(programmed_color_times(phases, 0), expected)
        events = [{'time_seconds': time, 'previous_phase': previous, 'phase_index': current}
                  for time, previous, current in [(3, 0, 1), (13, 1, 2), (16, 2, 3),
                                                  (21, 3, 0), (23, 0, 1), (33, 1, 2),
                                                  (36, 2, 3), (41, 3, 0)]]
        stats = colors_from_trace('signal', phases, events, [4, 20, 6, 10], 0, 40, 1)
        self.assertEqual(stats, {f'link_0_{name}_mean_seconds': value for name, value in expected.items()})
        self.assertEqual(colors_from_trace('signal', phases, events, [5, 19, 6, 10], 0, 40, 1), {})
