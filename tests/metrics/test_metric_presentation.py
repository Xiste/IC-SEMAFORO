"""Confere significado, população e prioridade sem executar o SUMO."""

import unittest

from SistemaDeSemaforos.metrics.metric_presentation import describe_metric, presentation_sort_key


class MetricPresentationTests(unittest.TestCase):
    def test_samples_and_exclusions_have_count_units_and_separate_priority(self):
        for base, unit in (("network_mean_speed_m_s", "m/s"),
                           ("vehicles_halting", "veículos"),
                           ("sumo_step_computation_ms", "ms")):
            with self.subTest(base=base):
                measured = describe_metric(base + "_mean")
                samples = describe_metric(base + "_samples")
                excluded = describe_metric(base + "_excluded_samples")
                self.assertEqual(measured["unit"], unit)
                self.assertEqual(samples["unit"], "amostras")
                self.assertEqual(excluded["unit"], "amostras")
                self.assertEqual(samples["priority"], 4)
                self.assertEqual(excluded["priority"], 3)
                self.assertEqual(excluded["category"], "integrity")

    def test_trip_status_and_aggregation_remain_explicit(self):
        for status, population in (("completed", "concluídas"),
                                   ("unfinished", "sem chegada registrada"),
                                   ("undeparted", "sem partida"),
                                   ("vaporized", "remoção excepcional")):
            mean = describe_metric(f"{status}_trip_waiting_time_mean")
            total = describe_metric(f"{status}_trip_waiting_time_sum")
            self.assertIn(population, mean["description_pt"])
            self.assertIn(population, total["description_pt"])
            self.assertIn("Média", mean["description_pt"])
            self.assertIn("Soma", total["description_pt"])
            self.assertEqual(mean["priority"], 1 if status == "completed" else 3)
        waiting = describe_metric("completed_trip_waiting_time_mean")
        self.assertIn("excluindo paradas programadas", waiting["description_pt"])
        delay = describe_metric("completed_trip_depart_delay_mean")
        self.assertIn("antes da entrada", delay["description_pt"])

    def test_emission_totals_rates_and_samples_have_distinct_units(self):
        for name, expected in (
            ("completed_emission_co2_abs_sum", "mg"),
            ("network_emission_co2_rate_mean", "mg/s"),
            ("completed_emission_fuel_abs_mean", "mg"),
            ("network_emission_fuel_rate_mean", "mg/s"),
            ("unfinished_emission_electricity_abs_sum", "Wh"),
            ("network_emission_electricity_rate_mean", "Wh/s"),
            ("completed_emission_n_ox_abs_samples", "amostras"),
        ):
            with self.subTest(name=name):
                self.assertEqual(describe_metric(name)["unit"], expected)
        self.assertIn("negativos indicando recuperação",
                      describe_metric("completed_emission_electricity_abs_mean")["description_pt"])

    def test_queue_coverage_and_halting_do_not_claim_queue_length(self):
        coverage = describe_metric("queue_observation_steps")
        self.assertEqual((coverage["kind"], coverage["priority"], coverage["unit"]),
                         ("diagnostic", 4, "passos"))
        self.assertIn("não mede comprimento de fila",
                      describe_metric("vehicles_halting_mean")["description_pt"])
        self.assertIn("toda a duração simulada",
                      describe_metric("completed_throughput_vehicles_per_hour")["description_pt"])

    def test_conditional_full_fields_and_hex_event_categories(self):
        for scope in ("edge", "lane"):
            self.assertEqual(describe_metric(f"{scope}_traffic_duration_seconds")["unit"], "s")
            self.assertEqual(describe_metric(f"{scope}_traffic_internal_included")["kind"], "context")
        reason = "strategic|urgent"
        prefix = "lane_change_reason_" + reason.encode().hex()
        self.assertIn(reason, describe_metric(prefix + "_count")["description_pt"])
        self.assertIn("seguir a rota; manobra urgente", describe_metric(prefix + "_count")["label_pt"])
        self.assertEqual(describe_metric(prefix + "_value")["kind"], "context")
        self.assertEqual(describe_metric("collision_victim_speed_mean")["priority"], 3)
        self.assertEqual(describe_metric("lane_change_follower_speed_mean")["unit"], "m/s")
        self.assertEqual(describe_metric("sumo_ride_statistics_aborted")["priority"], 3)
        self.assertIn("Duração média", describe_metric("sumo_pedestrian_statistics_duration")["description_pt"])

    def test_priority_and_headlines_are_independent_of_input_order(self):
        names = ["seed", "queue_observation_steps", "teleports", "vehicles_completed",
                 "network_mean_speed_m_s_mean", "completed_trip_waiting_time_mean",
                 "completed_throughput_vehicles_per_hour", "completed_trip_time_loss_mean",
                 "completed_trip_time_loss_samples", "execution_time_seconds"]
        records = [{"metric_name": n, **describe_metric(n)} for n in names]
        ordered = sorted(records, key=presentation_sort_key)
        self.assertEqual(ordered, sorted(reversed(records), key=presentation_sort_key))
        self.assertEqual([r["metric_name"] for r in ordered[:4]], [
            "completed_trip_time_loss_mean", "completed_trip_waiting_time_mean",
            "completed_throughput_vehicles_per_hour", "vehicles_completed",
        ])
        priorities = [r["priority"] for r in ordered]
        self.assertEqual(priorities, sorted(priorities))

    def test_unknown_metrics_are_not_given_invented_meaning(self):
        with self.assertRaisesRegex(ValueError, "sem apresentação cadastrada"):
            describe_metric("unknown_result")
        with self.assertRaisesRegex(ValueError, "Categoria de evento inválida"):
            describe_metric("lane_change_reason_ff_count")


if __name__ == "__main__":
    unittest.main()
