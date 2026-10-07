"""Exporta geometria dos candidatos para comparação manual com imagens públicas."""
import json
import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path

import sumolib
import traci

ROOT = Path(__file__).resolve().parents[1]
network_path = ROOT / "dados/rede/uberlandia.rondon_norte_corrigida.net.xml"
mapping = json.loads((ROOT / "config/mapeamento.json").read_text(encoding="utf-8"))
net = sumolib.net.readNet(
    str(network_path),
    withInternal=True,
)
records = []
network_hash = hashlib.sha256(network_path.read_bytes()).hexdigest()
xml_root = ET.parse(network_path).getroot()
programs = {(item.get("id"), item.get("programID")): item
            for item in xml_root.findall("tlLogic")}
edge_functions = {item.get("id"): item.get("function", "external")
                  for item in xml_root.findall("edge")}
traci.start([sumolib.checkBinary("sumo"), "--net-file", str(network_path),
             "--no-step-log", "true"], label="inventario_geo")
geo = traci.getConnection("inventario_geo")
try:
    coordinates = {node.getID(): geo.simulation.convertGeo(*node.getCoord())
                   for node in net.getNodes()}
    active_programs = {tls_id: geo.trafficlight.getProgram(tls_id)
                       for tls_id in geo.trafficlight.getIDList()}
finally:
    geo.close()
for entry in mapping["intersections"]:
    for tls_id in entry["candidate_tls_ids"]:
        connections = net.getTLS(tls_id).getConnections()
        nodes = sorted({item[0].getEdge().getToNode().getID() for item in connections})
        program_id = active_programs[tls_id]
        phases = programs[tls_id, program_id].findall("phase")
        missing_green = [index for index in range(len(phases[0].get("state")))
                         if not any(phase.get("state")[index] in "gG" for phase in phases)]
        records.append({
            "intersection": entry["name"],
            "tls_id": tls_id,
            "program_id_at_startup": program_id,
            "program_phases": [{"duration": float(phase.get("duration")),
                                "state": phase.get("state")} for phase in phases],
            "network_sha256": network_hash,
            "junctions": [{"id": node, "lon_lat": coordinates[node]}
                          for node in nodes],
            "connections": [{"from_lane": item[0].getID(), "to_lane": item[1].getID(),
                             "link_index": item[2],
                             "from_edge_function": edge_functions[item[0].getEdge().getID()],
                             "to_edge_function": edge_functions[item[1].getEdge().getID()],
                             "from_edge_name": item[0].getEdge().getName(),
                             "to_edge_name": item[1].getEdge().getName()}
                            for item in connections],
            "incoming_edges": [{"id": edge.getID(), "lane_count": edge.getLaneNumber(),
                                "function": edge_functions[edge.getID()],
                                "shape_sumo_xy": edge.getShape()}
                               for edge in sorted({item[0].getEdge() for item in connections},
                                                  key=lambda edge: edge.getID())],
            "indices_without_green": missing_green,
            "indices_always_red": [index for index in missing_green
                                   if all(phase.get("state")[index] in "rR" for phase in phases)],
            "indices_always_off": [index for index in missing_green
                                   if all(phase.get("state")[index] in "Oo" for phase in phases)],
        })
output = ROOT / "dados/auditoria/inventario_geografico_tls.json"
output.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"{len(records)} candidatos exportados: {output}")
