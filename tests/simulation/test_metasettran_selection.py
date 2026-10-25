"""Seleção livre e adjacência circular, sem executar o SUMO."""

import random
import unittest

from SistemaDeSemaforos.simulation.metasettran_selection import (
    group_sections, section_identifiers,
)


class SelectionTests(unittest.TestCase):
    def assert_groups(self, selection, expected, grouping=True):
        groups = group_sections(selection, grouping)
        self.assertEqual([group["selected_sections"] for group in groups], expected)
        for group in groups:
            self.assertEqual(group["sections"], len(group["selected_sections"]))
            self.assertEqual({"day": group["day"], "start": group["start"]},
                             section_identifiers(group["selected_sections"])[0])
        return groups

    def test_default_keeps_adjacent_sections_independent(self):
        self.assertEqual([group["selected_sections"] for group in group_sections([4, 2, 3])],
                         [[2], [3], [4]])
        self.assert_groups([55, 0], [[0], [55]], grouping=False)

    def test_isolated_sections_and_same_clock_on_different_days(self):
        for grouping in (False, True):
            self.assert_groups([38, 2, 20], [[2], [20], [38]], grouping)
            self.assert_groups([10, 2], [[2], [10]], grouping)

    def test_same_day_and_adjacent_days(self):
        self.assert_groups([4, 2, 3], [[2, 3, 4]])
        groups = self.assert_groups([9, 7, 8], [[7, 8, 9]])
        self.assertEqual(groups[0]["day"], "monday")
        self.assertEqual(groups[0]["start"], "21:00")

    def test_week_boundary_and_order_of_disjoint_groups(self):
        groups = self.assert_groups([0, 55], [[55, 0]])
        self.assertEqual(groups[0]["day"], "sunday")
        self.assertEqual(groups[0]["start"], "21:00")
        self.assert_groups([55, 30, 3, 29, 2], [[2, 3], [29, 30], [55]])
        self.assert_groups([0, 3, 55, 1, 29, 30], [[3], [29, 30], [55, 0, 1]])

    def test_whole_day_and_week_depend_on_grouping(self):
        for selection in (list(range(16, 24)), list(range(56))):
            self.assert_groups(selection[::-1], [selection])
            self.assert_groups(selection[::-1], [[index] for index in selection], grouping=False)
        self.assertEqual(group_sections(list(range(56)), True)[0], {
            "day": "monday", "start": "00:00", "sections": 56,
            "selected_sections": list(range(56)),
        })

    def test_identifiers_preserve_execution_order_and_inputs(self):
        selected = [55, 0, 1]
        self.assertEqual(section_identifiers(selected), [
            {"day": "sunday", "start": "21:00"},
            {"day": "monday", "start": "00:00"},
            {"day": "monday", "start": "03:00"},
        ])
        original = selected[:]
        group_sections(selected, True)
        self.assertEqual(selected, original)

    def test_invalid_selections_and_grouping_are_rejected(self):
        invalid = (None, [], (), (0,), "0", {0}, {"0": True},
                   [True], [False], [0.0], ["0"], [-1], [56], [0, 0], [0, 1, 0])
        for selection in invalid:
            for helper in (group_sections, section_identifiers):
                with self.subTest(selection=selection, helper=helper.__name__), self.assertRaises(ValueError):
                    helper(selection)
        for grouping in (None, 0, 1, "false", "true", [], {}):
            with self.subTest(grouping=grouping), self.assertRaises(ValueError):
                group_sections([0], grouping)

    def test_partitions_cover_selection_once_and_only_join_neighbors(self):
        rng = random.Random(720)
        selections = [[index] for index in range(56)]
        selections += [[index, (index + 1) % 56] for index in range(56)]
        selections += [[index for index in range(56) if index != absent] for absent in range(56)]
        selections += [rng.sample(range(56), rng.randint(1, 56)) for _ in range(300)]
        for selection in selections:
            for grouping in (False, True):
                with self.subTest(selection=selection, grouping=grouping):
                    groups = group_sections(selection, grouping)
                    flattened = [index for group in groups for index in group["selected_sections"]]
                    self.assertEqual(len(flattened), len(selection))
                    self.assertEqual(set(flattened), set(selection))
                    self.assertEqual(groups, group_sections(selection[::-1], grouping))
                    for group in groups:
                        indices = group["selected_sections"]
                        if not grouping:
                            self.assertEqual(len(indices), 1)
                        else:
                            self.assertTrue(all(right == (left + 1) % 56
                                                for left, right in zip(indices, indices[1:])))
                            if len(selection) != 56:
                                self.assertNotIn((indices[0] - 1) % 56, selection)
                                self.assertNotIn((indices[-1] + 1) % 56, selection)


if __name__ == "__main__":
    unittest.main()
