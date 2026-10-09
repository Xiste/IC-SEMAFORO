"""Corrige somente a infraestrutura comprovada da rede-base.

Uso: python3 scripts/correct_signal_infrastructure.py [--check].
Aproximações, faixas, retenções e conflitos são recalculados pelo netconvert 1.27.1.
Somente o delta local é incorporado. Nenhum plano SETTRAN é criado aqui.
Ajusta vínculos físicos de sinais e travessias com base nas evidências disponíveis.
Com --check, verifica a rede existente sem aplicar alterações ao arquivo.
"""

import argparse
import hashlib
import math
from pathlib import Path
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
NETWORK = ROOT / "SistemaDeSemaforos/network/uberlandia.vehicular.families.16_2_4.net.xml"
SOURCE_SHA256 = "46e7c4a4627cd511d419c01f15d65f66724941ac83360c4fc424b86626a5c10b"
LEGACY_SHA256 = "645b5fb5d8cf361d0345f2acf0d44e1c9c1f470caef49768e469e6faa6d81291"
FOUNDATION_SHA256 = "2bf6f012fdf86ecd122be6601f1eae2bd0d3907526f4e5aff3bcd0f3f0eaeb2d"
CORRECTED_SHA256 = "f30b0807fa46e3d4fb65c573be68f6544d75a64e44a2c32fee71389fd4106d56"

# Controles da revisão intermediária auditada, antes de completar a geometria.
# TLS, junctions, entradas externas, número de controlledLinks.
CORRECTIONS = (
    ("FAM_RONDON_BENJAMIM", ("338660524", "3050804948", "7963074868"),
     ("1156717163#3", "152937136#3", "666324302#6", "853751181#1"), 10),
    ("FAM_CESARIO_PARANA", ("339114019", "7963056110", "7963056109"),
     ("154252437#1", "602306713#21", "665897556#1"), 5),
    ("FAM_RONDON_BELEM", ("1561880261", "338685838"),
     ("331577750#1", "576876311#3", "965367673#1"), 10),
    ("FAM_RONDON_ANSELMO", ("2651934389", "2783757296"),
     ("576014296#2", "462991286"), 8),
    ("FAM_RONDON_PORTO_ALEGRE", ("339121007", "2042691678"),
     ("299471494#2", "30664532#3", "331577748#4"), 10),
    ("FAM_RONDON_NITEROI", ("338686240", "597213618"),
     ("30622933#12", "930831032#1", "931572689"), 13),
    ("FAM_RONDON_BATALHAO_7962385968", ("7962385968",), ("331577749#0",), 4),
    ("FAM_RONDON_BATALHAO_7962499397", ("7962499397",), ("1156717173#3",), 2),
)
SPECIAL_TLS = {"FAM_RONDON_BATALHAO_7962385968", "FAM_RONDON_BATALHAO_7962499397"}
REMOVED_TLS = "5494111602"
RECALCULATED_EDGES = {
    "1171563461", "292932042#0", "462991286", "462991287",
    ":2651934389_5", ":2651934389_6", ":2783757296_3", ":2783757296_5",
    ":3050761411_0", ":597213583_0", ":597213583_2",
    "853694507", "-853694507", ":7962385968_4", ":7962385968_5",
    ":7962385968_7", ":7962499397_2", ":7962499397_3", ":7962499397_4",
}
RECALCULATED_NODES = {"597213583", "2783757296"}
RECONNECTED_EDGES = {"1171563461", "462991286", ":597213583_2", ":2783757296_5"}


def _digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _blocks(text, tag):
    pattern = rf'    <{tag}(?=[ \t>])[^\n]*?(?:/>[ \t]*\n|>[ \t]*\n.*?    </{tag}>[ \t]*\n)'
    return list(re.finditer(pattern, text, re.S))


def _key(element):
    if element.tag == "connection":
        return tuple(element.get(field) for field in ("from", "to", "fromLane", "toLane"))
    if element.tag == "roundabout":
        return tuple(element.get("edges").split())
    return element.get("id")


def _indexed(text, tag):
    return {_key(ET.fromstring(match.group())): match.group() for match in _blocks(text, tag)}


def _semantic(block):
    element = ET.fromstring(block)
    element.tail = None
    return ET.tostring(element)


def source_network_text(text):
    """Aceita a fonte auditada ou migra a primeira correção, conferida por hash."""
    if _digest(text) == LEGACY_SHA256:
        tls_ids = {item[0] for item in CORRECTIONS} - SPECIAL_TLS
        for match in reversed(_blocks(text, "tlLogic")):
            if ET.fromstring(match.group()).get("id") in tls_ids:
                text = text[:match.start()] + text[match.end():]
        for tls_id in tls_ids:
            text = re.sub(rf' tl="{tls_id}" linkIndex="[0-9]+"', "", text)
        nodes = {node for _, group, _, _ in CORRECTIONS for node in group}
        for node in nodes:
            text = re.sub(rf'(<junction id="{node}" type=")traffic_light(\")',
                          r'\g<1>priority\2', text)
    if _digest(text) != SOURCE_SHA256:
        raise ValueError("A rede difere das revisões auditadas; nenhuma alteração foi aplicada.")
    return text


def _physical_delta(source):
    """O roundtrip separa mudanças locais das atualizações heurísticas do SUMO."""
    with tempfile.TemporaryDirectory(prefix="signal-infrastructure-") as directory:
        work = Path(directory)
        (work / "source.net.xml").write_text(source, encoding="utf-8")
        (work / "patch.edg.xml").write_text(
            '<edges><edge id="462991286" numLanes="3" speed="16.67"/>'
            '<edge id="853694507" allow="emergency"/>'
            '<edge id="-853694507" allow="emergency"/></edges>', encoding="utf-8")
        # As duas conexões do ramo direito são mantidas; três faixas seguem retas.
        connections = [
            '<delete from="1171563461" to="462991286"/>',
            '<delete from="462991286" to="46711471#0"/>',
            '<connection from="1171563461" to="292932042#0" fromLane="0" toLane="0"/>',
            '<connection from="1171563461" to="292932042#0" fromLane="1" toLane="1"/>',
        ]
        for lane in range(3):
            connections.extend([
                f'<connection from="1171563461" to="462991286" fromLane="{lane + 1}" toLane="{lane}"/>',
                f'<connection from="462991286" to="46711471#0" fromLane="{lane}" toLane="{lane + 1}"/>',
            ])
        (work / "patch.con.xml").write_text(
            '<connections>' + ''.join(connections) + '</connections>', encoding="utf-8")
        for name, patches in (("roundtrip", []), ("patched", [
                "--edge-files", str(work / "patch.edg.xml"),
                "--connection-files", str(work / "patch.con.xml")])):
            command = ["netconvert", "--sumo-net-file", str(work / "source.net.xml"),
                       "--output-file", str(work / f"{name}.net.xml"), "--no-warnings", "true"]
            subprocess.run(command + patches, check=True, capture_output=True, text=True)
        before = (work / "roundtrip.net.xml").read_text(encoding="utf-8")
        after = (work / "patched.net.xml").read_text(encoding="utf-8")

    changed = {}
    for tag, allowed in (("edge", RECALCULATED_EDGES), ("junction", RECALCULATED_NODES),
                         ("connection", None), ("tlLogic", set())):
        old, new = _indexed(before, tag), _indexed(after, tag)
        keys = {key for key in old.keys() | new.keys()
                if key not in old or key not in new or _semantic(old[key]) != _semantic(new[key])}
        if tag == "connection":
            if any(key[0] not in RECONNECTED_EDGES for key in keys):
                raise ValueError("netconvert alterou connections fora do recorte comprovado.")
        elif keys != allowed:
            raise ValueError(f"Delta inesperado de {tag}; conferir netconvert 1.27.1.")
        changed[tag] = keys

    result = source
    for tag in ("edge", "junction"):
        original, rebuilt = _indexed(result, tag), _indexed(after, tag)
        for key in changed[tag]:
            result = result.replace(original[key], rebuilt[key].replace('/>', ' />'), 1)
    rebuilt_connections = _indexed(after, "connection")
    for approach in sorted(RECONNECTED_EDGES):
        replacements = ''.join(block.replace('/>', ' />') for key, block in rebuilt_connections.items()
                               if key[0] == approach)
        matches = [match for match in _blocks(result, "connection")
                   if ET.fromstring(match.group()).get("from") == approach]
        for match in reversed(matches[1:]):
            result = result[:match.start()] + result[match.end():]
        first = matches[0]
        result = result[:first.start()] + replacements + result[first.end():]
    return result


def _control_infrastructure(text):
    # Porto tinha duas representações da mesma retenção, sem ramificação entre elas.
    for match in _blocks(text, "tlLogic"):
        if ET.fromstring(match.group()).get("id") == REMOVED_TLS:
            text = text[:match.start()] + text[match.end():]
            break
    text = re.sub(rf'(<junction id="{REMOVED_TLS}" type=")traffic_light(\")',
                  r'\g<1>priority\2', text)

    def remove_duplicate(match):
        if ET.fromstring(match.group()).get("tl") != REMOVED_TLS:
            return match.group()
        return re.sub(r' tl="[^"]+" linkIndex="[0-9]+"', '', match.group()).replace('state="O"', 'state="M"')
    text = re.sub(r'<connection [^\n]+ />', remove_duplicate, text)

    root = ET.fromstring(text)
    edges = {edge.get("id"): edge for edge in root.findall("edge")}
    assignments, programs, controlled_nodes = {}, [], set()
    for tls_id, nodes, approaches, expected in CORRECTIONS:
        links = [connection for connection in root.findall("connection")
                 if connection.get("from") in approaches
                 and edges[connection.get("from")].get("to") in nodes
                 and (tls_id not in SPECIAL_TLS or connection.get("dir") == "s")]
        if len(links) != expected or any(link.get("tl") is not None or
                                       link.get("state") not in {"M", "m"} for link in links):
            raise ValueError(f"Connections/prioridades divergem da auditoria: {tls_id}.")
        for index, link in enumerate(links):
            assignments[_key(link)] = (tls_id, index)
        # Batalhão fica aberto no regime normal. Comando de emergência é futuro.
        states = ''.join('G' if tls_id in SPECIAL_TLS else
                         ('O' if link.get("state") == 'M' else 'o') for link in links)
        programs.append(f'    <tlLogic id="{tls_id}" type="static" programID="current" offset="0">\n'
                        f'        <phase duration="1" state="{states}" />\n    </tlLogic>\n')
        controlled_nodes.update(nodes)

    def assign(match):
        key = _key(ET.fromstring(match.group()))
        if key not in assignments:
            return match.group()
        tls_id, index = assignments.pop(key)
        return match.group()[:-3] + f' tl="{tls_id}" linkIndex="{index}" />'
    text = re.sub(r'<connection [^\n]+ />', assign, text)
    if assignments:
        raise ValueError("Layout de connections diverge da rede auditada.")
    for node in controlled_nodes:
        text, count = re.subn(rf'(<junction id="{node}" type=")priority(\")',
                             r'\g<1>traffic_light\2', text)
        if count != 1:
            raise ValueError(f"Junction diverge da rede auditada: {node}.")
    insertion = text.index("    <tlLogic ")
    return text[:insertion] + ''.join(programs) + text[insertion:]


