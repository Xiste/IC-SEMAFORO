"""Contagem de carros e integridade das viagens do protótipo MetaSettran."""

from copy import deepcopy
import gzip
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import xml.etree.ElementTree as ET

from SistemaDeSemaforos.metrics.episode_metrics_collector import (
    collect_metasettran_validation, metasettran_observation_edges,
)
from SistemaDeSemaforos.metrics.sumo_output_configuration import prepare_outputs


class MetaSettranValidationTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        (self.directory / "raw").mkdir()
        (self.directory / "inputs").mkdir()
        self.identifiers = ["natural", "teleported", "incomplete", "undeparted", "removed"]
        routes = ET.Element("routes")
        for identifier in self.identifiers:
            vehicle = ET.SubElement(routes, "vehicle", id=identifier, depart="0", departPos="0", arrivalPos="max")
            ET.SubElement(vehicle, "route", edges="entry middle exit")
        self.routes_path = self.directory / "routes.xml"
        ET.ElementTree(routes).write(self.routes_path, encoding="utf-8")
        self.net_path = self.directory / "net.xml"
        self.net_path.write_text('<net><edge id="entry"><lane id="entry_0" length="100"/></edge>'
                                 '<edge id="exit"><lane id="exit_0" length="100"/></edge></net>')
        self.spatial = {"sensors": [
            {"sensor_id": sensor, "status": "unconfirmed", "candidates": [
                {"edge": f"s{sensor}_before", "position": "before_intersection"},
                {"edge": f"s{sensor}_after", "position": "after_intersection"},
            ]} for sensor in (6, 5)
        ]}
        profiles = {}
        for sensor, count in ((6, 2), (5, 4)):
            profiles[str(sensor)] = {
                "target_counts": [count] * 12,
                "validation": {
                    "primary": {"daily_counts": [{
                        "date": "2026-08-25", "counts": [count] * 12,
                        "eligible": [True] * 12, "exposure_seconds": [900] * 12,
                    }]},
                    "post": {"daily_counts": []},
                },
            }
        self.generation = {
            "routes_file": str(self.routes_path), "vehicles_generated": 5, "duration": 10800,
            "net_file": str(self.net_path),
            "spatial_model": self.spatial, "calibration": {"sensors": profiles},
        }
        self.trips = ET.Element("tripinfos")
        for identifier, depart, arrival, vaporized in (
            ("natural", "0", "100", ""),
            ("teleported", "1", "1000", ""),
            ("incomplete", "10801", "-1", "end"),
            ("undeparted", "-1", "-1", ""),
            ("removed", "5", "-1", "collision"),
        ):
            ET.SubElement(self.trips, "tripinfo", id=identifier, depart=depart,
                          arrival=arrival, vaporized=vaporized,
                          departLane="entry_0", departPos="0", arrivalLane="exit_0", arrivalPos="100",
                          routeLength=str({"natural": 3000, "teleported": 2800,
                                           "incomplete": 200, "undeparted": 0, "removed": 100}[identifier]))
        self.write_gz("trips.xml.gz", self.trips)
        self.vehicle_routes = ET.Element("routes")
        for identifier, depart, times in (
            ("natural", "0", "20 40 100"),
            ("teleported", "1", "20 40 1000"),
            ("incomplete", "10801", "10820 -1 -1"),
            ("removed", "5", "20 -1 -1"),
        ):
            vehicle = ET.SubElement(self.vehicle_routes, "vehicle", id=identifier, depart=depart)
            ET.SubElement(vehicle, "route", edges="entry middle exit", exitTimes=times)
        self.write_gz("vehicle_routes.xml.gz", self.vehicle_routes)
        self.log = (
            "Warning: Teleporting vehicle 'teleported'; waited too long (jam), lane='edge_0', time=500.00.\n"
            "Warning: Vehicle 'teleported' ends teleporting on edge 'next', time=501.00.\n"
            "Warning: Teleporting vehicle 'teleported'; waited too long (yield), lane='edge_0', time=600.00.\n"
            "Warning: Teleporting vehicle 'removed'; collision, lane='edge_0', time=700.00.\n"
        )
        (self.directory / "sumo.log").write_text(self.log, encoding="utf-8")
        self.summary = {"teleports": 3, "vehicles_inserted": 4}
        summary = ET.Element("summary")
        ET.SubElement(summary, "step", time="899", inserted="3", arrived="1", running="2",
                      waiting="2", teleports="3", halting="1")
        ET.SubElement(summary, "step", time="11699", inserted="4", arrived="2", running="1",
                      waiting="1", teleports="3", halting="1")
        self.write_gz("summary.xml.gz", summary)
        self.counts = ET.Element("meandata")
        for index in range(13):
            interval = ET.SubElement(self.counts, "interval", begin=str(index * 900),
                                     end=str((index + 1) * 900))
            for edge, amount in (("s6_before", 2), ("s6_after", 3),
                                 ("s5_before", 4), ("s5_after", 5)):
                ET.SubElement(interval, "edge", id=edge, entered=str(amount if index < 12 else 1))
        self.write_gz("metasettran_counts.xml.gz", self.counts)

    def write_gz(self, name, root):
        with gzip.open(self.directory / "raw" / name, "wb") as stream:
            ET.ElementTree(root).write(stream, encoding="utf-8")

    def collect(self, **kwargs):
        return collect_metasettran_validation(self.directory, self.generation,
                                             summary_metrics=self.summary, **kwargs)

    def test_teleport_arrival_never_becomes_natural_and_every_trip_is_accounted(self):
        vehicles = {"natural": {"legacy_duration": 100}}
        result = self.collect(vehicles=vehicles)
        metrics = result["metrics"]
        for name in ("completed_without_teleport", "completed_after_teleport", "not_inserted",
                     "incomplete_at_end", "removed_without_completion"):
            self.assertEqual(metrics[f"vehicles_{name}"], 1)
        self.assertEqual(metrics["vehicles_with_teleport"], 2)
        self.assertEqual(metrics["vehicles_inserted_after_demand_window"], 1)
        self.assertEqual(result["trip_accounting"], {
            "generated": 5, "accounted": 5, "teleport_events": 3,
            "teleport_vehicle_ids_verified": True,
        })
        self.assertEqual(vehicles["teleported"]["metasettran_trip_status"], "completed_after_teleport")
        self.assertTrue(vehicles["removed"]["experienced_teleport"])
        self.assertFalse(vehicles["natural"]["experienced_teleport"])
        self.assertEqual(vehicles["natural"]["legacy_duration"], 100)
        self.assertFalse(result["ready_for_weekly_expansion"])
        self.assertEqual(result["boundary_integrity"]["insertions_at_expected_portal_start"], 4)
        self.assertEqual(result["boundary_integrity"]["natural_arrivals_at_expected_portal_end"], 1)

    def test_native_insertions_and_natural_arrivals_use_the_planned_extremities(self):
        for attribute, value in (("departLane", "middle_0"), ("departPos", "10"),
                                 ("arrivalLane", "middle_0"), ("arrivalPos", "90")):
            with self.subTest(attribute=attribute):
                trips = deepcopy(self.trips)
                trips[0].set(attribute, value)
                self.write_gz("trips.xml.gz", trips)
                with self.assertRaisesRegex(ValueError, "portal previsto"):
                    self.collect()

    def test_incomplete_route_endpoint_declarations_are_rejected(self):
        root = ET.parse(self.routes_path).getroot()
        root[0].set("departPos", "random")
        ET.ElementTree(root).write(self.routes_path)
        with self.assertRaisesRegex(ValueError, "extremos completos"):
            self.collect()

    def test_sensor_candidates_are_compared_separately_and_only_as_car(self):
        result = self.collect()
        self.assertEqual(result["count_class"], "car")
        self.assertEqual(result["simulation_class"], "passenger")
        comparisons = {item["edge"]: item for item in result["count_comparisons"]}
        self.assertEqual(len(comparisons), 4)
        self.assertEqual(comparisons["s6_before"]["against_training_curve"]["mae_cars_per_15min"], 0)
        self.assertEqual(comparisons["s6_after"]["against_training_curve"]["mae_cars_per_15min"], 1)
        self.assertEqual(comparisons["s6_after"]["against_training_curve"]["wape"], 0.5)
        self.assertEqual(comparisons["s6_before"]["simulated_cars_per_15min"], [2] * 12)
        for comparison in comparisons.values():
            self.assertEqual(comparison["cars_passing_during_clearance"], 1)
            self.assertEqual(comparison["mapping_status"], "unconfirmed")

    def add_timed_sensor_routes(self):
        root = ET.parse(self.routes_path).getroot()
        for vehicle in root:
            vehicle.find("route").set("edges", "entry s6_before middle s5_before exit")
        ET.ElementTree(root).write(self.routes_path)
        for vehicle in self.vehicle_routes:
            route = vehicle.find("route")
            route.set("edges", "entry :a s6_before :b middle :c s5_before :d exit")
            route.set("exitTimes", "20 25 30 31 40 45 80 85 100")
            if vehicle.get("id") == "incomplete":
                route.set("exitTimes", "10820 10825 10830 10831 -1 -1 -1 -1 -1")
        self.write_gz("vehicle_routes.xml.gz", self.vehicle_routes)

    def test_sensor_timing_measures_internal_connections_and_keeps_censored_populations(self):
        self.add_timed_sensor_routes()
        result = self.collect()
        timing = result["sensor_passage_timing"]
        records = {item["edge"]: item for item in timing["candidates"]}
        six, five = records["s6_before"], records["s5_before"]
        self.assertEqual(timing["insertion_delay_seconds_all_inserted"]["samples"], 4)
        self.assertEqual(timing["insertion_delay_seconds_all_inserted"]["median"], 3)
        for record in (five, six):
            self.assertEqual(record["planned_trips_crossing"], 5)
            self.assertEqual(record["not_inserted"], 1)
            self.assertEqual(record["inserted_with_teleport_excluded"], 2)
            self.assertEqual(record["inserted_without_teleport"], 2)
        self.assertEqual(six["reached_without_teleport"], 2)
        self.assertEqual(six["not_reached_without_teleport"], 0)
        self.assertEqual(six["entry_to_sensor_seconds"]["mean"], 24.5)
        self.assertEqual(six["physical_passages_per_15min_without_teleport"], [1] + [0] * 11)
        self.assertEqual(six["physical_passages_during_clearance_without_teleport"], 1)
        self.assertEqual(five["reached_without_teleport"], 1)
        self.assertEqual(five["not_reached_without_teleport"], 1)
        self.assertEqual(five["entry_to_sensor_seconds"]["median"], 45)
        self.assertEqual(records["s5_after"]["planned_trips_crossing"], 0)
        # A observação de atrasos não otimiza um deslocamento das contagens.
        before = next(item for item in result["count_comparisons"] if item["edge"] == "s6_before")
        self.assertEqual(before["simulated_cars_per_15min"], [2] * 12)

    def test_native_millisecond_rounding_is_not_an_early_insertion(self):
        root = ET.parse(self.routes_path).getroot()
        root[0].set("depart", "0.000442")
        ET.ElementTree(root).write(self.routes_path)
        result = self.collect()
        self.assertEqual(result["sensor_passage_timing"]["insertion_delay_seconds_all_inserted"]["min"], 0)
        root[0].set("depart", "0.0006")
        ET.ElementTree(root).write(self.routes_path)
        with self.assertRaisesRegex(ValueError, "antecede"):
            self.collect()

    def test_operational_progression_keeps_queues_and_natural_arrivals_separate(self):
        rows = self.collect()["operational_progression"]["intervals"]
        self.assertEqual(rows[0]["programmed_cumulative"], 5)
        self.assertEqual(rows[0]["waiting_insertion"], 2)
        self.assertEqual(rows[-1]["natural_arrivals_cumulative"], 1)
        self.assertEqual(rows[-1]["arrived_cumulative_including_teleports"], 2)
        self.assertEqual(rows[-1]["teleport_events_cumulative"], 3)

    def test_portal_accounting_retains_pending_and_exclusive_statuses_without_raw_files(self):
        result = self.collect()["spatial_observation"]["portal_trip_accounting"]
        self.assertEqual(len(result["entries"]), 1)
        portal = result["entries"][0]
        self.assertEqual(portal["edge"], "entry")
        self.assertEqual(portal["programmed"], 5)
        self.assertEqual(portal["inserted"], 4)
        self.assertEqual(portal["vehicles_with_teleport"], 2)
        self.assertEqual(portal["inserted_during_clearance"], 1)
        for status in ("not_inserted", "completed_without_teleport", "completed_after_teleport",
                       "incomplete_at_end", "removed_without_completion"):
            self.assertEqual(portal[status], 1)
        self.assertEqual(portal["insertion_delay_seconds"]["samples"], 4)
        self.assertEqual(portal["insertion_delay_seconds"]["median"], 3)
        first, last = portal["intervals"][0], portal["intervals"][-1]
        self.assertEqual((first["programmed"], first["inserted"], first["pending_insertion_at_end"]), (5, 3, 2))
        self.assertEqual((last["programmed"], last["inserted"], last["pending_insertion_at_end"]), (0, 1, 1))
        self.assertEqual(last["phase"], "clearance")
        self.assertEqual(last["insertion_delay_seconds"]["mean"], 10801)

    def test_trip_details_record_scheduled_and_actual_departure_separately(self):
        vehicles = {}
        self.collect(vehicles=vehicles)
        self.assertEqual(vehicles["incomplete"]["scheduled_departure_seconds"], 0)
        self.assertEqual(vehicles["incomplete"]["actual_departure_seconds"], 10801)
        self.assertEqual(vehicles["incomplete"]["insertion_delay_seconds"], 10801)
        self.assertIsNone(vehicles["undeparted"]["actual_departure_seconds"])
        self.assertIsNone(vehicles["undeparted"]["insertion_delay_seconds"])

    def test_route_incidence_counts_overlapping_observations_as_unique_trips(self):
        self.add_timed_sensor_routes()
        result = self.collect()["spatial_observation"]["route_observation_incidence"]
        self.assertEqual(result["unique_programmed_trips"], 5)
        self.assertEqual(result["sensor_combinations"], [{"sensor_ids": ["5", "6"], "programmed_trips": 5}])
        counts = {item["edge"]: item["programmed_trips"] for item in result["candidate_edges"]}
        self.assertEqual(counts["s5_before"], 5)
        self.assertEqual(counts["s6_before"], 5)
        self.assertEqual(counts["s5_after"], 0)

    def test_physical_scores_exclude_teleports_without_shifting_observed_windows(self):
        self.add_timed_sensor_routes()
        comparison = next(item for item in self.collect()["count_comparisons"] if item["edge"] == "s6_before")
        physical = comparison["without_any_teleport"]
        self.assertEqual(comparison["against_training_curve"]["simulated_cars"], 24)
        self.assertEqual(physical["against_training_curve"]["simulated_cars"], 1)
        self.assertEqual(physical["against_training_curve"]["reference_cars"], 24)
        self.assertEqual(physical["against_training_curve"]["wape"], 23 / 24)
        self.assertEqual(physical["physical_passages_during_clearance"], 1)
        self.assertEqual(physical["against_held_out_dates"]["primary"][0]["simulated_cars"], 1)

    def test_movement_observations_distinguish_route_incidence_and_physical_passage(self):
        self.add_timed_sensor_routes()
        self.spatial["observation_movements"] = [
            {"id": "shared", "label": "Movimento compartilhado", "from_edge": "middle", "to_edge": "s5_before"},
            {"id": "absent", "from_edge": "middle", "to_edge": "s5_after"},
        ]
        for interval in self.counts:
            ET.SubElement(interval, "edge", id="middle", entered="0")
        self.write_gz("metasettran_counts.xml.gz", self.counts)
        observations = {item["id"]: item for item in self.collect()["spatial_observation"]["observed_movements"]}
        movement = observations["shared"]
        self.assertEqual(movement["planned_trips"], 5)
        self.assertEqual(movement["not_inserted"], 1)
        self.assertEqual(movement["inserted_with_teleport_excluded"], 2)
        self.assertEqual(movement["not_reached_without_teleport"], 1)
        self.assertEqual(movement["physical_passages_per_15min_without_teleport"], [1] + [0] * 11)
        self.assertEqual(movement["physical_passages_during_clearance_without_teleport"], 0)
        self.assertEqual(observations["absent"]["planned_trips"], 0)
        self.assertIn("middle", metasettran_observation_edges(self.spatial))

    def test_two_sections_keep_twenty_four_observation_windows_and_separate_clearance(self):
        self.generation.update(duration=21600, clearance_limit_seconds=2700,
                               start_week_second=6 * 86400 + 21 * 3600,
                               temporal_scope={"supported_contexts": 56})
        for profile in self.generation["calibration"]["sensors"].values():
            profile["target_counts"] *= 2
            for day in profile["validation"]["primary"]["daily_counts"]:
                for key in ("counts", "eligible", "exposure_seconds"):
                    day[key] *= 2
        root = ET.Element("meandata")
        for index in range(27):
            interval = ET.SubElement(root, "interval", begin=str(index * 900), end=str((index + 1) * 900))
            for edge, count in (("s6_before", 2), ("s6_after", 3), ("s5_before", 4), ("s5_after", 5)):
                ET.SubElement(interval, "edge", id=edge, entered=str(count if index < 24 else 7))
        self.write_gz("metasettran_counts.xml.gz", root)
        result = self.collect()
        comparison = next(item for item in result["count_comparisons"] if item["edge"] == "s6_before")
        self.assertEqual(comparison["simulated_cars_per_15min"], [2] * 24)
        self.assertEqual(comparison["against_training_curve"]["n_windows"], 24)
        self.assertEqual(comparison["against_held_out_dates"]["primary"][0]["n_windows"], 24)
        self.assertEqual(comparison["cars_passing_during_clearance"], 21)
        self.assertEqual(len(comparison["without_any_teleport"]["physical_passages_per_15min"]), 24)
        self.assertEqual(result["metrics"]["vehicles_inserted_after_demand_window"], 0)
        self.assertNotIn("ready_for_weekly_expansion", result)
        self.assertEqual(result["temporal_scope"], {
            "start_week_second": 594000, "duration_seconds": 21600,
            "bins": 24, "bin_seconds": 900, "supported_contexts": 56,
        })
        self.assertEqual(result["empirical_calibration_status"],
                         "conditional_on_unconfirmed_sensor_mapping_and_external_scope")
        spatial = result["spatial_observation"]
        self.assertEqual(spatial["departure_window_seconds"], [0, 21600])
        self.assertEqual(spatial["clearance_window_seconds"], [21600, 24300])
        self.assertEqual(len(spatial["portal_trip_accounting"]["entries"][0]["intervals"]), 27)

    def test_temporal_reference_mismatch_is_not_silently_truncated(self):
        self.generation["calibration"]["sensors"]["6"]["target_counts"] *= 2
        with self.assertRaisesRegex(ValueError, "janelas temporais incompatíveis"):
            self.collect()

    def test_sensor_entry_is_observed_even_when_vehicle_never_leaves_sensor_edge(self):
        self.add_timed_sensor_routes()
        incomplete = next(item for item in self.vehicle_routes if item.get("id") == "incomplete")
        incomplete.find("route").set("exitTimes", "10820 10825 -1 -1 -1 -1 -1 -1 -1")
        self.write_gz("vehicle_routes.xml.gz", self.vehicle_routes)
        record = next(item for item in self.collect()["sensor_passage_timing"]["candidates"]
                      if item["edge"] == "s6_before")
        self.assertEqual(record["reached_without_teleport"], 2)

    def test_sensor_timing_rejects_missing_duplicate_and_invalid_native_routes(self):
        original = deepcopy(self.vehicle_routes)
        for kind in ("missing", "duplicate", "unknown", "wrong_depart", "wrong_route", "missing_times",
                     "nonfinite", "backwards", "after_unfinished"):
            with self.subTest(kind=kind):
                root = deepcopy(original)
                if kind == "missing":
                    root.remove(root[0])
                elif kind == "duplicate":
                    root.append(deepcopy(root[0]))
                elif kind == "unknown":
                    root[0].set("id", "foreign")
                elif kind == "wrong_depart":
                    root[0].set("depart", "1")
                elif kind == "wrong_route":
                    root[0].find("route").set("edges", "entry other exit")
                else:
                    value = {"missing_times": "20 30", "nonfinite": "20 nan 100",
                             "backwards": "40 20 100", "after_unfinished": "20 -1 100"}[kind]
                    root[0].find("route").set("exitTimes", value)
                self.write_gz("vehicle_routes.xml.gz", root)
                with self.assertRaisesRegex(ValueError, "Vehroute"):
                    self.collect()

    def test_partial_and_missing_holdout_windows_are_excluded_without_zero_filling(self):
        day = self.generation["calibration"]["sensors"]["6"]["validation"]["primary"]["daily_counts"][0]
        day["counts"][0] = 999
        day["exposure_seconds"][0] = 899
        day["counts"][1] = 0
        day["eligible"][1] = False
        day["exposure_seconds"][1] = 0
        result = self.collect()
        before = next(item for item in result["count_comparisons"] if item["edge"] == "s6_before")
        comparison = before["against_held_out_dates"]["primary"][0]
        self.assertEqual(comparison["n_windows"], 10)
        self.assertEqual(comparison["reference_cars"], 20)
        self.assertEqual(comparison["simulated_cars"], 20)
        self.assertEqual(comparison["wape"], 0)
        day["eligible"] = [False] * 12
        result = self.collect()
        before = next(item for item in result["count_comparisons"] if item["edge"] == "s6_before")
        comparison = before["against_held_out_dates"]["primary"][0]
        self.assertEqual(comparison["n_windows"], 0)
        self.assertIsNone(comparison["mae_cars_per_15min"])
        self.assertIsNone(comparison["wape"])

    def test_aggregated_or_incomplete_teleport_log_cannot_certify_natural_arrivals(self):
        self.summary["teleports"] = 4
        (self.directory / "sumo.log").write_text(self.log + "Warning: 1 total messages of type: Teleporting vehicle '%'.\n")
        with self.assertRaises(ValueError):
            self.collect()

    def test_unknown_or_unparseable_teleport_vehicle_is_rejected(self):
        for replacement in ("Teleporting vehicle 'unknown'", "Teleporting vehicle [no-id]"):
            with self.subTest(replacement=replacement):
                (self.directory / "sumo.log").write_text(
                    self.log.replace("Teleporting vehicle 'removed'", replacement))
                with self.assertRaises(ValueError):
                    self.collect()

    def test_missing_duplicate_or_unknown_tripinfo_is_rejected(self):
        for kind in ("missing", "duplicate", "unknown"):
            with self.subTest(kind=kind):
                trips = deepcopy(self.trips)
                if kind == "missing":
                    trips.remove(trips[0])
                elif kind == "duplicate":
                    trips.append(deepcopy(trips[0]))
                else:
                    trips[0].set("id", "unknown")
                self.write_gz("trips.xml.gz", trips)
                with self.assertRaises(ValueError):
                    self.collect()

    def test_nonfinite_departure_or_arrival_is_rejected(self):
        for attribute in ("depart", "arrival"):
            for value in ("nan", "inf", "-inf"):
                with self.subTest(attribute=attribute, value=value):
                    trips = deepcopy(self.trips)
                    trips[0].set(attribute, value)
                    self.write_gz("trips.xml.gz", trips)
                    with self.assertRaises(ValueError):
                        self.collect()

    def test_invalid_and_duplicated_count_windows_are_rejected(self):
        for kind in ("missing", "duplicate", "partial", "foreign_edge", "negative_count", "duplicate_tail"):
            with self.subTest(kind=kind):
                counts = deepcopy(self.counts)
                if kind == "missing":
                    counts.remove(counts[0])
                elif kind == "duplicate":
                    counts.append(deepcopy(counts[0]))
                elif kind == "partial":
                    counts[0].set("end", "899")
                elif kind == "foreign_edge":
                    counts[0][0].set("id", "unknown")
                elif kind == "negative_count":
                    counts[0][0].set("entered", "-1")
                else:
                    counts.append(deepcopy(counts[-1]))
                self.write_gz("metasettran_counts.xml.gz", counts)
                with self.assertRaises(ValueError):
                    self.collect()

    def test_observation_edges_are_unique_sorted_candidates(self):
        self.spatial["sensors"][0]["candidates"].append({"edge": "s5_before"})
        self.assertEqual(metasettran_observation_edges(self.spatial),
                         ("s5_after", "s5_before", "s6_after", "s6_before"))

    def add_spatial_observations(self, arrivals=2):
        self.spatial["portals"] = {"entries": [{"edge": "entry", "name": "Entrada"}],
                                   "exits": [{"edge": "exit", "name": "Saída"}]}
        self.spatial["corridors"] = [{"id": "corridor", "label": "Corredor",
                                      "direction": "leste", "observation_edges": ["s6_before", "s6_after"]}]
        self.summary["vehicles_completed"] = 2
        for index, interval in enumerate(self.counts):
            # entered/left deliberadamente distintos de inserções/chegadas.
            ET.SubElement(interval, "edge", id="entry", entered="99", departed=str(4 if index == 0 else 0))
            ET.SubElement(interval, "edge", id="exit", entered="77", left="88", arrived=str(arrivals if index == 0 else 0))
        self.write_gz("metasettran_counts.xml.gz", self.counts)

    def test_portals_measure_insertions_and_arrivals_not_passages_or_exits(self):
        self.add_spatial_observations()
        result = self.collect()["spatial_observation"]
        self.assertEqual(result["portals"]["entries"][0]["cars_total"], 4)
        self.assertEqual(result["portals"]["exits"][0]["cars_total"], 2)
        self.assertEqual(result["portal_reconciliation"]["departures"]["status"], "matched")
        arrivals = result["portal_reconciliation"]["arrivals"]
        self.assertEqual(arrivals["tripinfo_without_teleport"], 1)
        self.assertEqual(arrivals["tripinfo_after_teleport"], 1)
        probes = result["corridor_probes"][0]["probes"]
        self.assertEqual([p["cars_during_demand"] for p in probes], [24, 36])
        self.assertEqual(len(metasettran_observation_edges(self.spatial)), 6)

    def test_teleport_affected_exit_count_does_not_manufacture_physical_arrivals(self):
        self.add_spatial_observations(arrivals=1)
        arrivals = self.collect()["spatial_observation"]["portal_reconciliation"]["arrivals"]
        self.assertEqual(arrivals["status"], "teleport_affected")
        self.assertEqual(arrivals["arrivals_not_observed_at_exit"], 1)

    def test_portal_counts_must_reconcile_and_never_hide_missing_attributes(self):
        self.add_spatial_observations()
        original = deepcopy(self.counts)
        for attribute, value in (("departed", "5"), ("arrived", "3"),
                                 ("departed", "-1"), ("arrived", None)):
            with self.subTest(attribute=attribute, value=value):
                counts = deepcopy(original)
                edge = next(
                    e for e in counts[0] if e.get("id") == ("entry" if attribute == "departed" else "exit"))
                if value is None:
                    del edge.attrib[attribute]
                else:
                    edge.set(attribute, value)
                self.write_gz("metasettran_counts.xml.gz", counts)
                with self.assertRaises(ValueError):
                    self.collect()

    def test_distances_keep_natural_teleported_and_unfinished_populations_separate(self):
        distances = self.collect()["spatial_observation"]["trip_distance_m"]
        self.assertEqual(distances["completed_without_teleport"]["mean"], 3000)
        self.assertEqual(distances["completed_after_teleport"]["mean"], 2800)
        self.assertEqual(distances["incomplete_at_end_without_teleport"]["mean"], 200)
        self.assertEqual(distances["removed_without_completion"]["mean"], 100)
        self.assertEqual(distances["incomplete_at_end_after_teleport"]["samples"], 0)

    def test_invalid_inserted_trip_distance_is_not_replaced_with_zero(self):
        for value in (None, "-1", "nan", "inf"):
            with self.subTest(value=value):
                trips = deepcopy(self.trips)
                if value is None:
                    del trips[0].attrib["routeLength"]
                else:
                    trips[0].set("routeLength", value)
                self.write_gz("trips.xml.gz", trips)
                with self.assertRaises(ValueError):
                    self.collect()

    def test_counts_are_passive_and_identical_in_core_and_full(self):
        measurements = []
        forbidden_options = {"--step-length", "--time-to-teleport", "--seed", "--scale",
                             "--max-depart-delay", "--collision.action", "--end"}
        for profile in ("core", "full"):
            with self.subTest(profile=profile):
                directory = self.directory / profile
                (directory / "inputs").mkdir(parents=True)
                options = prepare_outputs(directory, profile,
                                          demand_observation_edges=("s6_before", "s5_before", "s6_before"))
                self.assertFalse(forbidden_options.intersection(options))
                for flag in ("--tripinfo-output.write-unfinished", "--tripinfo-output.write-undeparted"):
                    self.assertEqual(options[options.index(flag) + 1], "true")
                for flag in ("--vehroute-output.exit-times", "--vehroute-output.write-unfinished",
                             "--vehroute-output.internal"):
                    self.assertEqual(options.count(flag), 1)
                    self.assertEqual(options[options.index(flag) + 1], "true")
                self.assertEqual(options[options.index("--vehroute-output") + 1],
                                 str(directory / "raw" / "vehicle_routes.xml.gz"))
                additional_path = Path(options[options.index("--additional-files") + 1])
                root = ET.parse(additional_path).getroot()
                items = [item for item in root.findall("edgeData") if item.get("id") == "metasettran_counts"]
                self.assertEqual(len(items), 1)
                attributes = dict(items[0].attrib)
                self.assertEqual(attributes.pop("file"), str(directory / "raw" / "metasettran_counts.xml.gz"))
                measurements.append(attributes)
        self.assertEqual(measurements[0], measurements[1])
        self.assertEqual(measurements[0], {
            "id": "metasettran_counts", "period": "900", "begin": "0",
            "edges": "s5_before s6_before", "excludeEmpty": "false",
        })


if __name__ == "__main__":
    unittest.main()
