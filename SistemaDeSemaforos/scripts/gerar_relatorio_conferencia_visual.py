"""Relaciona observações manuais do Maps ao inventário SUMO, sem validar operação."""
import json
import os
import math
from pathlib import Path
from urllib.parse import urlencode

import sumolib

ROOT = Path(__file__).resolve().parents[1]
audit_path = ROOT / "dados/auditoria/conferencia_visual_maps.json"
audit = json.loads(audit_path.read_text(encoding="utf-8"))
inventory = json.loads((ROOT / "dados/auditoria/inventario_geografico_tls.json").read_text(encoding="utf-8"))
mapping_path = ROOT / "config/mapeamento.json"
mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
observations = {item["mapping_name"]: item for item in audit["intersections"]}
assert len(observations) == len(audit["intersections"]) == 9
assert set(observations) == {item["name"] for item in mapping["intersections"]}
assert {item["tls_id"] for item in inventory} == {
    tls_id for item in mapping["intersections"] for tls_id in item["candidate_tls_ids"]}

lines = ["# Conferência visual dos nove cruzamentos — Rondon Norte", "",
         f"Consulta: {audit['review_date']}. Rede: `{audit['network']}`.", "",
         "Foram examinados mapa e panoramas dos nove locais. Esta é uma conferência preliminar de localização e elementos visíveis. Não houve levantamento completo de todas as aproximações, focos ou permissões. A programação e os tempos não podem ser confirmados por fotografias.", "",
         "As coordenadas de busca de sete locais vieram da rede SUMO: são um meio de localizar candidatos, não uma confirmação independente. A correspondência foi confrontada com nomes das ruas no mapa/panorama. Benjamim e Paraná foram encontrados por busca nominal.", "",
         "As conexões, quantidades de faixas e estados abaixo são do XML SUMO. Os IDs numéricos/FAM não foram confirmados como códigos oficiais de controladores físicos.", "",
         "## Resultado", "",
         "- 9 locais com imagem examinada; 0 cruzamentos plenamente validados.",
         "- 17 candidatos inventariados, incluindo conexões de pedestres.",
         "- Porto Alegre: captura de setembro de 2019 no ponto consultado; precisa de atualização em campo ou outro panorama recente.",
         "- João Naves: viaduto e acessos laterais exigem distinguir níveis e movimentos.",
         "- Anselmo: nome público dos Santos diverge de do Nascimento na chave legada; possível divergência de faixas precisa de conferência específica.", "",
         "## Problemas da rede corrigida", "",
         "O inventário consulta o programa ativo ao iniciar o SUMO apenas com esta rede, sem arquivo adicional ou ação externa. Isso não descreve necessariamente uma execução que carregue programas adicionais.", "",
         "Seis candidatos FAM têm programas veiculares em estado `O`, embora as imagens mostrem equipamentos semafóricos nesses locais. `O` significa sinal desligado com passagem por prioridade; não é verde e não significa que os veículos estejam permanentemente parados. [Documentação SUMO](https://sumo.dlr.de/docs/Simulation/Traffic_Lights.html).", "",
         "Há 16 candidatos com índices permanentemente vermelhos neste programa; as conexões correspondentes são de travessias de pedestres. Isso é uma lacuna do modelo, mesmo que a demanda atual não inclua pessoas. Não criar fases de pedestres sem conferir conflitos e tempos.", "",
         "| Candidato | Programa inicial | Índices sempre desligados | Índices sempre vermelhos |", "|---|---|---|---|"]
for item in inventory:
    lines.append(f"| `{item['tls_id']}` | `{item['program_id_at_startup']}` | {', '.join(map(str, item['indices_always_off'])) or '—'} | {', '.join(map(str, item['indices_always_red'])) or '—'} |")
lines += ["", "## Geometria do modelo", "",
          "![Conexões e faixas SUMO dos nove locais](../dados/auditoria/geometria_nove_cruzamentos.png)", "",
          "Figura extraída do XML; não é imagem do Google nem comprova a geometria real. As linhas são faixas, os pontos indicam nós associados aos IDs candidatos e as setas indicam sentido das faixas de entrada. Os diferentes níveis de viadutos não são representados por altura nesta figura."]