def _apply_local_patch(source, patches, options=()):
    """Incorpora o delta da correção, preservando o restante da rede auditada.

    O mesmo roundtrip, com as mesmas opções, elimina do delta as atualizações
    globais do importador. Connections são substituídas por aproximação inteira:
    sua ordem também participa da construção dos conflitos pelo SUMO.
    """
    with tempfile.TemporaryDirectory(prefix="signal-local-patch-") as directory:
        work = Path(directory)
        (work / "source.net.xml").write_text(source, encoding="utf-8")
        arguments = []
        for kind, xml in patches.items():
            file = work / f"patch.{kind}.xml"
            file.write_text(xml, encoding="utf-8")
            arguments.extend([{"nod": "--node-files", "edg": "--edge-files",
                              "con": "--connection-files", "tll": "--tllogic-files"}[kind],
                              str(file)])
        for name, extra in (("before", []), ("after", arguments)):
            command = ["netconvert", "--sumo-net-file", str(work / "source.net.xml"),
                       "--output-file", str(work / f"{name}.net.xml"),
                       "--internal-junctions.vehicle-width", "2.5", *options, *extra]
            subprocess.run(command, check=True, capture_output=True, text=True)
        before = (work / "before.net.xml").read_text(encoding="utf-8")
        after = (work / "after.net.xml").read_text(encoding="utf-8")

    # O importador pode gerar walkingareas globais quando a fonte contém zebras.
    # Conserva somente os caminhos pedonais dos crossings físicos existentes ou
    # declarados neste patch; a geometria veicular continua no delta normal.
    pedestrian_nodes = set()
    for text in (source,):
        for edge in ET.fromstring(text).findall('edge'):
            if edge.get('function') == 'crossing':
                pedestrian_nodes.add(edge.get('id')[1:].rsplit('_c', 1)[0])
    if 'con' in patches:
        pedestrian_nodes.update(c.get('node') for c in ET.fromstring(patches['con']).findall('crossing'))
    forbidden_walks = set()
    for text in (before, after):
        for edge in ET.fromstring(text).findall('edge'):
            if edge.get('function') == 'walkingarea' and edge.get('id')[1:].rsplit('_w', 1)[0] not in pedestrian_nodes:
                forbidden_walks.add(edge.get('id'))

    def has_forbidden_walk(block):
        element = ET.fromstring(block)
        return any(element.get(field, '').rsplit('_', 1)[0] in forbidden_walks
                   if field == 'via' else element.get(field) in forbidden_walks
                   for field in ('from', 'to', 'via'))

    result = source
    for tag in ("edge", "junction", "tlLogic", "roundabout"):
        old, new, original = _indexed(before, tag), _indexed(after, tag), _indexed(result, tag)
        changed = {key for key in old.keys() | new.keys()
                   if key not in old or key not in new or _semantic(old[key]) != _semantic(new[key])}
        additions = []
        for key in sorted(changed):
            if tag == 'edge' and key in forbidden_walks:
                continue
            if key not in new:
                if key in original:
                    result = result.replace(original[key], "", 1)
            elif key in original:
                result = result.replace(original[key], new[key].replace('/>', ' />'), 1)
            else:
                additions.append(new[key].replace('/>', ' />'))
        if additions:
            anchor = {"edge": "    <tlLogic ", "junction": "    <connection ",
                      "tlLogic": "    <junction "}[tag]
            position = result.index(anchor)
            result = result[:position] + ''.join(additions) + result[position:]

    old, new = _indexed(before, "connection"), _indexed(after, "connection")
    changed = {key for key in old.keys() | new.keys()
               if key not in old or key not in new or _semantic(old[key]) != _semantic(new[key])}
    original_connections = _indexed(source, "connection")
    for approach in sorted({key[0] for key in changed}):
        candidates = {key: block for key, block in new.items()
                      if key[0] == approach and not has_forbidden_walk(block)}
        # Connections da fonte que o roundtrip desviou para walkingareas globais
        # continuam como estavam; nenhum edge ausente entra no XML recomposto.
        for key, block in original_connections.items():
            if key[0] == approach and key in old and has_forbidden_walk(old[key]):
                candidates[key] = block
        replacements = ''.join(block.replace('/>', ' />') for block in candidates.values())
        matches = [match for match in _blocks(result, "connection")
                   if ET.fromstring(match.group()).get("from") == approach]
        if matches:
            for match in reversed(matches[1:]):
                result = result[:match.start()] + result[match.end():]
            first = matches[0]
            result = result[:first.start()] + replacements + result[first.end():]
        elif replacements:
            position = result.index("    <roundabout ")
            result = result[:position] + replacements + result[position:]
    # Aproximações recuperadas podem ampliar o contorno visível, conservando
    # projeção, offset e recorte de origem. Isso também mantém o zoom da GUI.
    old_boundary = ET.fromstring(before).find("location").get("convBoundary")
    new_boundary = ET.fromstring(after).find("location").get("convBoundary")
    if old_boundary != new_boundary:
        result = re.sub(r'convBoundary="[^"]+"', f'convBoundary="{new_boundary}"', result, count=1)
    return result


def _restore_cross_streets(source):
    """Reconstitui três cruzamentos que tinham TLS, mas não vias transversais.

    Centro de vias: OSM ways 659117881, 616180216, 647043774 e 659117933,
    consultadas em 02/10/2026; cruzamentos e faixas conferidos na imagem Esri.
    Belarmino tem uma faixa de circulação por sentido na imagem; estacionamento
    lateral não é convertido em faixa de circulação. Não são planos SETTRAN.
    """
    coordinates = {
        "2042693016": "4797.53,1848.62", "2963614071": "4854.24,2042.07",
        "2042693062": "4939.69,1807.21", "3050701647": "4902.40,1818.61",
        "6238793883": "4869.04,1827.98", "2963614077": "4741.74,1657.39",
        "3371652974": "4883.40,2139.87", "338955633": "4911.42,2240.92",
        "2042693080": "4243.18,1800.58", "2042693107": "4315.43,1778.00",
        "2042693128": "4390.32,1758.99",
    }
    segments = (
        ("659117881", ("2042693062", "3050701647", "6238793883", "2042693016"),
         "11.11", "Avenida Ortízio Borges"),
        ("616180216", ("2963614077", "2042693016"), "11.11", "Rua Nordau Gonçalves de Melo"),
        ("647043774#0", ("2042693016", "2963614071"), "11.11", "Rua Nordau Gonçalves de Melo"),
        ("647043774#1", ("2963614071", "3371652974", "338955633"),
         "11.11", "Rua Nordau Gonçalves de Melo"),
        ("659117933#west", ("2042693080", "2042693107"), "13.89", "Avenida Belarmino Cotta Pacheco"),
        ("659117933#east", ("2042693107", "2042693128"), "13.89", "Avenida Belarmino Cotta Pacheco"),
    )
    root = ET.fromstring(source)
    existing = {node.get("id") for node in root.findall("junction")}
    restrictions = root.find("edge[@id='647043773#0']/lane").get("disallow", "").split()
    if "pedestrian" not in restrictions:
        restrictions.append("pedestrian")
    nodes, edges, connections = ET.Element("nodes"), ET.Element("edges"), ET.Element("connections")
    for edge_id, sequence, speed, name in segments:
        for node_id in (sequence[0], sequence[-1]):
            if node_id not in existing:
                x, y = coordinates[node_id].split(',')
                ET.SubElement(nodes, "node", id=node_id, x=x, y=y, type="priority")
                existing.add(node_id)
        for reverse in (False, True):
            shape = sequence[::-1] if reverse else sequence
            ET.SubElement(edges, "edge", id=('-' if reverse else '') + edge_id,
                          **{"from": shape[0], "to": shape[-1], "numLanes": "1",
                             "speed": speed, "width": "3.2", "priority": "3", "name": name,
                             "disallow": ' '.join(restrictions),
                             "shape": ' '.join(coordinates[n] for n in shape)})
    # Todas as aproximações ganham reta/direita/esquerda. O retorno terminal
    # fictício de Ortízio é retirado; o centro físico é um cruzamento de quatro vias.
    for exits in (("647043773#0", "647043774#0", "-659117881", "-616180216"),
                  ("659117905#2", "-659117905#1", "647043774#1", "-647043774#0"),
                  ("616971271#1", "-616971271#0", "659117933#east", "-659117933#west")):
        for exit_id in exits:
            incoming = exit_id[1:] if exit_id.startswith('-') else '-' + exit_id
            for old in root.findall("connection"):
                if old.get("from") == incoming:
                    ET.SubElement(connections, "delete", **{"from": incoming, "to": old.get("to")})
            for destination in exits:
                if destination != exit_id:
                    ET.SubElement(connections, "connection", **{
                        "from": incoming, "to": destination, "fromLane": "0", "toLane": "0"})
    patches = {kind: ET.tostring(element, encoding="unicode")
               for kind, element in (("nod", nodes), ("edg", edges), ("con", connections))}
    # Programa SUMO de referência, com prioridades permissivas calculadas pelo
    # compilador. Recompilar é necessário porque os antigos programas só tinham
    # 1–2 links e não poderiam controlar as novas aproximações.
    return _apply_local_patch(source, patches, ("--tls.rebuild", "true",
                             "--tls.cycle.time", "90", "--tls.yellow.time", "3",
                             "--tls.allred.time", "5", "--tls.layout", "incoming"))


def _join_fragmented_junctions(source):
    """Reúne miolos físicos fragmentados, mantendo os movimentos carregados.

    Paraná, África × Holanda e África × Suíça: quatro pontos do mesmo cruzamento, conferidos
    no OSM e imagem Esri de 26/11/2023. Salomão × João Pereira: acesso de 5,86m
    junto à rotatória, onde duas arestas externas de 0,20m produziam retorno e
    destino artificiais. O círculo e as retenções externas são preservados.
    reset=false conserva a conectividade anterior; o SUMO recalcula trajetórias,
    prioridades internas e keep-clear no espaço do cruzamento completo.
    """
    joins = (
        ("FAM_RONDON_PARANA", "338942567 1668155077 1668155076 597213239"),
        ("AFRICA_HOLANDA", "1561880676 2042691919 4125318255 4125318256"),
        ("AFRICA_SUICA", "4125318258 4125318259 1561880748 2042691990"),
        ("SALOMAO_JOAO_PEREIRA", "4025923697 3371628024"),
    )
    nodes = '<nodes>' + ''.join(
        f'<join id="{node_id}" nodes="{members}" reset="false"/>'
        for node_id, members in joins) + '</nodes>'
    return _apply_local_patch(source, {"nod": nodes})


