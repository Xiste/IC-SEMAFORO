"""Atualiza o catálogo a partir do SUMO instalado, código e schemas XML.

Entrada: instalação SUMO e catálogo curado existente. Saída: CSV conferível.
Uso: python3 scripts/audit_configuration_catalog.py [--check] [--probe-defaults].
O probe opcional usa TraCI somente em t=0, fora do pipeline experimental.
"""

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import inspect
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch
from urllib.request import urlopen
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from SistemaDeSemaforos.demand import random_demand_generator as generator
from SistemaDeSemaforos.simulation import episode_runner as runner
from SistemaDeSemaforos.metrics.sumo_output_configuration import prepare_outputs

CATALOG = ROOT / "docs" / "configuration_catalog.csv"
FIELDS = [
    "configuration_name", "interface", "category", "description", "data_type",
    "native_default", "current_core", "current_full", "value_origin", "source_file",
    "modifiable", "change_impact", "currently_used", "scientific_relevance",
    "aliases_or_elements", "constraints", "source_reference", "source_sha256",
    "sumo_version", "description_source", "notes",
]
XSD = "{http://www.w3.org/2001/XMLSchema}"
SCHEMA_ROOTS = ("net_file.xsd", "routes_file.xsd", "additional_file.xsd", "viewsettings_file.xsd")
PROBE_GETTERS = (
    "getAccel", "getActionStepLength", "getApparentDecel", "getBoardingDuration",
    "getColor", "getDecel", "getEmergencyDecel", "getEmissionClass", "getHeight",
    "getImpatience", "getImperfection", "getLateralAlignment", "getLength", "getMaxSpeed",
    "getMaxSpeedLat", "getMinGap", "getMinGapLat", "getPersonCapacity", "getScale",
    "getShapeClass", "getSpeedDeviation", "getSpeedFactor", "getTau", "getVehicleClass",
    "getWidth", "getMass",
)
DOC_PAGES = {
    "Networks/SUMO_Road_Networks.md": {"netType", "edgeType", "laneType", "junctionType", "requestType", "connectionType", "locationType", "roundaboutType"},
    "Definition_of_Vehicles,_Vehicle_Types,_and_Routes.md": {"vTypeType", "vehicleType", "vehicleRouteType", "tripType", "flowType", "flowWithoutIDType", "routeType", "stopType", "vTypeDistributionType", "routeDistributionType"},
    "Simulation/Traffic_Lights.md": {"tlLogicType", "tlLogicAdditionalType", "phaseType", "WAUTType", "wautSwitchType", "wautJunctionType"},
    "Simulation/Output/Lanearea_Detectors_(E2).md": {"e2DetectorType"},
    "Simulation/Output/Induction_Loops_Detectors_(E1).md": {"e1DetectorType", "instantInductionLoopType"},
    "Simulation/Output/Multi-Entry-Exit_Detectors_(E3).md": {"e3DetectorType", "detEntryType", "detExitType"},
    "Simulation/Output/Lane-_or_Edge-based_Traffic_Measures.md": {"meandataType"},
    "Simulation/Public_Transport.md": {"busStopType", "accessType"},
    "Simulation/ParkingArea.md": {"parkingAreaType", "parkingSpaceType"},
    "Simulation/Rerouter.md": {"rerouterType", "rerouterValuesType"},
    "Simulation/Variable_Speed_Signs.md": {"variableSpeedSignType", "stepType"},
    "Simulation/Calibrator.md": {"calibratorType"},
    "Models/Electric.md": {"chargingStationType"},
    "Models/ElectricHybrid.md": {"overheadWireSegmentType", "tractionSubstationType", "overheadWireClampType", "overheadWireType"},
    "Simulation/Pedestrians.md": {"personType", "personBaseType", "personFlowType", "walkType", "rideType", "personTripType"},
    "Simulation/GenericParameters.md": {"paramType"},
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def row(**values):
    return {key: str(values.get(key, "")) for key in FIELDS}


def tool_template(program):
    """O binário documenta opções sem iniciar a simulação."""
    binary = shutil.which(program)
    if binary is None:
        raise FileNotFoundError(f"{program} não encontrado no PATH")
    result = subprocess.run([binary, "--save-template", "-"], check=True,
                            capture_output=True, text=True)
    return binary, ET.fromstring(result.stdout)


def flatten_template(root):
    return {option.tag: (group.tag, option.attrib) for group in root for option in group}


def output_options(profile):
    """Reutiliza a configuração real da coleta, sem executar SUMO."""
    with tempfile.TemporaryDirectory(prefix="configuration-audit-") as temporary:
        directory = Path(temporary)
        (directory / "inputs").mkdir()
        signature = inspect.signature(prepare_outputs)
        arguments = {"profile": profile} if "profile" in signature.parameters else {}
        if "metrics_profile" in signature.parameters:
            arguments = {"metrics_profile": profile}
        command = prepare_outputs(directory, **arguments)
        options = {command[index][2:]: command[index + 1].replace(temporary, "<episode>")
                   for index in range(0, len(command), 2)}
        additional = ET.parse(directory / "inputs" / "observations.add.xml").getroot()
        definitions = defaultdict(lambda: defaultdict(set))
        for element in additional.iter():
            for name, value in element.attrib.items():
                definitions[element.tag][name].add(value.replace(temporary, "<episode>"))
        return options, definitions


def native_options(version, sumo_home):
    core, core_xml = output_options("core")
    full, full_xml = output_options("full")
    common = {"net-file": "<baseline>/network.net.xml", "route-files": "<episode>/inputs/random.rou.xml",
              "begin": "0", "no-step-log": "true", "aggregate-warnings": "5"}
    overrides = {"sumo": ({**common, **core}, {**common, **full}), "duarouter": ({
        "net-file": "<baseline>/network.net.xml", "route-files": "<temporary>/random.trips.xml",
        "output-file": "<temporary>/random.rou.xml; validação: <temporary>/random.trips.xml.tmp",
        "begin": "0", "end": "7200", "ignore-errors": "true", "no-warnings": "true",
        "no-step-log": "true", "alternatives-output": "NUL",
        "write-trips": "false no roteamento; true na validação",
    }, {})}
    rows = []
    for program in ("sumo", "duarouter"):
        binary, template = tool_template(program)
        options = flatten_template(template)
        if program == "sumo":
            _, gui_template = tool_template("sumo-gui")
            if options != flatten_template(gui_template):
                raise ValueError("sumo-gui diverge do sumo; catalogar diferenças antes de continuar")
        core_values, full_values = overrides[program]
        full_values = full_values or core_values
        for name, (category, definition) in options.items():
            default = definition.get("value", "")
            explicit = name in core_values or name in full_values
            diagnostic = category in {"output", "report", "gui_only", "configuration"}
            current_core, current_full = core_values.get(name, default), full_values.get(name, default)
            notes = "Descrição e default literais do template instalado; vazio significa valor não definido."
            if program == "sumo":
                notes += " Mesma opção disponível em sumo e sumo-gui."
            if name in {"start", "quit-on-end"} and program == "sumo":
                notes += " true quando --gui está habilitado; padrão headless mostrado nas colunas atuais."
            if name == "end" and program == "sumo":
                notes += " Runner aceita --end; sem override, termina após esvaziar a simulação."
            if explicit:
                used = "sim: override do pipeline"
            elif category.endswith("device") or name.startswith("device."):
                used = "condicional: somente quando dispositivo/modelo correspondente está ativo"
            elif category in {"mesoscopic", "traci_server", "gui_only"}:
                used = "não no baseline headless microscópico; capacidade disponível"
            elif default in {"", "false"}:
                used = "não habilitada; valor padrão preservado"
            else:
                used = "padrão carregado; efeito condicionado à descrição da opção"
            rows.append(row(
                configuration_name=f"{program}:{name}", interface=program, category=category,
                description=definition.get("help", ""), data_type=definition.get("type", ""),
                native_default=default, current_core=current_core, current_full=current_full,
                value_origin="override pipeline" if explicit else "default do binário instalado",
                source_file="SistemaDeSemaforos/simulation/episode_runner.py; SistemaDeSemaforos/metrics/sumo_output_configuration.py"
                if program == "sumo" else str(sumo_home / "tools/randomTrips.py"),
                modifiable="sim" if diagnostic else "condicional",
                change_impact="diagnóstico/armazenamento/interface; comparar custo e dados preservados"
                if diagnostic else "pode mudar resultados; declarar variante e validar antes de alterar baseline",
                currently_used=used, scientific_relevance="operacional" if diagnostic else "alta se recurso ativo",
                aliases_or_elements=definition.get("synonymes", ""), constraints=definition.get("deprecated", ""),
                source_reference=f"{program} --save-template -; https://sumo.dlr.de/docs/{program}.html",
                source_sha256=digest(binary), sumo_version=version, notes=notes,
            ))
    # randomTrips não reconhece '-' como stdout; usa arquivo temporário explícito.
    script = sumo_home / "tools/randomTrips.py"
    with tempfile.TemporaryDirectory(prefix="randomtrips-catalog-") as temporary:
        target = Path(temporary) / "options.xml"
        subprocess.run([sys.executable, str(script), "--save-template", str(target)], check=True)
        template = ET.parse(target).getroot()
    current = {"net-file": "<baseline>/network.net.xml", "output-trip-file": "<temporary>/random.trips.xml",
               "route-file": "<temporary>/random.rou.xml", "begin": "0", "end": str(generator.DEFAULT_DURATION),
               "period": str(generator.DEFAULT_PERIOD), "seed": "sorteio inteiro inclusivo [0, 2147483647] por episódio",
               "vehicle-class": "passenger", "validate": "true"}
    for option in template:
        name = option.tag
        rows.append(row(
            configuration_name=f"randomTrips:{name}", interface="randomTrips",
            category=option.get("category", "general"), description=option.get("help", ""),
            data_type=option.get("type", ""), native_default=option.get("value", ""),
            current_core=current.get(name, option.get("value", "")),
            current_full=current.get(name, option.get("value", "")),
            value_origin="override generator" if name in current else "default randomTrips",
            source_file="SistemaDeSemaforos/demand/random_demand_generator.py", modifiable="condicional",
            change_impact="pode alterar população/rotas/tempos; preservar seed e declarar variante de demanda",
            currently_used="sim: explícita" if name in current else "padrão; aplicabilidade depende da opção",
            scientific_relevance="alta para distribuição da demanda",
            constraints=f"required={option.get('required', 'false')}; separator={option.get('listSeparator', '')}",
            source_reference="https://sumo.dlr.de/docs/Tools/Trip.html; randomTrips.py --save-template",
            source_sha256=digest(script), sumo_version=version,
            notes="Default nativo não é default do projeto. Opções duarouter podem ser encaminhadas com prefixo duarouter.; marouter não usado.",
        ))
    return rows, core_xml, full_xml


def schemas(sumo_home):
    """Resolve includes, preservando cada declaração por classe, não por instância."""
    roots = {}
    def load(path):
        path = path.resolve()
        if path in roots:
            return
        roots[path] = ET.parse(path).getroot()
        for include in roots[path].findall(f"{XSD}include"):
            load(path.parent / include.get("schemaLocation"))
    for name in SCHEMA_ROOTS:
        load(sumo_home / "data/xsd" / name)
    return roots


def summarized(values):
    if not values:
        return "não explícito"
    if len(values) <= 6:
        return " | ".join(sorted(values))
    try:
        numbers = [float(value) for value in values]
        return f"{len(values)} valores distintos; mínimo={min(numbers)}; máximo={max(numbers)}"
    except ValueError:
        return f"{len(values)} valores distintos; definições completas no arquivo de origem"


def xml_options(version, sumo_home, core_xml, full_xml):
    roots = schemas(sumo_home)
    associations = defaultdict(set)
    for root in roots.values():
        for element in root.iter(f"{XSD}element"):
            if element.get("type"):
                associations[element.get("type")].add(element.get("name", ""))
    network = defaultdict(lambda: defaultdict(set))
    for element in ET.parse(generator.DEFAULT_NET_FILE).getroot().iter():
        for name, value in element.attrib.items():
            network[element.tag][name].add(value)
    # Contrato verificado nos XMLs gerados: valores variáveis permanecem nos
    # arquivos do episódio, não são confundidos com defaults estruturais.
    demand = {
        "vType": {"id": {"passenger"}, "vClass": {"passenger"}},
        "vehicle": {"id": {"identificador da viagem"}, "type": {"passenger"},
                    "depart": {"0 até <duration>, intervalo <period>"}},
        "trip": {"id": {"identificador da viagem"}, "type": {"passenger"},
                 "depart": {"0 até <duration>, intervalo <period>"},
                 "from": {"origem sorteada"}, "to": {"destino sorteado"}},
        "route": {"edges": {"sequência calculada por duarouter; variável por viagem"}},
    }
    rows = []
    for path, root in sorted(roots.items()):
        parents = {child: parent for parent in root.iter() for child in parent}
        for attribute in root.iter(f"{XSD}attribute"):
            name = attribute.get("name")
            if not name:
                raise ValueError(f"Resolver atributo ref antes de catalogar: {path}")
            cursor, labels, type_name = parents[attribute], [], ""
            while cursor is not root:
                if cursor.get("name") and cursor.tag in {f"{XSD}complexType", f"{XSD}element"}:
                    labels.append(cursor.get("name"))
                    if cursor.tag == f"{XSD}complexType":
                        type_name = type_name or cursor.get("name")
                cursor = parents[cursor]
            owner = ".".join(reversed(labels))
            aliases = associations[type_name] if type_name else {labels[0]}
            core_values, full_values = set(), set()
            is_network = False
            is_demand = False
            for alias in aliases:
                values = network.get(alias, {}).get(name, set())
                is_network = is_network or alias in network
                generated = demand.get(alias, {}).get(name, set())
                is_demand = is_demand or bool(generated)
                core_values.update(values | generated | core_xml.get(alias, {}).get(name, set()))
                full_values.update(values | generated | full_xml.get(alias, {}).get(name, set()))
            structural = is_network and not any(alias in {"tlLogic", "phase", "param"} for alias in aliases)
            category = "network" if is_network else "demand" if path.name == "route.xsd" else "additional_or_gui"
            default = attribute.get("default", attribute.get("fixed", "não declarado no XSD"))
            constraints = [f"use={attribute.get('use', 'optional')}"]
            constraints += [f"{child.tag.split('}')[-1]}={child.get('value')}"
                            for child in attribute.iter() if child.get("value") is not None]
            rows.append(row(
                configuration_name=f"xml:{path.name}:{owner}.{name}", interface="xml", category=category,
                description=f"Atributo {name} da definição {owner}; consultar contrato e tipos no schema indicado.",
                data_type=attribute.get("type", "simpleType inline; ver constraints/schema"),
                native_default=default, current_core=summarized(core_values), current_full=summarized(full_values),
                value_origin="XML estrutural" if is_network else "XML gerado pela demanda" if is_demand else "XML de instrumentação" if core_values or full_values else "capacidade do schema; ausente ou herdada",
                source_file=str(generator.DEFAULT_NET_FILE.relative_to(ROOT)) if is_network
                else "<episode>/inputs/observations.add.xml ou random.rou.xml; ausência não equivale a zero",
                modifiable="não" if structural else "condicional",
                change_impact="muda cenário; não alterar no baseline Rondon Norte"
                if structural else "validar aplicação; sinal/demanda pode mudar dinâmica; instrumentação muda observabilidade",
                currently_used="sim: explícita" if core_values else "apenas full" if full_values else "não explícita; verificar default/contexto",
                scientific_relevance="alta: cenário/controlador" if is_network else "condicional ao elemento/modelo",
                aliases_or_elements=" | ".join(sorted(aliases)), constraints="; ".join(constraints),
                source_reference=f"https://sumo.dlr.de/xsd/{path.relative_to(sumo_home / 'data/xsd')}",
                source_sha256=digest(path), sumo_version=version,
                notes="Sem default XSD não significa zero. Tipos de veículo/modelos podem definir defaults em runtime. Herança extension aplica os atributos da classe base; IDs/geometrias individuais permanecem no XML.",
            ))
    return rows


def clarify_context(rows):
    """Explica campos estruturais/operacionais que não têm tabela própria."""
    descriptions = {
        "id": "Identificador único no domínio do elemento; referências entre arquivos dependem dele.",
        "key": "Nome de um parâmetro genérico; sua interpretação depende do dispositivo/modelo que o lê.",
        "value": "Valor do parâmetro genérico; tipo e efeito dependem da chave e do modelo consumidor.",
        "disallow": "Classes de veículos proibidas; restringe quais veículos podem utilizar a via/faixa.",
        "allow": "Classes de veículos permitidas; afeta acesso, roteamento e conectividade.",
        "numLanes": "Quantidade de faixas do tipo/definição de via. Não substitui as faixas explícitas da rede compilada.",
        "oneway": "Indicação de sentido único na definição do tipo de via; a rede compilada conserva seus sentidos explícitos.",
        "priority": "Prioridade relativa de passagem da via/tipo; participa das regras dos cruzamentos.",
        "speed": "Limite de velocidade do tipo/via/faixa em m/s; não é velocidade observada dos veículos.",
        "width": "Largura física em metros; ausência segue regras da classe, não significa zero.",
        "shape": "Sequência de pontos da geometria no sistema de coordenadas da rede; define o traçado do elemento.",
        "spreadType": "Regra usada para posicionar as faixas em relação à geometria de referência da via.",
        "fringe": "Classificação do nó como interno ao cenário ou fronteira; auxilia seleção/interpretação de demanda.",
        "visibility": "Distância de visibilidade da conexão em metros; pode influenciar aproximação e decisão de passagem.",
        "acceleration": "Marca faixa de aceleração; influencia as regras de aceleração na conexão/faixa.",
        "version": "Versão do formato da rede XML, distinta da versão do executável SUMO.",
        "avoidOverlap": "Metadado de construção para evitar sobreposição de geometria; não reconstrói a rede durante run.",
        "junctionCornerDetail": "Detalhamento de pontos dos cantos dos cruzamentos usado na construção da geometria.",
        "limitTurnSpeed": "Fator de limitação de velocidade em curvas usado na construção das conexões internas.",
        "edges": "Lista ordenada de vias referenciadas pelo elemento; em rotas determina o percurso.",
        "nodes": "Lista de nós que integram a estrutura, por exemplo uma rotatória.",
        "dest": "Arquivo de destino do evento/observador; controla persistência, não a política semafórica.",
    }
    project_descriptions = {
        "episodes": "Quantidade de episódios independentes e sequenciais a executar.",
        "gui": "Seleciona sumo-gui, com início e encerramento automáticos por episódio.",
        "net-file": "Arquivo de rede de entrada; trocar este arquivo muda a definição do cenário.",
        "output-dir": "Diretório de destino; runner exige localização sob outputs/outputs-random.",
        "duration": "Duração da janela de geração de partidas, em segundos; não limita o término da simulação.",
        "period": "Intervalo entre partidas solicitadas, em segundos; duração/período define a demanda prevista.",
        "end": "Instante limite de tempo simulado, em segundos; ausência permite esgotamento natural da demanda.",
        "seed": "Seed da geração random; ausência sorteia um inteiro. É distinta da seed interna do SUMO.",
    }
    for entry in rows:
        name = entry["configuration_name"].rsplit(".", 1)[-1]
        if entry["interface"] == "project" and name in project_descriptions:
            entry["description"] = project_descriptions[name]
        if entry["interface"] != "xml" or not entry["description"].startswith("Atributo "):
            continue
        owner = entry["configuration_name"].split(":", 2)[2].split(".")[0]
        if owner == "tripType" and name in {"from", "to", "id"}:
            entry["description"] = {
                "from": "Via de origem da viagem; sorteada por randomTrips antes do cálculo da rota.",
                "to": "Via de destino da viagem; sorteada por randomTrips e verificada pelo roteador.",
                "id": "Identificador único da viagem; relaciona solicitação, veículo roteado e resultados.",
            }[name]
            entry["description_source"] = "contrato randomTrips/duarouter e routes_file.xsd"
        if name in descriptions and owner not in {"vehicleType", "tripType", "flowType", "stopType"}:
            entry["description"] = descriptions[name]
            entry["description_source"] = "curadoria contextual; schema e documentação SUMO indicados na linha"
        if name == "type":
            entry["description"] = {
                "timedEventType": "Tipo de observação/evento. SaveTLSStates grava os estados semafóricos a cada passo.",
                "junctionType": "Regra do nó: prioridade, semáforo, mão direita, nó interno ou fim de via.",
                "edgeType": "Referência à categoria de via declarada em type; agrupa permissões e padrões de construção.",
            }.get(owner, f"Seleciona a variante/categoria de {owner}; o significado é específico deste domínio XML.")


def project_options(version):
    """Captura apenas a construção do argparse real; main não chega à execução."""
    class ParserCaptured(Exception):
        pass
    result = []
    for name, module in (("runner", runner), ("generator", generator)):
        holder = []
        def capture(parser, *args, **kwargs):
            holder.append(parser)
            raise ParserCaptured()
        try:
            with patch.object(argparse.ArgumentParser, "parse_args", capture):
                module.main([])
        except ParserCaptured:
            pass
        for action in holder[0]._actions:
            if action.dest == "help":
                continue
            option = next(value[2:] for value in action.option_strings if value.startswith("--"))
            default = action.default
            if isinstance(default, Path) and default.is_relative_to(ROOT):
                default = str(default.relative_to(ROOT))
            result.append(row(
                configuration_name=f"project:{name}.{option}", interface="project", category=name,
                description=action.help or f"Parâmetro público {option}; ver docs/GUIA_DE_EXECUCAO_E_TESTES.md e função {name}.main.",
                data_type=getattr(action.type, "__name__", "bool" if isinstance(default, bool) else type(default).__name__),
                native_default=default, current_core=default, current_full="full" if option == "metrics-profile" else default,
                value_origin="argparse do código atual", source_file=str(Path(module.__file__).relative_to(ROOT)),
                modifiable="sim" if option in {"episodes", "gui", "output-dir", "metrics-profile"} else "condicional",
                change_impact="operação/observabilidade" if option in {"episodes", "gui", "output-dir", "metrics-profile"}
                else "altera condições do episódio; registrar e comparar como variante",
                currently_used="sim", scientific_relevance="alta para rastreabilidade",
                aliases_or_elements=" ".join(action.option_strings), constraints=f"choices={action.choices}",
                source_reference="docs/GUIA_DE_EXECUCAO_E_TESTES.md", source_sha256=digest(module.__file__), sumo_version=version,
                notes="None indica ausência de override. Seed do gerador é distinta da seed interna do SUMO.",
            ))
    return result


def probe_defaults(version, sumo_home):
    """Consulta defaults embutidos em t=0; não avança nem insere veículos."""
    sys.path.insert(0, str(sumo_home / "tools"))
    import traci
    result = []
    with tempfile.TemporaryDirectory(prefix="sumo-type-audit-") as temporary:
        connection = None
        try:
            traci.start(["sumo", "--net-file", str(generator.DEFAULT_NET_FILE), "--no-step-log", "true",
                         "--log", str(Path(temporary) / "sumo.log")],
                        label="configuration_audit", stdout=subprocess.DEVNULL)
            connection = traci.getConnection("configuration_audit")
            assert connection.simulation.getTime() == 0
            for type_id in sorted(connection.vehicletype.getIDList()):
                for getter in PROBE_GETTERS:
                    method = getattr(connection.vehicletype, getter)
                    value = method(type_id)
                    encoded = json.dumps(value, ensure_ascii=False)
                    result.append(row(
                        configuration_name=f"builtin:{type_id}.{getter}", interface="builtin_vtype",
                        category="passenger_baseline" if type_id == "DEFAULT_VEHTYPE" else "other_vehicle_classes",
                        description=" ".join((method.__doc__ or getter).split()),
                        data_type=type(value).__name__, native_default=encoded,
                        current_core=encoded if type_id == "DEFAULT_VEHTYPE" else "não instanciado pela demanda random",
                        current_full=encoded if type_id == "DEFAULT_VEHTYPE" else "não instanciado pela demanda random",
                        value_origin="probe SUMO em t=0; read-only; sem veículo/step",
                        source_file="default embutido; randomTrips define somente vClass=passenger",
                        modifiable="condicional", change_impact="comportamento/população/modelo; nova variante experimental",
                        currently_used="default de referência para passenger" if type_id == "DEFAULT_VEHTYPE" else "não",
                        scientific_relevance="alta" if type_id == "DEFAULT_VEHTYPE" else "catálogo de capacidade",
                        source_reference=f"traci.vehicletype.{getter}; https://sumo.dlr.de/docs/TraCI/VehicleType_Value_Retrieval.html",
                        source_sha256=digest(shutil.which("sumo")), sumo_version=version,
                        notes="TraCI é usado apenas nesta auditoria opcional, nunca no runner de produção. Não representa distribuição individual de veículos nem todos parâmetros internos do modelo.",
                    ))
            omitted_width = [lane.get("id") for lane in ET.parse(generator.DEFAULT_NET_FILE).getroot().iter("lane")
                             if lane.get("width") is None]
            widths = sorted({connection.lane.getWidth(identifier) for identifier in omitted_width})
            result.append(row(
                configuration_name="builtin:network.omitted_lane_width", interface="builtin_network",
                category="network", description="Larguras efetivas das faixas que omitem width no XML; consulta em t=0.",
                data_type="float[]", native_default=json.dumps(widths), current_core=json.dumps(widths), current_full=json.dumps(widths),
                value_origin="probe SUMO t=0; todas as faixas sem width explícito", source_file=str(generator.DEFAULT_NET_FILE.relative_to(ROOT)),
                modifiable="não", change_impact="largura é parte do cenário; não mudar para otimizar execução",
                currently_used="sim", scientific_relevance="alta: geometria física", source_reference="traci.lane.getWidth; rede original",
                source_sha256=digest(generator.DEFAULT_NET_FILE), sumo_version=version,
                notes=f"{len(omitted_width)} faixas verificadas; unidade m; sem avanço de simulação.",
            ))
        finally:
            if connection is not None:
                connection.close()
    return result


def refresh_descriptions(rows, version):
    """Enriquece atributos por tabelas oficiais da mesma tag de release."""
    release = "v" + version.rsplit(" ", 1)[1].replace(".", "_")
    base = f"https://raw.githubusercontent.com/eclipse-sumo/sumo/{release}/docs/web/docs/"
    updated = 0
    def plain(value):
        value = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", value)
        return re.sub(r"<[^>]+>|[*`]", "", value).strip().replace("\\", "")
    for page, types in DOC_PAGES.items():
        url = base + page
        source = urlopen(url, timeout=30).read().decode("utf-8")
        table, heading, attributes = None, "", defaultdict(list)
        for line_number, line in enumerate(source.splitlines(), 1):
            if line.startswith("#"):
                heading = line.lstrip("# ")
            if line.count("|") < 2:
                table = None
                continue
            cells = [plain(cell) for cell in re.split(r"(?<!\\)\|", line.strip("|"))]
            if "Description" in cells and any("Name" in cell or "Attribute" in cell for cell in cells):
                table = cells
                continue
            if table is None or len(cells) != len(table):
                continue
            attribute_name = cells[0].split(" (")[0]
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", attribute_name):
                continue
            description = cells[table.index("Description")]
            default = cells[table.index("Default")] if "Default" in table else ""
            attributes[attribute_name].append((heading, description, default, line_number))
        for entry in rows:
            if entry["interface"] != "xml":
                continue
            owner = entry["configuration_name"].split(":", 2)[2].split(".", 1)[0]
            name = entry["configuration_name"].rsplit(".", 1)[1]
            if owner not in types or name not in attributes:
                continue
            candidates = attributes[name]
            # Ambiguidades de id/type e atributos partilhados não são resolvidas
            # por posição na página. Só usa tabela com contexto correspondente.
            hints = {"laneType": "Lanes", "edgeType": "Edges", "junctionType": "Junction",
                     "connectionType": "Connections", "requestType": "Requests", "locationType": "Coordinates",
                     "vTypeType": "vType", "vehicleType": "Vehicle attributes", "routeType": "Routes",
                     "stopType": "Stops", "flowType": "Flows", "flowWithoutIDType": "Flows"}
            hint = hints.get(owner)
            matching = [item for item in candidates if hint and hint.casefold() in item[0].casefold()]
            if matching:
                candidates = matching
            elif len({item[1] for item in candidates}) > 1:
                continue
            heading, description, default, number = candidates[0]
            entry["description"] = description
            entry["description_source"] = url + f"#L{number}"
            if default and entry["native_default"] == "não declarado no XSD":
                entry["native_default"] = f"documentação ({heading}): {default}; condicionado à classe/modelo"
            entry["notes"] = ("Descrição revisada contra tabela oficial versionada. "
                              "Defaults documentais podem depender de classe/modelo; defaults medidos de passenger estão em builtin:DEFAULT_VEHTYPE. "
                              "Herança extension aplica atributos da classe base; ausência XML não equivale a zero.")
            updated += 1
    print(f"Descrições XML atualizadas de tabelas oficiais: {updated}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Compara com CSV sem gravar")
    parser.add_argument("--probe-defaults", action="store_true", help="Revalida 26 getters dos tipos embutidos em t=0")
    parser.add_argument("--refresh-descriptions", action="store_true", help="Consulta tabelas da documentação oficial versionada")
    args = parser.parse_args()
    sumo_home = Path(os.environ.get("SUMO_HOME", "/usr/share/sumo"))
    version = subprocess.run(["sumo", "--version"], check=True, capture_output=True, text=True).stdout.splitlines()[0]
    previous = {}
    if CATALOG.exists():
        with CATALOG.open(newline="", encoding="utf-8") as stream:
            previous = {entry["configuration_name"]: entry for entry in csv.DictReader(stream)}
    rows, core_xml, full_xml = native_options(version, sumo_home)
    rows += xml_options(version, sumo_home, core_xml, full_xml) + project_options(version)
    rows += probe_defaults(version, sumo_home) if args.probe_defaults else [
        old for old in previous.values() if old["interface"] in {"builtin_vtype", "builtin_network"} and old["sumo_version"] == version
    ]
    # Texto curado não deve desaparecer ao atualizar valores extraídos. É aceito
    # somente se o contrato XML não mudou (mesmo hash do schema e versão SUMO).
    for entry in rows:
        old = previous.get(entry["configuration_name"], {})
        if (entry["interface"] == "xml" and old.get("source_sha256") == entry["source_sha256"]
                and old.get("sumo_version") == version and "Descrição revisada" in old.get("notes", "")):
            for field in ("description", "description_source", "notes"):
                entry[field] = old[field]
            if entry["native_default"] == "não declarado no XSD":
                entry["native_default"] = old["native_default"]
    if args.refresh_descriptions:
        refresh_descriptions(rows, version)
    clarify_context(rows)
    rows.sort(key=lambda entry: entry["configuration_name"])
    names = [entry["configuration_name"] for entry in rows]
    if len(names) != len(set(names)):
        raise ValueError("Chaves duplicadas no catálogo")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    rendered = stream.getvalue()
    if args.check:
        if not CATALOG.exists() or CATALOG.read_text(encoding="utf-8") != rendered:
            raise SystemExit("Catálogo desatualizado: execute scripts/audit_configuration_catalog.py e revise as diferenças.")
    else:
        CATALOG.parent.mkdir(exist_ok=True)
        CATALOG.write_text(rendered, encoding="utf-8")
    print(json.dumps({"rows": len(rows), "interfaces": Counter(entry["interface"] for entry in rows),
                      "sumo_version": version, "mode": "check" if args.check else "write"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
