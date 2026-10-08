"""Contagem efetiva com detectores virtuais E1 nos trechos medidos."""
import csv
import json
import xml.etree.ElementTree as ET

import traci


class FlowCounts:
    def __init__(self, config, network, output):
        self.output = output
        self.duration = float(config["duration_seconds"])
        self.loops = {}
        self.passed = {}
        self.target = {}
        self.fitted = {}
        self.file = None
        if config["demand"]["mode"] != "observed_counts":
            return
        report = json.loads((output / "calibration.json").read_text(encoding="utf-8"))
        root = ET.Element("additional")
        for number, row in enumerate(report["measurements"]):
            edge = row["from_edge"]
            self.target[edge] = row["measured_vehicles_per_hour"]
            self.fitted[edge] = row["fitted_vehicles_per_hour"]
            self.passed[edge] = set()
            for index, lane in enumerate(network.getEdge(edge).getLanes()):
                loop = f"measurement_{number}_{index}"
                self.loops[loop] = edge
                ET.SubElement(root, "inductionLoop", id=loop, lane=lane.getID(), pos=str(lane.getLength() / 2),
                              period=str(self.duration), file=str(output / "detector_output.xml"))
        self.file = output / "measurement_detectors.add.xml"
        ET.ElementTree(root).write(self.file, encoding="utf-8", xml_declaration=True)

    def step(self, window_start=0):
        for loop, edge in self.loops.items():
            self.passed[edge].update(data[0] for data in traci.inductionloop.getVehicleData(loop) if data[2] >= window_start)

    def rows(self, observed_seconds=None):
        seconds = self.duration if observed_seconds is None else float(observed_seconds)
        rows = [{"edge_id": edge, "measured_vehicles_per_hour": self.target[edge],
                 "fitted_vehicles_per_hour": self.fitted[edge], "passed_vehicles": len(passed),
                 'observed_seconds': seconds,
                 "realized_vehicles_per_hour": len(passed) * 3600 / seconds if seconds > 0 else None}
                for edge, passed in self.passed.items()]
        if rows:
            with (self.output / "flow_counts.csv").open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=rows[0])
                writer.writeheader()
                writer.writerows(rows)
        return rows
