"""Gera o catálogo Markdown de todas as opções do sumo.exe instalado."""

import html
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "docs" / "modelo_todas_opcoes.sumocfg"
CONFIG = ROOT / "config" / "cenario.json"
OUTPUT = ROOT / "docs" / "catalogo_completo_sumo.md"

CATEGORIES = {
    "configuration": "Configuração",
    "input": "Entradas",
    "output": "Saídas",
    "time": "Tempo",
    "processing": "Processamento",
    "routing": "Roteamento",
    "report": "Relatórios",
    "emissions": "Emissões",
    "communication": "Comunicação",
    "battery": "Bateria",
    "example_device": "Dispositivo de exemplo",
    "ssm_device": "Segurança substituta (SSM)",
    "toc_device": "Transferência de controle (ToC)",
    "driver_state_device": "Estado do motorista",
    "bluelight_device": "Veículos de emergência",
    "fcd_device": "Dados de veículos flutuantes (FCD)",
    "elechybrid_device": "Veículos híbridos elétricos",
    "taxi_device": "Táxis",
    "glosa_device": "GLOSA",
    "tripinfo_device": "Informações de viagem",
    "vehroutes_device": "Rotas dos veículos",
    "friction_device": "Atrito",
    "fcd_replay_device": "Reprodução FCD",
    "traci_server": "Servidor TraCI",
    "mesoscopic": "Simulação mesoscópica",
    "random_number": "Aleatoriedade",
    "gui_only": "Interface gráfica",
}


def cell(value):
    return html.escape(str(value)).replace("|", "\\|").replace("\n", " ")


def aliases(option):
    names = option.attrib.get("synonymes", "").split()
    return ", ".join(f"`{'-' if len(name) == 1 else '--'}{name}`" for name in names) or "—"


