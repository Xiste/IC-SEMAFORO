"""Contratos da distribuição OD, incidência dos sensores e reprodução."""

from collections import Counter
from contextlib import nullcontext
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from SistemaDeSemaforos.demand import metasettran_demand_generator as demand
from SistemaDeSemaforos.demand import metasettran_calibration as temporal


PATHS = {
    ("entry_a", "exit_a"): "entry_a sensor5 bypass middle exit_a",
    ("entry_a", "exit_b"): "entry_a sensor5 bridge sensor6 middle exit_b",
    ("entry_b", "exit_a"): "entry_b unseen middle exit_a",
    ("entry_b", "exit_b"): "entry_b sensor6 middle exit_b",
    ("entry_c", "exit_a"): "entry_c unseen middle exit_a",
    ("entry_c", "exit_b"): "entry_c middle exit_b",
    ("entry_d", "exit_a"): "entry_d unseen middle exit_a",
    ("entry_d", "exit_b"): "entry_d unseen middle exit_b",
}


def _network():
    root = ET.Element("net")
    endpoints = {
        "entry_a": ("A", "a", 100), "entry_b": ("B", "b", 100),
        "entry_c": ("C0", "b", 100), "entry_d": ("D0", "b", 100),
        "sensor5": ("a", "j1", 200), "sensor6": ("b", "j2", 200),
        "bridge": ("j1", "b", 300), "bypass": ("j1", "j2", 400),
        "unseen": ("b", "j2", 600), "middle": ("j2", "end", 500),
        "exit_a": ("end", "C", 100), "exit_b": ("end", "D", 100),
    }
    for index, node in enumerate(sorted({node for source, target, _ in endpoints.values() for node in (source, target)})):
        ET.SubElement(root, "junction", id=node, x=str(index * 100), y="0")
    for name, (source, target, length) in endpoints.items():
        edge = ET.SubElement(root, "edge", id=name, **{"from": source, "to": target, "type": "highway.tertiary"})
        ET.SubElement(edge, "lane", id=name + "_0", index="0", length=str(length), speed="10", allow="passenger")
    for source, target in sorted({connection for path in PATHS.values() for connection in zip(path.split(), path.split()[1:])}):
        ET.SubElement(root, "connection", **{"from": source, "to": target, "fromLane": "0", "toLane": "0", "dir": "s"})
    return ET.tostring(root, encoding="unicode")


def _option(command, name):
    return command[command.index(name) + 1]


def _native_routes(command, **kwargs):
    root = ET.Element("routes")
    for trip in ET.parse(_option(command, "--route-files")).getroot().findall("trip"):
        vehicle = ET.SubElement(root, "vehicle", id=trip.get("id"), depart="0")
        ET.SubElement(vehicle, "route", edges=PATHS[trip.get("from"), trip.get("to")])
    ET.ElementTree(root).write(_option(command, "--output-file"), encoding="utf-8")
    return subprocess.CompletedProcess(command, 0)


class MetaSettranTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.net = self.directory / "network.net.xml"
        self.net.write_text(_network(), encoding="utf-8")
        self.csv = self.directory / "measurements.csv"
        self.csv.write_text("original measurements", encoding="utf-8")
        self.spatial = self.directory / "spatial.json"
        self.model = {
            "network_sha256": hashlib.sha256(self.net.read_bytes()).hexdigest(),
            "sensor_mapping_status": "unconfirmed",
            "sources": {"regional_counts": {"external": {"vmd": 4000, "monitored_lanes": 1}}},
            "regional_demand": {
                "reference_expected_departures": 1200,
                "destination_hierarchy_weights": {"": 1},
                "relative_corridor_evidence": {"entry_c": "external"},
                "regional_equation": "one population with shared observations", "limitations": ["test hypotheses"],
            },
            "portals": {"entries": [dict(edge=e, boundary_group=e, passenger_lanes=1, corridor=e) for e in ("entry_a", "entry_b", "entry_c", "entry_d")],
                        "exits": [dict(edge=e, boundary_group=e, passenger_lanes=1, corridor=e) for e in ("exit_a", "exit_b")]},
            "sensors": [{"sensor_id": 5, "selected_observation_edge": "sensor5"},
                        {"sensor_id": 6, "selected_observation_edge": "sensor6"}],
            "corridors": [{"id": "main", "label": "Main", "direction": "a to b", "edges": ["sensor6"]}],
        }
        network = ET.parse(self.net).getroot()
        for role, endpoint in (("entries", "from"), ("exits", "to")):
            for portal in self.model["portals"][role]:
                node = network.find(f"edge[@id='{portal['edge']}']").get(endpoint)
                junction = network.find(f"junction[@id='{node}']")
                portal.update(status="geographically_audited_boundary", references=["fixture cartography"],
                              boundary_evidence="fixture boundary endpoint", boundary_node=node,
                              boundary_xy_m=[float(junction.get("x")), float(junction.get("y"))])
        self.write_model()
        begin = demand.WEEK_START_SECONDS
        self.calibration = {
            "version": "test", "source": {"sha256": "source_hash"},
            "sensors": {str(sensor): {"knots": [
                {"week_second": begin - 450 + 900 * i, "rate_per_second": rate + i * 0.001}
                for i in range(14)]} for sensor, rate in ((5, .015), (6, .04))},
        }
        for profile in self.calibration["sensors"].values():
            profile["realization_knots"] = profile["knots"]
            profile["baseline_reference_cars_15_18"] = demand.integrate_rate(profile["knots"], begin, begin + 10800)
        self.calibration["baseline_reference_cars_15_18"] = {
            sensor: profile["baseline_reference_cars_15_18"] for sensor, profile in self.calibration["sensors"].items()}
        for mocked in (
            patch.object(temporal, "calibrate_weekly", return_value=self.calibration),
            patch.object(temporal, "weekly_window", side_effect=self.window_calibration),
            patch.object(demand.shutil, "which", return_value="/usr/bin/duarouter"),
            patch.object(demand.subprocess, "run", side_effect=_native_routes),
        ):
            mocked.start()
            self.addCleanup(mocked.stop)

    def window_calibration(self, weekly, begin, duration):
        result = json.loads(json.dumps(weekly))
        for sensor, profile in result["sensors"].items():
            rate = .015 if sensor == "5" else .04
            profile["knots"] = [{"week_second": begin - 450 + 900 * index,
                                  "rate_per_second": rate + index * .001}
                                 for index in range(round(duration / 900) + 2)]
            realized_scale = getattr(self, "realization_multipliers", {}).get(sensor, 1.0)
            profile["realization_knots"] = [dict(knot, rate_per_second=knot["rate_per_second"] * realized_scale)
                                            for knot in profile["knots"]]
            profile["target_counts"] = [demand.integrate_rate(profile["knots"], begin + index * 900,
                                        begin + (index + 1) * 900) for index in range(round(duration / 900))]
        result["selection"] = {"start_week_second": begin, "end_week_second": begin + duration,
                               "departure_seconds": duration}
        return result

    def write_model(self):
        self.model["network_sha256"] = hashlib.sha256(self.net.read_bytes()).hexdigest()
        self.spatial.write_text(json.dumps(self.model), encoding="utf-8")

    def generate(self, output="demand", **kwargs):
        return demand.generate_metasettran_demand(net_file=self.net, csv_file=self.csv,
            spatial_file=self.spatial, output_dir=self.directory / output, **kwargs)

    def test_every_trip_uses_complete_valid_boundary_route(self):
        metadata = {}
        vehicles = ET.parse(self.generate(metadata=metadata)).getroot().findall("vehicle")
        trips = ET.parse(metadata["trips_file"]).getroot().findall("trip")
        self.assertGreater(len(vehicles), 100)
        self.assertEqual(len(vehicles), len(trips))
        times = []
        for vehicle, trip in zip(vehicles, trips):
            self.assertEqual(vehicle.get("id"), trip.get("id"))
            self.assertEqual(vehicle.get("departPos"), "0")
            self.assertEqual(vehicle.get("arrivalPos"), "max")
            self.assertEqual(vehicle.find("route").get("edges"), PATHS[trip.get("from"), trip.get("to")])
            times.append(float(vehicle.get("depart")))
        self.assertEqual(times, sorted(times))
        self.assertGreaterEqual(times[0], 0)
        self.assertLess(times[-1], 10800)
        self.assertEqual(metadata["route_validation"]["valid_boundary_routes"], len(vehicles))
        self.assertEqual(metadata["route_validation"]["used_pairs"], 8)
        self.assertEqual(metadata["measured_class"], "car")
        self.assertEqual(self.csv.read_text(), "original measurements")
        self.assertEqual(ET.parse(metadata["routes_file"]).getroot().find("vType").attrib,
                         {"id": "metasettran_car", "vClass": "passenger"})

    def urban_activity_fixture(self):
        edges, _, _, _ = demand._read_network(self.net)
        def gate(identifier):
            edge = edges[identifier]
            return {"edge": identifier, "passenger_lanes": 1, "road_type": edge["hierarchy"],
                    "position_xy_m": [(a + b) / 2 for a, b in zip(edge["from_xy"], edge["to_xy"])]}
        self.model["activity_zones"] = [{"id": "shops", "name": "Shops", "kind": "commerce",
            "references": ["fixture cartography"], "origins": [gate("unseen")],
            "destinations": [gate("sensor6")]}]
        profiles = {kind: {"hours": [0, 24], "origin": [1, 1], "destination": [1, 1]}
                    for kind in ("weekday", "saturday", "sunday")}
        zones = [{"id": p["boundary_group"], "kind": "mixed", "profiles": profiles}
                 for role in ("entries", "exits") for p in self.model["portals"][role]]
        zones.append({"id": "shops", "kind": "commerce", "opportunity": 2, "profiles": profiles})
        self.model["regional_demand"].update(route_choice={"method": "urban_activity_od"},
            urban_activity_model={"zones": zones, "road_cost_factors": {"highway.tertiary": 1.1}})
        paths = dict(PATHS)
        paths.update({("entry_a", "sensor6"): "entry_a sensor5 bridge sensor6",
                      ("entry_b", "sensor6"): "entry_b sensor6",
                      ("unseen", "exit_a"): "unseen middle exit_a",
                      ("unseen", "exit_b"): "unseen middle exit_b"})
        def router(command, **kwargs):
            root = ET.Element("routes")
            for trip in ET.parse(_option(command, "--route-files")).getroot().findall("trip"):
                route = paths.get((trip.get("from"), trip.get("to")))
                if route:
                    vehicle = ET.SubElement(root, "vehicle", id=trip.get("id"), depart="0")
                    ET.SubElement(vehicle, "route", edges=route)
            ET.ElementTree(root).write(_option(command, "--output-file"), encoding="utf-8")
            return subprocess.CompletedProcess(command, 0)
        self.write_model()
        return router

    def test_internal_activity_accesses_are_routed_geographically_and_get_native_alternatives(self):
        router = self.urban_activity_fixture()
        self.model["regional_demand"]["road_hierarchy_overrides"] = {"unseen": "highway.primary"}
        with patch.object(demand.subprocess, "run", side_effect=router) as run:
            pairs, _, catalog, _ = demand._route_pairs(self.model, self.net, self.directory, None)
        self.assertEqual(run.call_count, 2)
        weighted_command = run.call_args_list[1].args[0]
        weights = ET.parse(_option(weighted_command, "--weight-files")).getroot()
        self.assertAlmostEqual(float(weights.find("interval/edge[@id='unseen']").get("traveltime")), 60)
        self.assertAlmostEqual(float(weights.find("interval/edge[@id='sensor5']").get("traveltime")), 22)
        through = next(p for p in pairs.values() if p["origin"] == "entry_b" and p["destination"] == "exit_a")
        self.assertEqual(through["movement_target_hierarchies"][0], "highway.primary")
        self.assertAlmostEqual(through["urban_generalized_cost_s"], 137)
        self.assertEqual(catalog["entry_portals_available"], 4)
        self.assertEqual(catalog["activity_origin_accesses"], 1)
        self.assertTrue(any(p["origin_kind"] == "activity" for p in pairs.values()))
        self.assertTrue(any(p["destination_kind"] == "activity" for p in pairs.values()))
        self.assertFalse(any(p["origin_kind"] == p["destination_kind"] == "activity" for p in pairs.values()))
        self.model["activity_zones"][0]["origins"][0]["position_xy_m"] = [1e6, 1e6]
        with self.assertRaisesRegex(ValueError, "Posição do acesso"):
            demand._route_pairs(self.model, self.net, self.directory, None)

    def test_mixed_activity_demand_conserves_population_and_reports_internal_endpoints_separately(self):
        router = self.urban_activity_fixture()
        metadata, replayed = {}, {}
        with patch.object(demand.subprocess, "run", side_effect=router):
            original = self.generate(output="mixed", metadata=metadata)
            replay = self.generate(output="mixed_replay", metadata=replayed)
        self.assertEqual(original.read_bytes(), replay.read_bytes())
        spatial = metadata["spatial_distribution"]
        populations = spatial["trip_populations"]
        self.assertEqual(sum(populations.values()), metadata["vehicles_generated"])
        self.assertGreater(populations["boundary_to_activity"], 0)
        self.assertGreater(populations["activity_to_boundary"], 0)
        self.assertEqual(populations["activity_to_activity"], 0)
        self.assertEqual(metadata["route_validation"]["valid_routes"], metadata["vehicles_generated"])
        self.assertEqual(metadata["route_validation"]["valid_boundary_routes"], populations["boundary_to_boundary"])
        self.assertAlmostEqual(spatial["expected_network_departures"], 1200)
        for role, activity_role in (("entries", "origins"), ("exits", "destinations")):
            observed = sum(p["generated_departures"] for p in spatial["portals"][role])
            observed += sum(p["generated_departures"] for z in spatial["activity_locations"] for p in z[activity_role])
            self.assertEqual(observed, metadata["vehicles_generated"])

    def test_compact_metadata_preserves_routes_and_every_remaining_field(self):
        router = self.urban_activity_fixture()
        routing_directory = self.directory / "routing"
        routing_directory.mkdir()
        # Fix only the temporary path so recorded native commands are comparable.
        with patch.object(demand.subprocess, "run", side_effect=router), patch.object(
                demand, "TemporaryDirectory", side_effect=lambda **kwargs: nullcontext(str(routing_directory))):
            for options in ({"variation": 7},
                            {"day": "sunday", "start": "21:00", "sections": 2, "variations": [7, 8]}):
                with self.subTest(options=options):
                    detailed, compact = {}, {}
                    original = self.generate(metadata=detailed, **options).read_bytes()
                    original_trips = Path(detailed["trips_file"]).read_bytes()
                    reduced = self.generate(metadata=compact, include_route_details=False, **options).read_bytes()
                    self.assertEqual(reduced, original)
                    self.assertEqual(Path(compact["trips_file"]).read_bytes(), original_trips)
                    self.assertEqual(compact["routes_sha256"], detailed["routes_sha256"])
                    self.assertEqual(compact["trips_sha256"], detailed["trips_sha256"])
                    self.assertTrue(detailed["spatial_distribution"]["routes"])
                    self.assertEqual(detailed["spatial_distribution"]["groups"], detailed["groups"])
                    self.assertNotIn("routes", compact["spatial_distribution"])
                    self.assertNotIn("groups", compact["spatial_distribution"])
                    expected = {**detailed, "spatial_distribution": {
                        key: value for key, value in detailed["spatial_distribution"].items()
                        if key not in {"routes", "groups"}}}
                    for record in (expected, compact):
                        for key in ("started_at_utc", "finished_at_utc", "duration_seconds"):
                            record.pop(key)
                    self.assertEqual(compact, expected)

    def test_branch_choice_does_not_reward_number_of_downstream_destinations(self):
        def pair(identifier, route, angles):
            return dict(id=identifier, origin="entry", destination=route[-1], route=route,
                        movement_opportunities=[1] * (len(route)-1), movement_angles=angles)
        paths = {"a": pair("a", ["entry", "straight", "exit_a"], [0, 0]),
                 "b": pair("b", ["entry", "turn", "exit_b"], [math.pi/2, 0])}
        portals = {"entry": {"road_type": "highway.primary"}}
        demand._branch_prior(paths, {"entry": 4}, portals, {"angular_cost": 1})
        first_turn = paths["b"]["prior_weight"]
        paths["c"] = pair("c", ["entry", "straight", "exit_c"], [0, 0])
        demand._branch_prior(paths, {"entry": 4}, portals, {"angular_cost": 1})
        self.assertAlmostEqual(paths["b"]["prior_weight"], first_turn)
        self.assertAlmostEqual(sum(p["prior_weight"] for p in paths.values()), 1)
        self.assertAlmostEqual(first_turn, 1/3)

    def test_branch_prior_keeps_legal_return_positive_and_origin_opportunities(self):
        paths = {"a": dict(origin="a", route=["a", "return"], movement_opportunities=[1],
                           movement_angles=[math.pi]),
                 "b": dict(origin="a", route=["a", "forward"], movement_opportunities=[2],
                           movement_angles=[0]),
                 "c": dict(origin="c", route=["c", "short_exit"], movement_opportunities=[1],
                           movement_angles=[0])}
        demand._branch_prior(paths, {"a": 3, "c": 1}, {"a": {}, "c": {}}, {"angular_cost": 1})
        self.assertGreater(paths["a"]["prior_weight"], 0)
        self.assertAlmostEqual(paths["a"]["prior_weight"] + paths["b"]["prior_weight"], .75)
        self.assertAlmostEqual(paths["c"]["prior_weight"], .25)

    def test_native_branch_model_preserves_population_and_shared_observations(self):
        self.model["regional_demand"]["route_choice"] = {"method": "native_path_branch_opportunities", "angular_cost": 1}
        self.write_model()
        metadata = {}
        self.generate(metadata=metadata)
        self.assertAlmostEqual(sum(p["prior_weight"] for p in metadata["spatial_distribution"]["routes"]), 1)
        self.assertGreater(metadata["spatial_distribution"]["observation_incidence_generated"]["both"], 0)
        self.assertEqual(sum(metadata["spatial_distribution"]["observation_incidence_generated"].values()), metadata["vehicles_generated"])

    def test_contextual_choice_preserves_curved_arterial_over_straight_local(self):
        paths = {
            "arterial": dict(origin="entry", route=["entry", "arterial_exit"],
                             movement_opportunities=[1], movement_receiving_lanes=[1],
                             movement_target_hierarchies=["highway.primary"], movement_angles=[math.pi / 2]),
            "local": dict(origin="entry", route=["entry", "local_exit"],
                          movement_opportunities=[1], movement_receiving_lanes=[1],
                          movement_target_hierarchies=["highway.residential"], movement_angles=[0]),
        }
        config = {"method": "native_path_contextual_opportunities", "angular_cost": 1}
        demand._branch_prior(paths, {"entry": 1}, {"entry": {}}, config,
                             hierarchy_weights={"highway.primary": 4, "highway.residential": 1})
        self.assertGreater(paths["arterial"]["prior_weight"], paths["local"]["prior_weight"])
        self.assertAlmostEqual(paths["arterial"]["prior_weight"], 2 / 3)
        self.assertGreater(paths["local"]["prior_weight"], 0)

    def urban_fixture(self):
        def zone(identifier, opportunity=None):
            result = {"id": identifier, "profiles": {kind: {"hours": [0, 12, 24],
                "origin": [1, 1, 1], "destination": [1, 1, 1]}
                for kind in ("weekday", "saturday", "sunday")}}
            if opportunity is not None:
                result["opportunity"] = opportunity
            return result

        def endpoint(edge, zone_id, xy, kind="boundary"):
            return dict(edge=edge, zone_id=zone_id, boundary_group=zone_id, position_xy_m=xy,
                        endpoint_kind=kind, road_type="highway.primary")

        endpoints = {"entries": [endpoint("in", "west", [0, 0]),
                                  endpoint("shop_in", "shop", [1000, 0], "activity")],
                     "exits": [endpoint("near", "west", [10, 0]), endpoint("far", "east", [4000, 0]),
                               endpoint("shop_out", "shop", [1000, 0], "activity")]}

        def route(origin, destination, length, cost, middle, same_access=False):
            return dict(origin=origin, destination=destination, length_m=length, freeflow_time_s=cost,
                        urban_generalized_cost_s=cost, route=[origin, middle, destination],
                        urban_edge_lengths_m=[100, length - 200, 100], has_uturn=False,
                        returns_to_same_access=same_access)

        paths = {"near": route("in", "near", 400, 40, "loop", True),
                 "far": route("in", "far", 4200, 300, "main"),
                 "detour": route("in", "far", 7000, 600, "detour"),
                 "shop": route("in", "shop_out", 1100, 100, "local"),
                 "depart": route("shop_in", "far", 3100, 230, "main")}
        model = {"regional_demand": {"route_choice": {"method": "urban_activity_od"},
                 "urban_activity_model": {"zones": [zone("west"), zone("east"), zone("shop", 4)]}}}
        return paths, model, endpoints, {"in": 4, "shop_in": 1}, {"near": 1, "far": 1, "shop_out": 1}

    def test_urban_destination_choice_penalizes_boundary_loops_and_longer_alternatives(self):
        paths, model, endpoints, entries, exits = self.urban_fixture()
        demand._urban_prior(paths, model, endpoints, entries, exits)
        self.assertAlmostEqual(sum(pair["prior_weight"] for pair in paths.values()), 1)
        self.assertAlmostEqual(sum(pair["prior_weight"] for pair in paths.values() if pair["origin"] == "in"), .5)
        self.assertGreater(paths["far"]["prior_weight"], paths["near"]["prior_weight"])
        self.assertGreater(paths["far"]["prior_weight"], paths["detour"]["prior_weight"])
        self.assertGreater(paths["near"]["prior_weight"], 0)

    def test_urban_extra_route_does_not_increase_destination_attraction(self):
        paths, model, endpoints, entries, exits = self.urban_fixture()
        demand._urban_prior(paths, model, endpoints, entries, exits)
        before = sum(paths[key]["prior_weight"] for key in ("far", "detour"))
        other_before = paths["shop"]["prior_weight"]
        paths["third"] = dict(paths["detour"], route=["in", "third", "far"])
        demand._urban_prior(paths, model, endpoints, entries, exits)
        self.assertAlmostEqual(sum(paths[key]["prior_weight"] for key in ("far", "detour", "third")), before)
        self.assertAlmostEqual(paths["shop"]["prior_weight"], other_before)

    def test_urban_zone_opportunity_is_shared_between_its_gates(self):
        endpoints = [{"edge": "a", "zone_id": "campus"}, {"edge": "b", "zone_id": "campus"}]
        weights = demand._urban_endpoint_weights(endpoints, {"a": 1, "b": 3}, {"campus": {"opportunity": 4}})
        self.assertEqual(weights, {"a": 1, "b": 3})
        endpoints.append({"edge": "c", "zone_id": "campus"})
        changed = demand._urban_endpoint_weights(endpoints, {"a": 1, "b": 3, "c": 4}, {"campus": {"opportunity": 4}})
        self.assertEqual(sum(changed.values()), 4)
        self.assertEqual(changed["c"], 2)

    def test_urban_profiles_change_destinations_without_changing_origin_opportunity(self):
        paths, model, endpoints, entries, exits = self.urban_fixture()
        shop = model["regional_demand"]["urban_activity_model"]["zones"][-1]
        shop["profiles"]["weekday"]["destination"] = [.01, 2, .01]
        shop["profiles"]["sunday"]["destination"] = [.01, .2, .01]
        demand._urban_prior(paths, model, endpoints, entries, exits)
        rows = {clock: demand._route_prior_row(list(paths.values()), model, moment, {"5": 1, "6": 1})
                for clock, moment in (("night", 0), ("weekday", 12 * 3600), ("sunday", 6 * 86400 + 12 * 3600))}
        shop_index = list(paths).index("shop")
        self.assertGreater(rows["weekday"][shop_index], rows["sunday"][shop_index])
        self.assertGreater(rows["sunday"][shop_index], rows["night"][shop_index])
        for row in rows.values():
            self.assertAlmostEqual(sum(row), 1)
            self.assertAlmostEqual(sum(value for pair, value in zip(paths.values(), row) if pair["origin"] == "in"), .5)
        self.assertAlmostEqual(demand._urban_profile(shop, "destination", 6 * 3600), 1.005)

    def test_urban_configuration_rejects_invalid_profiles_and_penalties(self):
        _, model, _, _, _ = self.urban_fixture()
        config = model["regional_demand"]["urban_activity_model"]
        for key, value in (("distance_scale_m", 0), ("uturn_penalty", 2), ("path_size_exponent", -1),
                           ("detour_sensitivity", math.nan), ("same_access_penalty", True)):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "urbano"):
                demand._urban_zones(dict(config, **{key: value}))
        config["zones"][0]["profiles"]["weekday"]["origin"][1] = -1
        with self.assertRaisesRegex(ValueError, "Perfil urbano"):
            demand._urban_zones(config)

    def test_urban_observation_drift_records_spatial_changes_without_rebalancing(self):
        paths, model, endpoints, entries, exits = self.urban_fixture()
        demand._urban_prior(paths, model, endpoints, entries, exits)
        routes = list(paths.values())
        prior = [pair["prior_weight"] for pair in routes]
        fitted = prior.copy()
        transfer = fitted[-1] / 2
        fitted[-1] -= transfer
        fitted[0] += transfer
        result = demand._urban_prior_drift(routes, [prior], [fitted], [100])
        self.assertAlmostEqual(result["maximum_origins_total_variation"], transfer)
        self.assertAlmostEqual(sum(row["projected_expected_departures"] for row in result["zones"]["origin_zones"]), 100)
        self.assertEqual(fitted[0], prior[0] + transfer)

    def test_contextual_choice_limits_merging_lanes_and_preserves_origin_mass(self):
        paths = {
            "merge": dict(origin="entry", route=["entry", "merge_exit"],
                          movement_opportunities=[3], movement_receiving_lanes=[1],
                          movement_target_hierarchies=["highway.primary"], movement_angles=[0]),
            "single": dict(origin="entry", route=["entry", "single_exit"],
                           movement_opportunities=[1], movement_receiving_lanes=[1],
                           movement_target_hierarchies=["highway.primary"], movement_angles=[0]),
            "return": dict(origin="other", route=["other", "return_exit"],
                           movement_opportunities=[1], movement_receiving_lanes=[1],
                           movement_target_hierarchies=["unclassified"], movement_angles=[math.pi]),
        }
        config = {"method": "native_path_contextual_opportunities", "angular_cost": 1}
        demand._branch_prior(paths, {"entry": 3, "other": 1}, {"entry": {}, "other": {}}, config,
                             hierarchy_weights={"highway.primary": 4})
        self.assertAlmostEqual(paths["merge"]["prior_weight"], paths["single"]["prior_weight"])
        self.assertAlmostEqual(paths["merge"]["prior_weight"] + paths["single"]["prior_weight"], .75)
        self.assertAlmostEqual(paths["return"]["prior_weight"], .25)
        self.assertAlmostEqual(sum(pair["prior_weight"] for pair in paths.values()), 1)

    def test_contextual_choice_does_not_reward_extra_downstream_destinations(self):
        def pair(branch, destination):
            return dict(origin="entry", route=["entry", branch, destination],
                        movement_opportunities=[1, 1], movement_receiving_lanes=[1, 1],
                        movement_target_hierarchies=["highway.primary", "highway.residential"],
                        movement_angles=[0, 0])
        paths = {"a": pair("first", "exit_a"), "b": pair("second", "exit_b")}
        config = {"method": "native_path_contextual_opportunities", "angular_cost": 1}
        kwargs = {"hierarchy_weights": {"highway.primary": 4, "highway.residential": 1}}
        demand._branch_prior(paths, {"entry": 1}, {"entry": {}}, config, **kwargs)
        unaffected = paths["b"]["prior_weight"]
        paths["c"] = pair("first", "exit_c")
        demand._branch_prior(paths, {"entry": 1}, {"entry": {}}, config, **kwargs)
        self.assertAlmostEqual(paths["b"]["prior_weight"], unaffected)
        self.assertAlmostEqual(paths["a"]["prior_weight"] + paths["c"]["prior_weight"], 1 - unaffected)

    def test_contextual_choice_rejects_invalid_hierarchy_weights(self):
        paths = {"a": dict(origin="entry", route=["entry", "exit"],
                           movement_opportunities=[1], movement_receiving_lanes=[1],
                           movement_target_hierarchies=["highway.primary"], movement_angles=[0])}
        config = {"method": "native_path_contextual_opportunities", "angular_cost": 1}
        for value in (0, -1, float("nan"), float("inf"), True, "4", None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "hierarquia"):
                demand._branch_prior(paths, {"entry": 1}, {"entry": {}}, config,
                                     hierarchy_weights={"highway.primary": value})

    def test_catalog_counts_only_distinct_reachable_passenger_receiving_lanes(self):
        root = ET.parse(self.net).getroot()
        entry = root.find("edge[@id='entry_a']")
        sensor = root.find("edge[@id='sensor5']")
        for index in (1, 2):
            ET.SubElement(entry, "lane", id=f"entry_a_{index}", index=str(index), length="100", speed="10", allow="passenger")
        for index, allowed in ((1, "passenger"), (2, "bus"), (3, "passenger")):
            ET.SubElement(sensor, "lane", id=f"sensor5_{index}", index=str(index), length="200", speed="10", allow=allowed)
        for source_lane, target_lane in ((1, 0), (1, 1), (2, 1), (0, 2)):
            ET.SubElement(root, "connection", **{"from": "entry_a", "to": "sensor5",
                                                 "fromLane": str(source_lane), "toLane": str(target_lane), "dir": "s"})
        self.model["portals"]["entries"][0]["passenger_lanes"] = 3
        sensor.set("type", "highway.primary")
        root.find("edge[@id='exit_a']").attrib.pop("type")
        self.model["portals"]["exits"][0]["prior_road_type"] = "highway.secondary"
        ET.ElementTree(root).write(self.net)
        self.write_model()
        metadata = {}
        self.generate(metadata=metadata)
        route = next(p for p in metadata["spatial_distribution"]["routes"]
                     if p["origin"] == "entry_a" and p["destination"] == "exit_a")
        self.assertEqual(route["movement_opportunities"][0], 3)
        self.assertEqual(route["movement_receiving_lanes"][0], 2)
        self.assertEqual(route["movement_target_hierarchies"][0], "highway.primary")
        self.assertEqual(route["movement_target_hierarchies"][-1], "highway.secondary")

    def test_contextual_model_preserves_departure_schedule_and_paired_population(self):
        self.model["regional_demand"]["route_choice"] = {"method": "native_path_branch_opportunities", "angular_cost": 1}
        self.write_model()
        original_metadata = {}
        original_file = self.generate(output="legacy_contextual_reference", variation=7, metadata=original_metadata)
        original = ET.parse(original_file).getroot()
        root = ET.parse(self.net).getroot()
        root.find("edge[@id='bridge']").set("type", "highway.primary")
        root.find("edge[@id='bypass']").set("type", "highway.residential")
        ET.ElementTree(root).write(self.net)
        self.model["regional_demand"]["destination_hierarchy_weights"].update({"highway.primary": 4, "highway.residential": 1})
        self.model["regional_demand"]["route_choice"]["method"] = "native_path_contextual_opportunities"
        self.write_model()
        changed_metadata, paired_metadata = {}, {}
        changed = ET.parse(self.generate(output="contextual", variation=7, metadata=changed_metadata)).getroot()
        paired = ET.parse(self.generate(output="contextual_paired", variation=7, schedule_file=original_file,
                                        metadata=paired_metadata)).getroot()
        attributes = [vehicle.attrib for vehicle in original.findall("vehicle")]
        self.assertEqual(attributes, [vehicle.attrib for vehicle in changed.findall("vehicle")])
        self.assertEqual(attributes, [vehicle.attrib for vehicle in paired.findall("vehicle")])
        for metadata in (changed_metadata, paired_metadata):
            self.assertEqual(metadata["vehicles_generated"], len(attributes))
            self.assertAlmostEqual(sum(p["prior_weight"] for p in metadata["spatial_distribution"]["routes"]), 1)
            self.assertEqual(sum(metadata["spatial_distribution"]["observation_incidence_generated"].values()), len(attributes))
            self.assertAlmostEqual(metadata["spatial_distribution"]["expected_network_departures"],
                                   len(attributes) if metadata is paired_metadata else 1200)
            self.assertEqual(metadata["route_validation"]["valid_boundary_routes"], len(attributes))
        self.assertNotEqual([p["prior_weight"] for p in original_metadata["spatial_distribution"]["routes"]],
                            [p["prior_weight"] for p in changed_metadata["spatial_distribution"]["routes"]])

    def test_reproduction_is_independent_of_output_directory_and_tool_headers(self):
        first, second = {}, {}
        a = self.generate(output="a", variation=7, metadata=first)
        b = self.generate(output="b", variation=7, metadata=second)
        self.assertEqual(a.read_bytes(), b.read_bytes())
        self.assertEqual(first["routes_sha256"], second["routes_sha256"])
        self.assertEqual(first["seed"], 1082464323)
        self.assertNotEqual(a.read_bytes(), self.generate(output="c", variation=8).read_bytes())

    def test_explicit_seed_controls_same_realization(self):
        a = self.generate(output="a", variation=1, seed=42)
        b = self.generate(output="b", variation=25, seed=42)
        self.assertEqual(a.read_bytes(), b.read_bytes())

    def test_context_selection_covers_required_chronological_windows(self):
        cases = (("tuesday", "15:00", 1, "tuesday", "15:00"),
                 ("tuesday", "15:00", 2, "tuesday", "18:00"),
                 ("friday", "21:00", 2, "saturday", "00:00"),
                 ("sunday", "21:00", 2, "monday", "00:00"),
                 ("tuesday", "00:00", 7, "tuesday", "18:00"),
                 ("monday", "00:00", 8, "monday", "21:00"),
                 ("monday", "00:00", 16, "tuesday", "21:00"),
                 ("monday", "00:00", 56, "sunday", "21:00"),
                 ("sunday", "21:00", 56, "sunday", "18:00"))
        for day, start, sections, last_day, last_start in cases:
            with self.subTest(day=day, start=start, sections=sections):
                selection = demand.resolve_contexts(day=day, start=start, sections=sections, master_seed=42)
                contexts = selection["contexts"]
                self.assertEqual(len(contexts), sections)
                self.assertEqual((contexts[-1]["day"], contexts[-1]["start"]), (last_day, last_start))
                self.assertEqual(selection["combinations"], 25 ** sections)
                for index, context in enumerate(contexts):
                    self.assertEqual((context["begin"], context["end"]), (index * 10800, (index + 1) * 10800))
                    self.assertIn(context["variation"], range(1, 26))
                    self.assertEqual(context["effective_seed"], demand.effective_seed(context["variation"]))
                self.assertEqual([context["start_week_second"] for context in contexts],
                                 list(range(contexts[0]["start_week_second"],
                                            contexts[0]["start_week_second"] + sections * 10800, 10800)))
        weekly = demand.resolve_contexts(day="sunday", start="21:00", sections=56, master_seed=42)
        self.assertEqual(weekly["contexts"][0]["week_offset"], 0)
        self.assertEqual(weekly["contexts"][-1]["week_offset"], 1)

    def test_context_draws_cover_25_variations_without_locking_adjacent_choices(self):
        # Deterministic distribution check, not a claim that a finite PRNG
        # empirically proves independence. Repeats must remain eligible.
        marginal = [Counter(), Counter()]
        pairs, repeated = set(), 0
        for master_seed in range(5000):
            first, second = demand.resolve_contexts(sections=2, master_seed=master_seed)["variations"]
            marginal[0][first] += 1
            marginal[1][second] += 1
            repeated += first == second
            pairs.add((first, second))
        for counts in marginal:
            self.assertEqual(set(counts), set(range(1, 26)))
            self.assertLess(sum((counts[value] - 200) ** 2 / 200 for value in range(1, 26)), 70)
        self.assertGreater(len(pairs), 600)
        self.assertGreater(repeated, 100)
        self.assertLess(repeated, 300)

    def test_one_section_master_or_explicit_replay_is_the_existing_variation(self):
        selection = demand.resolve_contexts(master_seed=1847)
        chosen, = selection["variations"]
        original = self.generate(output="individual", variation=chosen)
        drawn = self.generate(output="drawn", master_seed=1847)
        replay = self.generate(output="replay", variations=[chosen])
        self.assertEqual(original.read_bytes(), drawn.read_bytes())
        self.assertEqual(original.read_bytes(), replay.read_bytes())

    def test_master_sequence_and_explicit_replay_have_identical_trip_and_route_bytes(self):
        first, replayed = {}, {}
        drawn = self.generate(output="drawn", day="sunday", start="21:00", sections=2,
                              master_seed=2468, metadata=first)
        replay = self.generate(output="replay", day="sunday", start="21:00", sections=2,
                               variations=first["context_selection"]["variations"], metadata=replayed)
        self.assertEqual(drawn.read_bytes(), replay.read_bytes())
        self.assertEqual(Path(first["trips_file"]).read_bytes(), Path(replayed["trips_file"]).read_bytes())
        self.assertEqual(first["seed"], replayed["seed"])
        self.assertEqual(first["context_selection"]["contexts"], replayed["context_selection"]["contexts"])
        self.assertEqual(first["chronological_composition"], replayed["chronological_composition"])

    def test_composition_calibrates_selected_context_seeds_without_using_the_master_as_variation(self):
        with patch.object(temporal, "calibrate_weekly", return_value=self.calibration) as calibrate:
            self.generate(sections=3, variations=[7, 8, 7], master_seed=123456789)
        self.assertEqual([(call.kwargs["variation"], call.kwargs["seed"]) for call in calibrate.call_args_list],
                         [(7, demand.effective_seed(7)), (8, demand.effective_seed(8))])

    def test_composition_conserves_each_selected_realization_and_expected_mass(self):
        self.model["regional_demand"]["volume_recalibration"] = {"retained_fraction": .85}
        self.write_model()
        metadata = {}
        combined = ET.parse(self.generate(output="combined", sections=2, variations=[7, 8],
                                           metadata=metadata)).getroot().findall("vehicle")
        contexts = metadata["context_selection"]["contexts"]
        individual_totals, expected_total, moved_count = [], 0.0, 0
        for context in contexts:
            standalone = {}
            vehicles = ET.parse(self.generate(output=f"single-{context['index']}", day=context["day"],
                                              start=context["start"], variation=context["variation"],
                                              metadata=standalone)).getroot().findall("vehicle")
            individual_totals.append(len(vehicles))
            expected_total += standalone["groups"][0]["expected_departures"]
            selected = [vehicle for vehicle in combined
                        if context["begin"] <= float(vehicle.get("depart")) < context["end"]]
            self.assertEqual(len(selected), len(vehicles))
            self.assertEqual(context["reference_programmed"], len(vehicles))
            self.assertEqual(context["programmed"], len(vehicles))
            original_times = {vehicle.get("id"): float(vehicle.get("depart")) for vehicle in vehicles}
            original_routes = {vehicle.get("id"): vehicle.find("route").get("edges") for vehicle in vehicles}
            for vehicle in selected:
                self.assertTrue(vehicle.get("id").startswith(f"ms_s{context['index']:03d}_"))
                original_id = "ms_" + vehicle.get("id").split("_")[-1]
                original_time = original_times.pop(original_id) + context["begin"]
                composed_time = float(vehicle.get("depart"))
                if abs(original_time - 10800) >= 900:
                    self.assertAlmostEqual(composed_time, original_time, places=5)
                    self.assertEqual(vehicle.find("route").get("edges"), original_routes[original_id])
                else:
                    self.assertEqual(composed_time < 10800, original_time < 10800)
                    moved_count += abs(composed_time - original_time) > 1e-5
            self.assertFalse(original_times)
        self.assertGreater(moved_count, 0)
        self.assertEqual(len(combined), sum(individual_totals))
        transition = metadata["chronological_composition"]
        self.assertEqual(transition["combined_programmed"], sum(individual_totals))
        self.assertEqual(transition["programmed_difference"], 0)
        self.assertAlmostEqual(transition["expected_before"], expected_total, places=7)
        self.assertAlmostEqual(transition["expected_after"], expected_total, places=7)
        self.assertAlmostEqual(metadata["groups"][0]["expected_departures"], expected_total, places=7)
        self.assertAlmostEqual(sum(metadata["groups"][0]["expected_departures_per_bin"]), expected_total, places=7)
        self.assertAlmostEqual(sum(route["expected_departures"] for route in metadata["spatial_distribution"]["routes"]),
                               expected_total, places=7)
        for section in transition["sections"]:
            self.assertAlmostEqual(section["expected_before"], section["expected_after"], places=7)

    def test_composition_metadata_and_small_windows_remain_comparable(self):
        metadata = {}
        vehicles = ET.parse(self.generate(sections=2, variations=[4, 17], metadata=metadata)).getroot().findall("vehicle")
        departures = [float(vehicle.get("depart")) for vehicle in vehicles]
        boundary, = metadata["chronological_composition"]["boundaries"]
        knots = metadata["chronological_composition"]["rate_knots"]
        moment = boundary["week_second"]
        self.assertAlmostEqual(demand.interpolate_rate(knots, moment - 1e-6),
                               demand.interpolate_rate(knots, moment + 1e-6), places=8)
        self.assertEqual(boundary["od_boundary_jump"], 0)
        for window in boundary["windows"]:
            width = window["seconds"]
            self.assertEqual(window["programmed_left"], sum(10800 - width <= t < 10800 for t in departures))
            self.assertEqual(window["programmed_right"], sum(10800 <= t < 10800 + width for t in departures))
            if width == 900:
                self.assertAlmostEqual(window["before_left"], window["after_left"], places=7)
                self.assertAlmostEqual(window["before_right"], window["after_right"], places=7)
        # This pre-existing fixture deliberately has no realized_target_counts;
        # composition still reports each selected curve and a complete bin axis.
        for sensor in ("5", "6"):
            profile = metadata["calibration"]["sensors"][sensor]
            self.assertNotIn("realization_knots", profile)
            self.assertEqual(len(profile["realization_contexts"]), 2)
            self.assertEqual(len(profile["realized_target_counts"]), 24)
            self.assertAlmostEqual(profile["realized_expected_cars"], sum(profile["realized_target_counts"]))

    def test_long_compositions_have_unique_ordered_half_open_departures(self):
        for sections, day, end_day, end_time in ((7, "tuesday", "tuesday", "21:00"),
                                                (8, "monday", "tuesday", "00:00"),
                                                (16, "monday", "wednesday", "00:00")):
            with self.subTest(sections=sections):
                metadata = {}
                root = ET.parse(self.generate(output=f"long-{sections}", day=day, start="00:00", sections=sections,
                                               master_seed=42, metadata=metadata)).getroot()
                vehicles = root.findall("vehicle")
                departures = [float(vehicle.get("depart")) for vehicle in vehicles]
                self.assertEqual(len({vehicle.get("id") for vehicle in vehicles}), len(vehicles))
                self.assertEqual(departures, sorted(departures))
                self.assertGreaterEqual(min(departures), 0)
                self.assertLess(max(departures), sections * 10800)
                self.assertEqual((metadata["end_day"], metadata["end"]), (end_day, end_time))
                self.assertEqual(metadata["route_validation"]["valid_boundary_routes"], len(vehicles))
                self.assertEqual(metadata["vehicles_generated"], len(vehicles))
                self.assertEqual(len(metadata["groups"][0]["generated_departures_per_bin"]), sections * 12)
                contexts = metadata["context_selection"]["contexts"]
                self.assertEqual(sum(context["reference_programmed"] for context in contexts), len(vehicles))
                self.assertEqual(len(metadata["chronological_composition"]["boundaries"]), sections - 1)
                for context in contexts:
                    self.assertEqual(sum(context["begin"] <= t < context["end"] for t in departures),
                                     context["programmed"])

    def test_volume_reduction_preserves_exact_reference_routes_times_and_observations(self):
        self.model["regional_demand"]["volume_recalibration"] = {"retained_fraction": .85}
        self.write_model()
        before, after = {}, {}
        reference = ET.parse(self.generate(output="reference", volume_retention=1, metadata=before)).getroot()
        reduced_file = self.generate(output="reduced", metadata=after)
        reduced = ET.parse(reduced_file).getroot()
        originals = {v.get("id"): ET.tostring(v) for v in reference.findall("vehicle")}
        self.assertEqual(len(reduced.findall("vehicle")), math.floor(.85 * len(originals)))
        for vehicle in reduced.findall("vehicle"):
            self.assertEqual(ET.tostring(vehicle), originals[vehicle.get("id")])
        self.assertEqual(after["calibration"], before["calibration"])
        self.assertEqual(reduced_file.read_bytes(), self.generate(output="repeat").read_bytes())
        self.assertAlmostEqual(after["groups"][0]["expected_departures"], .85*before["groups"][0]["expected_departures"])
        observations = after["spatial_distribution"]["observation_projection"]["observations"]
        for old, new in zip(before["spatial_distribution"]["observation_projection"]["observations"], observations):
            self.assertEqual(old["target_passages"], new["target_passages"])
            self.assertAlmostEqual(new["projected_freeflow_passages"], .85*old["projected_freeflow_passages"])
        paired = ET.parse(self.generate(output="paired", schedule_file=reduced_file)).getroot()
        self.assertEqual(len(paired.findall("vehicle")), len(reduced.findall("vehicle")))

    def test_retention_has_exact_count_and_preserves_temporal_quantiles(self):
        for count in (1, 2, 30, 555, 18117):
            for variation in range(1, 26):
                selected = sorted(demand._retained_indices(count, .85, demand.effective_seed(variation)))
                self.assertEqual(len(selected), math.floor(.85*count))
                self.assertLess(len(selected), .9*count)
                for cut in range(0, count, max(1, count//20)):
                    self.assertLess(abs(sum(i < cut for i in selected) - cut*len(selected)/count), 1.000001)

    def enable_lateral_reduction(self):
        self.model["regional_demand"]["volume_recalibration"] = {"retained_fraction": .85}
        self.model["regional_demand"]["lateral_origin_reduction"] = {
            "retained_fraction": .9, "protected_boundary_groups": ["entry_a"]}
        self.write_model()

    def test_lateral_reduction_preserves_protected_trips_and_every_retained_route_and_time(self):
        self.model["regional_demand"]["volume_recalibration"] = {"retained_fraction": .85}
        self.write_model()
        before, after = {}, {}
        original = ET.parse(self.generate(output="before-lateral", variation=7, metadata=before)).getroot()
        self.enable_lateral_reduction()
        revised_file = self.generate(output="after-lateral", variation=7, metadata=after)
        revised = ET.parse(revised_file).getroot()
        originals = {v.get("id"): ET.tostring(v) for v in original.findall("vehicle")}
        protected = lambda root: {v.get("id") for v in root.findall("vehicle")
                                 if v.find("route").get("edges").split()[0] == "entry_a"}
        self.assertEqual(protected(original), protected(revised))
        old_lateral = len(originals) - len(protected(original))
        new_lateral = len(revised.findall("vehicle")) - len(protected(revised))
        self.assertEqual(new_lateral, math.floor(.9 * old_lateral))
        for vehicle in revised.findall("vehicle"):
            self.assertEqual(ET.tostring(vehicle), originals[vehicle.get("id")])
        self.assertEqual(revised_file.read_bytes(), self.generate(output="repeat-lateral", variation=7).read_bytes())
        self.assertEqual(after["calibration"], before["calibration"])
        self.assertEqual(after["volume_recalibration"]["retained_programmed"], len(originals))
        reduction = after["lateral_origin_reduction"]
        self.assertTrue(reduction["applied"])
        self.assertEqual(reduction["removed_programmed"], old_lateral - new_lateral)
        for old, new in zip(before["spatial_distribution"]["routes"], after["spatial_distribution"]["routes"]):
            factor = 1 if old["origin"] == "entry_a" else .9
            self.assertAlmostEqual(new["expected_departures"], old["expected_departures"] * factor)
        old_observations = before["spatial_distribution"]["observation_projection"]["observations"]
        new_observations = after["spatial_distribution"]["observation_projection"]["observations"]
        for old, new in zip(old_observations, new_observations):
            self.assertEqual(old["target_passages"], new["target_passages"])
            self.assertLessEqual(new["projected_freeflow_passages"], old["projected_freeflow_passages"] + 1e-9)
            self.assertGreaterEqual(new["projected_freeflow_passages"], .9 * old["projected_freeflow_passages"] - 1e-9)
            if old["observation_id"] == "5":
                self.assertAlmostEqual(new["projected_freeflow_passages"], old["projected_freeflow_passages"])
        self.assertAlmostEqual(sum(after["groups"][0]["expected_departures_per_bin"]),
                               sum(p["expected_departures"] for p in after["spatial_distribution"]["routes"]))

    def test_lateral_rule_covers_all_56_contexts_and_25_variations(self):
        routes, factors = [{"origin": "rondon"}, {"origin": "side"}], {"rondon": 1, "side": .9}
        checked = 0
        for day in demand.DAYS:
            for start in range(0, 24, 3):
                for variation in range(1, 26):
                    contexts = demand.resolve_contexts(day=day, start=f"{start:02}:00", variation=variation)["contexts"]
                    count = 110 + start + variation
                    schedule = [{"id": str(i), "depart": str(i * 10800 / count)} for i in range(count)]
                    route_indices = [int((i + variation) % 3 != 0) for i in range(count)]
                    initial = demand._retained_indices(count, .85, contexts[0]["effective_seed"])
                    contexts[0]["reference_programmed"] = len(initial)
                    kept = demand._reduce_lateral_schedule(schedule, route_indices, routes, initial, contexts, factors)
                    self.assertEqual(kept, demand._reduce_lateral_schedule(
                        schedule, route_indices, routes, initial, contexts, factors))
                    protected = {i for i in initial if route_indices[i] == 0}
                    lateral = sorted(initial - protected)
                    self.assertTrue(protected <= kept <= initial)
                    self.assertEqual(len(kept - protected), math.floor(.9 * len(lateral)))
                    self.assertEqual(contexts[0]["programmed"], len(kept))
                    for cut in range(len(lateral) + 1):
                        self.assertLess(abs(sum(i in kept for i in lateral[:cut]) -
                                            cut * math.floor(.9 * len(lateral)) / len(lateral)), 1.000001)
                    checked += 1
        self.assertEqual(checked, 1400)

    def test_lateral_reduction_applies_once_per_context_across_week_boundary_and_replays(self):
        self.model["regional_demand"]["volume_recalibration"] = {"retained_fraction": .85}
        self.write_model()
        before, after = {}, {}
        baseline = ET.parse(self.generate(output="baseline-week", day="sunday", start="21:00",
                                         sections=2, master_seed=42, metadata=before)).getroot()
        self.enable_lateral_reduction()
        revised = self.generate(output="revised-week", day="sunday", start="21:00",
                                sections=2, master_seed=42, metadata=after)
        root = ET.parse(revised).getroot()
        originals = {v.get("id"): ET.tostring(v) for v in baseline.findall("vehicle")}
        for vehicle in root.findall("vehicle"):
            self.assertEqual(ET.tostring(vehicle), originals[vehicle.get("id")])
        for context in after["context_selection"]["contexts"]:
            old = [v for v in baseline.findall("vehicle") if context["begin"] <= float(v.get("depart")) < context["end"]]
            new = [v for v in root.findall("vehicle") if context["begin"] <= float(v.get("depart")) < context["end"]]
            lateral = lambda vs: [v for v in vs if v.find("route").get("edges").split()[0] != "entry_a"]
            self.assertEqual(len(lateral(new)), math.floor(.9 * len(lateral(old))))
            self.assertEqual(context["programmed"], len(new))
        replay = self.generate(output="replay-week", day="sunday", start="21:00", sections=2,
                               variations=after["context_selection"]["variations"])
        self.assertEqual(revised.read_bytes(), replay.read_bytes())
        transition = after["chronological_composition"]
        self.assertEqual(transition["combined_programmed"], len(root.findall("vehicle")))
        self.assertEqual(transition["context_programmed_sum"], transition["combined_programmed"])
        for window in transition["boundaries"][0]["windows"]:
            self.assertEqual(window["programmed_left"], sum(
                10800 - window["seconds"] <= float(v.get("depart")) < 10800 for v in root.findall("vehicle")))
        self.assertAlmostEqual(sum(after["groups"][0]["expected_departures_per_bin"]),
                               after["groups"][0]["expected_departures"])
        for old, new in zip(before["groups"][0]["expected_departures_per_bin"],
                            after["groups"][0]["expected_departures_per_bin"]):
            self.assertLessEqual(new, old + 1e-8)
            self.assertGreaterEqual(new, .9 * old - 1e-8)

    def test_explicit_paired_schedule_is_not_reduced_again_by_lateral_policy(self):
        self.enable_lateral_reduction()
        original = self.generate(output="reduced-once")
        metadata = {}
        paired = self.generate(output="paired-lateral", schedule_file=original, metadata=metadata)
        attrs = lambda path: [v.attrib for v in ET.parse(path).getroot().findall("vehicle")]
        self.assertEqual(attrs(original), attrs(paired))
        self.assertFalse(metadata["lateral_origin_reduction"]["applied"])
        self.assertEqual(metadata["lateral_origin_reduction"]["removed_programmed"], 0)

    def test_invalid_lateral_policy_is_rejected_before_generation(self):
        self.enable_lateral_reduction()
        policy = self.model["regional_demand"]["lateral_origin_reduction"]
        for value in (0, -1, 1.1, True, float("nan"), float("inf")):
            policy["retained_fraction"] = value
            self.write_model()
            with self.assertRaisesRegex(ValueError, "laterais"):
                self.generate()
        policy["retained_fraction"] = .9
        for groups in ([], None, "entry_a", ["internal_unknown"], [True]):
            policy["protected_boundary_groups"] = groups
            self.write_model()
            with self.assertRaisesRegex(ValueError, "grupos periféricos"):
                self.generate()

    def test_frozen_scale_is_not_renormalized_by_a_new_clock_reference(self):
        reference = {s: p["baseline_reference_cars_15_18"] for s,p in self.calibration["sensors"].items()}
        self.model["regional_demand"]["frozen_scale_reference_cars"] = reference
        self.write_model()
        before, after = {}, {}
        self.generate(output="oldclock", metadata=before)
        for profile in self.calibration["sensors"].values():
            profile["baseline_reference_cars_15_18"] *= 2
        self.generate(output="newclock", metadata=after)
        self.assertEqual(before["routes_sha256"], after["routes_sha256"])

    def test_invalid_retention_is_rejected(self):
        for fraction in (0, -1, 1.1, True, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                self.generate(volume_retention=fraction)

    def test_invalid_or_discontinuous_context_selections_are_rejected(self):
        invalid = [dict(day="2026-08-25"), dict(day="Tuesday"), dict(start="16:00"), dict(sections=0), dict(sections=57),
                   dict(sections=True), dict(sections=1.0), dict(variation=0), dict(variation=26),
                   dict(variation=True), dict(variation=1.5), dict(seed=-1),
                   dict(seed=2**31), dict(seed=True), dict(spatial_scenario="balanced"), dict(spatial_scenario="dispersed"), dict(spatial_scenario="local"),
                   dict(sections=2, variation=7), dict(sections=2, seed=42),
                   dict(master_seed=-1), dict(master_seed=2**63), dict(master_seed=True),
                   dict(variation=7, master_seed=42), dict(variation=7, variations=[7]),
                   dict(sections=2, variations=[7]), dict(sections=2, variations=[7, 26]),
                   dict(sections=2, variations=[7, True]), dict(variations="7")]
        for parameters in invalid:
            with self.subTest(parameters=parameters), self.assertRaises(ValueError):
                self.generate(**parameters)
        self.assertFalse((self.directory / "demand").exists())

    def test_network_identity_cannot_silently_change(self):
        self.net.write_text(self.net.read_text().replace('length="600"', 'length="700"'))
        with self.assertRaisesRegex(ValueError, "outra versão"):
            self.generate()

    def test_internal_origin_is_rejected(self):
        self.model["portals"]["entries"][0]["edge"] = "middle"
        self.write_model()
        with self.assertRaisesRegex(ValueError, "internos"):
            self.generate()

    def test_lane_opportunity_must_match_the_actual_network(self):
        self.model["portals"]["entries"][0]["passenger_lanes"] = 10
        self.write_model()
        with self.assertRaisesRegex(ValueError, "Faixas passenger"):
            self.generate()

    def test_geographically_qualified_return_is_not_excluded_by_sensor_population(self):
        self.model["portals"]["entries"][2]["boundary_group"] = "shared"
        self.model["portals"]["exits"][0]["boundary_group"] = "shared"
        self.write_model()
        metadata = {}
        self.generate(metadata=metadata)
        pair = next(p for p in metadata["spatial_distribution"]["routes"] if p["origin"] == "entry_c" and p["destination"] == "exit_a")
        self.assertTrue(pair["returns_to_same_access"])
        self.assertTrue(pair["demand_eligible"])
        self.assertGreater(pair["generated_departures"], 0)
        self.assertEqual(metadata["spatial_distribution"]["catalog"]["accepted_pairs"], 8)

    def test_permitted_uturn_remains_eligible_and_retains_complete_endpoints(self):
        root = ET.parse(self.net).getroot()
        for connection in root.findall("connection"):
            if connection.get("from") == "entry_c" and connection.get("to") == "unseen":
                connection.set("dir", "t")
        ET.ElementTree(root).write(self.net)
        self.write_model()
        metadata = {}
        self.generate(metadata=metadata)
        pair = next(p for p in metadata["spatial_distribution"]["routes"] if p["has_uturn"])
        self.assertGreater(pair["generated_departures"], 0)
        self.assertTrue(pair["demand_eligible"])

    def test_short_connected_trip_keeps_complete_boundary_edges(self):
        root = ET.parse(self.net).getroot()
        ET.SubElement(root, "connection", **{"from": "entry_c", "to": "exit_a", "fromLane": "0", "toLane": "0", "dir": "s"})
        ET.ElementTree(root).write(self.net)
        self.write_model()
        metadata = {}
        with patch.dict(PATHS, {("entry_c", "exit_a"): "entry_c exit_a"}):
            route_file = self.generate(metadata=metadata)
        short = next(p for p in metadata["spatial_distribution"]["routes"] if p["origin"] == "entry_c" and p["destination"] == "exit_a")
        self.assertEqual(short["length_m"], 200)
        self.assertEqual(short["normal_edge_count"], 2)
        self.assertGreater(short["generated_departures"], 0)
        self.assertTrue(all(v.get("departPos") == "0" and v.get("arrivalPos") == "max" for v in ET.parse(route_file).getroot().findall("vehicle")))

    def test_routing_catalog_seed_is_fixed_across_realization_seeds(self):
        results = []
        for variation in (1, 7):
            metadata = {}
            self.generate(output=str(variation), variation=variation, metadata=metadata)
            results.append(metadata)
        self.assertEqual([_option(m["command"], "--seed") for m in results], ["0", "0"])
        self.assertNotEqual(results[0]["seed"], results[1]["seed"])

    def test_shared_observations_count_one_vehicle_once_in_the_population(self):
        metadata = {}
        self.generate(metadata=metadata)
        self.assertEqual([group["id"] for group in metadata["groups"]], ["regional"])
        group = metadata["groups"][0]
        self.assertEqual(group["generated_departures"], metadata["vehicles_generated"])
        self.assertEqual(sum(group["generated_departures_per_bin"]), group["generated_departures"])
        self.assertAlmostEqual(sum(group["expected_departures_per_bin"]), group["expected_departures"])
        self.assertAlmostEqual(group["expected_departures"], 1200)
        incidence = metadata["spatial_distribution"]["observation_incidence_generated"]
        self.assertEqual(set(incidence), {"5", "6", "both", "neither"})
        self.assertEqual(sum(incidence.values()), metadata["vehicles_generated"])
        self.assertTrue(all(count > 0 for count in incidence.values()))
        both = next(p for p in metadata["spatial_distribution"]["routes"] if p["sensor_ids"] == ["5", "6"])
        self.assertGreater(both["generated_departures"], 0)
        self.assertEqual(set(both["observation_movements"]), {"5", "6"})
        self.assertLess(both["observation_freeflow_delay_s"]["5"], both["observation_freeflow_delay_s"]["6"])

    def test_legacy_midpoint_alias_preserves_integrated_demand_without_restoring_budgets(self):
        integrated, alias = {}, {}
        first = self.generate(output="integrated", variation=7, metadata=integrated)
        second = self.generate(output="alias", spatial_scenario="regional-midpoint", variation=7, metadata=alias)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(alias["requested_spatial_scenario"], "regional-midpoint")
        self.assertEqual(alias["spatial_scenario"], "regional-integrated")
        self.assertEqual(alias["groups"], integrated["groups"])

    def test_regional_reference_is_versioned_and_invalid_mass_is_rejected(self):
        baseline, modified = {}, {}
        self.generate(output="baseline", metadata=baseline)
        self.model["regional_demand"]["reference_expected_departures"] = 1800
        self.write_model()
        self.generate(output="modified", metadata=modified)
        self.assertAlmostEqual(modified["spatial_distribution"]["expected_network_departures"], 1800)
        self.assertNotEqual(baseline["spatial_sha256"], modified["spatial_sha256"])
        for value in (None, True, -1, 0, float("inf")):
            self.model["regional_demand"]["reference_expected_departures"] = value
            self.write_model()
            with self.assertRaisesRegex(ValueError, "regional de referência"):
                self.generate()

    def test_mapping_sensitivity_projects_fixed_demand_without_filling_an_uncovered_counter(self):
        baseline = self.generate(output="baseline").read_bytes()
        self.model["sensors"][0]["candidates"] = [{"edge": "bypass"}, {"edge": "never_crossed"}]
        self.write_model()
        metadata = {}
        self.assertEqual(baseline, self.generate(output="sensitivity", metadata=metadata).read_bytes())
        alternatives = metadata["spatial_distribution"]["sensor_mapping_sensitivity"]
        self.assertEqual(len(alternatives), 3)
        self.assertEqual(len({r["expected_network_departures"] for r in alternatives}), 1)
        uncovered = next(row for row in alternatives if row["observation_edges"]["5"] == "never_crossed")
        self.assertEqual(uncovered["expected_sensor_passages"]["5"], 0)

    def test_metadata_od_portals_and_corridors_conserve_generated_counts(self):
        metadata = {}
        self.generate(metadata=metadata)
        spatial = metadata["spatial_distribution"]
        self.assertEqual(sum(p["generated_departures"] for p in spatial["routes"]), metadata["vehicles_generated"])
        for role in ("entries", "exits"):
            self.assertEqual(sum(p["generated_departures"] for p in spatial["portals"][role]), metadata["vehicles_generated"])
        self.assertEqual(spatial["corridors"][0]["generated_departures"],
                         sum(p["generated_departures"] for p in spatial["routes"] if "6" in p["sensor_ids"]))
        self.assertEqual(spatial["coverage"]["used_normal_edges"], 12)
        self.assertEqual(spatial["distance_distribution"]["min"], 700)

    def test_internal_connections_are_included_in_route_length_and_impedance(self):
        root = ET.parse(self.net).getroot()
        internal = ET.SubElement(root, "edge", id=":junction", function="internal")
        ET.SubElement(internal, "lane", id=":junction_0", index="0", length="25", speed="5", allow="passenger")
        for connection in root.findall("connection"):
            if connection.get("from") == "sensor5" and connection.get("to") == "bypass":
                connection.set("via", ":junction_0")
        ET.SubElement(root, "connection", **{"from": ":junction", "to": "bypass", "fromLane": "0", "toLane": "0"})
        ET.ElementTree(root).write(self.net)
        self.write_model()
        metadata = {}
        self.generate(metadata=metadata)
        route = next(p for p in metadata["spatial_distribution"]["routes"] if p["sensor_ids"] == ["5"])
        self.assertEqual(route["internal_length_m"], 25)
        self.assertEqual(route["length_m"], 1325)
        self.assertEqual(route["freeflow_time_s"], 135)

    def test_no_remaining_routes_does_not_overwrite_previous_demand(self):
        previous = self.generate()
        original = previous.read_bytes()
        def empty(command, **kwargs):
            Path(_option(command, "--output-file")).write_text("<routes />")
        with patch.object(demand.subprocess, "run", side_effect=empty):
            with self.assertRaisesRegex(ValueError, "Nenhum percurso"):
                self.generate()
        self.assertEqual(previous.read_bytes(), original)
        self.assertEqual(list(previous.parent.glob(".metasettran-*")), [])

    def test_unconnected_route_is_fatal_even_if_endpoints_match(self):
        def disconnected(command, **kwargs):
            _native_routes(command, **kwargs)
            output = Path(_option(command, "--output-file"))
            output.write_text(output.read_text().replace("entry_a sensor5 bypass middle exit_a", "entry_a exit_a"))
        with patch.object(demand.subprocess, "run", side_effect=disconnected):
            with self.assertRaisesRegex(ValueError, "Percurso inválido"):
                self.generate()

    def test_destination_preference_cannot_inflate_the_regional_budget(self):
        original, changed = {}, {}
        self.generate(output="original", metadata=original)
        self.model["portals"]["exits"][0]["road_type"] = "highway.primary"
        self.model["regional_demand"]["destination_hierarchy_weights"]["highway.primary"] = 4
        self.write_model()
        self.generate(output="changed", metadata=changed)
        self.assertEqual(original["groups"], changed["groups"])
        original_routes = original["spatial_distribution"]["routes"]
        changed_routes = changed["spatial_distribution"]["routes"]
        self.assertNotEqual([r["prior_weight"] for r in original_routes], [r["prior_weight"] for r in changed_routes])

    def test_opposite_physical_entries_do_not_share_one_budget_because_of_street_name(self):
        before, after = {}, {}
        self.generate(output="before", metadata=before)
        # Renaming two independently qualified boundary accesses cannot halve
        # their combined opportunity. No external count is keyed to this name.
        for portal in self.model["portals"]["entries"][:2]:
            portal["corridor"] = "same_avenue_opposite_extremities"
        self.write_model()
        self.generate(output="after", metadata=after)
        a = before["spatial_distribution"]["routes"]
        b = after["spatial_distribution"]["routes"]
        self.assertEqual([r["prior_weight"] for r in a], [r["prior_weight"] for r in b])
        self.assertEqual(before["routes_sha256"], after["routes_sha256"])

    def test_alternative_branches_of_one_physical_access_do_not_double_its_opportunity(self):
        before, after = {}, {}
        self.generate(output="before", metadata=before)
        for portal in self.model["portals"]["entries"][:2]:
            portal["boundary_group"] = "shared_physical_access"
        self.write_model()
        self.generate(output="after", metadata=after)
        def ratio(metadata):
            rows = metadata["spatial_distribution"]["routes"]
            return (sum(r["prior_weight"] for r in rows if r["origin"] in ("entry_a", "entry_b")) /
                    sum(r["prior_weight"] for r in rows if r["origin"] in ("entry_c", "entry_d")))
        self.assertAlmostEqual(ratio(before), 2 * ratio(after))
        self.assertEqual(before["vehicles_generated"], after["vehicles_generated"])

    def test_extra_native_templates_do_not_duplicate_trips_or_expand_budgets(self):
        original, changed = {}, {}
        a = self.generate(output="original", metadata=original).read_bytes()
        self.model["route_templates"] = [{"id": "through", "origins": ["entry_a"], "via": ["sensor5"]}]
        self.write_model()
        b = self.generate(output="templates", metadata=changed).read_bytes()
        self.assertEqual(a, b)
        self.assertEqual(changed["spatial_distribution"]["catalog"]["rejected_by_reason"], {"duplicate_route_alternative": 2})

    def test_native_router_must_respect_requested_ordered_sections(self):
        self.model["route_templates"] = [{"id": "bad", "origins": ["entry_a"], "via": ["sensor6", "sensor5"]}]
        self.write_model()
        with self.assertRaisesRegex(ValueError, "seções ordenadas"):
            self.generate()

    def test_through_template_cannot_force_a_second_visit_to_the_same_junction(self):
        root = ET.parse(self.net).getroot()
        edge = ET.SubElement(root, "edge", id="back", **{"from": "j2", "to": "j1"})
        ET.SubElement(edge, "lane", id="back_0", index="0", length="150", speed="10", allow="passenger")
        for source, target in (("bypass", "back"), ("back", "bridge"), ("sensor6", "middle")):
            ET.SubElement(root, "connection", **{"from": source, "to": target, "fromLane": "0", "toLane": "0"})
        ET.ElementTree(root).write(self.net)
        self.write_model()
        route = "entry_a sensor5 bypass back bridge sensor6 middle exit_a"
        with patch.dict(PATHS, {("entry_a", "exit_a"): route}):
            previous = self.generate(output="previous").read_bytes()
            self.model["route_templates"] = [{"id": "through", "origins": ["entry_a"],
                "destinations": ["exit_a"], "via": ["sensor5", "bridge"], "require_junction_simple": True}]
            self.write_model()
            metadata = {}
            self.assertEqual(previous, self.generate(output="qualified", metadata=metadata).read_bytes())
        # The added via alternative is rejected on geometry, regardless of
        # its sensor incidences. No blanket prohibition of native returns.
        self.assertEqual(metadata["spatial_distribution"]["catalog"]["rejected_by_reason"],
                         {"through_template_revisits_junction": 1})

    def test_connectivity_alone_does_not_approve_a_geographic_portal(self):
        for field in ("status", "references", "boundary_evidence"):
            original = self.model["portals"]["entries"][0].pop(field)
            self.write_model()
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "qualificação cartográfica"):
                self.generate()
            self.model["portals"]["entries"][0][field] = original

    def test_geographic_node_and_coordinates_must_match_the_network(self):
        portal = self.model["portals"]["entries"][0]
        original = portal["boundary_node"]
        portal["boundary_node"] = "internal_junction"
        self.write_model()
        with self.assertRaisesRegex(ValueError, "Nó geográfico"):
            self.generate()
        portal["boundary_node"] = original
        portal["boundary_xy_m"][0] += 20
        self.write_model()
        with self.assertRaisesRegex(ValueError, "Coordenadas cartográficas"):
            self.generate()

    def test_paired_schedule_preserves_ids_departures_count_and_physical_attributes(self):
        baseline = self.generate(output="original", variation=7)
        original = ET.parse(baseline).getroot()
        self.model["portals"]["exits"][0]["road_type"] = "highway.primary"
        self.model["regional_demand"]["destination_hierarchy_weights"]["highway.primary"] = 4
        self.write_model()
        metadata = {}
        changed = ET.parse(self.generate(output="paired", variation=7, schedule_file=baseline, metadata=metadata)).getroot()
        self.assertEqual([vehicle.attrib for vehicle in original.findall("vehicle")],
                         [vehicle.attrib for vehicle in changed.findall("vehicle")])
        self.assertEqual([item.attrib for item in original.findall("vType")],
                         [item.attrib for item in changed.findall("vType")])
        self.assertNotEqual([vehicle.find("route").get("edges") for vehicle in original.findall("vehicle")],
                            [vehicle.find("route").get("edges") for vehicle in changed.findall("vehicle")])
        self.assertEqual(metadata["paired_schedule"]["count"], len(original.findall("vehicle")))
        self.assertEqual(metadata["spatial_distribution"]["expected_network_departures"], len(original.findall("vehicle")))

    def test_invalid_paired_schedule_is_rejected_before_publishing_routes(self):
        baseline = self.generate(output="original")
        root = ET.parse(baseline).getroot()
        root.findall("vehicle")[1].set("id", root.findall("vehicle")[0].get("id"))
        duplicate = self.directory / "duplicate.rou.xml"
        ET.ElementTree(root).write(duplicate)
        with self.assertRaisesRegex(ValueError, "Agenda pareada"):
            self.generate(output="paired", schedule_file=duplicate)
        self.assertFalse((self.directory / "paired" / "metasettran.rou.xml").exists())

    def test_required_six_hour_windows_keep_all_departures_in_one_output(self):
        for day, start, end_day, end_time in (("tuesday", "15:00", "tuesday", "21:00"),
                                              ("friday", "21:00", "saturday", "03:00"),
                                              ("sunday", "21:00", "monday", "03:00")):
            metadata = {}
            route_file = self.generate(output=day, day=day, start=start, sections=2, metadata=metadata)
            vehicles = ET.parse(route_file).getroot().findall("vehicle")
            departures = [float(vehicle.get("depart")) for vehicle in vehicles]
            self.assertEqual(metadata["duration"], 21600)
            self.assertEqual((metadata["end_day"], metadata["end"]), (end_day, end_time))
            self.assertEqual(departures, sorted(departures))
            self.assertTrue(any(timestamp < 10800 for timestamp in departures))
            self.assertTrue(any(timestamp >= 10800 for timestamp in departures))
            self.assertLess(departures[-1], 21600)
            self.assertEqual(len(metadata["groups"][0]["generated_departures_per_bin"]), 24)

    def test_observation_targets_follow_joint_realization_except_in_paired_comparison(self):
        # Unequal empirical changes must survive spatial projection, instead
        # of forcing both local observations back to the central profile.
        self.realization_multipliers = {"5": 1.4, "6": .8}
        realized_metadata, paired_metadata = {}, {}
        realized_file = self.generate(output="realized", variation=7, metadata=realized_metadata)
        paired_file = self.generate(output="paired", variation=7, schedule_file=realized_file,
                                    metadata=paired_metadata)
        for metadata, curve_key in ((realized_metadata, "realization_knots"), (paired_metadata, "knots")):
            projection = metadata["spatial_distribution"]["observation_projection"]
            self.assertTrue(projection["target_basis"].startswith(curve_key + "_"))
            for observation in projection["observations"]:
                sensor, index = observation["observation_id"], observation["bin"]
                curve = metadata["calibration"]["sensors"][sensor][curve_key]
                begin = demand.WEEK_START_SECONDS + index * 900
                self.assertAlmostEqual(observation["target_passages"], demand.integrate_rate(curve, begin, begin + 900))
        realized_targets = realized_metadata["spatial_distribution"]["observation_projection"]["observations"]
        paired_targets = paired_metadata["spatial_distribution"]["observation_projection"]["observations"]
        for realized, central in zip(realized_targets, paired_targets):
            self.assertAlmostEqual(realized["target_passages"], central["target_passages"] *
                                   self.realization_multipliers[realized["observation_id"]])
        self.assertEqual([vehicle.attrib for vehicle in ET.parse(realized_file).getroot().findall("vehicle")],
                         [vehicle.attrib for vehicle in ET.parse(paired_file).getroot().findall("vehicle")])

    def test_directional_observation_can_share_a_trip_with_both_sensors_without_new_departures(self):
        baseline_metadata, estimated_metadata = {}, {}
        baseline = self.generate(output="baseline", variation=7, metadata=baseline_metadata)
        # The fixture bridge lies between both observed probes. Its section
        # count is another incidence of the same cars, not a population.
        self.model["regional_demand"]["directional_prior"] = {"probe_edge": "bridge", "ratios": [.1, .3]}
        self.write_model()
        estimated = self.generate(output="estimated", variation=7, metadata=estimated_metadata)
        self.assertEqual([vehicle.attrib for vehicle in ET.parse(baseline).getroot().findall("vehicle")],
                         [vehicle.attrib for vehicle in ET.parse(estimated).getroot().findall("vehicle")])
        self.assertEqual(estimated_metadata["vehicles_generated"], baseline_metadata["vehicles_generated"])
        spatial = estimated_metadata["spatial_distribution"]
        self.assertAlmostEqual(spatial["expected_network_departures"], 1200)
        self.assertAlmostEqual(sum(route["expected_departures"] for route in spatial["routes"]), 1200)
        self.assertEqual(sum(spatial["observation_incidence_generated"].values()), estimated_metadata["vehicles_generated"])
        overlapping = next(route for route in spatial["routes"] if route["sensor_ids"] == ["5", "6"])
        self.assertGreater(overlapping["generated_departures"], 0)
        delays = overlapping["observation_freeflow_delay_s"]
        self.assertLess(delays["5"], delays["rondon_reverse_estimate"])
        self.assertLess(delays["rondon_reverse_estimate"], delays["6"])
        observations = spatial["observation_projection"]["observations"]
        directional = [row for row in observations if row["observation_id"] == "rondon_reverse_estimate"]
        sensor6 = [row for row in observations if row["observation_id"] == "6"]
        self.assertEqual(len(directional), 12)
        for estimated_row, measured_row in zip(directional, sensor6):
            self.assertEqual(estimated_row["target_kind"], "estimated_external_direction_transfer")
            self.assertEqual(measured_row["target_kind"], "measured_car_curve_conditional_on_mapping")
            self.assertAlmostEqual(estimated_row["target_passages"], .2 * measured_row["target_passages"])

    def test_infeasible_directional_target_records_residual_instead_of_inflating_mass(self):
        baseline_metadata, infeasible_metadata = {}, {}
        self.generate(output="baseline", variation=7, metadata=baseline_metadata)
        self.model["regional_demand"]["directional_prior"] = {"probe_edge": "bridge", "ratios": [100.0]}
        self.write_model()
        self.generate(output="infeasible", variation=7, metadata=infeasible_metadata)
        self.assertEqual(baseline_metadata["groups"], infeasible_metadata["groups"])
        projection = infeasible_metadata["spatial_distribution"]["observation_projection"]
        self.assertAlmostEqual(projection["total_fixed"], 1200)
        rows = [row for row in projection["observations"] if row["observation_id"] == "rondon_reverse_estimate"]
        self.assertGreater(sum(row["target_passages"] for row in rows), projection["total_fixed"])
        self.assertTrue(all(row["residual"] < 0 for row in rows))
        self.assertLessEqual(sum(row["projected_freeflow_passages"] for row in rows), projection["total_fixed"])

    def test_directional_ratio_interpolates_and_is_continuous_at_day_and_week_boundaries(self):
        config = {"daily_ratio_knots": [
            {"second": 0, "ratio": .8}, {"second": 21600, "ratio": .8},
            {"second": 32400, "ratio": 1.3}, {"second": 54000, "ratio": 1.0},
            {"second": 64800, "ratio": .6}, {"second": 75600, "ratio": .8},
            {"second": 86400, "ratio": .8},
        ]}
        self.assertAlmostEqual(demand._directional_ratio(config, 27000), 1.05)
        self.assertGreater(demand._directional_ratio(config, 32400), demand._directional_ratio(config, 64800))
        epsilon = 1e-4
        for day in range(8):
            for clock in (0, 21600, 32400, 54000, 64800, 75600):
                moment = day * 86400 + clock
                self.assertAlmostEqual(demand._directional_ratio(config, moment - epsilon),
                                       demand._directional_ratio(config, moment + epsilon), places=7)
            self.assertAlmostEqual(demand._directional_ratio(config, day * 86400 + 27000), 1.05)
        incomplete_day = {"daily_ratio_knots": [{"second": 900, "ratio": .8}, {"second": 86400, "ratio": .8}]}
        with self.assertRaisesRegex(ValueError, "dia civil completo"):
            demand._directional_ratio(incomplete_day, 0)

    def test_inversion_preserves_continuity_across_rate_segments(self):
        class KnownHazard:
            first = True
            def expovariate(self, rate):
                if self.first:
                    self.first = False
                    return .5
                return 1
        samples = list(demand._departures([(0, 2, 0, 2), (2, 4, 2, 0)], KnownHazard()))
        for timestamp, expected in zip(samples, (1, math.sqrt(3), 4 - math.sqrt(3), 3)):
            self.assertAlmostEqual(timestamp, expected)
        self.assertEqual(len(samples), 4)


if __name__ == "__main__":
    unittest.main()