def _correct_benjamim(source):
    """Quatro faixas e retenções em uma única interseção física.

    Faixas conferidas na imagem Esri/WV03 de 26/11/2023, corroboradas pelo
    equipamento F1–F4 no DOM4110/2013. Os seis pontos ficam no mesmo miolo;
    reuni-los elimina quatro conectores internos e duas sobras de 20 cm.
    São conservados os 12 pares viários alcançáveis na topologia anterior.
    As permissões de conversão seguem direita/direita e esquerda/esquerda,
    sem criar destinos ou afirmar exclusividade de faixa não documentada.
    """
    edges = ET.Element('edges')
    four_lane_edges = (
        '1156717163#2', '1156717163#3',
        '152937136#1', '152937136#2', '152937136#3',
        '1156272391#0', '1156272391#1', '1156272391#2', '1156272391#3',
        '1156272393#0', '1156272393#1', '1156272393#2',
    )
    for edge_id in four_lane_edges:
        ET.SubElement(edges, 'edge', id=edge_id, numLanes='4', width='3.2')
    ET.SubElement(edges, 'edge', id='152937136#0', numLanes='3', width='3.2')
    nodes = ET.Element('nodes')
    ET.SubElement(nodes, 'join', nodes='338660524 3050804948 7963074868 3050767830 3175865971 3050767735',
                  id='FAM_RONDON_BENJAMIM_JUNCTION', type='traffic_light',
                  tl='FAM_RONDON_BENJAMIM', reset='false')
    stage = _apply_local_patch(source, {'edg': ET.tostring(edges, encoding='unicode'),
                                      'nod': ET.tostring(nodes, encoding='unicode')})
    root = ET.fromstring(stage)
    connections = ET.Element('connections')
    # Conserva os 12 pares origem/destino já alcançáveis no antigo miolo.
    main_a, main_b = '1156717163#3', '152937136#3'
    lateral_b, lateral_c = '666324302#5', '853751181#0'
    ne, sw, lateral_out = '1156272391#0', '1156272393#0', '1156272395#1'
    links = [(main_a, ne, lane, lane) for lane in range(4)]
    links += [(main_a, lateral_out, 0, 0), (main_a, sw, 3, 3)]
    links += [(main_b, sw, lane, lane) for lane in range(4)]
    links += [(main_b, lateral_out, 3, 0), (main_b, ne, 3, 3)]
    links += [(lateral_b, ne, 0, 0), (lateral_b, lateral_out, 0, 0), (lateral_b, sw, 0, 3)]
    links += [(lateral_c, sw, 0, 0), (lateral_c, lateral_out, 0, 0), (lateral_c, ne, 0, 3)]
    corridors = (
        ('1156717163#2', '1156717163#3'),
        ('152937136#1', '152937136#2'), ('152937136#2', '152937136#3'),
        ('1156272391#0', '1156272391#1'), ('1156272391#1', '1156272391#2'),
        ('1156272391#2', '1156272391#3'),
        ('1156272393#0', '1156272393#1'), ('1156272393#1', '1156272393#2'),
    )
    replacements = {origin: [] for origin, _ in corridors}
    for origin, destination in corridors:
        replacements[origin].extend((origin, destination, lane, lane) for lane in range(4))
        # Saídas laterais existentes continuam na faixa direita já utilizada.
        replacements[origin].extend((origin, c.get('to'), int(c.get('fromLane')), int(c.get('toLane')))
                                    for c in root.findall('connection') if c.get('from') == origin
                                    and c.get('to') != destination)
    replacements[main_a] = [link for link in links if link[0] == main_a]
    replacements[main_b] = [link for link in links if link[0] == main_b]
    replacements[lateral_b] = [link for link in links if link[0] == lateral_b]
    replacements[lateral_c] = [link for link in links if link[0] == lateral_c]
    replacements['152937136#0'] = [('152937136#0', '152937136#1', lane, lane + 1) for lane in range(3)]
    replacements['152937010#3'] = [('152937010#3', '152937136#1', 0, 0)]
    for origin, desired in replacements.items():
        for destination in sorted({c.get('to') for c in root.findall('connection') if c.get('from') == origin}):
            ET.SubElement(connections, 'delete', **{'from': origin, 'to': destination})
        for _, destination, lane_from, lane_to in desired:
            ET.SubElement(connections, 'connection', **{'from': origin, 'to': destination,
                          'fromLane': str(lane_from), 'toLane': str(lane_to)})
    tl = '<tlLogics><tlLogic id="FAM_RONDON_BENJAMIM" type="static" programID="current" offset="0"><phase duration="1" state="OOOOOOOOOOOOOOOOOO"/></tlLogic></tlLogics>'
    nodes = '<nodes><node id="FAM_RONDON_BENJAMIM_JUNCTION" type="traffic_light" tl="FAM_RONDON_BENJAMIM"/></nodes>'
    result = _apply_local_patch(stage, {
        'con': ET.tostring(connections, encoding='unicode'), 'nod': nodes, 'tll': tl})
    root = ET.fromstring(result)
    controlled = sorted((c for c in root.findall('connection')
                         if c.get('tl') == 'FAM_RONDON_BENJAMIM'),
                        key=lambda c: int(c.get('linkIndex')))
    if len(controlled) != 18 or len({(c.get('from'), c.get('to')) for c in controlled}) != 12:
        raise ValueError('Benjamim diverge dos 18 links e 12 pares viários comprovados.')
    # O/o seguem a ordem geométrica efetiva e as prioridades recompiladas,
    # não uma string anterior cuja indexação deixou de ser válida.
    states = ''.join('O' if c.get('state') in {'M', 'O'} else 'o' for c in controlled)
    original = _indexed(result, 'tlLogic')['FAM_RONDON_BENJAMIM']
    program = ('    <tlLogic id="FAM_RONDON_BENJAMIM" type="static" '
               'programID="current" offset="0">\n'
               f'        <phase duration="1" state="{states}" />\n    </tlLogic>\n')
    return result.replace(original, program, 1)


def _collapse_short_signal_approaches(source):
    """Retira pontos geométricos intermediários sem mover a interseção real.

    Junta as duas partes da mesma aproximação, conservando sua linha central,
    junction de controle, destinos, tempos e índices semafóricos anteriores.
    """
    root = ET.fromstring(source)
    groups = (
        ('FAM_RONDON_NITEROI', '338686240', '3050767812', '30622933#12', '30622933#11'),
        ('FAM_RONDON_PORTO_ALEGRE', '2042691678', '3034565314', '30664532#3', '30664532#2'),
        ('FAM_RONDON_BELEM', '338685838', '3050767816', '965367673#1', '965367673#0'),
    )
    original_edges = {edge.get('id'): edge for edge in root.findall('edge')}
    original_nodes = {node.get('id'): node for node in root.findall('junction')}
    nodes, edges, connections = ET.Element('nodes'), ET.Element('edges'), ET.Element('connections')
    aliases = {}
    for _, junction, marker, old_id, continuous_id in groups:
        approach, tail = original_edges[continuous_id], original_edges[old_id]
        points = []
        for edge in (approach, tail):
            shape = edge.get('shape')
            if not shape:
                shape = ' '.join(original_nodes[edge.get(end)].get('x') + ',' +
                                 original_nodes[edge.get(end)].get('y') for end in ('from', 'to'))
            for point in shape.split():
                if not points or points[-1] != point:
                    points.append(point)
        ET.SubElement(edges, 'delete', id=old_id)
        ET.SubElement(edges, 'edge', id=continuous_id, to=junction, shape=' '.join(points))
        ET.SubElement(nodes, 'delete', id=marker)
        ET.SubElement(connections, 'delete', **{'from': continuous_id, 'to': old_id})
        for old in root.findall('connection'):
            if old.get('from') == old_id:
                attrs = {key: old.get(key) for key in ('to', 'fromLane', 'toLane')}
                ET.SubElement(connections, 'connection', **{'from': continuous_id}, **attrs)
        aliases[old_id] = continuous_id
    rebuilt = _apply_local_patch(source, {
        'nod': ET.tostring(nodes, encoding='unicode'),
        'edg': ET.tostring(edges, encoding='unicode'),
        'con': ET.tostring(connections, encoding='unicode'),
    })
    assignments = {}
    tls_ids = {item[0] for item in groups}
    for old in root.findall('connection'):
        if old.get('tl') in tls_ids:
            attrs = dict(old.attrib)
            attrs['from'] = aliases.get(attrs['from'], attrs['from'])
            assignments[_key(ET.Element('connection', attrs))] = (old.get('tl'), old.get('linkIndex'))
    for match in reversed(_blocks(rebuilt, 'connection')):
        connection = ET.fromstring(match.group())
        assignment = assignments.pop(_key(connection), None)
        if assignment is None:
            continue
        connection.set('tl', assignment[0]); connection.set('linkIndex', assignment[1])
        block = '    ' + ET.tostring(connection, encoding='unicode').strip() + '\n'
        rebuilt = rebuilt[:match.start()] + block + rebuilt[match.end():]
    if assignments:
        raise ValueError('A recomposição transversal perdeu controlledLinks comprovados.')
    programs = _indexed(source, 'tlLogic')
    for match in reversed(_blocks(rebuilt, 'tlLogic')):
        tls = ET.fromstring(match.group()).get('id')
        if tls in tls_ids:
            rebuilt = rebuilt[:match.start()] + programs[tls] + rebuilt[match.end():]
    return _align_connector_priorities(rebuilt)


def _align_connector_priorities(source):
    """Alinha conectores cedentes com as próprias requests recompiladas.

    Preserva a cessão já expressa nas matrizes de Rondon e Cesário.
    Não cria outro TLS,
    altera foes ou muda programa: M inconsistente com a obrigação de ceder vira m.
    A verificação também é aplicada após compilar as travessias físicas.
    """
    root = ET.fromstring(source)
    roads = {e.get('id'): e for e in root.findall('edge')}
    junctions = {n.get('id'): n for n in root.findall('junction')}
    for match in reversed(_blocks(source, 'connection')):
        connection = ET.fromstring(match.group())
        origin, via = connection.get('from'), connection.get('via')
        if (origin not in {'1156717174', '1156717171', '965367671',
                                  '853749385', '853749386', '602306713#22'}
                or connection.get('tl') or connection.get('state') != 'M' or not via):
            continue
        junction = junctions[roads[origin].get('to')]
        request_index = junction.get('intLanes').split().index(via)
        response = junction.find(f"request[@index='{request_index}']").get('response')
        if '1' in response:
            connection.set('state', 'm')
            block = '    ' + ET.tostring(connection, encoding='unicode').strip() + '\n'
            source = source[:match.start()] + block + source[match.end():]
    return source


def _preserve_vehicle_phases(source, rebuilt, new_tls=()):
    """Conserva tempos/estados veiculares, estende retas equivalentes e deixa pedestres vermelhos.

    Programas de referência atuais não são programação SETTRAN. Nenhuma fase
    pedestre ou agenda real é inferida da localização de uma faixa de pedestres.
    """
    before, after = ET.fromstring(source), ET.fromstring(rebuilt)
    old_links, links = {}, {}
    for root, target in ((before, old_links), (after, links)):
        for link in root.findall('connection'):
            if link.get('tl'):
                target.setdefault(link.get('tl'), {})[int(link.get('linkIndex'))] = link
    programs = {p.get('id'): p for p in before.findall('tlLogic')}
    for match in reversed(_blocks(rebuilt, 'tlLogic')):
        program = ET.fromstring(match.group())
        tls_id = program.get('id')
        if tls_id in new_tls:
            states = ''.join('r' if link.get('from', '').startswith(':') else 'O'
                             for _, link in sorted(links[tls_id].items()))
            text = (f'    <tlLogic id="{tls_id}" type="static" programID="current" offset="0">\n'
                    f'        <phase duration="1" state="{states}" />\n    </tlLogic>\n')
        elif tls_id in programs:
            original = programs[tls_id]
            phases = []
            for phase in original.findall('phase'):
                state = phase.get('state')
                extended = []
                for _, link in sorted(links[tls_id].items()):
                    if link.get('from', '').startswith(':'):
                        extended.append('r')
                        continue
                    candidates = [index for index, old in old_links[tls_id].items()
                                  if old.get('from') == link.get('from') and old.get('to') == link.get('to')]
                    if not candidates:
                        candidates = [index for index, old in old_links[tls_id].items()
                                      if old.get('dir') == link.get('dir')]
                    values = {state[index] for index in candidates}
                    if len(values) != 1:
                        raise ValueError(f'Não é possível conservar estados atuais: {tls_id}, {link.attrib}.')
                    attrs = dict(phase.attrib)
                    extended.append(values.pop())
                attrs = dict(phase.attrib); attrs['state'] = ''.join(extended)
                phases.append('        ' + ET.tostring(ET.Element('phase', attrs), encoding='unicode') + '\n')
            attrs = ' '.join(f'{key}="{value}"' for key, value in original.attrib.items())
            text = f'    <tlLogic {attrs}>\n' + ''.join(phases) + '    </tlLogic>\n'
        else:
            continue
        rebuilt = rebuilt[:match.start()] + text + rebuilt[match.end():]
    return rebuilt


