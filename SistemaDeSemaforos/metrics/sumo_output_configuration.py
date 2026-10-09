"""Configura as saídas passivas do SUMO conforme o perfil de coleta.

Entrada: perfil de coleta e pasta exclusiva do episódio. Saída: additional.xml e opções
de saída nativa; usado por run_simulation antes de iniciar o SUMO.
core observa os indicadores essenciais; full acrescenta fontes detalhadas.
A escolha do perfil muda a observação, mantendo o tempo e a dinâmica simulados.
"""

from pathlib import Path
import xml.etree.ElementTree as ET


def prepare_outputs(directory: Path, profile: str = "core") -> list[str]:
    """Core observa resultados globais; full também preserva detalhes individuais.

    Ambos observam a dinâmica existente. Nenhum perfil muda passos, sementes,
    controladores, veículos ou a frequência das fontes que mantém habilitadas.
    """
    if profile not in {"core", "full"}:
        raise ValueError("O perfil de métricas deve ser core ou full.")
    raw = directory / "raw"
    raw.mkdir(exist_ok=True)
    options = ["--precision", "8"]
    if profile == "full":
        configuration = directory / "inputs" / "observations.add.xml"
        additional = ET.Element("additional")
        for tag, filename in (("edgeData", "edges"), ("laneData", "lanes")):
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
        options.extend(["--additional-files", str(configuration)])

    files = {
        "summary-output": "summary.xml.gz",
        "tripinfo-output": "trips.xml.gz",
        "statistic-output": "statistics.xml",
        "queue-output": "queues.xml.gz",
    }
    if profile == "full":
        files.update({
            "lanechange-output": "lanechanges.xml.gz",
            "collision-output": "collisions.xml.gz",
            "vehroute-output": "vehicle_routes.xml.gz",
            "fcd-output": "fcd.xml.gz", "emission-output": "emissions.xml.gz",
        })
    for option, filename in files.items():
        options.extend([f"--{option}", str(raw / filename)])
    flags = [
        "tripinfo-output.write-unfinished", "tripinfo-output.write-undeparted",
    ]
    if profile == "full":
        flags.extend(["vehroute-output.exit-times", "vehroute-output.write-unfinished",
                      "vehroute-output.route-length", "fcd-output.acceleration", "fcd-output.signals",
                      "fcd-output.distance", "fcd-output.speed-relative"])
    for option in flags:
        options.extend([f"--{option}", "true"])
    if profile == "full":
        options.extend(["--device.emissions.probability", "1", "--emission-output.precision", "8"])
    return options