for index, entry in enumerate(mapping["intersections"], start=1):
    obs = observations[entry["name"]]
    pano_url = "https://www.google.com/maps/@?" + urlencode({
        "api": 1, "map_action": "pano", "pano": obs["panorama_id"],
        "heading": obs["heading_degrees"]})
    obs["panorama_url"] = pano_url
    entry["visual_review"] = {
        "status": "preliminary", "date": audit["review_date"],
        "evidence_file": "../dados/auditoria/conferencia_visual_maps.json",
        "evidence_key": entry["name"], "maps_name": obs["maps_name"],
        "image_date": obs["image_date"], "panorama_url": pano_url,
    }
    lines += ["", f"## {index}. {entry['name']}", "",
              f"Identificação pública: **{obs['maps_name']}**. Captura: **{obs['image_date']}**. [Panorama consultado]({pano_url}).",
              "", f"Correspondência espacial: {obs['location_correspondence']}.", "", "Observações:", ""]
    lines += [f"- {note}" for note in obs["observations"]]
    lines += ["", "Limitações e pendências:", ""]
    lines += [f"- {note}" for note in obs["limitations"]]
    lines += ["", "Inventário do modelo:", "",
              "| TLS candidato | Arestas de entrada externas: ID (faixas) | Conexões totais |", "|---|---|---|"]
    for item in inventory:
        if item["intersection"] == entry["name"]:
            edges = "; ".join(f"`{edge['id']}` ({edge['lane_count']})"
                              for edge in item["incoming_edges"] if edge["function"] == "external")
            lines.append(f"| `{item['tls_id']}` | {edges} | {len(item['connections'])} |")
    lines += ["", "Pendente: relacionar individualmente cada faixa e movimento ao foco real, identificar todas as travessias e completar o diagrama de estágios com fonte operacional. As marcas `controlled_links_verified`, `movements_verified`, `pedestrians_verified` e `safety_verified` permanecem falsas."]
lines += ["", "## Como reproduzir", "", "Na pasta SistemaDeSemaforos:", "", "```powershell",
          r".\.venv\Scripts\python.exe scripts/inventario_geografico_tls.py",
          r".\.venv\Scripts\python.exe scripts/gerar_relatorio_conferencia_visual.py", "```", "",
          "O primeiro comando abre uma conexão SUMO/TraCI sem simular passos e exporta os candidatos. O segundo gera este relatório e a figura e atualiza somente as anotações `visual_review` do mapeamento. A fonte de observações é manual: executar os scripts novamente não revisita o Google Maps.", ""]

os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "resultados/matplotlib_cache"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

net = sumolib.net.readNet(str(ROOT / audit["network"]), withInternal=True)
fig, axes = plt.subplots(3, 3, figsize=(18, 18))
for index, (axis, entry) in enumerate(zip(axes.flat, mapping["intersections"]), start=1):
    records = [item for item in inventory if item["intersection"] == entry["name"]]
    nodes = {node["id"]: net.getNode(node["id"]).getCoord()
             for item in records for node in item["junctions"]}
    xs, ys = zip(*nodes.values())
    bounds = (min(xs)-65, max(xs)+65, min(ys)-65, max(ys)+65)
    segments = [lane.getShape() for edge in net.getEdges(withInternal=True)
                for lane in edge.getLanes() if len(lane.getShape()) > 1]
    axis.add_collection(LineCollection(segments, colors="#bcc4ca", linewidths=0.65))
    incoming_ids = {edge["id"] for item in records for edge in item["incoming_edges"]
                    if edge["function"] == "external"}
    for edge_id in incoming_ids:
        for lane in net.getEdge(edge_id).getLanes():
            shape = lane.getShape()
            axis.plot(*zip(*shape), color="#277daf", linewidth=1.1)
            if len(shape) > 1:
                end_x, end_y = shape[-1]
                dx, dy = end_x-shape[-2][0], end_y-shape[-2][1]
                length = math.hypot(dx, dy)
                if length:
                    scale = min(length, 6) / length
                    arrow = axis.annotate("", xy=shape[-1],
                                          xytext=(end_x-dx*scale, end_y-dy*scale),
                                          arrowprops={"arrowstyle": "->", "color": "#277daf", "lw": 1})
                    arrow.arrow_patch.set_clip_path(axis.patch)
    for tls_index, item in enumerate(records, start=1):
        for node in item["junctions"]:
            x, y = nodes[node["id"]]
            axis.scatter(x, y, color="#bc312b", s=22, zorder=3)
            axis.annotate(str(tls_index), (x, y), xytext=(3,3), textcoords="offset points", fontsize=8)
    axis.set_xlim(bounds[:2]); axis.set_ylim(bounds[2:]); axis.set_aspect("equal")
    axis.set_title(f"{index}. {entry['name']}\n" + " | ".join(
        f"{i}: {item['tls_id']}" for i, item in enumerate(records, start=1)), fontsize=8)
    axis.set_xlabel("X SUMO (m)", fontsize=8); axis.set_ylabel("Y SUMO (m)", fontsize=8)
fig.suptitle("Geometria SUMO dos candidatos — conferência visual preliminar, operação não validada", fontsize=14)
fig.tight_layout(rect=(0,0,1,0.97))
fig.savefig(ROOT / "dados/auditoria/geometria_nove_cruzamentos.png", dpi=130)
plt.close(fig)
(ROOT / "docs/conferencia_visual_nove_cruzamentos.md").write_text("\n".join(lines), encoding="utf-8")
audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
mapping_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("9 locais documentados; anotações visuais registradas; nenhuma validação operacional atribuída.")
