"""Recupera nomes OSM das entradas dos nove locais sem alterar a rede."""
import datetime
import json
import re
import urllib.request
from pathlib import Path

import sumolib

ROOT = Path(__file__).resolve().parents[1]
network = sumolib.net.readNet(str(ROOT / "dados/rede/uberlandia.rondon_norte_corrigida.net.xml"))
mapping = json.loads((ROOT / "config/mapeamento_associado.json").read_text(encoding="utf-8"))
ids = {c["tls_id"] for e in mapping["intersections"] for c in e["controllers"]}
edges = {c[0].getEdge().getID() for light in network.getTrafficLights() if light.getID() in ids
         for c in light.getConnections() if c[0].getEdge().allows("passenger")}
ways = sorted({re.match(r"^-?(\d+)(?:#|$)", edge).group(1) for edge in edges if re.match(r"^-?(\d+)(?:#|$)", edge)})
url = "https://api.openstreetmap.org/api/0.6/ways.json?ways=" + ",".join(ways)
request = urllib.request.Request(url, headers={"User-Agent": "RondonNorteResearch/1.0 (street-name lookup)"})
with urllib.request.urlopen(request, timeout=30) as response:
    data = json.load(response)
records = {str(e["id"]): {"name": e.get("tags", {}).get("name", ""),
                            "highway": e.get("tags", {}).get("highway", ""),
                            "version": e.get("version"), "osm_timestamp": e.get("timestamp"),
                            "source": f"https://www.openstreetmap.org/way/{e['id']}"}
           for e in data["elements"] if e["type"] == "way"}
destination = ROOT / "dados/auditoria/nomes_vias_osm.json"
destination.write_text(json.dumps({"retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                   "query": url, "ways": records}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"{len(edges)} entradas, {len(ways)} vias OSM, {sum(bool(r['name']) for r in records.values())} nomes recuperados")
for edge in sorted(edges):
    match = re.match(r"^-?(\d+)(?:#|$)", edge)
    print(edge, records.get(match.group(1), {}).get("name", "SEM NOME") if match else "ID SINTETICO")