def _complete_rondon_widths(source):
    """Quatro corredores visíveis em Esri2023; remove largura1,75m incompatível com tráfego veicular.

    Não cria destinos de conversão: só completa as mesmas retas longitudinalmente.
    As permissões de conversão existentes permanecem explícitas.
    """
    root = ET.fromstring(source)
    roads = {e.get('id'): e for e in root.findall('edge') if e.get('function') is None}
    widened = {edge for edge, element in roads.items()
               if any(lane.get('width') == '1.75' for lane in element.findall('lane'))}
    four_lanes = {'1156717163#0', '1156717163#1', '1156717168',
                  *(f'1156272393#{i}' for i in range(3, 8)),
                  *(f'1156717173#{i}' for i in range(6))}
    patches = ET.Element('edges')
    for edge_id in sorted(widened | four_lanes):
        if edge_id in roads:
            attrs = {'id': edge_id, 'width': '3.2'}
            if edge_id in four_lanes:
                attrs['numLanes'] = '4'
            ET.SubElement(patches, 'edge', attrs)
    connections = ET.Element('connections')
    for link in root.findall('connection'):
        incoming, outgoing = link.get('from'), link.get('to')
        if incoming not in roads or outgoing not in roads or link.get('dir') != 's':
            continue
        if incoming not in four_lanes and outgoing not in four_lanes:
            continue
        count_in = 4 if incoming in four_lanes else len(roads[incoming].findall('lane'))
        count_out = 4 if outgoing in four_lanes else len(roads[outgoing].findall('lane'))
        if link.get('fromLane') != '0':
            continue
        if count_in == count_out == 4:
            pairs = [(lane, lane) for lane in range(4)]
        elif count_in == 2 and count_out == 4:
            # A aproximação já existente abre as duas faixas, uma para cada lado,
            # sem acrescentar destinos nem mudar o sentido de circulação.
            pairs = [(0, 0), (0, 1), (1, 2), (1, 3)]
        else:
            continue
        ET.SubElement(connections, 'delete', {'from': incoming, 'to': outgoing})
        for from_lane, to_lane in pairs:
            ET.SubElement(connections, 'connection', {'from': incoming, 'to': outgoing,
                          'fromLane': str(from_lane), 'toLane': str(to_lane)})
    result = _apply_local_patch(source, {'edg': ET.tostring(patches, encoding='unicode'),
                                       'con': ET.tostring(connections, encoding='unicode')})
    return _preserve_vehicle_phases(source, result)


def _complete_documented_crossings(source):
    """Zebras conferidas em Esri2023 e OSM; Rio confirmado também pela prefeitura2020.

    Belém tem zebra visível, mas OSM2026 a informa não semaforizada; mantém-se
    crossing físico sem atribuir-lhe um controle que as fontes contraditórias não provam.
    Os acessos pedonais locais apenas conectam a zebra aos dois lados da calçada.
    """
    root = ET.fromstring(source)
    roads = {e.get('id'): e for e in root.findall('edge') if e.get('function') is None}
    junctions = {n.get('id'): n for n in root.findall('junction')}
    nodes, edges, connections = ET.Element('nodes'), ET.Element('edges'), ET.Element('connections')
    # O TLS1593 legado estava16m antes da zebra; a travessia real está neste nodeOSM.
    ET.SubElement(nodes, 'node', {'id': '5494111593', 'type': 'priority'})
    ET.SubElement(nodes, 'node', {'id': '5525815656', 'type': 'traffic_light', 'tl': '5494111593'})
    crossings = [
        ('FAM_RONDON_BENJAMIM_JUNCTION', '1156717163#3'),
        ('FAM_RONDON_BENJAMIM_JUNCTION', '152937136#3'),
        ('FAM_RONDON_BENJAMIM_JUNCTION', '1156272391#0'),
        ('FAM_RONDON_BENJAMIM_JUNCTION', '1156272393#0'),
        ('FAM_RONDON_BENJAMIM_JUNCTION', '853751181#0'),
        ('FAM_RONDON_BENJAMIM_JUNCTION', '666324302#5 1156272395#1'),
        ('5494111589', '576014290#0'), ('5494111590', '1156717175#5'),
        ('5494111594', '576014301#0'), ('5525815656', '462993308#1'),
        ('5494111596', '1156717175#0'), ('5494111597', '930831032#0'),
        ('3386573305', '331577748#2'), ('3386573306', '299471494#1'),
        ('5494111603', '1156717170#0'),
        ('2042691678', '30664532#2'), ('339121007', '1156717172#0'),
        ('338686240', '30622933#11'), ('597213618', '1156717177#0'),
        ('3386573294', '1156272393#6'), ('3386573296', '901328279#0'),
        ('3386573297', '1156717168'), ('3386573298', '1156717173#4'),
        ('8622218071', '463014795#0'), ('8622218072', '930831033#0'),
        ('8622218073', '965367672#2'),
        ('13738551275', '331577750#0'), ('13738551276', '299471494#0'),
        ('339114019', '154252437#1'), ('7963056109', '665897556#1'),
        ('7963056110', '602306713#21'),
        ('2651934389', '576014296#2'), ('2783757296', '462991286'),
        ('338654991', '625668273#2'), ('3050761411', '292932042#0'),
        ('FAM_RIO_SW', '1156272393#5'), ('FAM_RIO_NE', '1156717163#1'),
    ]
    for node_id, road in crossings:
        junction = junctions[node_id]
        x, y = float(junction.get('x')), float(junction.get('y'))
        road_ids = road.split()
        edge = roads[road_ids[0]]
        shape = edge.get('shape')
        if shape:
            points = [tuple(map(float, value.split(','))) for value in shape.split()]
        else:
            points = [(float(junctions[edge.get(k)].get('x')), float(junctions[edge.get(k)].get('y')))
                      for k in ('from', 'to')]
        a, b = points[-2:] if edge.get('to') == node_id else (points[1], points[0])
        dx, dy = b[0] - a[0], b[1] - a[1]
        distance = math.hypot(dx, dy)
        lateral = sum(len(roads[e].findall('lane')) for e in road_ids) * 3.2 / 2 + 4
        for side, sign in enumerate((-1, 1)):
            ped_id = f'{node_id}.ped.{road_ids[0]}.{side}'
            px = x - dx / distance * lateral * 2 + sign * dy / distance * lateral
            py = y - dy / distance * lateral * 2 - sign * dx / distance * lateral
            ET.SubElement(nodes, 'node', {'id': ped_id, 'x': f'{px:.2f}', 'y': f'{py:.2f}', 'type': 'priority'})
            ET.SubElement(edges, 'edge', {'id': ped_id, 'from': ped_id, 'to': node_id,
                          'numLanes': '1', 'speed': '1.4', 'width': '2', 'allow': 'pedestrian'})
        # Somente vias incidentes nesta travessia deixam de aceitar pedestrian no leito viário.
        for adjacent in roads.values():
            if node_id not in (adjacent.get('from'), adjacent.get('to')):
                continue
            for lane in adjacent.findall('lane'):
                disallowed = set(lane.get('disallow', '').split()); disallowed.add('pedestrian')
                # O patch do edge aceita lanes explícitas sem alterar índices veiculares.
                patch = next((e for e in edges.findall('edge') if e.get('id') == adjacent.get('id')), None)
                if patch is None:patch = ET.SubElement(edges, 'edge', {'id': adjacent.get('id')})
                if not any(l.get('index') == lane.get('index') for l in patch.findall('lane')):
                    ET.SubElement(patch, 'lane', {'index': lane.get('index'), 'disallow': ' '.join(sorted(disallowed))})
        ET.SubElement(connections, 'crossing', {'node': node_id, 'edges': road, 'width': '4'})
    rebuilt = _apply_local_patch(source, {'nod': ET.tostring(nodes, encoding='unicode'),
                                         'edg': ET.tostring(edges, encoding='unicode'),
                                         'con': ET.tostring(connections, encoding='unicode')},
                                 ('--walkingareas', 'true'))
    preserved = _preserve_vehicle_phases(source, rebuilt)
    return _preserve_benjamim_priority_responses(preserved)


def _complete_rio_and_loop(source):
    """Rio tem duas zebras e sinais reais, sem qualquer plano SETTRAN conhecido.

    O pontoSW é10,96m após a convergência comRio; o pontoNE coincide com
    vértice da geometriaOSM sobre a mesma faixa visível na imagemEsri2023.
    A alçaJoão mantém o conflito físico, com espera antes da primeira faixa.
    """
    nodes, edges, connections = ET.Element('nodes'), ET.Element('edges'), ET.Element('connections')
    ET.SubElement(nodes, 'join', {'nodes': '338664406 8062374303', 'id': 'FAM_RIO_ACCESS'})
    rebuilt = _apply_local_patch(source, {'nod': ET.tostring(nodes, encoding='unicode')},
                                 ('--junctions.join-dist', '0', '--junctions.join-turns', 'true',
                                  '--junctions.join-reset', 'false'))
    nodes, edges, connections = ET.Element('nodes'), ET.Element('edges'), ET.Element('connections')
    root = ET.fromstring(rebuilt); roads = {e.get('id'): e for e in root.findall('edge')}
    locations = [('1156272393#5', 'FAM_RIO_SW', '10.95671322'),
                 ('1156717163#1', 'FAM_RIO_NE', '93.50')]
    for edge_id, node, position in locations:
        edge = ET.SubElement(edges, 'edge', {'id': edge_id})
        ET.SubElement(edge, 'split', {'pos': position, 'idBefore': edge_id,
                      'idAfter': edge_id + '.rio', 'id': node, 'type': 'traffic_light',
                      'tl': 'FAM_RONDON_RIO_DE_JANEIRO'})
    ET.SubElement(connections, 'connection', {'from': '462993309', 'to': '577166561#0',
                  'fromLane': '0', 'toLane': '0', 'contPos': '1', 'keepClear': 'true'})
    rebuilt = _apply_local_patch(rebuilt, {'nod': ET.tostring(nodes, encoding='unicode'),
                                          'edg': ET.tostring(edges, encoding='unicode'),
                                          'con': ET.tostring(connections, encoding='unicode')})
    return _preserve_vehicle_phases(source, rebuilt, {'FAM_RONDON_RIO_DE_JANEIRO'})


