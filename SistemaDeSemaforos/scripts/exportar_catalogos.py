"""Atualiza as tabelas CSV do cenário padrão e da instalação local."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from semaforos.relatorios.catalogos import export_catalogs
from semaforos.cenario.configuracao import read_config
from semaforos.relatorios.catalogos import sumo_options

if __name__ == "__main__":
    output = ROOT / "docs/catalogos"
    output.mkdir(parents=True, exist_ok=True)
    export_catalogs(output, read_config(ROOT / "config/cenario.json"))
    version, options = sumo_options()
    lines = ["# Catálogo completo do SUMO instalado", "", version, "",
             f"{len(options)} opções CLI. Gerado com scripts/exportar_catalogos.py, sem depender de um template XML estático.",
             "", "[CSV integral](catalogos/sumo_options.csv). As descrições originais e padrões vêm do executável instalado.",
             "Atributos de rede/vType e outras ferramentas possuem catálogos próprios.", ""]
    for category in dict.fromkeys(row["categoria"] for row in options):
        rows = [row for row in options if row["categoria"] == category]
        lines.extend([f"## {rows[0]['categoria em português']} ({category})", "",
                      "| Opção | Tipo | Padrão | Descrição SUMO |", "| --- | --- | --- | --- |"])
        for row in rows:
            values = [row[key].replace("|", "\\|").replace("\n", " ") for key in ("opção", "tipo", "padrão no template", "descrição SUMO")]
            lines.append("| " + " | ".join(values) + " |")
        lines.append("")
    (ROOT / "docs/catalogo_completo_sumo.md").write_text("\n".join(lines), encoding="utf-8")
    print(output)
