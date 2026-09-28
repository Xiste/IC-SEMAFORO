"""Configura saídas passivas do SUMO e descreve a rede utilizada.

Entrada: rede e pasta exclusiva do episódio. Saída: additional.xml e opções
de saída nativa; usado por run_simulation antes de iniciar o SUMO.
"""

from pathlib import Path
import xml.etree.ElementTree as ET


def prepare_outputs(directory: Path, profile: str = "core") -> list[str]:
    """Core preserva viagens/eventos; full acrescenta séries individuais densas.

    Ambos observam a dinâmica existente. Nenhum perfil muda passos, sementes,
    controladores, veículos ou a frequência das fontes que mantém habilitadas.
    """
    if profile not in {"core", "full"}:
        raise ValueError("O perfil de métricas deve ser core ou full.")
    raw = directory / "raw"
    raw.mkdir(exist_ok=True)
    configuration = directory / "inputs" / "observations.add.xml"
    additional = ET.Element("additional")
    traffic_outputs = (("edgeData", "edges"), ("laneData", "lanes")) if profile == "full" else ()
    for tag, filename in traffic_outputs:
        ET.SubElement(additional, tag, {
            "id": f"observations_{filename}", "period": "1",
            "file": str(raw / f"{filename}.xml.gz"), "excludeEmpty": "true",
            "withInternal": "true",
        })
    # Duas fases podem ter o mesmo estado de luzes. Observar cada passo
    # preserva essas transições, que SaveTLSSwitchStates não registra.
    ET.SubElement(additional, "timedEvent", {
        "type": "SaveTLSStates", "dest": str(raw / "tls.xml.gz"),
    })
    ET.indent(additional)
    ET.ElementTree(additional).write(configuration, encoding="utf-8", xml_declaration=True)

    options = ["--additional-files", str(configuration), "--precision", "8"]
    files = {
        "summary-output": "summary.xml.gz",
        "tripinfo-output": "trips.xml.gz",
        "statistic-output": "statistics.xml",
        "queue-output": "queues.xml.gz",
        "lanechange-output": "lanechanges.xml.gz",
        "collision-output": "collisions.xml.gz",
        "vehroute-output": "vehicle_routes.xml.gz",
    }
    if profile == "full":
        files.update({"fcd-output": "fcd.xml.gz", "emission-output": "emissions.xml.gz"})
    for option, filename in files.items():
        options.extend([f"--{option}", str(raw / filename)])
    flags = [
        "tripinfo-output.write-unfinished", "tripinfo-output.write-undeparted",
        "vehroute-output.exit-times",
        "vehroute-output.write-unfinished", "vehroute-output.route-length",
    ]
    if profile == "full":
        flags.extend(["fcd-output.acceleration", "fcd-output.signals",
                      "fcd-output.distance", "fcd-output.speed-relative"])
    for option in flags:
        options.extend([f"--{option}", "true"])
    # O dispositivo mantém totais por viagem mesmo sem emission-output temporal.
    options.extend(["--device.emissions.probability", "1"])
    if profile == "full":
        options.extend(["--emission-output.precision", "8"])
    return options


def describe_network(path: Path) -> dict:
    """Preserva programas, fases e conexões para interpretar as medições."""
    root = ET.parse(path).getroot()
    edges = root.findall("edge")
    controllers = [
        {**logic.attrib, "phases": [phase.attrib for phase in logic.findall("phase")],
         "parameters": [param.attrib for param in logic.findall("param")]}
        for logic in root.findall("tlLogic")
    ]
    return {
        "edges": len(edges),
        "normal_edges": sum(edge.get("function") != "internal" for edge in edges),
        "lanes": sum(len(edge.findall("lane")) for edge in edges),
        "junctions": len(root.findall("junction")),
        "controllers": controllers,
        "controlled_connections": [connection.attrib for connection in root.findall("connection")
                                   if connection.get("tl") is not None],
        "location": root.find("location").attrib if root.find("location") is not None else {},
    }