def _preserve_benjamim_priority_responses(source):
    """Current O/o deve conservar a preferência viária do cruzamento priority.

    O compilador calcula outro response para verdes permissivos e pode criar
    espera mútua entre esquerdas. Derivamos as prioridades da mesma geometria
    e mesmas roads. Foes, controlledLinks e retenções internas não são alterados.
    Nenhuma matriz é ajustada manualmente nem conflito físico é omitido.
    """
    node_id, tls_id = 'FAM_RONDON_BENJAMIM_JUNCTION', 'FAM_RONDON_BENJAMIM'
    root = ET.fromstring(source)
    program = next(p for p in root.findall('tlLogic') if p.get('id') == tls_id)
    if any(set(p.get('state')) - {'O', 'o', 'r'} for p in program.findall('phase')):
        raise ValueError('A derivação priority só se aplica ao programa current O/o de Benjamim.')
    reference = _apply_local_patch(source, {'nod': f'<nodes><node id="{node_id}" type="priority"/></nodes>'},
                                   ('--walkingareas', 'true'))
    node = next(n for n in ET.fromstring(reference).findall('junction') if n.get('id') == node_id)
    requests = {req.get('index'): req for req in node.findall('request')}
    for match in _blocks(source, 'junction'):
        current = ET.fromstring(match.group())
        if current.get('id') != node_id:
            continue
        for request in current.findall('request'):
            reference_request = requests[request.get('index')]
            if request.get('foes') != reference_request.get('foes'):
                raise ValueError('A derivação priority divergiu dos conflitos físicos de Benjamim.')
            request.set('response', reference_request.get('response'))
        ET.indent(current, space='    ', level=1)
        replacement = '    ' + ET.tostring(current, encoding='unicode') + '\n'
        return source[:match.start()] + replacement + source[match.end():]
    raise ValueError('Junction Benjamim ausente.')


def _restore_maria_segismundo(source):
    """Completa o TLS terminal na abertura Maria das Dores × Segismundo.

    OSM 616971270/931172668 e 398537158/616971268: duas pistas unidirecionais.
    Foto Esri de 26/11/2023 confirma abertura, zebras e retenções. Croqui SETTRAN
    Segismundo × João Balbino de 14/01/2025 confirma duas faixas e esquerda
    exclusiva de ônibus no corredor; publicação municipal reproduzida pela V9
    em 21/07/2018 e relações OSM 8531027/8531030 confirmam proibição de esquerda
    a partir da avenida. A regra não é transferida às aproximações de Maria.
    Fechos locais usam pontos reais de Nelson Oliveira, Delmira Cândida e acesso
    de serviço ao sul, evitando incluir os semáforos do próximo quarteirão.
    O programa gerado pelo SUMO é referência current, não programação SETTRAN.
    """
    coordinates = {
        "2042693363": "4259.78,1590.83", "2042693385": "4254.95,1578.04",
        "954823567": "4188.27,1610.63", "3370282693": "4186.50,1597.56",
        "2042693399": "4333.97,1572.96", "2042693444": "4326.49,1557.37",
        "6051154708": "4230.07,1490.49",
    }
    road_sections = (
        ("616971270#east", "2042693363", "954823567"),
        ("931172668#west", "2042693399", "2042693363"),
        ("398537158#east", "3370282693", "2042693385"),
        ("616971268#west", "2042693385", "2042693444"),
    )
    root = ET.fromstring(source)
    # As novas faixas gerais usam as mesmas permissões de Maria existente;
    # somente a faixa comprovadamente exclusiva mantém allow=bus.
    base_lane = root.find("edge[@id='616971271#0']/lane")
    road_disallowed = ' '.join(sorted(set(base_lane.get("disallow", "").split()) | {"pedestrian"}))
    existing_nodes = {node.get("id") for node in root.findall("junction")}
    nodes, edges, connections = ET.Element("nodes"), ET.Element("edges"), ET.Element("connections")
    for node_id, xy in coordinates.items():
        if node_id in existing_nodes:
            continue
        x, y = xy.split(',')
        attributes = {"id": node_id, "x": x, "y": y, "type": "priority"}
        if node_id == "2042693385":
            attributes.update(type="traffic_light", tl="2042693363")
        else:
            attributes["fringe"] = "inner"
        ET.SubElement(nodes, "node", **attributes)
    for edge_id, first, last in road_sections:
        road = ET.SubElement(edges, "edge", id=edge_id, **{
            "from": first, "to": last, "numLanes": "2", "speed": "16.67",
            "width": "3.2", "priority": "8", "name": "Avenida Segismundo Pereira",
            "spreadType": "center", "disallow": road_disallowed,
            "shape": f"{coordinates[first]} {coordinates[last]}",
        })
        ET.SubElement(road, "lane", index="1", allow="bus")
    for edge_id, first, last in (("616971269", "2042693385", "2042693363"),
                                ("154562663#north", "6051154708", "2042693385")):
        for reverse in (False, True):
            start, end = (last, first) if reverse else (first, last)
            ET.SubElement(edges, "edge", id=('-' if reverse else '') + edge_id, **{
                "from": start, "to": end, "numLanes": "1", "speed": "13.89",
                "width": "3.2", "priority": "3", "name": "Rua Maria das Dores Dias",
                "disallow": road_disallowed, "shape": f"{coordinates[start]} {coordinates[end]}",
            })
    # A antiga conexão era apenas retorno do ramo terminal. O cruzamento aberto
    # tem a continuação transversal real, além dos acessos às pistas da avenida.
    ET.SubElement(connections, "delete", **{
        "from": "-616971271#0", "to": "616971271#0"})
    turns = (
        ("-616971271#0", "616971270#east"), ("-616971271#0", "-616971269"),
        ("616971269", "616971271#0"), ("616971269", "616971270#east"),
        ("931172668#west", "616971271#0"),
        ("154562663#north", "616971269"), ("154562663#north", "616971268#west"),
        ("-616971269", "-154562663#north"), ("-616971269", "616971268#west"),
        ("398537158#east", "-154562663#north"),
    )
    for first, last in turns:
        ET.SubElement(connections, "connection", **{
            "from": first, "to": last, "fromLane": "0", "toLane": "0"})
    for first, last in (("931172668#west", "616971270#east"),
                        ("398537158#east", "616971268#west")):
        for lane in range(2):
            ET.SubElement(connections, "connection", **{
                "from": first, "to": last, "fromLane": str(lane), "toLane": str(lane)})
    ET.SubElement(nodes, "join", id="FAM_MARIA_SEGISMUNDO", nodes="2042693363 2042693385",
                  type="traffic_light", tl="2042693363", reset="false")
    patches = {kind: ET.tostring(element, encoding="unicode")
               for kind, element in (("nod", nodes), ("edg", edges), ("con", connections))}
    result = _apply_local_patch(source, patches, ("--tls.rebuild", "true",
                                "--tls.cycle.time", "90", "--tls.yellow.time", "3",
                                "--tls.allred.time", "5", "--tls.layout", "incoming"))
    # Quatro zebras visíveis na imagem são objetos físicos; o programa atual
    # conserva os estados veiculares acima e não presume atendimento pedonal.
    nodes, edges, connections = ET.Element("nodes"), ET.Element("edges"), ET.Element("connections")
    for side, xy in enumerate(((4245.0, 1604.0), (4270.0, 1604.0),
                                (4245.0, 1565.0), (4270.0, 1565.0))):
        node_id = f"FAM_MARIA_SEGISMUNDO.ped.{side}"
        ET.SubElement(nodes, "node", id=node_id, x=f"{xy[0]:.2f}", y=f"{xy[1]:.2f}", type="priority")
        ET.SubElement(edges, "edge", id=node_id, **{
            "from": node_id, "to": "FAM_MARIA_SEGISMUNDO", "numLanes": "1",
            "speed": "1.4", "width": "2", "allow": "pedestrian"})
    for edge_id in ("616971271#0", "-616971271#0"):
        old_edge = ET.fromstring(result).find(f"edge[@id='{edge_id}']")
        edge = ET.SubElement(edges, "edge", id=edge_id)
        for lane in old_edge.findall("lane"):
            disallowed = set(lane.get("disallow", "").split()) | {"pedestrian"}
            ET.SubElement(edge, "lane", index=lane.get("index"), disallow=' '.join(sorted(disallowed)))
    for roads in ("-616971271#0 616971271#0", "154562663#north -154562663#north",
                  "931172668#west 616971268#west", "616971270#east 398537158#east"):
        ET.SubElement(connections, "crossing", node="FAM_MARIA_SEGISMUNDO", edges=roads, width="4")
    patches = {kind: ET.tostring(element, encoding="unicode")
               for kind, element in (("nod", nodes), ("edg", edges), ("con", connections))}
    crossing_result = _apply_local_patch(result, patches, ("--walkingareas", "true"))
    result = _preserve_vehicle_phases(result, crossing_result)
    # O domínio geográfico original não muda; a área projetada passa a incluir
    # a aproximação sul necessária ao mesmo cruzamento.
    location = ET.fromstring(result).find("location")
    bounds = [float(value) for value in location.get("convBoundary").split(',')]
    bounds[1] = min(bounds[1], 1490.49)
    old_boundary = location.get("convBoundary")
    new_boundary = ','.join(f"{value:.2f}" for value in bounds)
    return result.replace(f'convBoundary="{old_boundary}"', f'convBoundary="{new_boundary}"', 1)


