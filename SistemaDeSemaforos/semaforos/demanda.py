"""Geração de rotas sintéticas ou fluxos informados por via."""

import subprocess
import sys
import xml.etree.ElementTree as ET

from .configuracao import sumo_executable


def create_demand(config, network, output, seed):
    demand = config["demand"]
    routes = output / "routes.rou.xml"
    if demand["mode"] == "random":
        rate = demand["vehicles_per_hour"]
        if rate <= 0:
            raise ValueError("vehicles_per_hour deve ser positivo")
        tool = sumo_executable().parent.parent / "tools" / "randomTrips.py"
        if not tool.is_file():
            raise RuntimeError(f"randomTrips.py não encontrado: {tool}")
        result = subprocess.run([
            sys.executable, str(tool), "-n", str(config["network"]),
            "-o", str(output / "trips.trips.xml"), "--route-file", str(routes),
            "-b", "0", "-e", str(config["duration_seconds"]),
            "-p", str(3600 / rate), "--seed", str(seed),
        ], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f"Falha ao gerar rotas: {result.stderr[-2000:]}")
    else:
        known_edges = {edge.getID() for edge in network.getEdges(withInternal=False)}
        if not demand["flows"]:
            raise ValueError("demand.flows está vazio")
        root = ET.Element("routes")
        for index, flow in enumerate(demand["flows"]):
            origin, destination = flow["from_edge"], flow["to_edge"]
            rate = float(flow["vehicles_per_hour"])
            if origin not in known_edges or destination not in known_edges or rate <= 0:
                raise ValueError(f"Fluxo {index}: vias ausentes ou taxa inválida")
            ET.SubElement(root, "flow", {
                "id": f"flow_{index}", "from": origin, "to": destination,
                "begin": "0", "end": str(config["duration_seconds"]),
                "vehsPerHour": str(rate),
            })
        ET.ElementTree(root).write(routes, encoding="utf-8", xml_declaration=True)
    return routes
