"""Contrato executável com fonte sintética; não declara planos reais prontos."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from SistemaDeSemaforos.simulation.settran_configuration import (
    compile_selection, prepare_selection, validate_schedule,
)


NETWORK = """<net>
  <edge id="a" to="n"><lane id="a_0" index="0"/></edge>
  <edge id="b" to="n"><lane id="b_0" index="0"/></edge>
  <edge id="p" function="crossing"><lane id="p_0" index="0" allow="pedestrian"/></edge>
  <edge id="out"><lane id="out_0" index="0"/></edge>
  <edge id="u" to="m"><lane id="u_0" index="0"/></edge>
  <junction id="n" intLanes=":n_0_0 :n_1_0">
    <request index="0" foes="10" response="00"/>
    <request index="1" foes="01" response="01"/>
  </junction>
  <junction id="m" intLanes=":m_0_0"><request index="0" foes="0" response="0"/></junction>
  <connection from="a" to="out" fromLane="0" toLane="0" via=":n_0_0" tl="T" linkIndex="0"/>
  <connection from="b" to="out" fromLane="0" toLane="0" via=":n_1_0" tl="T" linkIndex="1"/>
  <connection from="p" to="p" fromLane="0" toLane="0" tl="T" linkIndex="2"/>
  <connection from="u" to="out" fromLane="0" toLane="0" via=":m_0_0" tl="U" linkIndex="0"/>
  <tlLogic id="T" programID="current" type="static" offset="0"><phase duration="45" state="Grr"/></tlLogic>
  <tlLogic id="U" programID="current" type="static" offset="0"><phase duration="45" state="G"/></tlLogic>
