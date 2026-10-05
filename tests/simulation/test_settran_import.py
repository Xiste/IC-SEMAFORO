"""Preservação da fonte SETTRAN e recusa de interpretações não auditadas."""

import contextlib
import csv
import io
from itertools import combinations
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from scripts import audit_settran


EXPECTED_PHYSICAL_LINKS = {
    ("A39", "A51", "A"): ("FAM_CESARIO_PARANA", [1, 2]),
    ("A39", "A52", "B"): ("FAM_CESARIO_PARANA", [3, 4]),
    ("A39", "A53", "C"): ("FAM_CESARIO_PARANA", [0]),
    ("A56", "A70", "C"): ("FAM_RONDON_PORTO_ALEGRE", [3, 4]),
    ("A74", "A86", "A"): ("FAM_RONDON_BELEM", [4, 5, 6]),
    ("A74", "A87", "B"): ("FAM_RONDON_BELEM", [0, 1, 2, 3, 4, 5, 6]),
    ("A74", "A88", "C"): ("FAM_RONDON_BELEM", [0, 1, 2, 3]),
    ("A74", "A89", "D"): ("FAM_RONDON_BELEM", [7, 8, 9]),
    ("A110", "A122", "A"): ("FAM_RONDON_NITEROI", [0, 1, 2, 3, 4, 5, 6]),
    ("A110", "A124", "C"): ("FAM_RONDON_NITEROI", [12, 13, 14, 15, 16]),
}

EXPECTED_STAGE_APPROACHES = {
    ("A39", "A51", "A"): {"602306713#21"},
    ("A39", "A52", "B"): {"665897556#1"},
    ("A39", "A53", "C"): {"154252437#1"},
    ("A56", "A70", "C"): {"30664532#2"},
    ("A74", "A86", "A"): {"576876311#3"},
    ("A74", "A87", "B"): {"576876311#3", "331577750#1"},
    ("A74", "A88", "C"): {"331577750#1"},
    ("A74", "A89", "D"): {"965367673#0"},
    ("A110", "A122", "A"): {"931572689"},
    ("A110", "A124", "C"): {"30622933#11"},
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

    def test_only_audited_physical_stage_bindings_are_normalized(self):
        document = audit_settran.normalize_source()
        confirmed_bindings = set()
        bound_stage_count = 0
        for program in document["programs"]:
            expected_tls = set()
            for stage in program["stages"]:
                key = (program["source_cells"]["intersection"],
                       stage["source_cells"]["stage_id"], stage["stage_id"])
                expected = EXPECTED_PHYSICAL_LINKS.get(key)
                if expected is None:
                    self.assertIsNone(stage["sumo_links"])
                else:
                    tls_id, indices = expected
                    self.assertEqual(stage["sumo_links"], [{
                        "tls_id": tls_id, "link_indices": indices,
                    }])
                    expected_tls.add(tls_id)
                    confirmed_bindings.add((program["intersection"], stage["stage_id"]))
                    bound_stage_count += 1
            self.assertEqual(program["sumo_tls_ids"], sorted(expected_tls))
            self.assertIsNone(program["sumo_phases"])
        self.assertEqual(bound_stage_count, 40)  # Dez vínculos nos quatro planos.
        audit_file = audit_settran.ROOT / "docs/settran/settran_audit.csv"
        with audit_file.open(encoding="utf-8", newline="") as source:
            audited_bindings = {
                (row["intersecao"], row["estagio_movimento"])
                for row in csv.DictReader(source)
                if row["estagio_movimento"] and row["status_mapeamento"] == "confirmado"
            }
        self.assertEqual(len(audited_bindings), 10)
        self.assertEqual(confirmed_bindings, audited_bindings)

    def test_confirmed_links_exist_and_have_no_local_foe_pairs(self):
        # Associação física não confirma sequência, permissões ou
        # coordenação entre nós/TLS; nenhum phase.state é gerado neste teste.
        network_file = audit_settran.ROOT / (
            "SistemaDeSemaforos/network/uberlandia.vehicular.families.16_2_4.net.xml"
        )
        root = ET.parse(network_file).getroot()
        edges = {edge.get("id"): edge for edge in root.findall("edge")}
        junctions = {junction.get("id"): junction for junction in root.findall("junction")}
        links = {}
        for connection in root.findall("connection"):
            if connection.get("tl") is not None:
                key = (connection.get("tl"), int(connection.get("linkIndex")))
                links.setdefault(key, []).append(connection)
        document = audit_settran.normalize_source()
        for program in document["programs"]:
            for stage in program["stages"]:
                for binding in stage["sumo_links"] or []:
                    with self.subTest(intersection=program["intersection"],
                                      plan=program["plan_id"], stage=stage["stage_id"]):
                        tls_id = binding["tls_id"]
                        self.assertIsNotNone(root.find(f"tlLogic[@id='{tls_id}']"))
                        connections = []
                        for index in binding["link_indices"]:
                            self.assertEqual(len(links.get((tls_id, index), [])), 1)
                            connections.append(links[tls_id, index][0])
                        stage_key = (program["source_cells"]["intersection"],
                                     stage["source_cells"]["stage_id"], stage["stage_id"])
                        self.assertEqual(
                            {connection.get("from") for connection in connections},
                            EXPECTED_STAGE_APPROACHES[stage_key],
                        )
                        for first, second in combinations(connections, 2):
                            node_id = edges[first.get("from")].get("to")
                            if edges[second.get("from")].get("to") != node_id:
                                continue
                            junction = junctions[node_id]
                            internal_lanes = junction.get("intLanes").split()
                            indices = [internal_lanes.index(connection.get("via"))
                                       for connection in (first, second)]
                            # foes usa índice zero à direita; state usa-o à esquerda.
                            for own_index, other_index in (indices, indices[::-1]):
                                request = junction.find(f"request[@index='{own_index}']")
                                self.assertIsNotNone(request)
                                self.assertEqual(request.get("foes")[-1 - other_index], "0")

    def test_no_executable_program_or_schedule_is_invented(self):
        document = audit_settran.normalize_source()
        self.assertEqual(document["status"], "blocked")
        for field in ("schedule", "operational_day_start", "initial_plan_id"):
            self.assertIsNone(document[field])
        self.assertTrue(all(p["sumo_phases"] is None for p in document["programs"]))
        self.assertIn("missing_schedule", {b["id"] for b in document["blockers"]})

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

    def test_check_detects_artifact_drift_without_writing(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "programs.json"
            output.write_text('{"status":"ready"}\n', encoding="utf-8")
            with patch.object(audit_settran, "OUTPUT", output), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    audit_settran.main(["--check"])
            self.assertEqual(json.loads(output.read_text())["status"], "ready")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(audit_settran.main(["--check"]), 0)


if __name__ == "__main__":
    unittest.main()