def _restore_europa_benjamim(source):
    """Restaura o miolo Europa × Benjamim, incluindo os ramos da Praça das Nações.

    DOM 4224/2013, p. 74, documenta sinal no cruzamento; imagem Esri de
    26/11/2023 e OSM corroboram geometria e sentidos. Relações OSM 8413864 e
    13015335 proíbem esquerdas da Benjamim; 8411803/8411804 usam vias internas.
    Os fechos são os primeiros acessos/interseções reais de cada aproximação.
    A Europa conserva velocidade/faixas legadas, sem inferir os 50 da Benjamim.
    O programa local é referência SUMO current, não programação real SETTRAN.
    """
    coordinates = {
        "8947803947": "4670.32,3038.19", "8947803946": "4671.97,3039.38",
        "4086937778": "4667.04,3045.79", "8947803941": "4677.28,3032.02",
        "8947803944": "4680.91,3045.91", "8947803942": "4685.67,3039.71",
        "4053646850": "4675.80,3052.42", "1561880196": "4621.37,3111.20",
        "2042691708": "4630.94,3117.67", "4055449701": "4825.37,3150.20",
        "4125318230": "4859.52,3186.34", "7961952649": "4713.87,3000.56",
        "7961952650": "4704.30,2994.55", "1671075991": "4777.88,3028.38",
        "2744514583": "4661.30,2942.24",
    }
    root = ET.fromstring(source)
    europa = root.find("edge[@id='403166945#2']")
    road_disallowed = ' '.join(sorted(set(europa.find("lane").get("disallow", "").split()) | {"pedestrian"}))
    europa_speed = europa.find("lane").get("speed")
    residential_speed = root.find("edge[@id='269160815#0']/lane").get("speed")
    existing = {node.get("id") for node in root.findall("junction")}
    nodes, edges, connections = ET.Element("nodes"), ET.Element("edges"), ET.Element("connections")
    for node_id, xy in coordinates.items():
        if node_id in existing:
            continue
        x, y = xy.split(',')
        ET.SubElement(nodes, "node", id=node_id, x=x, y=y, type="priority", fringe="inner")
    # Seguem as mesmas vias OSM, inclusive seus fragmentos internos ao miolo.
    sections = (
        ("30621478#east", "1561880196", "4086937778", "benjamim"),
        ("602306725#east", "4053646850", "2042691708", "benjamim"),
        ("402968127#west", "7961952649", "8947803942", "benjamim"),
        ("602306745#west", "8947803941", "7961952650", "benjamim"),
        ("402968133#west", "4125318230", "4053646850", "europa"),
        ("602306733#west", "8947803944", "4055449701", "europa"),
        ("269160814#west", "1671075991", "8947803942", "praca"),
        ("1167877348#west", "8947803941", "2744514583", "praca"),
        ("402968134", "4053646850", "4086937778", "europa"),
        ("602306729", "8947803944", "4053646850", "benjamim"),
        ("602306736", "8947803942", "8947803944", "benjamim"),
        ("602306739", "8947803946", "8947803944", "europa"),
        ("602306742", "8947803946", "8947803941", "benjamim"),
        ("602306752", "4086937778", "8947803946", "benjamim"),
    )
    for edge_id, first, last, road in sections:
        shape = f"{coordinates[first]} {coordinates[last]}"
        if edge_id == "402968133#west":
            shape = f"{coordinates[first]} 4677.90,3053.95 {coordinates[last]}"
        if edge_id == "602306736":
            shape = f"{coordinates[first]} 4681.98,3044.50 {coordinates[last]}"
        ET.SubElement(edges, "edge", id=edge_id, **{
            "from": first, "to": last, "numLanes": "2" if road == "benjamim" else "1",
            "speed": "13.89" if road == "benjamim" else (europa_speed if road == "europa" else residential_speed),
            "width": "3.2", "priority": "8" if road != "praca" else "3",
            "name": {"europa": "Avenida Europa", "benjamim": "Avenida Benjamim Magalhães", "praca": "Praça das Nações"}[road],
            "spreadType": "center", "disallow": road_disallowed, "shape": shape,
        })
    # A restrição vale na conexão entre vias originais, antes de agrupá-las.
    for first, last in (("602306729", "402968134"), ("602306752", "602306739")):
        ET.SubElement(connections, "delete", **{"from": first, "to": last})
    ET.SubElement(nodes, "join", id="FAM_EUROPA_BENJAMIM",
                  nodes="8947803947 8947803946 4086937778 8947803941 8947803944 8947803942 4053646850",
                  type="traffic_light", tl="8947803947", reset="false")
    patches = {kind: ET.tostring(element, encoding="unicode")
               for kind, element in (("nod", nodes), ("edg", edges), ("con", connections))}
    result = _apply_local_patch(source, patches, ("--tls.rebuild", "true",
                                "--tls.cycle.time", "90", "--tls.yellow.time", "6",
                                "--tls.allred.time", "5", "--tls.layout", "incoming"))
    # Confere o conjunto de movimentos obtido das vias e restrições, evitando
    # que o agrupamento acrescente retornos ou esquerdas proibidas.
    allowed = {
        "403166945#2": {"602306733#west", "602306725#east", "602306745#west", "1167877348#west"},
        "402968133#west": {"602306749#0", "602306725#east", "602306745#west", "1167877348#west"},
        "30621478#east": {"602306749#0", "602306745#west", "1167877348#west"},
        "402968127#west": {"602306733#west", "602306725#east"},
        "269160814#west": {"602306733#west", "602306725#east"},
    }
    rebuilt = ET.fromstring(result)
    connections = ET.Element("connections")
    for connection in rebuilt.findall("connection"):
        if connection.get("from") in allowed:
            ET.SubElement(connections, "delete", **{
                "from": connection.get("from"), "to": connection.get("to")})
    lane_pairs = (
        ("403166945#2", "602306733#west", 0, 0),
        ("403166945#2", "602306725#east", 0, 1),
        ("403166945#2", "602306745#west", 0, 0),
        ("403166945#2", "1167877348#west", 0, 0),
        ("402968133#west", "602306749#0", 0, 0),
        ("402968133#west", "602306725#east", 0, 0),
        ("402968133#west", "602306745#west", 0, 1),
        ("402968133#west", "1167877348#west", 0, 0),
        ("30621478#east", "602306749#0", 0, 0),
        ("30621478#east", "602306745#west", 0, 0),
        ("30621478#east", "602306745#west", 1, 1),
        ("30621478#east", "1167877348#west", 0, 0),
        ("402968127#west", "602306733#west", 0, 0),
        ("402968127#west", "602306725#east", 0, 0),
        ("402968127#west", "602306725#east", 1, 1),
        ("269160814#west", "602306733#west", 0, 0),
        ("269160814#west", "602306725#east", 0, 0),
    )
    for first, last, from_lane, to_lane in lane_pairs:
        ET.SubElement(connections, "connection", **{
            "from": first, "to": last, "fromLane": str(from_lane), "toLane": str(to_lane)})
    # O netconvert resolve o join antes das connections. Por isso a restrição
    # é reiterada no conjunto final de aproximações, com faixas explícitas.
    result = _apply_local_patch(result, {"con": ET.tostring(connections, encoding="unicode")},
                               ("--tls.rebuild", "true", "--tls.cycle.time", "90",
                                "--tls.yellow.time", "6", "--tls.allred.time", "5", "--tls.layout", "incoming"))
    rebuilt = ET.fromstring(result)
    actual = {}
    links = []
    for connection in rebuilt.findall("connection"):
        if connection.get("tl") == "8947803947":
            actual.setdefault(connection.get("from"), set()).add(connection.get("to"))
            links.append(connection)
    if actual != allowed or len(links) != len(lane_pairs):
        raise ValueError(f"Movimentos Europa × Benjamim divergem das vias/restrições: {actual}")
    return result


def _complete_suica_junctions(source):
    """Reúne três cruzamentos físicos conferidos no OSM e na imagem Esri de 26/11/2023.

    Europa, Atenas e Austrália atravessam as pistas da Suíça no mesmo miolo.
    As arestas de 20 cm eram fragmentos internos, incapazes de armazenar veículos.
    reset=false mantém os movimentos carregados; não acrescenta semáforo nem
    programação. O SUMO recalcula conflitos e retenções no espaço completo.
    """
    joins=(
      ('EUROPA_SUICA','4053646858 4053646862 4053646870 1561880602'),
      ('ATENAS_SUICA','2042691601 4125318226'),
      ('AUSTRALIA_SUICA','1561880700 2042691942 2744514589 2744514592'),
    )
    nodes='<nodes>'+''.join(f'<join id="{name}" nodes="{members}" reset="false"/>' for name,members in joins)+'</nodes>'
    # Conserva também as escolhas de faixa dos movimentos de Austrália.
    # O heurístico do join prefere a faixa 0 em duas curvas; a fonte tinha 1.
    connections = '''<connections>
      <delete from="269160815#3" to="30648910#3"/>
      <connection from="269160815#3" to="30648910#3" fromLane="0" toLane="1"/>
      <delete from="299469392#0" to="30648910#3"/>
      <connection from="299469392#0" to="30648910#3" fromLane="0" toLane="1"/>
      <delete from="30648910#1" to="299469392#2"/>
      <connection from="30648910#1" to="299469392#2" fromLane="0" toLane="0"/>
      <connection from="30648910#1" to="299469392#2" fromLane="1" toLane="0"/>
      <delete from="307152129#5" to="30648910#3"/>
      <connection from="307152129#5" to="30648910#3" fromLane="0" toLane="0"/>
      <connection from="307152129#5" to="30648910#3" fromLane="0" toLane="1"/>
    </connections>'''
    joined = _apply_local_patch(source,{'nod':nodes})
    # As esperas internas geradas no miolo não abrigam veículos longos:
    # a cauda do ônibus alcança a pista preferencial oposta.
    # contPos=0 conserva a cessão e os foes, mas aguarda na linha da entrada.
    waits=(
      ('299469392#0','30648910#3','1'),
      ('299469392#0','307152129#7','0'),
      ('307152129#5','269160815#5','0'),
      ('307152129#5','299469392#2','0'),
      ('402968135#0','299469392#0','0'),
      ('402968136#8','30648041#11','0'),
      ('402968136#8','402968141#2','0'),
      ('402968141#1','-30648041#9','0'),
      ('402968141#1','402968136#9','0'),
      ('665897547','402968136#0','0'),
      ('665897547','402968135#2','0'),
    )
    connections=connections.replace('</connections>',''.join(
        f'<connection from="{a}" to="{b}" fromLane="0" toLane="{lane}" contPos="0" keepClear="true"/>'
        for a,b,lane in waits)+'</connections>')
    return _apply_local_patch(joined,{'con':connections})


def _join_cesario_parana(source):
    """Unifica os três pontos do único miolo Cesário × Paraná.

    OSM 339114019/7963056110/7963056109 e foto WorldView-3 de 26/11/2023
    mostram uma só abertura sem separador entre os três nós, distantes 8–15 m.
    Os conectores 853749385/386 e 602306713#22 atravessavam esse espaço como
    ruas externas de 0,20–1,18 m, causando reconvergência artificial de rotas.
    Mantém sentidos, retenções externas e o controlador FAM_CESARIO_PARANA.
    O programa current conserva seu regime O; não é um plano SETTRAN real.
    """
    nodes = '<nodes><join id="FAM_CESARIO_PARANA_JUNCTION" nodes="339114019 7963056110 7963056109" type="traffic_light" tl="FAM_CESARIO_PARANA" reset="false"/></nodes>'
    result = _apply_local_patch(source, {"nod": nodes})
    # As duas branches de Paraná vindo de Brasil deixam de ser caminhos
    # externos distintos para o mesmo destino; os movimentos físicos continuam.
    root = ET.fromstring(result)
    expected = {
        ("154252437#1", "665897572"),
        ("602306713#21", "665897572"), ("602306713#21", "901328279#0"),
        ("665897556#1", "665897572"), ("665897556#1", "901328279#0"),
    }
    connections = ET.Element("connections")
    origins = {first for first, _ in expected}
    for c in root.findall("connection"):
        if c.get("from") in origins:
            ET.SubElement(connections, "delete", **{"from": c.get("from"), "to": c.get("to")})
    for first, last in sorted(expected):
        ET.SubElement(connections, "connection", **{
            "from": first, "to": last, "fromLane": "0", "toLane": "0"})
    for origin in ("154252437#1", "602306713#21", "665897556#1"):
        ET.SubElement(connections, "crossing", node="FAM_CESARIO_PARANA_JUNCTION", edges=origin, width="4")
    nodes = '<nodes><node id="FAM_CESARIO_PARANA_JUNCTION" type="traffic_light" tl="FAM_CESARIO_PARANA"/></nodes>'
    tls = '<tlLogics><tlLogic id="FAM_CESARIO_PARANA" type="static" programID="current" offset="0"><phase duration="1" state="OOOOOrrr"/></tlLogic></tlLogics>'
    result = _apply_local_patch(result, {"nod": nodes,
                                "con": ET.tostring(connections, encoding="unicode"), "tll": tls}, ("--walkingareas", "true"))
    root = ET.fromstring(result)
    actual = {(c.get("from"), c.get("to")) for c in root.findall("connection")
              if c.get("tl") == "FAM_CESARIO_PARANA" and not c.get("from").startswith(':')}
    controlled = [c for c in root.findall("connection") if c.get("tl") == "FAM_CESARIO_PARANA"]
    if actual != expected or len(controlled) != 8:
        raise ValueError(f"Movimentos Cesário × Paraná não preservados: {actual}")
    ordered = sorted(controlled, key=lambda c: int(c.get("linkIndex")))
    states = ''.join('r' if c.get('from').startswith(':') else
                     ('O' if c.get('state') in {'M', 'O'} else 'o') for c in ordered)
    original = _indexed(result, 'tlLogic')['FAM_CESARIO_PARANA']
    program = ('    <tlLogic id="FAM_CESARIO_PARANA" type="static" '
               'programID="current" offset="0">\n'
               f'        <phase duration="1" state="{states}" />\n    </tlLogic>\n')
    return result.replace(original, program, 1)


