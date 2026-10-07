"""Preservação da fonte SETTRAN e recusa de interpretações não auditadas."""

import contextlib
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from scripts import audit_settran


EXPECTED_STAGE_APPROACHES = {
    ("A3", "A"): {"152937136#3", "1156717163#3"},
    ("A3", "B"): {"666324302#5"}, ("A3", "C"): {"853751181#0"},
    ("A21", "A"): {"1156272393#6"}, ("A21", "B"): {"1156717173#4"},
    ("A21", "C"): {"901328279#0"}, ("A21", "D"): {"1156717168"},
    ("A39", "A"): {"602306713#21"}, ("A39", "B"): {"665897556#1"},
    ("A39", "C"): {"154252437#1"},
    ("A56", "A"): {"299471494#2"},
    ("A56", "B"): {"299471494#2", "331577748#4"}, ("A56", "C"): {"30664532#2"},
    ("A74", "A"): {"576876311#3"},
    ("A74", "B"): {"576876311#3", "331577750#1"},
    ("A74", "C"): {"331577750#1"}, ("A74", "D"): {"965367673#0"},
    ("A92", "A"): {"965367672#2"},
    ("A92", "B"): {"965367672#2", "930831033#0"}, ("A92", "C"): {"930831033#0"},
    ("A110", "A"): {"931572689"},
    ("A110", "B"): {"931572689", "930831032#1"}, ("A110", "C"): {"30622933#11"},
    ("A128", "A"): {"1156717175#5"},
    ("A128", "B"): {"576014290#0", "576014301#0"},
    ("A144", "A"): {"576014296#2"},
    ("A144", "B"): {"576014296#2", "462991286"}, ("A144", "C"): {"625668273#2"},
}


