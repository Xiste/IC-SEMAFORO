"""Contratos da distribuição OD, incidência dos sensores e reprodução."""

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

    def test_invalid_or_discontinuous_context_selections_are_rejected(self):
        invalid = [dict(day="2026-08-25"), dict(day="Tuesday"), dict(start="16:00"), dict(sections=0), dict(sections=57),
                   dict(sections=True), dict(sections=1.0), dict(variation=0), dict(variation=26),
                   dict(variation=True), dict(variation=1.5), dict(seed=-1),
                   dict(seed=2**31), dict(seed=True), dict(spatial_scenario="balanced"), dict(spatial_scenario="dispersed"), dict(spatial_scenario="local")]
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
