"""Associa os candidatos e extrai movimentos sem inventar grupos operacionais."""

import csv
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from semaforos.cenario.configuracao import read_config
from semaforos.cenario.mapeamento import mapping_report


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    config = read_config(ROOT / "config/cenario_rede_corrigida.json")
    mapping = json.loads(Path(config["mapping_path"]).read_text(encoding="utf-8"))
    inventory_path = ROOT / "dados/auditoria/inventario_geografico_tls.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    digest = hashlib.sha256(Path(config["network"]).read_bytes()).hexdigest()
    if any(row["network_sha256"] != digest for row in inventory):
        raise ValueError("Rede mudou; atualize scripts/inventario_geografico_tls.py antes de extrair o cadastro")
    by_id = {row["tls_id"]: row for row in inventory}
    xml = ET.parse(config["network"]).getroot()
    xml_connections = {(item.get("tl"), int(item.get("linkIndex", -1)),
                        f"{item.get('from')}_{item.get('fromLane')}",
                        f"{item.get('to')}_{item.get('toLane')}"): item
                       for item in xml.findall("connection") if item.get("tl")}
    audited_plans = json.loads((ROOT / "dados/auditoria/settran_programs.json").read_text(encoding="utf-8"))
    if audited_plans["source"]["sha256"] != hashlib.sha256(Path(config["plans"]).read_bytes()).hexdigest():
        raise ValueError("Planilha mudou; atualize sua auditoria antes de preparar o cadastro")
    output = ROOT / "dados/auditoria/cadastro_nove"
    destination = ROOT / "config/mapeamento_associado.json"
    if destination.exists() or (output.exists() and any(output.iterdir())):
        raise FileExistsError("Cadastro já existe; revise os arquivos gerados. O script não sobrescreve suas associações manuais.")
    output.mkdir(parents=True, exist_ok=True)
    controllers, links, matrix, stages = [], [], [], []
    assigned = set()
    turn_names = {"s": "reto", "l": "esquerda", "r": "direita", "t": "retorno",
                  "L": "esquerda parcial", "R": "direita parcial"}
    for entry in mapping["intersections"]:
        existing = {item["tls_id"]: item for item in entry.get("controllers", [])}
        entry["controllers"] = []
        for tls_id in entry["candidate_tls_ids"]:
            record = by_id[tls_id]
            if tls_id in assigned or record["intersection"] != entry["name"]:
                raise ValueError(f"Associação inconsistente: {tls_id}")
            assigned.add(tls_id)
            phases = record["program_phases"]
            controller = existing.get(tls_id, {"tls_id": tls_id, "stage_to_phase": {},
                "controlled_links_verified": False, "movements_verified": False,
                "pedestrians_verified": False, "safety_verified": False,
                "review_source": "", "reconciliation_note": ""})
            controller["association_source"] = "inventario_geografico_tls.json; conferência visual; geometria aceita pelo usuário em 06/10/2026"
            controller["network_connections_extracted"] = True
            entry["controllers"].append(controller)
            off = bool(record["indices_always_off"])
            controllers.append({"cruzamento": entry["name"], "tls_id": tls_id,
                "program_id": record["program_id_at_startup"], "conexões": len(record["connections"]),
                "fases": len(phases), "ciclo_s": sum(phase["duration"] for phase in phases),
                "estado": "contém sinais desligados" if off else "programa com fases",
                "links_sempre_vermelhos": ";".join(map(str, record["indices_always_red"])),
                "associação": "extraída do inventário; geografia confirmada pelo usuário",
                "validação_operacional": False})
            for connection in record["connections"]:
                index = connection["link_index"]
                key = (tls_id, index, connection["from_lane"], connection["to_lane"])
                if key not in xml_connections:
                    raise ValueError(f"Conexão do inventário ausente da rede: {key}")
                attributes = xml_connections[key]
                pedestrian = connection["to_edge_function"] in ("crossing", "walkingarea") or connection["from_edge_function"] in ("crossing", "walkingarea")
                colors = "".join(phase["state"][index] for phase in phases)
                link = {"cruzamento": entry["name"], "tls_id": tls_id, "link_index": index,
                    "from_edge": attributes.get("from"), "from_lane": connection["from_lane"],
                    "to_edge": attributes.get("to"), "to_lane": connection["to_lane"],
                    "tipo": "pedestre" if pedestrian else "veicular",
                    "direção_SUMO": attributes.get("dir", ""),
                    "movimento_geométrico": turn_names.get(attributes.get("dir"), "consultar geometria"),
                    "estados_por_fase": colors,
                    "atendimento_atual": "tem verde" if any(color in "Gg" for color in colors)
                        else "desligado/prioridade" if all(color in "Oo" for color in colors)
                        else "sem verde",
                    "grupo_real": "", "estágio_real": "", "evidência_operacional": ""}
                links.append(link)
                for index_phase, phase in enumerate(phases):
                    matrix.append({"tls_id": tls_id, "link_index": index,
                        "from_lane": connection["from_lane"], "to_lane": connection["to_lane"],
                        "phase_index": index_phase, "duration_s": phase["duration"],
                        "state": phase["state"][index]})
        plan = next(item for item in audited_plans["programs"]
                    if item["intersection"] == entry["name"] and str(item["plan_id"]) == str(config["plan_id"]))
        for stage in plan["stages"]:
            stages.append({"cruzamento": entry["name"], "plano": plan["plan_id"],
                "estágio": stage["stage_id"], "movimento_planilha": stage["movement"],
                "verde_s": stage["green_seconds"], "amarelo_s": stage["yellow_seconds"],
                "limpeza_s": stage["clearance_red_seconds"], "ciclo_s": plan["cycle_seconds"],
                "defasagem_planilha_s": plan["offset_seconds"],
                "tls_ids_confirmados": "", "link_indices_confirmados": "", "evidência": ""})
    if len(mapping["intersections"]) != 9 or len(assigned) != 17:
        raise ValueError("Esperados nove cruzamentos e 17 controladores distintos")
    for name, rows in (("controladores.csv", controllers), ("movimentos.csv", links),
                       ("fases_por_movimento.csv", matrix), ("estagios_a_associar.csv", stages)):
        write_csv(output / name, rows)
    destination.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = mapping_report(config, destination)
    (output / "auditoria_operacional.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {"intersections": 9, "controllers_assigned": len(assigned), "connections": len(links),
               "pedestrian_connections": sum(row["tipo"] == "pedestre" for row in links),
               "off_controllers": sum(row["estado"] == "contém sinais desligados" for row in controllers),
               "stages_to_associate": len(stages), "operationally_validated": report["validated_count"],
               "network_sha256": digest, "mapping": str(destination),
               "note": "Faixas e conversões extraídas da rede aceita pelo usuário. Grupos reais, estados e tempos não foram inventados; o mapeamento ativo permanece separado."}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
