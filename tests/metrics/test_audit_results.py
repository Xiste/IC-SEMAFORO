"""Confere resultados publicados sem exigir entradas antigas para reproduzi-los."""

from contextlib import redirect_stderr, redirect_stdout
import gzip
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from SistemaDeSemaforos.metrics.metrics_storage import (
    metric_records, read_json, save_entities, save_episode, write_json,
)
from scripts.audit_results import audit, audit_distribution, episode_records_valid, main, records_valid


def episode_fixture(root, profile):
    directory = root / profile
    directory.mkdir()
    save_episode(directory, {
        "vehicles_completed": 2, "seed": 7, "simulation_seed": 23423,
        "status": "completed", "metrics_profile": profile,
    }, {"status": "completed", "sumo_version": "SUMO fixture",
        "collection": {"profile": profile}},
        include_entities=profile != "core")
    if profile != "core":
        save_entities(directory, {"vehicles": {"car0": {"trip_duration": 12.0}}})
    return directory


class AuditResultsTests(unittest.TestCase):
    def test_diagnostic_profile_is_audited_with_entities(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = episode_fixture(root, "diagnostic")
            self.assertEqual(audit(root)["episodes_verified"], 1)
            (directory / "entities.json.gz").unlink()
            with self.assertRaisesRegex(ValueError, "diagnostic"):
                audit(root)

    def test_audit_reads_old_and_new_files_and_rejects_ambiguous_duplicates(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            old = episode_fixture(root, "core")
            episode_fixture(root, "full")
            compressed = old / "metrics.json.gz"
            plain = old / "metrics.json"
            plain.write_bytes(gzip.decompress(compressed.read_bytes()))
            compressed.unlink()
            self.assertEqual(audit(root)["episodes_verified"], 2)
            compressed.write_bytes(gzip.compress(plain.read_bytes()))
            self.assertEqual(audit(root)["episodes_verified"], 2)
            compressed.write_bytes(gzip.compress(b"{}"))
            with self.assertRaisesRegex(ValueError, "divergentes"):
                audit(root)

    def test_core_and_full_validate_without_archived_inputs_or_terminal_report(self):
        with TemporaryDirectory() as temporary, redirect_stdout(io.StringIO()) as terminal:
            root = Path(temporary)
            core = episode_fixture(root, "core")
            full = episode_fixture(root, "full")
            self.assertEqual({path.name for path in core.iterdir()}, {"metrics.json.gz"})
            self.assertEqual({path.name for path in full.iterdir()}, {"metrics.json.gz", "entities.json.gz"})
            result = audit(root)
        self.assertEqual(terminal.getvalue(), "")
        self.assertEqual(result["episodes_verified"], 2)
        self.assertEqual(result["typed_records_verified"], 11)

    def test_unified_cli_preserves_episode_mode_and_rejects_mixed_inputs(self):
        with TemporaryDirectory() as temporary:
            directory = episode_fixture(Path(temporary), "core")
            self.assertEqual(main(["--episodes", str(directory)]), 0)
            for arguments in (
                ["--episodes", str(directory), "--routes-file", "routes.xml"],
                ["--episodes", str(directory), "--output", str(Path(temporary) / "report.json")],
                ["--routes-file", "routes.xml"],
            ):
                with self.subTest(arguments=arguments), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    main(arguments)

    def test_rejects_missing_directory_and_directory_without_episodes(self):
        with TemporaryDirectory() as temporary:
            for path in (Path(temporary), Path(temporary) / "missing"):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    audit(path)

    def test_entities_follow_profile_and_explicit_declaration(self):
        for variant in ("full_null", "full_missing", "core_omitted", "core_undeclared_file", "core_full"):
            with self.subTest(variant=variant), TemporaryDirectory() as temporary:
                profile = "full" if variant.startswith("full") else "core"
                root = Path(temporary)
                directory = episode_fixture(root, profile)
                document = read_json(directory / "metrics.json.gz")
                if variant == "core_omitted":
                    document.pop("entity_metrics_file")
                elif variant == "full_missing":
                    (directory / "entities.json.gz").unlink()
                elif variant == "core_full":
                    document["entity_metrics_file"] = "entities.json.gz"
                else:
                    document["entity_metrics_file"] = None
                if variant == "core_undeclared_file":
                    write_json(directory / "entities.json.gz", {"entities": {}})
                write_json(directory / "metrics.json.gz", document)
                with self.assertRaises(ValueError):
                    audit(root)

    def test_rejects_missing_version_and_inconsistent_execution_state(self):
        for variant in ("sumo_version", "execution_status", "metric_status", "profile", "version"):
            with self.subTest(variant=variant), TemporaryDirectory() as temporary:
                root = Path(temporary)
                directory = episode_fixture(root, "core")
                document = read_json(directory / "metrics.json.gz")
                if variant == "sumo_version":
                    document["execution"].pop("sumo_version")
                elif variant == "execution_status":
                    document["execution"]["status"] = "failed"
                elif variant == "metric_status":
                    next(r for r in document["metrics"] if r["metric_name"] == "status")["value"] = "running"
                elif variant == "profile":
                    document["execution"]["collection"]["profile"] = "full"
                else:
                    document["schema_version"] = 2
                write_json(directory / "metrics.json.gz", document)
                with self.assertRaises(ValueError):
                    audit(root)

    def test_rejects_invalid_global_types_and_entity_aggregates(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = episode_fixture(root, "full")
            document = read_json(directory / "metrics.json.gz")
            next(r for r in document["metrics"] if r["metric_name"] == "seed")["value"] = "7"
            write_json(directory / "metrics.json.gz", document)
            with self.assertRaisesRegex(ValueError, "Tipo/chave inválido"):
                audit(root)
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = episode_fixture(root, "full")
            save_entities(directory, {"lanes": {"lane": {
                "speed_min": 2.0, "speed_mean": 1.0, "speed_max": 3.0,
            }}})
            with self.assertRaisesRegex(ValueError, "Agregados fora de ordem"):
                audit(root)

    def test_rejects_unknown_globals_and_duplicate_records(self):
        with self.assertRaisesRegex(ValueError, "sem apresentação"):
            episode_records_valid({"schema_version": 1,
                                   "metrics": metric_records({"unknown": 1.0})}, set())
        record = metric_records({"seed": 7})[0]
        with self.assertRaisesRegex(ValueError, "Tipo/chave inválido"):
            records_valid([record, record], set())


class DemandDistributionAuditTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.net = self.directory / "network.xml"
        self.routes = self.directory / "routes.xml"
        self.spatial = self.directory / "spatial.json"
        root = ET.Element("net")
        names = ("entry", "main", "exit", "bypass", "alternative", "dead", "isolated", "source2", "sink2")
        for name in names:
            edge = ET.SubElement(root, "edge", id=name, type="highway.residential")
            ET.SubElement(edge, "lane", id=name + "_0", index="0", length="100", speed="10")
        for source, target in (("entry", "main"), ("main", "exit"), ("entry", "bypass"),
                               ("bypass", "exit"), ("entry", "alternative"), ("alternative", "exit"),
                               ("entry", "dead"), ("source2", "main"), ("main", "sink2")):
            ET.SubElement(root, "connection", **{"from": source, "to": target, "fromLane": "0", "toLane": "0"})
        ET.ElementTree(root).write(self.net)
        self.write_vehicles([("one", "0", "entry main exit"), ("two", "1", "entry main exit")])
        self.spatial.write_text(json.dumps({
            "network_sha256": hashlib.sha256(self.net.read_bytes()).hexdigest(),
            "regional_demand": {}, "portals": {
                role: [{"edge": name, "boundary_group": name}]
                for role, name in (("entries", "entry"), ("exits", "exit"))}}))
        self.pairs = {"a": {"route": ["entry", "main", "exit"]},
                      "b": {"route": ["entry", "bypass", "exit"]}}

    def write_vehicles(self, vehicles):
        root = ET.Element("routes")
        for identifier, depart, path in vehicles:
            vehicle = ET.SubElement(root, "vehicle", id=identifier, depart=depart)
            ET.SubElement(vehicle, "route", edges=path)
        ET.ElementTree(root).write(self.routes)

    def test_classifies_every_edge_and_conserves_coverage(self):
        with patch("scripts.audit_results._route_pairs",
                   return_value=(self.pairs, [], {"accepted_pairs": 2}, {})):
            report = audit_distribution(net_file=self.net, routes_file=self.routes, spatial_file=self.spatial)
        self.assertEqual(report["coverage"]["by_reason"], {
            "used_in_planned_routes": 3, "catalog_route_not_sampled": 1,
            "outside_route_catalog": 1, "cannot_reach_configured_destinations": 2,
            "unreachable_from_configured_origins": 2})
        self.assertEqual(sum(report["coverage"]["by_reason"].values()), 9)
        self.assertEqual(report["coverage"]["planned_used_edges"], 3)
        self.assertEqual(report["coverage"]["unused_edges"], 6)
        self.assertEqual(report["coverage"]["planned_used_length_m"], 300)
        self.assertEqual(report["configured_endpoints"]["network_sources_without_origin"], ["isolated", "source2"])
        self.assertEqual(report["configured_endpoints"]["network_sinks_without_destination"], ["dead", "isolated", "sink2"])
        self.assertEqual(report["top_edges"][0]["share_of_vehicles"], 1)
        self.assertEqual(report["vehicles"], 2)
        self.assertEqual(report["distinct_routes"], 1)

    def test_without_spatial_model_does_not_invent_catalog_or_physical_traffic(self):
        report = audit_distribution(net_file=self.net, routes_file=self.routes)
        self.assertIsNone(report["catalog"])
        unused = [row for row in report["edges"] if row["planned_vehicles"] == 0]
        self.assertEqual(len(unused), 6)
        self.assertTrue(all(row["status"] == "not_in_planned_routes" for row in unused))
        self.assertTrue(all(row["catalog_routes"] is None for row in unused))
        self.assertNotIn("physical_vehicles", report["edges"][0])
        self.assertNotIn("physical_observation", report)
        self.assertNotIn("teleport_observation", report)

    def test_missing_catalog_edge_keeps_the_bounded_search_diagnosis(self):
        diagnosis = {"edge": "alternative", "status": "no_admissible_candidate_found",
                     "covered_by_admissible_alternative": False}
        catalog = {"coverage_completion": {"edges": [diagnosis]}}
        with patch("scripts.audit_results._route_pairs",
                   return_value=(self.pairs, [], catalog, {})):
            report = audit_distribution(net_file=self.net, routes_file=self.routes, spatial_file=self.spatial)
        row = next(row for row in report['edges'] if row['edge'] == 'alternative')
        self.assertEqual(row['status'], 'outside_route_catalog')
        self.assertEqual(row['coverage_review'], diagnosis)

    def test_rejects_invalid_routes_ids_and_departures(self):
        cases = [
            [("one", "0", "entry exit")], [("one", "0", "unknown")],
            [("one", "0", "")], [("one", "nan", "entry main exit")],
            [("one", "-1", "entry main exit")],
            [("one", "1", "entry main exit"), ("two", "0", "entry main exit")],
            [("one", "0", "entry main exit"), ("one", "1", "entry main exit")], []]
        for vehicles in cases:
            with self.subTest(vehicles=vehicles):
                self.write_vehicles(vehicles)
                with self.assertRaises(ValueError):
                    audit_distribution(net_file=self.net, routes_file=self.routes)

    def test_rejects_catalog_from_other_network_and_routes_outside_catalog(self):
        with patch("scripts.audit_results._route_pairs",
                   return_value=({"b": self.pairs["b"]}, [], {}, {})):
            with self.assertRaisesRegex(ValueError, "não pertencem"):
                audit_distribution(net_file=self.net, routes_file=self.routes, spatial_file=self.spatial)
        model = json.loads(self.spatial.read_text())
        model["network_sha256"] = "wrong"
        self.spatial.write_text(json.dumps(model))
        with self.assertRaisesRegex(ValueError, "outra rede"):
            audit_distribution(net_file=self.net, routes_file=self.routes, spatial_file=self.spatial)

    def test_episode_detects_early_stop_and_rejects_mismatched_route_hash(self):
        metrics = self.directory / "metrics.json"
        document = {"execution": {"generation": {
            "demand_model": "metasettran", "vehicles_generated": 2, "duration": 3,
            "routes_sha256": hashlib.sha256(self.routes.read_bytes()).hexdigest()}},
            "metrics": [{"metric_name": "simulation_duration_seconds", "value": .5}]}
        metrics.write_text(json.dumps(document))
        report = audit_distribution(net_file=self.net, routes_file=self.routes, metrics_file=metrics)
        self.assertTrue(report["episode"]["ended_before_last_scheduled_departure"])
        self.assertEqual(report["top_movements"][0]["planned_vehicles_per_hour"], 2400)
        self.write_vehicles([("changed", "0", "entry main exit")])
        with self.assertRaisesRegex(ValueError, "routes_sha256"):
            audit_distribution(net_file=self.net, routes_file=self.routes, metrics_file=metrics)

    def test_cli_cannot_overwrite_inputs_or_existing_results(self):
        before = self.routes.read_bytes()
        args = ["--net-file", str(self.net), "--routes-file", str(self.routes), "--output", str(self.routes)]
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(args)
        self.assertEqual(self.routes.read_bytes(), before)

    def write_observation_metrics(self, end=2, teleports=0):
        path = self.directory / "metrics.json"
        path.write_text(json.dumps({"execution": {"generation": {"vehicles_generated": 2}},
            "metrics": [{"metric_name": name, "value": value} for name, value in {
                "simulation_begin_seconds": 0, "simulation_end_seconds": end,
                "simulation_duration_seconds": end, "teleports": teleports}.items()]}))
        return path

    def test_edge_data_gzip_distinguishes_occupancy_zero_and_missing_records(self):
        path = self.directory / "edges.xml.gz"
        content = ('<meandata><interval begin="0" end="1">'
                   '<edge id="main" sampledSeconds="10"/><edge id="entry" sampledSeconds="0"/>'
                   '</interval><interval begin="1" end="2">'
                   '<edge id="main" sampledSeconds="0"/><edge id="entry" sampledSeconds="0"/>'
                   '</interval></meandata>')
        with gzip.open(path, "wt") as stream:
            stream.write(content)
        report = audit_distribution(net_file=self.net, routes_file=self.routes,
                       metrics_file=self.write_observation_metrics(), edge_data=path)
        observation = report['physical_observation']
        self.assertTrue(observation['matches_episode_time_window'])
        self.assertEqual(observation['observed_passenger_edges'], 2)
        self.assertEqual(observation['occupied_passenger_edges'], 1)
        self.assertEqual(observation['passenger_edges_without_records'], 7)
        rows = {r['edge']: r['physical_observation'] for r in report['edges']}
        self.assertEqual(rows['main']['sampled_seconds'], 10)
        self.assertEqual(rows['main']['status'], 'occupied_in_supplied_intervals')
        self.assertEqual(rows['entry']['status'], 'no_occupancy_in_supplied_records')
        self.assertEqual(rows['exit']['status'], 'not_observed')
        self.assertIsNone(rows['exit']['sampled_seconds'])
        self.assertEqual(report['coverage']['planned_used_edges'], 3)

    def test_incomplete_edge_data_does_not_claim_full_window_or_missing_zero(self):
        path = self.directory / 'edges.xml'
        path.write_text('<meandata><interval begin="0" end="1"><edge id="entry" sampledSeconds="0"/>'
                        '</interval><interval begin="2" end="3"></interval></meandata>')
        report = audit_distribution(net_file=self.net, routes_file=self.routes,
                       metrics_file=self.write_observation_metrics(end=3), edge_data=path)
        self.assertFalse(report['physical_observation']['matches_episode_time_window'])
        self.assertEqual(report['physical_observation']['interval_gaps'], 1)
        entry = next(r for r in report['edges'] if r['edge'] == 'entry')
        self.assertEqual(entry['physical_observation']['interval_records'], 1)
        without_metrics = audit_distribution(net_file=self.net, routes_file=self.routes, edge_data=path)
        self.assertIsNone(without_metrics['physical_observation']['matches_episode_time_window'])

    def test_edge_data_rejects_invalid_samples_duplicate_edges_and_overlap(self):
        path = self.directory / 'edges.xml'
        cases = [
            '<interval begin="0" end="1"><edge id="main" sampledSeconds="nan"/></interval>',
            '<interval begin="0" end="1"><edge id="main" sampledSeconds="-1"/></interval>',
            '<interval begin="0" end="1"><edge id="main"/></interval>',
            '<interval begin="0" end="1"><edge id="main" sampledSeconds="0"/>'
                '<edge id="main" sampledSeconds="1"/></interval>',
            '<interval begin="0" end="2"/><interval begin="1" end="3"/>',
        ]
        for content in cases:
            with self.subTest(content=content):
                path.write_text('<meandata>' + content + '</meandata>')
                with self.assertRaises(ValueError):
                    audit_distribution(net_file=self.net, routes_file=self.routes, edge_data=path)

    def test_teleports_distinguish_events_vehicles_internal_lanes_and_partial_logs(self):
        network = ET.parse(self.net)
        edge = ET.SubElement(network.getroot(), 'edge', id=':junction_0', function='internal')
        ET.SubElement(edge, 'lane', id=':junction_0_0', length='10', speed='10')
        network.write(self.net)
        log = self.directory / 'sumo.log'
        log.write_text("Warning: Teleporting vehicle 'one'; waited too long (jam), lane='main_0', time=1.000.\n"
                       "Warning: Vehicle 'one' ends teleporting on edge 'exit', time=1.000.\n"
                       "Warning: Teleporting vehicle 'one'; waited too long (yield), lane=':junction_0_0', time=2.000.\n"
                       "Warning: Teleporting vehicle 'two'; waited too long (jam), lane='unknown_0', time=3.000.\n"
                       "Warning: Teleporting vehicle 'three'; unsupported format.\n")
        report = audit_distribution(net_file=self.net, routes_file=self.routes, sumo_log=log,
                       metrics_file=self.write_observation_metrics(teleports=5))
        observed = report['teleport_observation']
        self.assertEqual(observed['reported_start_messages'], 4)
        self.assertEqual(observed['unique_vehicles_in_parsed_messages'], 2)
        self.assertEqual(observed['unparsed_start_messages'], 1)
        self.assertEqual(observed['count_status'], 'incomplete_or_mismatched_log')
        self.assertEqual(observed['unknown_lane_ids'], ['unknown_0'])
        self.assertEqual(sum(r['reported_events'] for r in observed['by_edge']), 2)
        self.assertTrue(next(r for r in observed['by_edge'] if r['edge'] == ':junction_0')['internal'])
        matched = audit_distribution(net_file=self.net, routes_file=self.routes, sumo_log=log,
                        metrics_file=self.write_observation_metrics(teleports=4))
        self.assertEqual(matched['teleport_observation']['count_status'], 'matches_episode_event_total')
        unverifiable = audit_distribution(net_file=self.net, routes_file=self.routes, sumo_log=log)
        self.assertEqual(unverifiable['teleport_observation']['count_status'], 'not_verifiable_without_episode_total')

    def test_audit_accepts_compressed_routes_and_log_using_original_hash(self):
        original = self.routes.read_bytes()
        log = self.directory / 'sumo.log'
        log.write_text("Warning: Teleporting vehicle 'one'; waited too long (jam), lane='main_0', time=1.000.\n")
        log_bytes = log.read_bytes()
        route_gz = self.routes.with_name(self.routes.name + '.gz')
        log_gz = log.with_name(log.name + '.gz')
        route_gz.write_bytes(gzip.compress(original))
        log_gz.write_bytes(gzip.compress(log_bytes))
        self.routes.unlink()
        log.unlink()
        report = audit_distribution(net_file=self.net, routes_file=self.routes, sumo_log=log)
        self.assertEqual(report['routes_sha256'], hashlib.sha256(original).hexdigest())
        self.assertEqual(report['teleport_observation']['sha256'], hashlib.sha256(log_bytes).hexdigest())
        self.assertEqual(report['teleport_observation']['reported_start_messages'], 1)

    def test_cli_observation_inputs_are_explicit_and_cannot_be_overwritten(self):
        edge_data, log, output = (self.directory / name for name in ('edges.xml', 'sumo.log', 'audit.json'))
        edge_data.write_text('<meandata><interval begin="0" end="2"><edge id="main" sampledSeconds="2"/></interval></meandata>')
        log.write_text('No teleport start warnings in this supplied log.\n')
        args = ['--net-file', str(self.net), '--routes-file', str(self.routes),
                '--edge-data', str(edge_data), '--sumo-log', str(log)]
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(args + ['--output', str(edge_data)])
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(args + ['--output', str(output)]), 0)
        document = json.loads(output.read_text())
        self.assertEqual(document['physical_observation']['occupied_passenger_edges'], 1)
        self.assertEqual(document['teleport_observation']['reported_start_messages'], 0)
        self.assertEqual(document['teleport_observation']['count_status'], 'not_verifiable_without_episode_total')


if __name__ == "__main__":
    unittest.main()
