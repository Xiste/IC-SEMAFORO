"""Geração de demanda por volume de cada via da rede."""

import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from semaforos.configuracao import read_config
from semaforos.demanda import create_demand
from semaforos.simulacao import load_scenario


ROOT = Path(__file__).resolve().parents[1]


class EdgeVolumeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = read_config(ROOT / "config" / "cenario.json")
        _, cls.network, _ = load_scenario(cls.config)

    def test_counts_and_reachable_destinations(self):
        config = dict(self.config)
        config["duration_seconds"] = 60
        config["demand"] = {"mode": "edge_volumes", "edge_volumes": [
            {"from_edge": "1156272393#6", "vehicles_per_hour": 360},
            {"from_edge": "1156717168", "vehicles_per_hour": 180},
        ]}
        with tempfile.TemporaryDirectory() as folder:
            path = create_demand(config, self.network, Path(folder), 11)
            trips = ET.parse(path).getroot().findall("trip")
            manifest = json.loads((Path(folder) / "demand_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(trips), 9)
            self.assertEqual([entry["planned_vehicles"] for entry in manifest["entries"]], [6, 3])
            departures = [float(trip.attrib["depart"]) for trip in trips]
            self.assertEqual(departures, sorted(departures))
            for trip in trips:
                origin = self.network.getEdge(trip.attrib["from"])
                destination = self.network.getEdge(trip.attrib["to"])
                self.assertTrue(self.network.getShortestPath(origin, destination, vClass="passenger")[0])

    def test_duplicate_origin_rejected(self):
        config = dict(self.config)
        config["demand"] = {"mode": "edge_volumes", "edge_volumes": [
            {"from_edge": "1156272393#6", "vehicles_per_hour": 360},
            {"from_edge": "1156272393#6", "vehicles_per_hour": 180},
        ]}
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "repetida"):
                create_demand(config, self.network, Path(folder), 11)

    def test_profile_destination_shares_and_vehicle_type(self):
        origin = self.network.getEdge("1156272393#6")
        exits = [edge.getID() for edge in self.network.getEdges(withInternal=False)
                 if not edge.getOutgoing() and edge.allows("passenger")
                 and self.network.getShortestPath(origin, edge, vClass="passenger")[0]]
        self.assertGreaterEqual(len(exits), 2)
        config = dict(self.config)
        config["duration_seconds"] = 100
        config["demand"] = {"mode": "edge_volumes", "edge_volumes": [{
            "from_edge": origin.getID(), "vehicles_per_hour": 360,
            "destinations": [{"to_edge": exits[0], "share": 0.75},
                             {"to_edge": exits[1], "share": 0.25}]}],
            "time_profile": [{"begin": 0, "end": 50, "multiplier": 1},
                             {"begin": 50, "end": 100, "multiplier": 3}],
            "vehicle_types": [{"id": "cars", "vClass": "passenger", "share": 1}]}
        with tempfile.TemporaryDirectory() as folder:
            path = create_demand(config, self.network, Path(folder), 11)
            root = ET.parse(path).getroot()
            trips = root.findall("trip")
            self.assertEqual(len(trips), 10)
            self.assertEqual(len([trip for trip in trips if float(trip.attrib["depart"]) < 50]), 3)
            self.assertTrue(all(trip.attrib["to"] in exits[:2] for trip in trips))
            self.assertTrue(all(trip.attrib["type"] == "cars" for trip in trips))
            self.assertEqual(root.find("vType").attrib["vClass"], "passenger")


if __name__ == "__main__":
    unittest.main()
