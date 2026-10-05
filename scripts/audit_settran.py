"""Normaliza a planilha auditada em dados intermediários, sem emitir programas SUMO.

Uso: python3 scripts/audit_settran.py [--check]. A fonte tem layout e hash
conhecidos: uma revisão do XLSX exige nova auditoria antes de alterar este leitor.
"""

import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "RondonNorte.xlsx"
OUTPUT = ROOT / "docs" / "settran" / "settran_programs.json"
SOURCE_SHA256 = "5d6014fb9978e55513beda8db8793dbec67c94b5555ea7989a7862cf56882d2a"
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
# Cabeçalho, primeira linha de plano, primeira descrição de estágio, quantidade.
BLOCKS = (
    (3, 7, 15, 4), (21, 25, 33, 4), (39, 43, 51, 3),
    (56, 60, 68, 4), (74, 78, 86, 4), (92, 96, 104, 4),
    (110, 114, 122, 4), (128, 132, 140, 2), (144, 148, 156, 3),
)
TIMING_FIELDS = (
    "green_seconds", "yellow_seconds", "clearance_red_seconds", "red_seconds",
)
# Associações físicas confirmadas em settran_audit.csv, identificadas pelas
# células do cabeçalho/estágio e pelo rótulo original. Não definem permissões,
# phase.state, sequência ou transições entre estágios que compartilham links.
CONFIRMED_STAGE_LINKS = {
    ("A39", "A51", "A"): ("FAM_CESARIO_PARANA", (1, 2)),
    ("A39", "A52", "B"): ("FAM_CESARIO_PARANA", (3, 4)),
    ("A39", "A53", "C"): ("FAM_CESARIO_PARANA", (0,)),
    ("A56", "A70", "C"): ("FAM_RONDON_PORTO_ALEGRE", (3, 4)),
    ("A74", "A86", "A"): ("FAM_RONDON_BELEM", (4, 5, 6)),
    ("A74", "A87", "B"): ("FAM_RONDON_BELEM", (0, 1, 2, 3, 4, 5, 6)),
    ("A74", "A88", "C"): ("FAM_RONDON_BELEM", (0, 1, 2, 3)),
    ("A74", "A89", "D"): ("FAM_RONDON_BELEM", (7, 8, 9)),
    ("A110", "A122", "A"): ("FAM_RONDON_NITEROI", (0, 1, 2, 3, 4, 5, 6)),
    ("A110", "A124", "C"): ("FAM_RONDON_NITEROI", (12, 13, 14, 15, 16)),
}


def read_source(path):
    """Lê valores armazenados no XLSX; nenhuma fórmula é executada."""
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != SOURCE_SHA256:
        raise ValueError(
            "RondonNorte.xlsx difere da fonte auditada. Reaudite o conteúdo, "
            "as fórmulas e o layout antes de atualizar o importador; "
            "nenhum artefato foi gravado."
        )
    with ZipFile(path) as archive:
        strings = [
            "".join(item.itertext())
            for item in ET.fromstring(archive.read("xl/sharedStrings.xml"))
        ]
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    cells = {}
    for cell in sheet.findall(".//s:c", NS):
        value = cell.find("s:v", NS)
        if value is not None:
            cells[cell.attrib["r"]] = (
                strings[int(value.text)] if cell.get("t") == "s" else value.text
            )
    return cells