</net>"""


class SettranConfigurationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.network = self.directory / "fixture.net.xml"
        self.network.write_text(NETWORK, encoding="utf-8")
        reference = "Fonte sintética de teste; não representa programação SETTRAN real"
        stages = [{"stage_id": stage, "scope": scope, "green_seconds": 10,
                   "yellow_seconds": 3, "clearance_red_seconds": 2, "red_seconds": 30,
                   "sumo_links": None}
                  for stage, scope in (("A", "vehicle"), ("B", "vehicle"), ("P", "pedestrian"))]
        phases = []
        for stage, states in (("A", ("Grr", "yrr", "rrr")),
                              ("B", ("rGr", "ryr", "rrr")),
                              ("P", ("rrr", "rrr", "rrr"))):
            for transition, duration, state in zip(("green", "yellow", "clearance_red"),
                                                   (10, 3, 2), states):
                phases.append({"stage_id": stage, "transition": transition,
                               "duration_seconds": duration, "states": {"T": state},
                               "source_reference": reference})
        operational = {
            "tls_ids": ["T"], "current_tls_ids": [],
            "network_sha256": sha256(self.network.read_bytes()).hexdigest(),
            "stage_links": {"A": [{"tls_id": "T", "link_indices": [0]}],
                            "B": [{"tls_id": "T", "link_indices": [1]}]},
            "phases": phases,
            "evidence": {field: {"status": "CONFIRMADO", "source_reference": reference}
                         for field in ("control_scope", "movement_mapping", "permissions", "sequence",
                                       "transitions", "offset_reference")},
            "offset_reference": {"reference_type": "clock", "reference_id": "fixture-clock",
                                 "reference_time_seconds": 100, "direction": "delay",
                                 "target_phase_index": 3, "source_reference": reference},
        }
        self.document = {
            "schema_version": 2, "schedule": None, "operational_day_start": None,
            "initial_plan_id": None,
            "programs": [{"intersection": "INTERSEÇÃO SINTÉTICA", "plan_id": "2",
                          "cycle_seconds": 45, "offset_seconds": 7, "stages": stages,
                          "sumo_tls_ids": ["T"], "operational": operational}],
        }

    @property
    def operational(self):
        return self.document["programs"][0]["operational"]

    def select(self, **kwargs):
        return prepare_selection(self.document, "2", self.network, **kwargs)

    def assert_blocked(self, message):
        with self.assertRaisesRegex(ValueError, message):
            self.select()

    def make_simultaneous_groups(self, state="Ggr"):
        self.operational["stage_links"] = {
            stage: [{"tls_id": "T", "link_indices": [0, 1]}] for stage in ("A", "B")}
        for phase in self.operational["phases"]:
            if phase["stage_id"] in ("A", "B"):
                phase["states"]["T"] = {
                    "green": state, "yellow": "yyr", "clearance_red": "rrr"}[phase["transition"]]

    def test_fixed_selection_does_not_consult_missing_or_empty_schedule(self):
        first = self.select()
        self.document["schedule"] = []
        second = self.select()
        self.assertEqual(first["offsets"], second["offsets"])
        self.assertIsNone(first["document_snapshot"]["schedule"])
        self.assertEqual(second["document_snapshot"]["schedule"], [])
        self.assertEqual(first["tls_ids"], ["T"])
        self.assertEqual(first["current_tls_ids"], ["U"])

    def test_source_stage_times_and_pedestrian_red_are_preserved(self):
        selection = self.select()
        target = compile_selection(selection, self.directory / "settran.add.xml")
        logic = ET.parse(target).getroot().find("tlLogic")
        self.assertEqual(logic.attrib, {"id": "T", "type": "static", "programID": "settran_2", "offset": "2"})
        self.assertEqual(sum(float(p.get("duration")) for p in logic), 45)
        self.assertTrue(all(p.get("state")[-1] == "r" for p in logic))
        expected_bytes = target.read_bytes()
        self.assertEqual(compile_selection(selection, target).read_bytes(), expected_bytes)
        self.assertEqual(self.network.read_text(), NETWORK)

    def test_offset_requires_reference_and_preserves_sign_target_event(self):
        self.assertEqual(self.select()["offsets"]["T"], 2)
        self.operational["offset_reference"]["direction"] = "advance"
        self.assertEqual(self.select()["offsets"]["T"], 33)
        self.operational["offset_reference"]["reference_type"] = "tls_event"
        self.operational["offset_reference"]["reference_id"] = "U"
        self.operational["offset_reference"]["reference_event"] = "início do verde; fonte sintética"
        self.assertEqual(self.select()["offsets"]["T"], 33)
        del self.operational["offset_reference"]["reference_time_seconds"]
        self.assert_blocked("reference_time_seconds")

    def test_local_explicit_selection_ignores_an_unrelated_incomplete_intersection(self):
        incomplete = deepcopy(self.document["programs"][0])
        incomplete.update(intersection="OUTRA INTERSEÇÃO", sumo_tls_ids=["U"], operational=None)
        self.document["programs"].append(incomplete)
        self.assert_blocked("OUTRA INTERSEÇÃO.*DADO_EXTERNO_AUSENTE")
        selection = self.select(intersections=["INTERSEÇÃO SINTÉTICA"])
        self.assertEqual(selection["tls_ids"], ["T"])
        self.assertEqual(selection["current_tls_ids"], ["U"])
        self.assertFalse(any(self.directory.glob("*.add.xml")))

    def test_selection_snapshot_is_independent_and_contains_evidence(self):
        selection = self.select()
        json.dumps(selection)
        self.operational["phases"][0]["states"]["T"] = "rrr"
        self.assertEqual(selection["programs"][0]["operational"]["phases"][0]["states"]["T"], "Grr")
        self.assertIn("evidence", selection["document_snapshot"]["programs"][0]["operational"])

    def test_missing_evidence_never_uses_a_ready_flag(self):
        self.document["status"] = "READY"
        del self.operational["evidence"]["sequence"]
        self.assert_blocked("evidence.sequence")

    def test_missing_source_group_is_reported_with_its_local_external_document(self):
        program = self.document["programs"][0]
        program["stages"][0].update(mapping_status="DADO_EXTERNO_AUSENTE",
                                   mapping_note="falta desenho que identifique os movimentos do Grupo A")
        program["operational"] = None
        self.assert_blocked("TLS T: falta quadro veicular.*Grupo A: falta desenho")

    def test_multi_tls_group_requires_complete_vectors_not_a_silent_subset(self):
        self.document["programs"][0]["sumo_tls_ids"] = ["T", "U"]
        self.operational["tls_ids"] = ["T", "U"]
        self.operational["stage_links"]["A"].append({"tls_id": "U", "link_indices": [0]})
        self.assert_blocked("todos e somente os TLS")
        for phase in self.operational["phases"]:
            phase["states"]["U"] = ({"green": "G", "yellow": "y", "clearance_red": "r"}
                                     [phase["transition"]] if phase["stage_id"] == "A" else "r")
        self.assertEqual(self.select()["tls_ids"], ["T", "U"])

    def test_geographic_tls_can_remain_current_only_with_explicit_proven_scope(self):
        self.document["programs"][0]["sumo_tls_ids"] = ["T", "U"]
        self.assert_blocked("partição explícita")
        self.operational["current_tls_ids"] = ["U"]
        selection = self.select()
        self.assertEqual(selection["tls_ids"], ["T"])
        self.assertEqual(selection["current_tls_ids"], ["U"])
        target = compile_selection(selection, self.directory / "explicit.add.xml")
        self.assertEqual([logic.get("id") for logic in ET.parse(target).getroot()], ["T"])
        del self.operational["evidence"]["control_scope"]
        self.assert_blocked("evidence.control_scope")

    def test_distinct_tls_offsets_require_complete_explicit_references(self):
        self.document["programs"][0]["sumo_tls_ids"] = ["T", "U"]
        self.operational["tls_ids"] = ["T", "U"]
        self.operational["stage_links"]["A"].append({"tls_id": "U", "link_indices": [0]})
        for phase in self.operational["phases"]:
            phase["states"]["U"] = ({"green": "G", "yellow": "y", "clearance_red": "r"}
                                     [phase["transition"]] if phase["stage_id"] == "A" else "r")
        reference = self.operational["offset_reference"]
        self.operational["offset_reference"] = {"by_tls": {"T": reference}}
        self.assert_blocked("referência exata para cada TLS")
        other = deepcopy(reference)
        other["direction"] = "advance"
        self.operational["offset_reference"]["by_tls"]["U"] = other
        self.assertEqual(self.select()["offsets"], {"T": 2, "U": 33})

    def test_mapping_requires_all_vehicle_links_and_known_scope(self):
        del self.operational["stage_links"]["B"]
        self.assert_blocked(r"stage_links\[B\]")
        self.operational["stage_links"]["B"] = [{"tls_id": "T", "link_indices": [0]}]
        self.assert_blocked("controlledLinks veiculares sem grupo")

    def test_physical_candidates_do_not_override_documented_operational_permissions(self):
        self.document["programs"][0]["stages"][0]["sumo_links"] = [{"tls_id": "T", "link_indices": [1]}]
        self.assertEqual(self.select()["tls_ids"], ["T"])

    def test_wrong_or_other_network_vectors_and_pedestrian_green_are_refused(self):
        phase = self.operational["phases"][0]
        phase["states"]["T"] = "Gr"
        self.assert_blocked("vetor state/dimensão")
        phase["states"]["T"] = "GrG"
        self.assert_blocked("atendimento pedestre fora do escopo")
        phase["states"]["T"] = "Gor"
        self.assert_blocked("vetor state/dimensão")
        phase["states"] = {}
        self.assert_blocked("todos e somente os TLS")

    def test_network_revision_is_part_of_operational_contract(self):
        self.network.write_text(NETWORK + "\n")
        self.assert_blocked("network_sha256")

    def test_source_timings_and_cycle_cannot_be_changed(self):
        self.operational["phases"][0]["duration_seconds"] = 9
        self.assert_blocked("A.green: duração 9 difere da fonte")
        self.operational["phases"][0]["duration_seconds"] = 10
        self.document["programs"][0]["cycle_seconds"] = 44
        self.assert_blocked("soma não fecha cycle_seconds")

    def test_green_to_red_without_yellow_is_refused(self):
        first, yellow = self.operational["phases"][:2]
        first["states"]["T"], yellow["states"]["T"] = "Grr", "Grr"
        self.assert_blocked("verde→vermelho sem amarelo")

    def test_stage_permutation_and_cycle_rotation_do_not_assume_source_order(self):
        phases = self.operational["phases"]
        self.operational["phases"] = phases[3:6] + phases[:3] + phases[6:]
        self.assertEqual(self.select()["tls_ids"], ["T"])
        reordered = self.operational["phases"]
        self.operational["phases"] = reordered[2:] + reordered[:2]
        self.assertEqual(self.select()["tls_ids"], ["T"])

    def test_clearance_cannot_be_relocated_after_another_group(self):
        phases = self.operational["phases"]
        self.operational["phases"] = phases[:2] + phases[3:6] + phases[2:3] + phases[6:]
        self.assert_blocked("não contíguos")
        self.operational["phases"] = [phases[0], phases[2], phases[1]] + phases[3:]
        self.assert_blocked("fora da ordem")

    def test_unrecognized_relative_reference_never_defaults_to_zero(self):
        self.operational["offset_reference"].update(reference_type="tls_event", reference_id="MISSING_TLS")
        self.assert_blocked("TLS de referência desconhecido")
        self.operational["offset_reference"]["reference_id"] = "U"
        self.assert_blocked("reference_event")

    def agenda_row(self, **changes):
        row = dict(intersection="INTERSEÇÃO SINTÉTICA", plan_id="2", start_time="06:00:00",
                   end_time="12:00:00", weekdays=[1, 2, 3, 4, 5], exceptions=[],
                   valid_from="2026-10-05", valid_until="2026-11-01",
                   source_reference="SYNTHETIC_TEST_FIXTURE_NOT_SETTRAN")
        return row | changes

    def test_schedule_distinguishes_missing_from_provided_empty_without_starting_a_clock(self):
        self.assertEqual(validate_schedule(self.document), "DADO_EXTERNO_AUSENTE")
        self.document["schedule"] = []
        self.assertEqual(validate_schedule(self.document), "CONFIRMADO_SEM_ATIVACOES")
        self.document["schedule"] = "AGENDA INVÁLIDA, NÃO CONSULTADA EM PLANO FIXO"
        self.assertEqual(self.select()["tls_ids"], ["T"])
        with self.assertRaisesRegex(ValueError, "lista declarativa"):
            validate_schedule(self.document)

    def test_schedule_allows_adjacent_intervals_and_requires_explicit_midnight_split(self):
        self.document["schedule"] = [self.agenda_row(), self.agenda_row(start_time="12:00:00", end_time="24:00:00")]
        self.assertEqual(validate_schedule(self.document), "CONFIRMADO")
        self.document["schedule"] = [self.agenda_row(start_time="22:00:00", end_time="06:00:00")]
        with self.assertRaisesRegex(ValueError, "dividir faixas"):
            validate_schedule(self.document)

    def test_schedule_rejects_unknown_identifiers_and_undocumented_source(self):
        for changes in ({"intersection": "MISSING"}, {"plan_id": "4"}, {"source_reference": ""}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.document["schedule"] = [self.agenda_row(**changes)]
                validate_schedule(self.document)

    def test_schedule_uses_strict_dates_time_and_iso_weekdays(self):
        for changes in ({"weekdays": []}, {"weekdays": [True]}, {"weekdays": [0, 8]},
                        {"weekdays": [1, 1]}, {"start_time": "6:00:00"}, {"end_time": "24:00:01"},
                        {"valid_from": "2026-02-30"}, {"valid_from": "20261005"},
                        {"valid_until": "2026-10-04"}, {"exceptions": None}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.document["schedule"] = [self.agenda_row(**changes)]
                validate_schedule(self.document)

    def test_schedule_checks_real_calendar_days_and_validity_before_overlap(self):
        self.document["schedule"] = [self.agenda_row(), self.agenda_row(start_time="11:00:00")]
        with self.assertRaisesRegex(ValueError, "sobrepostas"):
            validate_schedule(self.document)
        self.document["schedule"][1]["weekdays"] = [6, 7]
        self.assertEqual(validate_schedule(self.document), "CONFIRMADO")
        self.document["schedule"][1].update(weekdays=[1], valid_from="2026-11-02", valid_until="2026-11-30")
        self.assertEqual(validate_schedule(self.document), "CONFIRMADO")
        self.document["schedule"] = [self.agenda_row(weekdays=[2], valid_until="2026-10-05")] * 2
        self.assertEqual(validate_schedule(self.document), "CONFIRMADO")  # Só segunda-feira na validade.

    def test_schedule_cancellations_are_applied_to_the_exact_date(self):
        cancellation = [{"date": "2026-10-05", "plan_id": None}]
        first = self.agenda_row(weekdays=[1], valid_until="2026-10-05", exceptions=cancellation)
        second = self.agenda_row(weekdays=[1], valid_until="2026-10-05")
        self.document["schedule"] = [first, second]
        self.assertEqual(validate_schedule(self.document), "CONFIRMADO")
        first["valid_until"] = second["valid_until"] = "2026-10-12"
        with self.assertRaisesRegex(ValueError, "sobrepostas"):
            validate_schedule(self.document)

    def test_schedule_exception_can_activate_a_nonregular_weekday(self):
        first = self.agenda_row(exceptions=[{"date": "2026-10-10", "plan_id": "2"}])
        second = self.agenda_row(weekdays=[6])
        self.document["schedule"] = [first, second]
        with self.assertRaisesRegex(ValueError, "sobrepostas"):
            validate_schedule(self.document)

    def test_schedule_exception_requires_valid_unique_date_and_known_plan(self):
        for exceptions in ([{"date": "2026-10-05"}], [{"date": "2026-10-05", "plan_id": "4"}],
                           [{"date": "2026-11-02", "plan_id": None}],
                           [{"date": "2026-10-05", "plan_id": None}] * 2):
            with self.subTest(exceptions=exceptions), self.assertRaises(ValueError):
                self.document["schedule"] = [self.agenda_row(exceptions=exceptions)]
                validate_schedule(self.document)

    def test_simultaneous_foes_cannot_have_protected_green(self):
        self.make_simultaneous_groups("GGr")
        self.assert_blocked("Verdes protegidos conflitantes")

    def test_new_green_cannot_conflict_with_yellow_of_another_group(self):
        self.operational["phases"][0]["states"]["T"] = "Gyr"
        self.assert_blocked("Verde novo conflitante com amarelo, sem limpeza")

    def test_continuing_green_with_yellow_requires_preserved_yield_priority(self):
        for yellow, clearance in (("ygr", "rgr"), ("Gyr", "Grr")):
            with self.subTest(yellow=yellow):
                self.make_simultaneous_groups()
                self.operational["phases"][1]["states"]["T"] = yellow
                self.operational["phases"][2]["states"]["T"] = clearance
                self.assertEqual(self.select()["tls_ids"], ["T"])

    def test_permissive_green_requires_existing_correct_yield_priority(self):
        self.make_simultaneous_groups()
        self.assertEqual(self.select()["tls_ids"], ["T"])
        self.make_simultaneous_groups("gGr")
        self.assert_blocked("g sem prioridade de cessão")
        self.make_simultaneous_groups("ggr")
        self.assert_blocked("g sem prioridade de cessão")

    def test_numeric_booleans_zero_and_nonfinite_durations_are_refused(self):
        for value in (True, 0, -1, float("nan"), float("inf")):
            with self.subTest(value=value):
                self.operational["phases"][0]["duration_seconds"] = value
                self.assert_blocked("número finito positivo")

    def test_duplicate_or_unknown_scope_cannot_be_silently_reduced(self):
        for scope in ([], ["DESCONHECIDA"], ["INTERSEÇÃO SINTÉTICA"] * 2, "INTERSEÇÃO SINTÉTICA"):
            with self.subTest(scope=scope), self.assertRaises(ValueError):
                self.select(intersections=scope)

    def test_real_dataset_still_refuses_each_official_plan(self):
        project = Path(__file__).resolve().parents[2]
        document = json.loads((project / "docs/settran/settran_programs.json").read_text())
        network = project / "SistemaDeSemaforos/network/uberlandia.vehicular.families.16_2_4.net.xml"
        self.assertEqual(document["schema_version"], 2)
        for plan_id in ("2", "4", "16", "24"):
            with self.subTest(plan=plan_id), self.assertRaisesRegex(ValueError, "DADO_EXTERNO_AUSENTE"):
                prepare_selection(document, plan_id, network)


if __name__ == "__main__":
    unittest.main()
