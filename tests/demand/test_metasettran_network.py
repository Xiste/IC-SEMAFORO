"""Acessos locais, ramais e cobertura de percursos na rede MetaSettran."""

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from SistemaDeSemaforos.demand.metasettran_network import (
    _midpoint, apply_local_activity_weights, coverage_candidates, expand_local_activity, terminal_branches,
)


def edge(source, target, shape, length=100, hierarchy="highway.residential"):
    return {"from": source, "to": target, "shape": shape, "length": length,
            "hierarchy": hierarchy, "lanes": {"0": None},
            "from_xy": shape[0], "to_xy": shape[-1]}


class LocalActivityTests(unittest.TestCase):
    def setUp(self):
        profiles = {kind: {"hours": [0, 24], "origin": [1, 1], "destination": [1, 1]}
                    for kind in ("weekday", "saturday", "sunday")}
        self.model = {"portals": {"entries": [], "exits": []},
            "activity_zones": [{"id": "legacy", "origins": [], "destinations": []}],
            "regional_demand": {"local_activity_distribution": {
                "version": "fixture", "method": "local_street_length_grid", "cell_size_m": 600,
                "opportunity_per_km": 1, "minimum_access_length_m": 40,
                "max_accesses_per_cell": 4, "references": ["fixture cartography"],
                "profile_zone": "legacy", "replace_activity_zones": ["legacy"]},
                "urban_activity_model": {"zones": [{"id": "legacy", "profiles": profiles}]}}}
        self.edges = {
            "a": edge("a0", "a1", [(100, 100), (200, 100)]),
            "-a": edge("a1", "a0", [(200, 103), (100, 103)]),
            "b": edge("b0", "b1", [(400, 100), (500, 100)]),
            "c": edge("c0", "c1", [(700, 100), (800, 100)])}
        self.connections = {(name, name) for name in self.edges}

    def expand(self):
        return expand_local_activity(self.model, self.edges, self.connections)

    def test_bidirectional_street_counts_once_and_opportunity_is_conserved(self):
        result = self.expand()
        summary = result["local_activity_expansion"]
        self.assertEqual(summary["local_street_length_m"], 300)
        self.assertAlmostEqual(summary["total_opportunity"], .3)
        self.assertEqual(summary["represented_cells"], 2)
        self.assertAlmostEqual(sum(z["opportunity"] for z in result["regional_demand"]["urban_activity_model"]["zones"]), .3)

    def test_experimental_weights_redistribute_opportunities_and_keep_accesses(self):
        model = self.expand()
        accesses = deepcopy(model["activity_zones"])
        opportunities = {"local_activity_0_0": .12, "local_activity_1_0": .18}
        document = {"base_spatial_sha256": "fixture", "version": "test",
                    "opportunities": opportunities}
        with TemporaryDirectory() as directory:
            path = Path(directory) / "weights.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            metadata = apply_local_activity_weights(model, path, "fixture")
            self.assertEqual(metadata, {"file": str(path.resolve()), "version": "test",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "base_spatial_sha256": "fixture"})
        self.assertEqual(model["activity_zones"], accesses)
        expansion = model["local_activity_expansion"]
        self.assertAlmostEqual(expansion["total_opportunity"], .3)
        self.assertEqual({c["zone_id"]: c["opportunity"] for c in expansion["cells"]}, opportunities)
        self.assertEqual({z["id"]: z["opportunity"]
                          for z in model["regional_demand"]["urban_activity_model"]["zones"]}, opportunities)

    def test_invalid_experimental_weights_are_rejected_before_reassignment(self):
        original = self.expand()
        document = {"base_spatial_sha256": "fixture", "version": "test",
                    "opportunities": {"local_activity_0_0": .12, "local_activity_1_0": .18}}
        invalid = (
            {"base_spatial_sha256": "other"},
            {"version": ""},
            {"opportunities": {"local_activity_0_0": .3}},
            {"opportunities": {"local_activity_0_0": .2, "local_activity_1_0": .2}},
            {"opportunities": {"local_activity_0_0": 0, "local_activity_1_0": .3}},
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "weights.json"
            for override in invalid:
                with self.subTest(override=override):
                    path.write_text(json.dumps(document | override), encoding="utf-8")
                    model = deepcopy(original)
                    with self.assertRaises(ValueError):
                        apply_local_activity_weights(model, path, "fixture")
                    self.assertEqual(model, original)

    def test_extra_gates_do_not_multiply_zone_opportunity(self):
        original = self.expand()
        self.model["regional_demand"]["local_activity_distribution"]["max_accesses_per_cell"] = 1
        changed = self.expand()
        self.assertGreater(original["local_activity_expansion"]["accesses_per_role"],
                           changed["local_activity_expansion"]["accesses_per_role"])
        self.assertEqual(original["local_activity_expansion"]["total_opportunity"],
                         changed["local_activity_expansion"]["total_opportunity"])

    def test_splitting_a_street_preserves_its_exposure_and_opportunity(self):
        original = self.expand()["local_activity_expansion"]["total_opportunity"]
        del self.edges["b"]
        self.edges.update({"b#0": edge("b0", "bm", [(400, 100), (450, 100)], 50),
                           "b#1": edge("bm", "b1", [(450, 100), (500, 100)], 50)})
        self.connections = {(name, name) for name in self.edges}
        self.assertEqual(self.expand()["local_activity_expansion"]["total_opportunity"], original)

    def test_functional_hierarchy_and_boundary_connectivity_filter_accesses(self):
        self.model["regional_demand"]["road_hierarchy_overrides"] = {"b": "highway.primary"}
        self.model["portals"]["entries"] = [{"edge": "c"}]
        self.connections = {("a", "-a"), ("-a", "a"), ("a", "b"), ("c", "a")}
        result = self.expand()
        accesses = {g["edge"] for z in result["activity_zones"] for g in z["origins"]}
        self.assertEqual(accesses, {"a", "-a"})
        self.assertEqual(result["local_activity_expansion"]["eligible_directed_edges"], 2)

    def test_named_activity_access_is_not_reused_by_local_cells(self):
        self.model["activity_zones"].append({"id": "school", "origins": [{"edge": "b"}], "destinations": []})
        result = self.expand()
        for zone in result["activity_zones"]:
            if zone["id"].startswith("local_activity_"):
                self.assertNotIn("b", {g["edge"] for g in zone["origins"]})
        self.assertEqual(result["local_activity_expansion"]["local_street_length_m"], 200)

    def test_midpoint_follows_length_instead_of_vertex_count(self):
        self.assertEqual(_midpoint([(0, 0), (1, 0), (2, 0), (100, 0)]), [50, 0])
        self.assertEqual(_midpoint([(0, 0), (0, 100), (100, 100)]), [0, 100])
        with self.assertRaises(ValueError):
            _midpoint([(0, 0), (0, 0)])

    def test_expansion_is_deterministic_idempotent_and_preserves_source_evidence(self):
        before = deepcopy(self.model)
        result = self.expand()
        self.assertEqual(self.model, before)
        self.assertEqual(result, self.expand())
        self.assertIs(expand_local_activity(result, self.edges, self.connections), result)
        self.assertNotIn("legacy", {z["id"] for z in result["activity_zones"]})
        self.assertNotIn("legacy", {z["id"] for z in result["regional_demand"]["urban_activity_model"]["zones"]})
        self.assertIn("legacy", {z["id"] for z in self.model["activity_zones"]})

    def test_short_streets_have_no_forced_access_and_are_reported(self):
        self.edges["c"]["length"] = 20
        result = self.expand()
        self.assertEqual(result["local_activity_expansion"]["cells_without_admissible_access"],
                         [{"cell": [1, 0], "local_street_length_m": 20}])
        self.assertEqual(result["local_activity_expansion"]["represented_local_street_length_m"], 200)
        self.assertEqual(result["local_activity_expansion"]["total_opportunity"], .2)

    def test_nonfinite_or_out_of_range_parameters_are_rejected(self):
        policy = self.model["regional_demand"]["local_activity_distribution"]
        for key, value in (("cell_size_m", 0), ("cell_size_m", math.nan),
                           ("opportunity_per_km", math.inf), ("opportunity_per_km", True),
                           ("minimum_access_length_m", -1), ("max_accesses_per_cell", 0),
                           ("max_accesses_per_cell", 9), ("max_accesses_per_cell", True)):
            with self.subTest(key=key, value=value):
                previous = policy[key]
                policy[key] = value
                with self.assertRaises(ValueError):
                    self.expand()
                policy[key] = previous

    def test_no_eligible_street_or_missing_geography_is_not_silently_accepted(self):
        with self.assertRaisesRegex(ValueError, "Nenhuma célula"):
            expand_local_activity(self.model, self.edges, set())
        self.edges["a"]["shape"] = []
        self.edges["a"]["from_xy"] = None
        with self.assertRaisesRegex(ValueError, "coordenadas"):
            self.expand()

    def test_disabled_policy_keeps_legacy_models_compatible(self):
        del self.model["regional_demand"]["local_activity_distribution"]
        self.assertIs(self.expand(), self.model)

    def test_terminal_frontage_has_directional_access_without_new_opportunity(self):
        self.edges={
            'b':edge('A','B',[(100,100),(500,100)],400),
            'c':edge('B','C',[(500,100),(300,500)],450),
            'd':edge('C','A',[(300,500),(100,100)],450),
            'a':edge('A','L',[(100,100),(-100,100)],200),
            '-a':edge('L','A',[(-100,103),(100,103)],200)}
        self.connections={('b','c'),('c','d'),('d','b'),('d','a'),('a','-a'),('-a','b')}
        policy=self.model['regional_demand']['local_activity_distribution'];policy['max_accesses_per_cell']=1
        before=self.expand();policy['include_terminal_accesses']=True;after=self.expand()
        self.assertAlmostEqual(before['local_activity_expansion']['total_opportunity'],after['local_activity_expansion']['total_opportunity'])
        zone=next(z for z in after['activity_zones'] if z['id']=='local_activity_0_0')
        self.assertIn('-a',{g['edge'] for g in zone['origins']})
        self.assertIn('a',{g['edge'] for g in zone['destinations']})
        self.assertEqual(len(zone['origins']),2)
        self.assertEqual(len(zone['destinations']),2)

    def test_intrazonal_policy_is_explicit_and_boolean(self):
        policy=self.model['regional_demand']['local_activity_distribution']
        policy['allow_intrazonal_trips']=True
        self.assertTrue(all(z['allow_intrazonal_trips'] for z in self.expand()['activity_zones']))
        for key in ('allow_intrazonal_trips','include_terminal_accesses'):
            policy[key]='yes'
            with self.assertRaises(ValueError):self.expand()
            policy[key]=False

    def test_directional_terminal_accesses_require_a_normal_connection_on_one_side(self):
        a, b, c, d = (100, 100), (500, 100), (300, 300), (300, 500)
        self.edges = {
            "a": edge("A", "B", [a, b]), "-a": edge("B", "A", [b, a]),
            "ac": edge("A", "C", [a, c]), "cb": edge("C", "B", [c, b]),
            "bd": edge("B", "D", [b, d]), "da": edge("D", "A", [d, a]),
        }
        self.connections = {("ac", "cb"), ("cb", "bd"), ("bd", "da"), ("da", "ac"),
                            ("da", "a"), ("a", "-a"), ("-a", "ac")}
        policy = self.model["regional_demand"]["local_activity_distribution"]
        policy.update(max_accesses_per_cell=1, include_terminal_accesses=True)
        before = self.expand()
        policy["directional_terminal_edges"] = ["-a", "a"]
        after = self.expand()
        self.assertEqual(after["local_activity_expansion"]["directional_terminal_accesses"], [
            {"edge": "-a", "role": "origins", "return_edge": "a"},
            {"edge": "a", "role": "destinations", "return_edge": "-a"},
        ])
        self.assertEqual(after["local_activity_expansion"]["total_opportunity"],
                         before["local_activity_expansion"]["total_opportunity"])
        self.connections.update({("a", "bd"), ("cb", "-a")})
        with self.assertRaisesRegex(ValueError, "sem restrição de retorno"):
            self.expand()


class RouteCoverageTests(unittest.TestCase):
    def setUp(self):
        self.edges = {name: {"time": time, "length": length, "hierarchy": "highway.residential"}
                      for name, time, length in (("a",10,100),("b",10,100),("c",10,100),("gap",12,120))}
        self.connections = {("a","b"),("b","c"),("a","gap"),("gap","c")}
        self.costs = {pair:(0,0) for pair in self.connections}
        self.pairs = {"base":{"origin":"a","destination":"c","route":["a","b","c"],
                              "urban_generalized_cost_s":30,"length_m":300}}

    def candidates(self, **kwargs):
        return coverage_candidates(self.edges,self.connections,self.costs,self.pairs,
            cost_factors={},hierarchy_overrides={},max_cost_ratio=1.35,max_length_ratio=1.5,**kwargs)

    def test_origin_destination_and_connection_costs_are_counted_once(self):
        self.costs["a","gap"]=(20,2)
        candidates,review=self.candidates()
        self.assertEqual(len(candidates),1)
        self.assertEqual(candidates[0]["via"],["gap"])
        self.assertAlmostEqual(candidates[0]["lower_bound_cost_ratio"],34/30)
        self.assertAlmostEqual(candidates[0]["lower_bound_length_ratio"],340/300)
        self.assertEqual(review["edges"][0]["status"],"native_validation_required")

    def test_unreachable_is_separate_from_an_excessive_detour(self):
        self.edges["isolated"]={"time":1,"length":1,"hierarchy":"highway.residential"}
        self.edges["gap"]["time"]=100
        candidates,review=self.candidates()
        self.assertFalse(candidates)
        rows={r["edge"]:r for r in review["edges"]}
        self.assertEqual(rows["isolated"]["status"],"no_directed_path_between_current_endpoints")
        self.assertEqual(rows["gap"]["status"],"outside_detour_limits_for_current_endpoints")
        self.assertGreater(rows["gap"]["reachable_endpoint_pairs"],0)

    def test_independent_lower_bounds_do_not_claim_joint_feasibility(self):
        self.edges.update({"a":{"time":1,"length":1,"hierarchy":"highway.residential"},
                           "b":{"time":10,"length":10,"hierarchy":"highway.residential"},
                           "c":{"time":1,"length":1,"hierarchy":"highway.residential"},
                           "gap":{"time":1,"length":1,"hierarchy":"highway.residential"},
                           "long":{"time":1,"length":1000,"hierarchy":"highway.residential"},
                           "costly":{"time":500,"length":1,"hierarchy":"highway.residential"}})
        self.connections={('a','b'),('b','c'),('a','gap'),('gap','long'),('long','c'),('gap','costly'),('costly','c')}
        self.costs={pair:(0,0) for pair in self.connections}
        self.pairs['base'].update(urban_generalized_cost_s=12,length_m=12)
        candidates,review=self.candidates()
        row=next(r for r in review['edges'] if r['edge']=='gap')
        self.assertEqual(row['status'],'native_validation_required')
        self.assertTrue(any(c['coverage_edge']=='gap' for c in candidates))

    def test_candidates_are_bounded_deterministic_and_leave_inputs_unchanged(self):
        before=deepcopy((self.edges,self.connections,self.costs,self.pairs))
        first=self.candidates(candidates_per_edge=1)
        self.assertEqual(first,self.candidates(candidates_per_edge=1))
        self.assertEqual(before,(self.edges,self.connections,self.costs,self.pairs))
        self.assertLessEqual(len(first[0]),first[1]['missing_before'])

    def test_already_covered_network_has_no_completion_candidates(self):
        self.pairs['alternative']={'origin':'a','destination':'c','route':['a','gap','c'],
                                   'urban_generalized_cost_s':32,'length_m':320}
        candidates,review=self.candidates()
        self.assertEqual(candidates,[])
        self.assertEqual(review['missing_before'],0)

    def test_candidate_preserves_the_simple_prefix_and_suffix(self):
        self.edges.update({name: {"time": 1, "length": 1, "hierarchy": "highway.residential"}
                           for name in ("before", "after")})
        self.connections = {("a", "b"), ("b", "c"), ("a", "before"),
                            ("before", "gap"), ("gap", "after"), ("after", "c")}
        self.costs = {pair: (0, 0) for pair in self.connections}
        candidates, _ = self.candidates()
        gap = next(candidate for candidate in candidates if candidate['coverage_edge'] == 'gap')
        self.assertEqual(gap['via'], ['before', 'gap', 'after'])

    def test_compatible_search_finds_suffix_without_revisiting_a_prefix_junction(self):
        layout = {
            "a": ("O", "A", 1), "direct": ("A", "D", 6), "z": ("D", "T", 1),
            "approach": ("A", "X", 1), "before": ("X", "B", 1), "gap": ("B", "C", 1),
            "short": ("C", "X", 1), "finish": ("X", "D", 1),
            "detour": ("C", "Y", 2), "merge": ("Y", "D", 2),
        }
        self.edges = {key: {"from": a, "to": b, "time": cost, "length": cost,
                            "hierarchy": "highway.residential"} for key, (a, b, cost) in layout.items()}
        self.connections = {("a", "direct"), ("direct", "z"), ("a", "approach"),
                            ("approach", "before"), ("before", "gap"), ("gap", "short"),
                            ("short", "finish"), ("finish", "z"), ("gap", "detour"),
                            ("detour", "merge"), ("merge", "z")}
        self.costs = dict.fromkeys(self.connections, (0, 0))
        self.pairs = {"base": {"origin": "a", "destination": "z", "route": ["a", "direct", "z"],
                               "urban_generalized_cost_s": 8, "length_m": 8}}
        self.assertNotIn("gap", {row["coverage_edge"] for row in self.candidates()[0]})
        candidates, review = self.candidates(compatible_witness_search_limit=1)
        gap = next(row for row in candidates if row["coverage_edge"] == "gap")
        self.assertEqual(gap["via"], ["approach", "before", "gap", "detour", "merge"])
        row = next(row for row in review["edges"] if row["edge"] == "gap")
        self.assertEqual(row["compatible_witness_searches"], 1)

    def test_invalid_candidate_budgets_are_rejected(self):
        for value in (0,9,True,1.5):
            with self.subTest(value=value),self.assertRaises(ValueError):
                self.candidates(candidates_per_edge=value)

    def test_terminal_loop_and_stem_are_not_a_through_street(self):
        edges={name:{'from':a,'to':b} for name,a,b in (
            ('ab','A','B'),('bc','B','C'),('ca','C','A'),('ad','A','D'),
            ('de','D','E'),('ef','E','F'),('fd','F','D'))}
        branches=terminal_branches(edges)
        ring=next(b for b in branches if 'ef' in b['terminal_edges'])
        self.assertEqual(ring['attachment'],'A')
        self.assertEqual(set(ring['edges']),{'ad','de','ef','fd'})
        self.assertNotIn('ab',ring['edges'])

    def test_terminal_chain_is_combined_across_split_nodes(self):
        edges={name:{'from':a,'to':b} for name,a,b in (
            ('ab','A','B'),('bc','B','C'),('ca','C','A'),('ad','A','D'),
            ('de','D','E'),('ef','E','F'))}
        branch=next(b for b in terminal_branches(edges) if 'ef' in b['terminal_edges'])
        self.assertEqual(branch['attachment'],'A')
        self.assertEqual(set(branch['edges']),{'ad','de','ef'})

    def test_connected_ring_without_articulation_does_not_create_a_terminal_access(self):
        edges={name:{'from':a,'to':b} for name,a,b in (
            ('ab','A','B'),('bc','B','C'),('ca','C','A'))}
        self.assertEqual(terminal_branches(edges),[])


if __name__ == "__main__":
    unittest.main()