def _join_viena_suica(source):
    """Um único miolo Viena × Suíça, sem dois conectores externos de 0,20 m.

    OSM Rua Viena 30648048 cruza as pistas Suíça 402968141/402968136 na
    abertura 4125318252/1561880529 (7,30 m), confirmada pela imagem WV-3
    de 26/11/2023. Mantém todos os 16 pares viários anteriormente alcançáveis.
    """
    joined = _apply_local_patch(source, {"nod":
             '<nodes><join id="VIENA_SUICA" nodes="4125318252 1561880529" reset="false"/></nodes>'})
    connections = ET.Element("connections")
    # As quatro esperas internas de 6,96–8,74 m não abrigam ônibus de 12 m;
    # conserva a cessão, aguardando na retenção externa em vez do meio da via.
    waits = (("402968136#0", "-30648048#0"), ("402968136#0", "402968141#10"),
             ("402968141#9", "30648048#2"), ("402968141#9", "402968136#1"))
    for first, last in waits:
        ET.SubElement(connections, "connection", **{
            "from": first, "to": last, "fromLane": "0", "toLane": "0",
            "contPos": "0", "keepClear": "true"})
    result = _apply_local_patch(joined, {"con": ET.tostring(connections, encoding="unicode")})
    root = ET.fromstring(result)
    origins = {"30648048#0", "-30648048#2", "402968141#9", "402968136#0"}
    destinations = {"-30648048#0", "30648048#2", "402968141#10", "402968136#1"}
    expected = {(first, last) for first in origins for last in destinations}
    actual = {(c.get('from'), c.get('to')) for c in root.findall('connection')
              if c.get('from') in origins and c.get('to') in destinations}
    if actual != expected:
        raise ValueError(f"Movimentos Viena alterados: {actual}")
    return result


def _join_niteroi(source):
    """Um único miolo físico Niterói, sem reter veículos no fragmento de20cm.

    Os canteiros terminam antes da abertura comum, conferida na imagem Esri de
    26/11/2023 e OSM338686240/597213618. Os controles1596/1597 fora do miolo
    permanecem separados. Cada ligação abaixo já era alcançável na fonte.
    Não cria movimentos, programa SETTRAN ou fase pedestre presumida.
    """
    node_id, tls_id = 'FAM_RONDON_NITEROI_JUNCTION', 'FAM_RONDON_NITEROI'
    result = _apply_local_patch(source, {'nod': f'<nodes><join id="{node_id}" nodes="338686240 597213618" reset="false"/></nodes>'})
    # Pares de faixas obtidos atravessando o antigo conector1156717174;
    # a ordenação mantém os grupos de aproximação explícitos e rastreáveis.
    pairs = (
        ('30622933#11','1156717175#0',0,0), ('30622933#11','1156717175#0',0,1),
        ('30622933#11','1156717177#0',0,0),
        ('30622933#11','1156717176',0,2), ('30622933#11','1156717176',0,3),
        ('930831032#1','1156717177#0',0,0),
        *(('930831032#1','1156717176',lane,lane) for lane in range(4)),
        *(('931572689','1156717175#0',lane,lane) for lane in range(4)),
        ('931572689','1156717177#0',3,0),
        ('931572689','1156717176',3,2), ('931572689','1156717176',3,3),
    )
    root=ET.fromstring(result);connections=ET.Element('connections')
    origins={pair[0] for pair in pairs}
    for c in root.findall('connection'):
        if c.get('from') in origins:
            ET.SubElement(connections,'delete',**{'from':c.get('from'),'to':c.get('to')})
    for first,last,start,end in pairs:
        ET.SubElement(connections,'connection',**{'from':first,'to':last,'fromLane':str(start),'toLane':str(end),'contPos':'0','keepClear':'true'})
    for road in ('30622933#11','1156717177#0'):
        ET.SubElement(connections,'crossing',node=node_id,edges=road,width='4')
    result=_apply_local_patch(result, {'nod':f'<nodes><node id="{node_id}" type="traffic_light" tl="{tls_id}"/></nodes>',
                   'con':ET.tostring(connections,encoding='unicode'),
                   'tll':f'<tlLogics><tlLogic id="{tls_id}" type="static" programID="current" offset="0"><phase duration="1" state="{"O"*17}rr"/></tlLogic></tlLogics>'}, ('--walkingareas','true'))
    # As prioridades são as do mesmo cruzamento não semaforizado: current
    # utiliza O/o. Copiar somente response exige foes e geometria idênticos.
    priority=_apply_local_patch(result,{'nod':f'<nodes><node id="{node_id}" type="priority"/></nodes>'}, ('--walkingareas','true'))
    native=ET.fromstring(priority);native_links={_key(c):c for c in native.findall('connection') if c.get('from') in origins}
    target=ET.fromstring(result);controlled=[c for c in target.findall('connection') if c.get('tl')==tls_id]
    expected={(first,last,str(start),str(end)) for first,last,start,end in pairs}
    if {_key(c) for c in controlled if not c.get('from').startswith(':')} != expected or len(controlled)!=19:
        raise ValueError('Movimentos físicos Niterói divergiram da fonte.')
    ordered=sorted(controlled,key=lambda c:int(c.get('linkIndex')))
    states=''.join('r' if c.get('from').startswith(':') else ('O' if native_links[_key(c)].get('state')=='M' else 'o') for c in ordered)
    old_program=_indexed(result,'tlLogic')[tls_id]
    program=f'    <tlLogic id="{tls_id}" type="static" programID="current" offset="0">\n        <phase duration="1" state="{states}" />\n    </tlLogic>\n'
    result=result.replace(old_program,program,1)
    old_node=_indexed(result,'junction')[node_id];new_node=ET.fromstring(old_node)
    native_node=native.find(f"junction[@id='{node_id}']")
    for request in new_node.findall('request'):
        reference=native_node.find(f"request[@index='{request.get('index')}']")
        if request.get('foes')!=reference.get('foes'):
            raise ValueError('Conflitos físicos Niterói divergiram da referência priority.')
        request.set('response',reference.get('response'))
    ET.indent(new_node,space='    ',level=1)
    return result.replace(old_node,'    '+ET.tostring(new_node,encoding='unicode')+'\n',1)


def _join_rotary(source):
    """Unifica o miolo Europa × Rotary Club, separado de Europa × Suíça.

    OSM 665897549 é Rua Rotary Club entre as pistas da Avenida Europa;
    a imagem WV-3 de 26/11/2023 confirma a abertura única de 8,42 m entre
    338677202/4055449706. O miolo Suíça fica cerca de 27 m adiante.
    Conserva os nove movimentos externos e todos os programas existentes.
    """
    original = ET.fromstring(source)
    roads = {e.get('id'): e for e in original.findall('edge')}
    # O caminho real cruza o centro OSM 665897549. O heurístico do join corta
    # a esquerda cedo demais, deixando a cauda do ônibus na pista contrária.
    # Conserva a geometria composta da fonte, sem desenhar uma curva empírica.
    points = []
    for first, last in (("402968147#2", "665897549"), ("665897549", "30622679#0")):
        connection = next(c for c in original.findall('connection')
                          if c.get('from') == first and c.get('to') == last)
        edge_id, lane_index = connection.get('via').rsplit('_', 1)
        lane = roads[edge_id].find(f"lane[@index='{lane_index}']")
        points.extend(lane.get('shape').split())
        if last == "665897549":
            points.extend(roads[last].find("lane").get("shape").split())
    joined = _apply_local_patch(source, {"nod":
              '<nodes><join id="EUROPA_ROTARY_CLUB" nodes="338677202 4055449706" reset="false"/></nodes>'})
    root = ET.fromstring(joined)
    roads = {e.get('id'): e for e in root.findall('edge')}
    points = [roads['402968147#2'].find('lane').get('shape').split()[-1], *points,
              roads['30622679#0'].find('lane').get('shape').split()[0]]
    curve = []
    for point in points:
        if not curve or curve[-1] != point:
            curve.append(point)
    connections = ET.Element("connections")
    ET.SubElement(connections, "connection", **{
        "from": "402968147#2", "to": "30622679#0", "fromLane": "0", "toLane": "0",
        "shape": ' '.join(curve)})
    # Esperas de 1,01/6,38 m não abrigam ônibus de 12 m: a cessão permanece
    # na retenção de entrada. Foes e prioridades são recompilados pelo SUMO.
    for first, last in (("-30622679#0", "30622679#0"), ("402968135#2", "665897547")):
        ET.SubElement(connections, "connection", **{
            "from": first, "to": last, "fromLane": "0", "toLane": "0",
            "contPos": "0", "keepClear": "true"})
    result = _apply_local_patch(joined, {"con": ET.tostring(connections, encoding="unicode")})
    root = ET.fromstring(result)
    origins = {"402968135#2", "402968147#2", "-30622679#0"}
    destinations = {"665897547", "402968139#0", "30622679#0"}
    expected = {(first, last) for first in origins for last in destinations}
    actual = {(c.get('from'), c.get('to')) for c in root.findall('connection')
              if c.get('from') in origins and c.get('to') in destinations}
    if actual != expected:
        raise ValueError(f"Movimentos Rotary alterados: {actual}")
    return result


def _complete_maranhao_crossings(source):
    """Representa as duas zebras existentes, sem presumir atendimento pedestre.

    WV03/26-11-2023 e OSM3391594553/54 confirmam as zebras junto às duas
    retenções do controle veicular já agrupado. DOM4792/2015 p.33 confirma
    o semáforo. A associação segue os nós/TLS existentes; não é cadastro
    comprovado de grupos focais pedestres nem programação real.
    """
    tls_id = 'FAM_MARANHAO_MONSENHOR_EDUARDO'
    root = ET.fromstring(source)
    roads = {e.get('id'): e for e in root.findall('edge') if e.get('function') is None}
    junctions = {j.get('id'): j for j in root.findall('junction')}
    original = root.find(f"tlLogic[@id='{tls_id}']")
    nodes, edges, connections = ET.Element('nodes'), ET.Element('edges'), ET.Element('connections')
    for node_id, road_id, index in (('3391594553', '30620737#14', '3'),
                                    ('3391594554', '261533405#17', '4')):
        junction = junctions[node_id]
        road = roads[road_id]
        shape = [tuple(map(float, p.split(','))) for p in road.find('lane').get('shape').split()]
        (ax, ay), (bx, by) = shape[-2:]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy)
        x, y = float(junction.get('x')), float(junction.get('y'))
        lateral = len(road.findall('lane')) * 3.2 / 2 + 3
        for side, sign in enumerate((-1, 1)):
            ped_id = f'{node_id}.ped.{road_id}.{side}'
            px, py = x + sign * dy / norm * lateral, y - sign * dx / norm * lateral
            ET.SubElement(nodes, 'node', id=ped_id, x=f'{px:.2f}', y=f'{py:.2f}', type='priority')
            ET.SubElement(edges, 'edge', {'id': ped_id, 'from': ped_id, 'to': node_id,
                          'numLanes': '1', 'speed': '1.4', 'width': '2', 'allow': 'pedestrian'})
        for road in roads.values():
            if node_id not in (road.get('from'), road.get('to')):
                continue
            edge = ET.SubElement(edges, 'edge', id=road.get('id'))
            for lane in road.findall('lane'):
                denied = set(lane.get('disallow', '').split()) | {'pedestrian'}
                ET.SubElement(edge, 'lane', index=lane.get('index'), disallow=' '.join(sorted(denied)))
        ET.SubElement(connections, 'crossing', node=node_id, edges=road_id,
                      width='4', linkIndex=index, linkIndex2=index)
    tls = ET.Element('tlLogics')
    program = ET.fromstring(ET.tostring(original, encoding='unicode'))
    for phase in program.findall('phase'):
        phase.set('state', phase.get('state') + 'rr')
    tls.append(program)
    for link in root.findall('connection'):
        if link.get('tl') == tls_id:
            ET.SubElement(tls, 'connection', {k: link.get(k) for k in
                          ('from', 'to', 'fromLane', 'toLane', 'tl', 'linkIndex')})
    rebuilt = _apply_local_patch(source, {'nod': ET.tostring(nodes, encoding='unicode'),
                   'edg': ET.tostring(edges, encoding='unicode'),
                   'con': ET.tostring(connections, encoding='unicode'),
                   'tll': ET.tostring(tls, encoding='unicode')}, ('--walkingareas', 'true'))
    before = {_key(c): (c.get('tl'), c.get('linkIndex')) for c in root.findall('connection')
              if c.get('from') in roads}
    after = {_key(c): (c.get('tl'), c.get('linkIndex')) for c in ET.fromstring(rebuilt).findall('connection')
             if c.get('from') in roads}
    if before != after:
        raise ValueError('As zebras Maranhão alteraram os movimentos ou controlledLinks veiculares.')
    new = ET.fromstring(rebuilt).find(f"tlLogic[@id='{tls_id}']")
    if [(p.get('duration'), p.get('state')[:3]) for p in new.findall('phase')] != [
            (p.get('duration'), p.get('state')) for p in original.findall('phase')]:
        raise ValueError('As zebras Maranhão alteraram cores/tempos veiculares.')
    return rebuilt