def main():
    source = TEMPLATE.read_text(encoding="utf-8-sig")
    # O SUMO 1.27.1 escreve '--' dentro de alguns comentários XML; removê-los
    # permite ler os elementos e seus defaults sem alterar o arquivo de origem.
    root = ET.fromstring(re.sub(r"<!--.*?-->", "", source, flags=re.S))
    scenario = json.loads(CONFIG.read_text(encoding="utf-8"))
    network = (CONFIG.parent / scenario["network"]).resolve()
    light_id = scenario["targets"][0]["tls_id"]
    program = next(element for _, element in ET.iterparse(network, events=("end",))
                   if element.tag == "tlLogic" and element.attrib["id"] == light_id)
    phases = program.findall("phase")
    version = re.search(r"sumo (\d+\.\d+\.\d+)", source).group(1)
    total = sum(len(group) for group in root)

    lines = [
        "# Catálogo completo de opções do SUMO",
        "",
        "Este é o anexo técnico do [item 2: configurações-base](configuracoes_sumo.md). "
        "Comece pelo item 2 para entender o que o projeto configura hoje.",
        "",
        f"Catálogo completo das **{total} opções principais** do executável `sumo` {version} instalado neste projeto. "
        "A lista foi gerada do template de configuração produzido pelo próprio SUMO. "
        "Ela inclui opções que não são usadas pelo pipeline atual; algumas só fazem sentido com dispositivos, "
        "arquivos adicionais ou interface gráfica.",
        "",
        "Os nomes das opções e seus valores padrão são os da instalação, não recomendações de uso. "
        "`—` na coluna Padrão significa valor vazio. Aliases levam à mesma opção principal. "
        "O arquivo [opcoes_sumo_1.27.1.txt](opcoes_sumo_1.27.1.txt) traz a ajuda integral do executável, "
        "e [modelo_todas_opcoes.sumocfg](modelo_todas_opcoes.sumocfg) guarda o template original. "
        "A [documentação oficial de opções e arquivos de configuração]"
        "(https://sumo.dlr.de/docs/Basics/Using_the_Command_Line_Applications.html) "
        "explica como o SUMO lê esses valores.",
        "",
        "## Configuração-base carregada pelo projeto",
        "",
        "O pipeline lê `config/cenario.json`. Ele não usa um arquivo `.sumocfg` fixo: "
        "monta os argumentos da execução e inicia `sumo` por TraCI. A planilha é referência; "
        "`plan_id` não aplica automaticamente os tempos dela ao programa do SUMO.",
        "",
        "| Item | Valor atual |",
        "| --- | --- |",
        f"| Rede | `{cell(scenario['network'])}` |",
        f"| Planilha de referência | `{cell(scenario['plans'])}`; plano `{scenario['plan_id']}` |",
        f"| Duração | `{scenario['duration_seconds']}` s |",
        f"| Passo | `{scenario['step_seconds']}` s |",
        f"| Sementes | `{', '.join(map(str, scenario['seeds']))}` |",
        f"| Demanda de teste | `{scenario['demand']['mode']}`; "
        f"`{scenario['demand'].get('vehicles_per_hour', 'por fluxo')}` veículos/h |",
        f"| Semáforo selecionado | `{light_id}`; fases `{scenario['targets'][0]['phase_indices']}` |",
        "| Saídas | `tripinfo.xml`, `summary.xml`, `statistics.xml`, `metrics.json` |",
        "",
        f"### Programa-base de `{light_id}` na rede",
        "",
        f"Programa `{program.attrib.get('programID', '')}`, tipo `{program.attrib.get('type', '')}`, "
        f"defasagem `{program.attrib.get('offset', '0')}` s. "
        f"Ciclo atual `{sum(float(phase.attrib['duration']) for phase in phases):g}` s.",
        "",
        "| Fase | Estado SUMO | Categoria | Duração atual (s) | Treinada? |",
        "| ---: | --- | --- | ---: | --- |",
    ]
    selected = set(scenario["targets"][0]["phase_indices"])
    for index, phase in enumerate(phases):
        state = phase.attrib["state"]
        kind = "amarelo" if any(c in "yY" for c in state) else "verde" if any(c in "Gg" for c in state) else "totalmente vermelho"
        lines.append(f"| {index} | `{state}` | {kind} | {phase.attrib['duration']} | {'sim' if index in selected else 'não'} |")

    lines += [
        "",
        "O vermelho de um movimento também depende do tempo concedido aos demais movimentos. "
        "As fases totalmente vermelhas acima são intervalos de limpeza; "
        "o pipeline não define um tempo vermelho independente para cada via.",
        "",
        "### Opções passadas diretamente em cada execução",
        "",
        "| Opção SUMO | Origem do valor |",
        "| --- | --- |",
        "| `--net-file` | `network` em `config/cenario.json` |",
        "| `--route-files` | Rotas geradas pela etapa de demanda |",
        "| `--begin` | `0` s |",
        "| `--end` | `duration_seconds` |",
        "| `--step-length` | `step_seconds` |",
        "| `--seed` | Cada valor de `seeds` |",
        "| `--tripinfo-output` | `tripinfo.xml` da execução |",
        "| `--summary-output` | `summary.xml` da execução |",
        "| `--statistic-output` | `statistics.xml` da execução |",
        "| `--no-step-log` | `true` |",
        "",
        "TraCI estabelece a conexão com o SUMO. Durações candidatas são aplicadas "
        "ao programa semafórico durante a execução via `setProgramLogic`.",
        "",
        "### Comandos para carregar e consultar",
        "",
        "Execute na pasta `SistemaDeSemaforos`:",
        "",
        "```powershell",
        "python pipeline.py inspect",
        "python pipeline.py run --config config/cenario.json",
        "python pipeline.py train --config config/cenario.json",
        "python pipeline.py options",
        "```",
        "",
        "Para obter novamente o template completo do executável instalado:",
        "",
        "```powershell",
        "sumo --save-template docs/modelo_todas_opcoes.sumocfg --save-commented",
        "python scripts/gerar_catalogo_sumo.py",
        "```",
        "",
        "As opções de `randomTrips.py`, `netconvert` e outros executáveis têm catálogos próprios. "
        "Esta lista cobre **todas as opções principais de `sumo` desta versão**. "
        "Atributos internos dos arquivos de rede/rotas e métodos TraCI não são opções de linha de comando "
        "e não fazem parte deste catálogo.",
        "",
        "## Todas as opções de `sumo`",
        "",
        "Tipo e padrão vêm do template oficial gerado localmente. "
        "Os detalhes de cada opção estão na ajuda integral ligada no início deste documento. "
        "As 27 categorias abaixo preservam a divisão do próprio executável.",
        "",
        "| Tipo | Valor esperado |",
        "| --- | --- |",
        "| `BOOL` | verdadeiro ou falso |",
        "| `INT` | número inteiro |",
        "| `FLOAT` | número decimal |",
        "| `TIME` | duração ou instante de simulação |",
        "| `STR` | texto |",
        "| `STR[]` | lista de textos |",
        "| `FILE` | caminho de arquivo |",
        "",
        "| Categoria | Opções |",
        "| --- | ---: |",
    ]
    for group in root:
        lines.append(f"| {CATEGORIES.get(group.tag, group.tag)} (`{group.tag}`) | {len(group)} |")
    lines.append("")

    for group in root:
        lines += [f"### {CATEGORIES.get(group.tag, group.tag)} (`{group.tag}`)", "",
                  "| Opção | Alias | Tipo | Padrão |", "| --- | --- | --- | --- |"]
        for option in group:
            default = option.attrib.get("value", "")
            default_text = f"`{cell(default)}`" if default else "—"
            name = f"`--{option.tag}`"
            if option.attrib.get("deprecated"):
                name += " (possui alias obsoleto)"
            lines.append(f"| {name} | {aliases(option)} | `{cell(option.attrib.get('type', ''))}` | {default_text} |")
        lines.append("")

    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"{OUTPUT}: {total} opções em {len(root)} categorias")


if __name__ == "__main__":
    main()
