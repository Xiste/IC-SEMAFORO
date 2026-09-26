"""Confere agregações SUMO com observações de resultado conhecido.

Entrada: XMLs mínimos, incluindo zeros e viagens truncadas. Saída: verificações
numéricas; usado por make test sem uma instalação SUMO.
"""

from collections import defaultdict
import gzip
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from SistemaDeSemaforos.metrics import collector as c
from SistemaDeSemaforos.metrics.sumo_outputs import prepare_outputs


class CollectorTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)

    def xml(self, name, contents):
        path = self.directory / name
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "wt", encoding="utf-8") as stream:
            stream.write(contents)
        return path

    def test_summary_uses_final_counters_and_excludes_empty_speed(self):
        path = self.xml("summary.xml.gz", '''<summary>
          <step time="0" running="2" waiting="0" arrived="0" inserted="2" meanSpeed="10" />
          <step time="1" running="1" waiting="1" arrived="1" inserted="2" meanSpeed="4" />
          <step time="2" running="0" waiting="0" arrived="2" inserted="2" meanSpeed="-1" />
        </summary>''')
        result = c._summary(path)
        self.assertEqual(result["vehicles_completed"], 2)
        self.assertEqual(result["vehicles_running_mean"], 1)
        self.assertEqual(result["network_mean_speed_m_s_mean"], 7)
        self.assertEqual(result["network_mean_speed_m_s_samples"], 2)
        self.assertEqual(result["simulation_end_seconds"], 3)
        self.assertEqual(result["completed_throughput_vehicles_per_hour"], 2400)

    def test_traffic_fills_empty_with_zero_but_not_speed(self):
        path = self.xml("traffic.xml.gz", '''<meandata>
          <interval begin="0" end="1"><edge id="a" density="4" occupancy="10" speed="10" sampledSeconds="2" left="1" waitingTime="1" /></interval>
          <interval begin="1" end="2" />
          <interval begin="2" end="3"><edge id="a" density="2" occupancy="5" speed="4" sampledSeconds="1" left="1" waitingTime="0" /></interval>
        </meandata>''')
        result, global_metrics = {}, {}
        c._traffic(path, "edge", {"a", "empty"}, result, global_metrics)
        a = result["a"]
        self.assertEqual(a["traffic_density_mean"], 2)
        self.assertEqual(a["traffic_density_min"], 0)
        self.assertEqual(a["traffic_speed_mean"], 7)
        self.assertEqual(a["traffic_speed_vehicle_seconds_weighted_mean"], 8)
        self.assertEqual(a["traffic_left_sum"], 2)
        self.assertIsInstance(a["traffic_left_sum"], int)
        self.assertEqual(a["traffic_left_flow_per_hour"], 2400)
        self.assertEqual(result["empty"]["traffic_speed_samples"], 0)
        self.assertNotIn("traffic_speed_mean", result["empty"])

    def test_incompatible_traffic_period_is_not_silently_averaged(self):
        path = self.xml("traffic.xml.gz", '<meandata><interval begin="0" end="2" /></meandata>')
        with self.assertRaises(ValueError):
            c._traffic(path, "edge", set(), {}, {})

    def test_trip_status_and_sentinels_do_not_bias_completed_distribution(self):
        path = self.xml("trips.xml.gz", '''<tripinfos>
          <tripinfo id="a" depart="0" arrival="10" duration="10" waitingTime="2" vaporized="" vtype="passenger"><emissions CO2_abs="30" /></tripinfo>
          <tripinfo id="b" depart="1" arrival="-1" duration="2" waitingTime="1" vaporized="end" />
          <tripinfo id="c" depart="-1" arrival="-1" duration="-1" waitingTime="-1" vaporized="end" />
        </tripinfos>''')
        metrics, vehicles = {}, {}
        c._trips(path, metrics, vehicles)
        self.assertEqual(metrics["completed_trip_duration_mean"], 10)
        self.assertEqual(metrics["unfinished_trip_duration_mean"], 2)
        self.assertEqual(metrics["trip_records_undeparted"], 1)
        self.assertNotIn("trip_duration", vehicles["c"])
        self.assertEqual(vehicles["b"]["trip_vaporized"], "end")
        self.assertEqual(vehicles["a"]["emission_co2_abs"], 30)

    def test_tls_counts_phase_changes_and_includes_last_partial_phase(self):
        path = self.xml("tls.xml.gz", '''<tlsStates>
          <tlsState time="0" id="x" programID="0" phase="0" state="Gr" />
          <tlsState time="2" id="x" programID="0" phase="0" state="gr" />
          <tlsState time="4" id="x" programID="0" phase="1" state="rG" />
          <tlsState time="7" id="x" programID="0" phase="0" state="Gr" />
        </tlsStates>''')
        result = {}
        c._tls(path, 0, 9, result)
        light = result["x"]
        self.assertEqual(light["phase_changes"], 2)
        self.assertEqual(light["state_changes"], 3)
        self.assertEqual(light["program_30_phase_0_duration_seconds_min"], 2)
        self.assertEqual(light["program_30_phase_0_duration_seconds_max"], 4)
        self.assertEqual(light["program_30_phase_0_duration_seconds_mean"], 3)
        self.assertEqual(sum(v for k, v in light.items() if k.startswith("state_") and k.endswith("duration_seconds")), 9)

    def test_queues_aggregate_lanes_at_each_step_before_temporal_statistics(self):
        path = self.xml("queues.xml.gz", '''<queue-export>
          <data timestep="0"><lanes><lane id="a" queueing_time="3" queueing_length="4" queueing_length_experimental="5" /><lane id="b" queueing_time="2" queueing_length="6" queueing_length_experimental="7" /></lanes></data>
          <data timestep="1"><lanes /></data>
        </queue-export>''')
        group = ("intersections", "tls")
        entities = {"lanes": {}, "intersections": {}}
        c._queues(path, {"a", "b"}, {group: {"a", "b"}},
                  defaultdict(list, {"a": [group], "b": [group]}), entities, {})
        self.assertEqual(entities["lanes"]["a"]["queueing_length_mean"], 2)
        self.assertEqual(entities["intersections"]["tls"]["queueing_length_lane_sum_mean"], 5)

    def test_tls_observes_phase_changes_even_when_lights_do_not_change(self):
        path = self.xml("tls.xml.gz", '''<tlsStates>
          <tlsState time="0" id="x" programID="0" phase="0" state="Gr" />
          <tlsState time="1" id="x" programID="0" phase="1" state="Gr" />
          <tlsState time="2" id="x" programID="0" phase="1" state="Gr" />
        </tlsStates>''')
        result = {}
        c._tls(path, 0, 3, result)
        self.assertEqual(result["x"]["phase_changes"], 1)
        self.assertEqual(result["x"]["state_changes"], 0)
        self.assertEqual(result["x"]["program_30_phase_1_duration_seconds_mean"], 2)

    def test_emissions_use_energy_average_for_noise_and_accept_accumulation(self):
        path = self.xml("emissions.xml.gz", '''<emission-export>
          <timestep time="0"><vehicle id="a" CO2="10" noise="10" waiting="0" /></timestep>
          <timestep time="1"><vehicle id="a" CO2="30" noise="20" waiting="1" /></timestep>
          <timestep time="2" />
        </emission-export>''')
        vehicles, metrics = {}, {}
        c._emissions(path, vehicles, metrics)
        self.assertEqual(vehicles["a"]["emission_co2_rate_mean"], 20)
        self.assertAlmostEqual(vehicles["a"]["noise_db_equivalent"], 10 * math.log10(55))
        self.assertEqual(metrics["network_emission_co2_rate_mean"], 40 / 3)
        self.assertEqual(vehicles["a"]["current_waiting_time_seconds_mean"], 0.5)

    def test_fcd_preserves_deceleration_and_circular_heading(self):
        path = self.xml("fcd.xml.gz", '''<fcd-export>
          <timestep time="0"><vehicle id="a" lane="x" speed="0" acceleration="-2" angle="359" signals="0" /></timestep>
          <timestep time="1"><vehicle id="a" lane="x" speed="2" acceleration="2" angle="1" signals="2" /></timestep>
        </fcd-export>''')
        entities = {"vehicles": {}, "lanes": {}}
        c._trajectories(path, {"x"}, defaultdict(list), {}, entities, {})
        self.assertEqual(entities["vehicles"]["a"]["fcd_acceleration_min"], -2)
        angle = entities["vehicles"]["a"]["heading_circular_mean_degrees"]
        self.assertLess(min(angle, 360 - angle), 1e-8)
        self.assertEqual(entities["lanes"]["x"]["stopped_vehicles_mean"], 0.5)

    def test_missing_required_output_raises_instead_of_returning_empty_success(self):
        with self.assertRaises(FileNotFoundError):
            c.collect_episode(self.directory, self.directory / "net.xml")

    def test_core_requires_only_its_enabled_sources_and_full_rejects_missing_sources(self):
        net = self.xml("net.xml", '<net><edge id="a"><lane id="a_0" /></edge></net>')
        self.xml("summary.xml.gz", '<summary><step time="0" running="0" arrived="0" /></summary>')
        for name, root in (("trips.xml.gz", "tripinfos"), ("statistics.xml", "statistics"),
                           ("tls.xml.gz", "tlsStates"), ("queues.xml.gz", "queue-export"),
                           ("lanechanges.xml.gz", "lanechanges"), ("collisions.xml.gz", "collisions")):
            self.xml(name, f"<{root} />")
        result = c.collect_episode(self.directory, net)
        self.assertEqual(result["metrics"]["metrics_profile"], "core")
        self.assertNotIn("fcd_observation_steps", result["metrics"])
        self.assertIn("collection_trips_time_seconds", result["metrics"])
        self.assertNotIn("edge_id", result["entities"]["lanes"]["a_0"])
        with self.assertRaises(FileNotFoundError):
            c.collect_episode(self.directory, net, profile="full")
        for name, root in (("lanes.xml.gz", "meandata"), ("edges.xml.gz", "meandata"),
                           ("fcd.xml.gz", "fcd-export"), ("emissions.xml.gz", "emission-export")):
            self.xml(name, f"<{root} />")
        result = c.collect_episode(self.directory, net, profile="full")
        self.assertEqual(result["metrics"]["metrics_profile"], "full")
        self.assertEqual(result["metrics"]["fcd_observation_steps"], 0)

    def test_profiles_preserve_trip_emissions_and_only_full_requests_dense_series(self):
        (self.directory / "inputs").mkdir()
        core = prepare_outputs(self.directory)
        self.assertIn("--device.emissions.probability", core)
        self.assertNotIn("--fcd-output", core)
        self.assertNotIn("--emission-output", core)
        self.assertNotIn("edgeData", (self.directory / "inputs/observations.add.xml").read_text())
        full = prepare_outputs(self.directory, "full")
        self.assertIn("--fcd-output", full)
        self.assertIn("--emission-output", full)
        self.assertIn("edgeData", (self.directory / "inputs/observations.add.xml").read_text())
        with self.assertRaises(ValueError):
            prepare_outputs(self.directory, "unknown")
        with self.assertRaises(ValueError):
            c.collect_episode(self.directory, self.directory / "net.xml", "unknown")

    def test_network_includes_internal_lanes_but_groups_only_external_approaches(self):
        path = self.xml("net.xml", '''<net>
          <edge id="a"><lane id="a_0" /></edge>
          <edge id=":j" function="internal"><lane id=":j_0" /></edge>
          <connection from="a" fromLane="0" tl="tls" />
          <connection from=":j" fromLane="0" tl="tls" />
        </net>''')
        lanes, edges, mapping, groups, membership = c._network(path)
        self.assertIn(":j_0", lanes)
        self.assertEqual(groups[("intersections", "tls")], {"a_0"})


if __name__ == "__main__":
    unittest.main()