def _restore_isolated_crossing_envelopes(source):
    """Acessos pedestres sintéticos não devem deslocar retenções reais.

    Envelopes recompilados com as mesmas roads, faixas e zebras de 4 m,
    retirando apenas os footstubs diagonais. Conserva os vinte e um heads
    e três contornos de Anselmo/João com deslocamento artificial >4 m.
    Ilhas, convergências, TLS agrupados, programas e limites são conservados.
    PlainXML shape evita que uma rota pedestre aumente o leito viário.
    """
    shapes = {
        '13738551275': '3379.75,3089.70 3392.31,3087.24 3391.45,3083.17 3378.97,3086.04',
        '13738551276': '3399.05,3085.75 3405.34,3084.58 3404.61,3080.65 3398.32,3081.82',
        '3050761411': '3270.98,1969.13 3274.20,1963.60 3270.66,1961.66 3267.72,1967.34',
        '338654991': '3281.68,1994.07 3284.18,1988.17 3283.76,1988.00 3283.61,1987.95 3283.46,1987.90 3283.27,1987.86 3283.02,1987.81',
        '3386573294': '3646.80,3587.44 3656.78,3579.42 3646.26,3586.72',
        '3386573296': '3624.66,3574.47 3622.75,3571.90 3619.54,3574.28 3621.45,3576.86',
        '3386573297': '3678.67,3557.56 3671.60,3546.90 3669.69,3549.15 3669.34,3550.28 3668.98,3551.39 3668.29,3552.47 3666.96,3553.49 3670.11,3559.06 3673.21,3558.26 3674.45,3558.41 3675.69,3558.54 3677.05,3558.36',
        '3386573298': '3643.91,3552.32 3654.35,3544.92 3652.00,3541.63 3641.61,3549.10',
        '3386573305': '3401.93,3193.54 3414.26,3190.10 3413.06,3186.10 3400.88,3190.02',
        '3386573306': '3410.85,3149.02 3417.17,3147.98 3416.47,3144.00 3410.18,3145.18',
        '5494111589': '3243.07,2296.18 3255.87,2296.16 3255.86,2292.15 3243.06,2292.19',
        '5494111594': '3256.28,2242.64 3243.53,2241.49 3243.48,2242.47',
        '5494111596': '3292.50,2671.83 3304.67,2667.89 3303.51,2664.18 3291.27,2667.93',
        '5494111597': '3305.85,2657.01 3318.02,2653.04 3316.89,2649.42 3304.62,2653.06',
        '5494111603': '3416.06,3174.82 3422.31,3173.44 3421.39,3169.50 3415.18,3171.03',
        '5525815656': '3264.10,2247.45 3267.16,2241.83 3262.46,2246.18 3263.00,2246.73 3263.20,2246.91 3263.43,2247.07 3263.71,2247.24',
        '8622218071': '3353.13,2756.87 3351.00,2754.48 3348.01,2757.14 3350.15,2759.53',
        '8622218072': '3331.84,2765.70 3344.30,2762.75 3343.39,2758.87 3330.92,2761.79',
        '8622218073': '3320.76,2795.89 3333.35,2793.56 3332.61,2789.61 3320.03,2791.98',
        'FAM_RIO_NE': '3759.63,3705.56 3768.52,3696.34 3758.78,3704.64 3759.08,3704.99 3759.19,3705.11 3759.30,3705.23 3759.44,3705.37',
        'FAM_RIO_SW': '3741.49,3713.81 3751.34,3705.65 3748.79,3702.57 3738.93,3710.73',
        '2651934389': '3248.94,1997.60 3261.40,1994.71 3261.34,1992.57 3261.72,1991.86 3262.37,1991.38 3263.29,1991.13 3264.49,1991.11 3264.97,1984.73 3262.97,1984.36 3261.10,1983.55 3259.34,1982.30 3257.69,1980.62 3256.16,1978.50 3254.74,1975.94 3243.24,1981.57 3241.06,1985.84 3242.14,1992.14',
        '2783757296': '3266.31,2000.26 3278.82,1997.14 3278.94,1995.12 3279.32,1994.49 3279.93,1994.10 3280.75,1993.97 3281.79,1994.09 3283.12,1987.83 3280.35,1987.03 3277.90,1985.87 3275.78,1984.35 3273.99,1982.49 3272.52,1980.26 3271.39,1977.68 3262.33,1980.86 3262.63,1982.92 3262.33,1983.61 3261.74,1984.08 3260.85,1984.32 3259.67,1984.33 3259.19,1990.71 3262.64,1991.97 3263.96,1993.32 3265.01,1995.16 3265.80,1997.47',
        '5494111590': '3245.26,2279.09 3242.33,2277.77 3240.76,2277.48 3227.96,2277.72 3228.54,2291.61 3241.34,2291.92 3241.52,2289.08 3241.90,2287.01 3242.47,2285.34 3243.22,2283.71 3244.15,2281.75',
    }
    nodes = ET.Element("nodes")
    for node_id, shape in shapes.items():
        ET.SubElement(nodes, "node", id=node_id, shape=shape)
    original = ET.fromstring(source)
    junctions = {n.get("id"): n for n in original.findall("junction")}
    edge = original.find("edge[@id='1156717175#5']")
    head = junctions["5494111590"]
    origin = junctions[edge.get("from")]
    x, y = float(head.get("x")), float(head.get("y"))
    dx, dy = x - float(origin.get("x")), y - float(origin.get("y"))
    length = math.hypot(dx, dy)
    lateral = len(edge.findall("lane")) * 3.2 / 2 + 4
    # A zebra João atravessa a pista antes da alça. Entradas de calçada ficam
    # na transversal da zebra, sem o avanço longitudinal artificial anterior.
    for side, sign in enumerate((-1, 1)):
        ET.SubElement(nodes, "node", id=f"5494111590.ped.1156717175#5.{side}",
                      x=f"{x + sign * dy / length * lateral:.2f}",
                      y=f"{y - sign * dx / length * lateral:.2f}")
    rebuilt = _apply_local_patch(source, {"nod": ET.tostring(nodes, encoding="unicode")},
                                 ("--walkingareas", "true"))
    original = ET.fromstring(source)
    roads = {e.get("id") for e in original.findall("edge")
             if e.get("function") is None and ".ped." not in e.get("id")}
    assignments = lambda text: {_key(c): (c.get("tl"), c.get("linkIndex"))
                                for c in ET.fromstring(text).findall("connection")
                                if c.get("from") in roads}
    if assignments(source) != assignments(rebuilt):
        raise ValueError("Restaurar retenções alterou movimentos ou controlledLinks.")
    crossing_ids = lambda text: {e.get("id") for e in ET.fromstring(text).findall("edge")
                                 if e.get("function") == "crossing"}
    def indices(text):
        groups = {}
        for c in ET.fromstring(text).findall("connection"):
            if c.get("tl") is not None:
                groups.setdefault(c.get("tl"), set()).add(int(c.get("linkIndex")))
        return groups
    if crossing_ids(source) != crossing_ids(rebuilt) or indices(source) != indices(rebuilt):
        raise ValueError("Restaurar retenções removeu travessia ou controlledLink.")
    # O patch altera geometria. Cores e tempos da configuração de referência
    # continuam exatamente iguais, inclusive os links pedestres vermelhos.
    old_programs = _indexed(source, "tlLogic")
    for tls_id, block in _indexed(rebuilt, "tlLogic").items():
        if tls_id in old_programs:
            rebuilt = rebuilt.replace(block, old_programs[tls_id], 1)
    return rebuilt



def corrected_network_text(text):
    """Reproduz a correção física comum aos perfis, aceitando só revisões conhecidas."""
    if _digest(text) == CORRECTED_SHA256:
        return text
    if _digest(text) != FOUNDATION_SHA256:
        text = _control_infrastructure(_physical_delta(source_network_text(text)))
        if _digest(text) != FOUNDATION_SHA256:
            raise ValueError("Revisão intermediária diverge; usar netconvert 1.27.1.")
    for correction in (
        _restore_cross_streets,
        _correct_benjamim,
        _join_fragmented_junctions,
        _restore_maria_segismundo,
        _complete_rondon_widths,
        _complete_rio_and_loop,
        _collapse_short_signal_approaches,
        _complete_documented_crossings,
        _align_connector_priorities,
        _restore_europa_benjamim,
        _complete_suica_junctions,
        _join_rotary,
        _join_cesario_parana,
        _join_viena_suica,
        _join_niteroi,
        _align_connector_priorities,
        _complete_maranhao_crossings,
        _restore_isolated_crossing_envelopes,
    ):
        text = correction(text)
    if _digest(text) != CORRECTED_SHA256:
        raise ValueError("Resultado difere da revisão comprovada; usar netconvert 1.27.1.")
    return text


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--net-file", type=Path, default=NETWORK)
    parser.add_argument("--check", action="store_true", help="confere sem gravar a rede")
    args = parser.parse_args(argv)
    try:
        text = args.net_file.read_bytes().decode("utf-8")
        if args.check:
            if _digest(text) != CORRECTED_SHA256:
                raise ValueError("A rede não corresponde à infraestrutura comprovada.")
        else:
            corrected = corrected_network_text(text)
            if corrected != text:
                args.net_file.write_bytes(corrected.encode("utf-8"))
    except (OSError, ValueError, ET.ParseError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Erro: {error}\n")
    network = ET.fromstring(args.net_file.read_text(encoding="utf-8"))
    controlled = sum(c.get("tl") is not None for c in network.findall("connection"))
    print(f"Infraestrutura: {len(network.findall('tlLogic'))} TLS e "
          f"{controlled} connections controladas; correções locais conferidas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
