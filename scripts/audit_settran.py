"""Normaliza a fonte SETTRAN e conserva suplementos operacionais explícitos.

Uso: python3 scripts/audit_settran.py [--check]. A fonte tem layout e hash
conhecidos: uma revisão do XLSX exige nova auditoria antes de alterar este leitor.
Conserva os dados originais da planilha ao gerar o JSON usado pelo conversor.
Com --check, compara o arquivo existente com a fonte sem regravá-lo.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "RondonNorte.xlsx"
OUTPUT = ROOT / "docs" / "settran_programs.json"
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
# Cobertura geográfica inclui retenções auxiliares, mesmo quando o XLSX não
# demonstra se elas recebem o mesmo comando do cruzamento principal.
INTERSECTION_TLS_IDS = {
    "A3": ("FAM_RONDON_BENJAMIM",),
    "A21": ("FAM_RONDON_PARANA",),
    "A39": ("FAM_CESARIO_PARANA",),
    "A56": ("FAM_RONDON_PORTO_ALEGRE", "3386573305", "3386573306", "5494111603"),
    "A74": ("FAM_RONDON_BELEM",),
    "A92": ("FAM_RONDON_ROTARY_CLUB",),
    "A110": ("FAM_RONDON_NITEROI", "5494111596", "5494111597"),
    "A128": ("5494111589", "5494111590", "5494111594"),
    "A144": ("FAM_RONDON_ANSELMO", "338654991"),
}

# São conjuntos físicos de connections, não uma matriz de permissões.
# Esquerdas/retornos presentes nesses conjuntos podem conflitar com retas:
# aplicar G a todos os índices seria uma interpretação operacional indevida.
PHYSICAL_STAGE_LINKS = {
    ("A3", "A15", "A"): (("FAM_RONDON_BENJAMIM", (0, 1, 2, 3, 4, 5, 9, 10, 11, 12, 13, 14)),),
    ("A3", "A16", "B"): (("FAM_RONDON_BENJAMIM", (6, 7, 8)),),
    ("A3", "A17", "C"): (("FAM_RONDON_BENJAMIM", (15, 16, 17)),),
    ("A21", "A33", "A"): (("FAM_RONDON_PARANA", (0, 1, 2, 3)),),
    ("A21", "A34", "B"): (("FAM_RONDON_PARANA", (7, 8, 9, 10)),),
    ("A21", "A35", "C"): (("FAM_RONDON_PARANA", (4,)),),
    ("A21", "A36", "D"): (("FAM_RONDON_PARANA", (5, 6)),),
    ("A39", "A51", "A"): (("FAM_CESARIO_PARANA", (1, 2)),),
    ("A39", "A52", "B"): (("FAM_CESARIO_PARANA", (3, 4)),),
    ("A39", "A53", "C"): (("FAM_CESARIO_PARANA", (0,)),),
    ("A56", "A68", "A"): (("FAM_RONDON_PORTO_ALEGRE", (0, 1, 2)),),
    ("A56", "A69", "B"): (("FAM_RONDON_PORTO_ALEGRE", (0, 1, 2, 5, 6, 7, 8, 9)),),
    ("A56", "A70", "C"): (("FAM_RONDON_PORTO_ALEGRE", (3, 4)),),
    ("A74", "A86", "A"): (("FAM_RONDON_BELEM", (4, 5, 6)),),
    ("A74", "A87", "B"): (("FAM_RONDON_BELEM", (0, 1, 2, 3, 4, 5, 6)),),
    ("A74", "A88", "C"): (("FAM_RONDON_BELEM", (0, 1, 2, 3)),),
    ("A74", "A89", "D"): (("FAM_RONDON_BELEM", (7, 8, 9)),),
    ("A92", "A104", "A"): (("FAM_RONDON_ROTARY_CLUB", (5, 6, 7, 8)),),
    ("A92", "A105", "B"): (("FAM_RONDON_ROTARY_CLUB", (1, 2, 3, 4, 5, 6, 7, 8)),),
    ("A92", "A106", "C"): (("FAM_RONDON_ROTARY_CLUB", (1, 2, 3, 4)),),
    ("A110", "A122", "A"): (("FAM_RONDON_NITEROI", (0, 1, 2, 3, 4, 5, 6)),),
    ("A110", "A123", "B"): (("FAM_RONDON_NITEROI", (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)),),
    ("A110", "A124", "C"): (("FAM_RONDON_NITEROI", (12, 13, 14, 15, 16)),),
    ("A128", "A140", "A"): (("5494111590", (0, 1, 2, 3, 4)),),
    ("A128", "A141", "B"): (("5494111589", (0, 1, 2, 3)), ("5494111594", (0, 1, 2, 3))),
    ("A144", "A156", "A"): (("FAM_RONDON_ANSELMO", (3, 4, 5, 6, 7)),),
    ("A144", "A157", "B"): (("FAM_RONDON_ANSELMO", (0, 1, 2, 3, 4, 5, 6, 7)),),
    ("A144", "A158", "C"): (("338654991", (0, 1)),),
}
CONFIRMED_BINDINGS = {
    ("A3", "A16", "B"), ("A39", "A51", "A"), ("A39", "A52", "B"),
    ("A39", "A53", "C"), ("A56", "A70", "C"),
    ("A74", "A86", "A"), ("A74", "A87", "B"), ("A74", "A88", "C"), ("A74", "A89", "D"),
    ("A110", "A122", "A"), ("A110", "A124", "C"), ("A144", "A158", "C"),
}
MAPPING_NOTES = {
    ("A3", "A17", "C"):
        "Alagoas 30620978#11 alimenta -403166934 (trecho Ricardo Siquierolli Tucci), "
        "depois 853751181#0, única aproximação lateral restante. Continuidade física "
        "comprovada, sem renomear vias ou presumir grupo focal.",
    ("A92", "A107", "D"):
        "Falta documento que identifique quais movimentos pertencem ao Grupo D: "
        "a fonte diz Antônio Crescêncio, via 303101571 de saída; a entrada controlada "
        "463014795#0, índice 0, é Rotary Club. Não associar nomes distintos automaticamente.",
    ("A144", "A158", "C"):
        "B158 identifica Anselmo Alves dos Santos e corresponde à via 625668273#2, "
        "índices 0/1. Cabeçalho A144 Nascimento preservado como divergência de origem; "
        "não impede a identificação física explícita desta descrição.",
}
INTERSECTION_MAPPING_NOTES = {
    "A56": "Retenções auxiliares: 3386573305 rumo centro índices 0–3, "
            "3386573306 rumo BR050 índices 0/1 e 5494111603 saída BR050 índices 0/1. "
            "Falta comprovar seus grupos focais e coordenação; não vinculadas automaticamente ao estágio.",
    "A110": "Retenções auxiliares: 5494111596 saída rumo centro índices 0–3 e "
             "5494111597 entrada rumo BR050 índices 0–3. Falta comprovar seus grupos "
             "focais e coordenação; não vinculadas automaticamente ao estágio.",
    "A128": "A identifica o conjunto físico rumo centro 5494111590, incluindo a alça "
             "de índice 4; B identifica retas rumo BR050 5494111589/5494111594. "
             "Não comprova comando comum ou coordenação entre as retenções.",
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
    """Extrai a fonte imutável; não reconstrói permissões ou fases ausentes."""
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
                key = (f"A{heading}", f"A{description_row}", stage_id)
                binding = PHYSICAL_STAGE_LINKS.get(key)
                scope = "pedestrian" if cells[f"B{description_row}"].strip() == "Pedestres" else "vehicle"
                if scope == "pedestrian":
                    mapping_status = "NAO_APLICAVEL"
                    mapping_note = "Dados originais conservados; programação pedestre fora do escopo da V2 veicular."
                elif binding is None:
                    mapping_status = "DADO_EXTERNO_AUSENTE"
                    mapping_note = MAPPING_NOTES[key]
                else:
                    mapping_status = "CONFIRMADO" if key in CONFIRMED_BINDINGS else "INFERIVEL_COM_SEGURANCA"
                    mapping_note = MAPPING_NOTES.get(
                        key, "Cobertura física das aproximações descritas, determinada pela "
                        "topologia e identificação das vias; não define grupo focal, G/g, ordem ou transições."
                    )
                    if f"A{heading}" in INTERSECTION_MAPPING_NOTES:
                        mapping_note += " " + INTERSECTION_MAPPING_NOTES[f"A{heading}"]
                stages.append({
                    "stage_id": stage_id,
                    "movement": cells[f"B{description_row}"].strip(),
                    "scope": scope,
                    "mapping_status": mapping_status,
                    "mapping_note": mapping_note,
                    **timings,
                    "sumo_links": [{
                        "tls_id": tls_id,
                        "link_indices": list(indices),
                    } for tls_id, indices in binding] if binding is not None else None,
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
                "sumo_tls_ids": sorted(INTERSECTION_TLS_IDS[f"A{heading}"]),
                "operational": None,
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
        "schema_version": 2,
        "signal_profile": "settran",
        "status": "partial_external_data",
        "representation": "normalized_source_with_optional_operational_supplements",
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
            "sumo_links descreve cobertura física confirmada ou inferível; não define grupos focais, permissões, estados ou transições.",
            "sumo_tls_ids inventaria todos os TLS geográficos associados à interseção, inclusive auxiliares sem comando SETTRAN comprovado.",
            "stages.scope distingue descrições veiculares de pedestres; estas últimas são preservadas sem reconstrução nesta V2.",
            "operational é suplemento explícito por interseção/plano; null significa dados operacionais ainda ausentes.",
        ],
        "programs": programs,
        "schedule": None,
        "operational_day_start": None,
        "initial_plan_id": None,
        "blockers": [
            {"id": "missing_vehicle_permissions", "scope": "fixed_plan",
             "detail": "Falta matriz grupo/intervalo→movimentos, indicando proteção, permissão ou exclusão de cada conexão veicular."},
            {"id": "unconfirmed_transitions", "scope": "fixed_plan",
             "detail": "Falta ordem dos intervalos e quadro de continuidade/amarelo/limpeza entre grupos sobrepostos; a ordem das linhas não comprova a sequência."},
            {"id": "unconfirmed_offset_reference", "scope": "fixed_plan",
             "detail": "Falta evento de referência da defasagem, relógio/interseção de referência e sentido da contagem para convertê-la a SUMO."},
            {"id": "unconfirmed_auxiliary_control", "scope": "local_tls",
             "detail": "Porto Alegre, Niterói e João Naves: faltam grupos focais e coordenação das retenções auxiliares identificadas em mapping_note."},
            {"id": "rotary_stage_d_identity", "scope": "local_stage",
             "detail": MAPPING_NOTES[("A92", "A107", "D")]},
            {"id": "missing_schedule", "scope": "temporal_operation",
             "detail": "Faltam start_time, end_time, plan_id, weekdays e exceções aplicáveis por interseção; não bloqueia por si só um plano fixo explicitamente selecionado."},
            {"id": "missing_operational_day_start", "scope": "temporal_operation",
             "detail": "Falta marco oficial do relógio operacional; nenhum início do dia é presumido."},
        ],
        "anomalies": anomalies,
    }


def source_values(document):
    """Somente valores/células provenientes do XLSX, independentes do schema."""
    values = {}
    for program in document["programs"]:
        key = (program["intersection"], program["plan_id"])
        if key in values:
            raise ValueError("Artefato SETTRAN contém interseção/plano duplicado.")
        values[key] = {
            **{field: program[field] for field in (
                "intersection", "plan_id", "cycle_seconds", "offset_seconds", "source_cells"
            )},
            "stages": [{field: stage[field] for field in (
                "stage_id", "movement", *TIMING_FIELDS, "source_cells"
            )} for stage in program["stages"]],
        }
    return values


def preserve_supplements(document, previous):
    """Migra dados derivados sem apagar suplementos nem ocultar fonte alterada."""
    if previous["source"] != document["source"] or source_values(previous) != source_values(document):
        raise ValueError("Artefato SETTRAN altera valores/células da fonte; nenhuma informação foi sobrescrita.")
    previous_programs = {(p["intersection"], p["plan_id"]): p for p in previous["programs"]}
    for program in document["programs"]:
        prior = previous_programs[program["intersection"], program["plan_id"]]
        if prior.get("sumo_phases") is not None:
            raise ValueError("Artefato legado contém sumo_phases preenchido; migre esses dados para operational antes de regenerar.")
        program["operational"] = prior.get("operational")
    for field in ("schedule", "operational_day_start", "initial_plan_id"):
        if field in previous:
            document[field] = previous[field]
    return document


def validate_source_document(document):
    """Confere origem e mapeamentos; suplementos são validados na execução."""
    try:
        expected = preserve_supplements(normalize_source(SOURCE), document)
    except (OSError, KeyError, TypeError) as error:
        raise ValueError("Artefato SETTRAN está incompleto ou possui estrutura incompatível com a origem auditada.") from error
    if document != expected:
        raise ValueError("Artefato SETTRAN diverge da origem ou dos mapeamentos auditados; reaudite antes de executar.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="confere o JSON sem gravar arquivos")
    args = parser.parse_args(argv)
    try:
        document = normalize_source(SOURCE)
        previous = None
        if OUTPUT.exists():
            previous = json.loads(OUTPUT.read_text(encoding="utf-8"))
            document = preserve_supplements(document, previous)
        # A agenda é somente validada como dado; isto não habilita operação
        # temporal nem interfere na seleção deliberada de um plano fixo.
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from SistemaDeSemaforos.simulation.settran_configuration import validate_schedule
        schedule_status = validate_schedule(document)
        content = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
        if args.check:
            if previous != document:
                raise ValueError("settran_programs.json está ausente ou diverge da fonte auditada.")
        else:
            OUTPUT.write_text(content, encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Erro: {error}\n")
    print("SETTRAN: 36 planos e 128 descrições conferidos; suplementos explícitos preservados. "
          f"Agenda: {schedule_status}. Validação operacional por plano/TLS na execução.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