class SettranImportTests(unittest.TestCase):
    def test_preserves_all_programs_and_source_values(self):
        document = audit_settran.normalize_source()
        cells = audit_settran.read_source(audit_settran.SOURCE)
        self.assertEqual(len(document["programs"]), 36)
        self.assertEqual(len({p["intersection"] for p in document["programs"]}), 9)
        self.assertEqual({p["plan_id"] for p in document["programs"]}, {"2", "4", "16", "24"})
        self.assertEqual(sum(len(p["stages"]) for p in document["programs"]), 128)
        timing_cells = set()
        for program in document["programs"]:
            for key, cell in program["source_cells"].items():
                expected = cells[cell] if key in {"plan_id", "intersection"} else int(cells[cell])
                self.assertEqual(program[key], expected)
            for stage in program["stages"]:
                for key, cell in stage["source_cells"].items():
                    expected = cells[cell].strip() if key in {"stage_id", "movement"} else int(cells[cell])
                    self.assertEqual(stage[key], expected)
                    if key.endswith("_seconds"):
                        timing_cells.add(cell)
        self.assertEqual(len(timing_cells), 512)

    def test_geographic_coverage_is_independent_of_operational_stage_bindings(self):
        document = audit_settran.normalize_source()
        self.assertEqual(document["schema_version"], 2)
        self.assertEqual(len({tls for p in document["programs"] for tls in p["sumo_tls_ids"]}), 17)
        physical_keys, vehicle_keys, pedestrian_keys = set(), set(), set()
        for program in document["programs"]:
            heading = program["source_cells"]["intersection"]
            self.assertEqual(program["sumo_tls_ids"], sorted(audit_settran.INTERSECTION_TLS_IDS[heading]))
            self.assertIsNone(program["operational"])
            self.assertNotIn("sumo_phases", program)
            for stage in program["stages"]:
                key = (heading, stage["stage_id"])
                if stage["scope"] == "pedestrian":
                    pedestrian_keys.add(key)
                    self.assertEqual(stage["movement"], "Pedestres")
                    self.assertEqual(stage["mapping_status"], "NAO_APLICAVEL")
                else:
                    vehicle_keys.add(key)
                if stage["sumo_links"]:
                    physical_keys.add(key)
                    self.assertIn(stage["mapping_status"], {"CONFIRMADO", "INFERIVEL_COM_SEGURANCA"})
                self.assertTrue(stage["mapping_note"])
        self.assertEqual(len(vehicle_keys), 29)
        self.assertEqual(len(physical_keys), 28)
        self.assertEqual(pedestrian_keys, {("A3", "D"), ("A56", "D"), ("A110", "D")})
        rotary = next(p for p in document["programs"] if p["source_cells"]["intersection"] == "A92")
        stage_d = next(s for s in rotary["stages"] if s["stage_id"] == "D")
        self.assertEqual(stage_d["mapping_status"], "DADO_EXTERNO_AUSENTE")
        self.assertIsNone(stage_d["sumo_links"])
        self.assertIn("Rotary Club", stage_d["mapping_note"])

    def test_physical_links_cover_the_correct_approaches_in_the_current_network(self):
        network_file = audit_settran.ROOT / (
            "SistemaDeSemaforos/network/uberlandia.vehicular.families.16_2_4.net.xml"
        )
        root = ET.parse(network_file).getroot()
        edges = {edge.get("id"): edge for edge in root.findall("edge")}
        links = {}
        for connection in root.findall("connection"):
            if connection.get("tl") is not None:
                key = (connection.get("tl"), int(connection.get("linkIndex")))
                links.setdefault(key, []).append(connection)
        document = audit_settran.normalize_source()
        for program in document["programs"]:
            for tls_id in program["sumo_tls_ids"]:
                self.assertIsNotNone(root.find(f"tlLogic[@id='{tls_id}']"))
            for stage in program["stages"]:
                connections = []
                for binding in stage["sumo_links"] or []:
                    with self.subTest(intersection=program["intersection"],
                                      plan=program["plan_id"], stage=stage["stage_id"]):
                        tls_id = binding["tls_id"]
                        self.assertIsNotNone(root.find(f"tlLogic[@id='{tls_id}']"))
                        for index in binding["link_indices"]:
                            self.assertEqual(len(links.get((tls_id, index), [])), 1)
                            connections.append(links[tls_id, index][0])
                if not connections:
                    continue
                stage_key = (program["source_cells"]["intersection"], stage["stage_id"])
                approaches = EXPECTED_STAGE_APPROACHES[stage_key]
                self.assertEqual({c.get("from") for c in connections}, approaches)
                expected = [c for cs in links.values() for c in cs if c.get("from") in approaches]
                self.assertEqual({tuple(sorted(c.attrib.items())) for c in connections},
                                 {tuple(sorted(c.attrib.items())) for c in expected})
                self.assertTrue(all(edges[c.get("from")].get("function") is None for c in connections))

    def test_bidirectional_physical_coverage_does_not_imply_protected_green(self):
        network = audit_settran.ROOT / "SistemaDeSemaforos/network/uberlandia.vehicular.families.16_2_4.net.xml"
        root = ET.parse(network).getroot()
        edges = {e.get("id"): e for e in root.findall("edge")}
        nodes = {n.get("id"): n for n in root.findall("junction")}
        connections = root.findall("connection")

        def request_index(connection):
            node = nodes[edges[connection.get("from")].get("to")]
            lanes = node.get("intLanes").split()
            via = connection.get("via")
            for _ in range(20):
                if via in lanes:
                    return node, lanes.index(via)
                edge, lane = via.rsplit("_", 1)
                following = [c for c in connections if c.get("from") == edge
                             and c.get("fromLane") == lane and c.get("to") == connection.get("to")
                             and c.get("toLane") == connection.get("toLane")]
                self.assertEqual(len(following), 1)
                via = following[0].get("via")
            self.fail("Trajetória interna sem request correspondente.")

        for tls_id, pair in (("FAM_RONDON_BENJAMIM", (4, 10)), ("FAM_RONDON_NITEROI", (4, 8))):
            first, second = [next(c for c in connections if c.get("tl") == tls_id
                                  and int(c.get("linkIndex")) == index) for index in pair]
            node, own_index = request_index(first)
            other_node, other_index = request_index(second)
            self.assertIs(node, other_node)
            self.assertEqual(node.find(f"request[@index='{own_index}']").get("foes")[-1 - other_index], "1")

    def test_no_executable_program_or_schedule_is_invented(self):
        document = audit_settran.normalize_source()
        self.assertEqual(document["status"], "partial_external_data")
        for field in ("schedule", "operational_day_start", "initial_plan_id"):
            self.assertIsNone(document[field])
        self.assertTrue(all(p["operational"] is None for p in document["programs"]))
        agenda = next(b for b in document["blockers"] if b["id"] == "missing_schedule")
        self.assertEqual(agenda["scope"], "temporal_operation")

    def test_preserves_inconsistent_red_values_without_repair(self):
        document = audit_settran.normalize_source()
        anomalies = [a for a in document["anomalies"] if a["kind"] == "red_cycle_mismatch"]
        self.assertEqual(
            [(a["source_cell"], a["source_red_seconds"], a["arithmetic_residual_seconds"]) for a in anomalies],
            [("R115", 33, 90), ("R116", 35, 110), ("R117", 29, 130)],
        )
        for anomaly in anomalies:
            program = next(p for p in document["programs"]
                           if p["intersection"] == anomaly["intersection"] and p["plan_id"] == anomaly["plan_id"])
            pedestrian = next(s for s in program["stages"] if s["stage_id"] == "D")
            self.assertEqual(pedestrian["red_seconds"], anomaly["source_red_seconds"])
        self.assertEqual(document["anomalies"][-1]["source_cells"], ["A144", "B158"])

    def test_changed_source_fails_before_overwriting_artifact(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.xlsx"
            source.write_bytes(audit_settran.SOURCE.read_bytes() + b"changed")
            output = Path(temporary) / "programs.json"
            output.write_text("preserved", encoding="utf-8")
            with patch.object(audit_settran, "SOURCE", source), patch.object(audit_settran, "OUTPUT", output):
                with contextlib.redirect_stderr(io.StringIO()) as error:
                    with self.assertRaises(SystemExit) as stopped:
                        audit_settran.main([])
                self.assertEqual(stopped.exception.code, 1)
                self.assertIn("Reaudite", error.getvalue())
            self.assertEqual(output.read_text(encoding="utf-8"), "preserved")

    def test_regeneration_preserves_operational_and_explicit_empty_schedule(self):
        document = audit_settran.normalize_source()
        document["programs"][0]["operational"] = {
            "status": "PARTIAL_EXTERNAL_DATA", "source_reference": "Documento futuro"
        }
        document["schedule"] = []  # Agenda fornecida vazia difere de agenda ausente.
        document["operational_day_start"] = "00:00:00"
        document["initial_plan_id"] = "24"
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "programs.json"
            output.write_text(json.dumps(document), encoding="utf-8")
            with patch.object(audit_settran, "OUTPUT", output), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(audit_settran.main([]), 0)
                self.assertEqual(audit_settran.main(["--check"]), 0)
            regenerated = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(regenerated, document)
            audit_settran.validate_source_document(regenerated)
        self.assertIsNone(audit_settran.normalize_source()["schedule"])

    def test_regeneration_refuses_source_value_drift_without_discarding_supplement(self):
        document = audit_settran.normalize_source()
        document["programs"][0]["operational"] = {"source_reference": "Preservar documento"}
        document["programs"][0]["stages"][0]["green_seconds"] += 1
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "programs.json"
            original = json.dumps(document)
            output.write_text(original, encoding="utf-8")
            with patch.object(audit_settran, "OUTPUT", output), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    audit_settran.main([])
            self.assertEqual(output.read_text(encoding="utf-8"), original)

    def test_runtime_source_validation_rejects_geographic_mapping_drift(self):
        original = audit_settran.normalize_source()
        for mutate in (
            lambda d: d["programs"][0]["sumo_tls_ids"].append("unknown"),
            lambda d: d["programs"][0]["stages"][0]["sumo_links"][0]["link_indices"].append(23),
            lambda d: d["programs"][0]["stages"][0].update(mapping_status="READY"),
        ):
            document = deepcopy(original)
            mutate(document)
            with self.assertRaises(ValueError):
                audit_settran.validate_source_document(document)

    def test_legacy_artifact_migrates_without_changing_raw_source(self):
        legacy = audit_settran.normalize_source()
        legacy["schema_version"] = 1
        for program in legacy["programs"]:
            del program["operational"]
            program["sumo_phases"] = None
            for stage in program["stages"]:
                for field in ("scope", "mapping_status", "mapping_note"):
                    del stage[field]
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "programs.json"
            output.write_text(json.dumps(legacy), encoding="utf-8")
            with patch.object(audit_settran, "OUTPUT", output), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(audit_settran.main([]), 0)
            regenerated = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(regenerated["schema_version"], 2)
            self.assertEqual(audit_settran.source_values(regenerated), audit_settran.source_values(legacy))

    def test_check_detects_artifact_drift_without_writing(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "programs.json"
            output.write_text('{"status":"ready"}\n', encoding="utf-8")
            with patch.object(audit_settran, "OUTPUT", output), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    audit_settran.main(["--check"])
            self.assertEqual(json.loads(output.read_text())["status"], "ready")
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "programs.json"
            output.write_text(json.dumps(audit_settran.normalize_source()), encoding="utf-8")
            with patch.object(audit_settran, "OUTPUT", output), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(audit_settran.main(["--check"]), 0)

    def test_invalid_supplied_schedule_is_rejected_without_erasing_data(self):
        document = audit_settran.normalize_source()
        document["schedule"] = [{"intersection": document["programs"][0]["intersection"],
                                 "plan_id": "inventado"}]
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "programs.json"
            original = json.dumps(document)
            output.write_text(original, encoding="utf-8")
            with patch.object(audit_settran, "OUTPUT", output), contextlib.redirect_stderr(io.StringIO()):
                for arguments in (["--check"], []):
                    with self.subTest(arguments=arguments), self.assertRaises(SystemExit) as error:
                        audit_settran.main(arguments)
                    self.assertEqual(error.exception.code, 1)
                    self.assertEqual(output.read_text(), original)

    def test_supplied_schedule_is_validated_and_preserved_without_activation(self):
        document = audit_settran.normalize_source()
        document["schedule"] = [{
            "intersection": document["programs"][0]["intersection"], "plan_id": "2",
            "start_time": "06:00:00", "end_time": "08:00:00", "weekdays": [1, 2, 3, 4, 5],
            "exceptions": [], "valid_from": "2026-01-01", "valid_until": "2026-12-31",
            "source_reference": "SYNTHETIC_TEST_FIXTURE_NOT_SETTRAN",
        }]
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "programs.json"
            output.write_text(json.dumps(document), encoding="utf-8")
            with patch.object(audit_settran, "OUTPUT", output), contextlib.redirect_stdout(io.StringIO()) as log:
                self.assertEqual(audit_settran.main([]), 0)
                self.assertEqual(audit_settran.main(["--check"]), 0)
            self.assertIn("Agenda: CONFIRMADO", log.getvalue())
            self.assertEqual(json.loads(output.read_text()), document)
        self.assertIsNone(document["initial_plan_id"])
        self.assertIsNone(document["operational_day_start"])


if __name__ == "__main__":
    unittest.main()