def normalize_source(path=SOURCE):
    """Conserva planos e tempos; lacunas impedem conversão em phase.state."""
    cells = read_source(path)
    programs = []
    anomalies = []
    for heading, first_plan, first_description, stage_count in BLOCKS:
        intersection = cells[f"A{heading}"]
        for row in range(first_plan, first_plan + 4):
            plan_id = cells[f"A{row}"]
            cycle = int(cells[f"S{row}"])
            stages = []
            for index in range(stage_count):
                columns = ("CDEF", "GHIJ", "KLMN", "OPQR")[index]
                description_row = first_description + index
                stage_id = cells[f"A{description_row}"].strip()
                timings = {
                    name: int(cells[f"{column}{row}"])
                    for name, column in zip(TIMING_FIELDS, columns)
                }
                binding = CONFIRMED_STAGE_LINKS.get(
                    (f"A{heading}", f"A{description_row}", stage_id)
                )
                stages.append({
                    "stage_id": stage_id,
                    "movement": cells[f"B{description_row}"].strip(),
                    **timings,
                    "sumo_links": [{
                        "tls_id": binding[0],
                        "link_indices": list(binding[1]),
                    }] if binding is not None else None,
                    "source_cells": {
                        "stage_id": f"A{description_row}",
                        "movement": f"B{description_row}",
                        **{name: f"{column}{row}"
                           for name, column in zip(TIMING_FIELDS, columns)},
                    },
                })
                if sum(timings.values()) != cycle:
                    anomalies.append({
                        "kind": "red_cycle_mismatch",
                        "intersection": intersection,
                        "plan_id": plan_id,
                        "stage_id": stage_id,
                        "source_cell": f"{columns[3]}{row}",
                        "source_red_seconds": timings["red_seconds"],
                        "cycle_seconds": cycle,
                        "arithmetic_residual_seconds": cycle - sum(
                            timings[field] for field in TIMING_FIELDS[:3]
                        ),
                        "resolution": "pending_settran_confirmation",
                    })
            programs.append({
                "intersection": intersection,
                "plan_id": plan_id,
                "cycle_seconds": cycle,
                "offset_seconds": int(cells[f"B{row}"]),
                "stages": stages,
                "sumo_tls_ids": sorted({
                    link["tls_id"] for stage in stages
                    for link in (stage["sumo_links"] or [])
                }),
                "sumo_phases": None,
                "source_cells": {
                    "intersection": f"A{heading}",
                    "plan_id": f"A{row}",
                    "cycle_seconds": f"S{row}",
                    "offset_seconds": f"B{row}",
                },
            })
    anomalies.append({
        "kind": "intersection_name_mismatch",
        "source_cells": ["A144", "B158"],
        "source_values": [cells["A144"], cells["B158"]],
        "resolution": "pending_settran_confirmation",
    })
    return {
        "schema_version": 1,
        "signal_profile": "settran",
        "status": "blocked",
        "representation": "audited_intermediate_not_executable",
        "source": {
            "path": "RondonNorte.xlsx",
            "sha256": SOURCE_SHA256,
            "sheet": "Plan1",
            "range": "A1:S158",
            "unit": "seconds",
            "unit_source_cell": "A11",
            "numeric_values": "stored_values_in_audited_xlsx",
        },
        "normalization_notes": [
            "IDs dos planos preservados como strings; Plan1 é o nome da aba.",
            "Tempos numéricos em segundos; somente espaços externos dos rótulos foram removidos.",
            "A ordem dos estágios é a apresentação na fonte, não uma sequência SUMO confirmada.",
            "offset_seconds preserva Defasagem; origem, sinal e marco não confirmados para SUMO.",
            "Vermelho é residual do ciclo em 125 fórmulas; não é fase adicional a concatenar.",
            "Os três vermelhos discrepantes são preservados sem correção automática.",
            "null representa informação ausente ou não comprovada; não representa agenda de dia inteiro.",
            "sumo_links conserva apenas associações físicas confirmadas na auditoria; não define permissões, estados ou transições.",
            "sumo_tls_ids reúne somente TLS de estágios com vínculo físico confirmado; não inventaria toda a interseção.",
        ],
        "programs": programs,
        "schedule": None,
        "operational_day_start": None,
        "initial_plan_id": None,
        "blockers": [
            {"id": "missing_schedule", "detail": "Faltam horários, dias e vínculos horário→plano por interseção."},
            {"id": "missing_operational_day_start", "detail": "Falta o marco oficial para iniciar o relógio operacional de cada episódio."},
            {"id": "unconfirmed_stage_links", "detail": "Não há correspondência confirmada de todos os estágios com controlled links, permissões e travessias SUMO."},
            {"id": "unconfirmed_transitions", "detail": "Faltam estados, transições entre grupos e interpretação dos tempos de pedestres."},
            {"id": "unconfirmed_offset_reference", "detail": "Falta confirmar a referência e o sinal da defasagem para SUMO."},
            {"id": "source_anomalies", "detail": "Três vermelhos de Niterói e a divergência Nascimento/Santos exigem confirmação da SETTRAN."},
        ],
        "anomalies": anomalies,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="confere o JSON sem gravar arquivos")
    args = parser.parse_args(argv)
    try:
        document = normalize_source(SOURCE)
        content = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
        if args.check:
            if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != content:
                raise ValueError("settran_programs.json está ausente ou diverge da fonte auditada.")
        else:
            OUTPUT.write_text(content, encoding="utf-8")
    except (OSError, ValueError) as error:
        parser.exit(1, f"Erro: {error}\n")
    print("SETTRAN: 36 planos e 128 estágios conferidos; perfil bloqueado pelas lacunas documentadas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
