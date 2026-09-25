"""Gera uma demanda random para o SUMO.

Entrada principal: rede, duração, período e diretório de saída.
Saída principal: random.trips.xml e random.rou.xml.
Uso normal: ``make demand-random`` ou uma chamada de ``simulation.py``.
"""

import argparse
import math
import os
from pathlib import Path
import random
import subprocess
import sys
from tempfile import TemporaryDirectory
import xml.etree.ElementTree as ET


DEFAULT_NET_FILE = (
    Path(__file__).resolve().parent
    / "uberlandia.vehicular.families.16_2_4.net.xml"
)
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "demandas"
DEFAULT_DURATION = 7200.0
DEFAULT_PERIOD = 1.5


def _find_random_trips() -> Path:
    """Retorna o randomTrips.py da instalação indicada por SUMO_HOME."""
    sumo_home = os.environ.get("SUMO_HOME")
    if not sumo_home:
        raise RuntimeError("Defina SUMO_HOME para o diretório da instalação SUMO.")

    script = Path(sumo_home).expanduser().resolve() / "tools" / "randomTrips.py"
    if not script.is_file():
        raise FileNotFoundError(f"randomTrips.py não encontrado em {script}")
    return script


def _validate_xml_output(path: Path, element: str) -> int:
    """Confere o XML produzido e retorna sua quantidade de viagens ou veículos."""
    if not path.is_file():
        raise RuntimeError(f"O SUMO não produziu o arquivo esperado: {path}")

    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise RuntimeError(f"O SUMO produziu XML inválido: {path}") from exc

    count = len(root.findall(element))
    if root.tag != "routes" or count == 0:
        raise RuntimeError(f"O SUMO não produziu demanda válida em {path}")
    return count


def generate_random_demand(
    *,
    net_file: Path | str = DEFAULT_NET_FILE,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    duration: float = DEFAULT_DURATION,
    period: float = DEFAULT_PERIOD,
) -> Path:
    """Gera os dois XMLs e retorna o random.rou.xml usado pela simulação."""
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("duration deve ser um número finito maior que zero.")
    if not math.isfinite(period) or period <= 0:
        raise ValueError("period deve ser um número finito maior que zero.")

    net_file = Path(net_file).expanduser().resolve()
    if not net_file.is_file():
        raise FileNotFoundError(f"Rede SUMO não encontrada: {net_file}")

    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    trips_file = output_dir / "random.trips.xml"
    routes_file = output_dir / "random.rou.xml"

    seed = random.randint(0, 2**31 - 1)
    random_trips = _find_random_trips()

    # A pasta temporária preserva a demanda anterior se a geração falhar.
    with TemporaryDirectory(prefix=".random-", dir=output_dir) as temporary:
        temporary_dir = Path(temporary)
        new_trips_file = temporary_dir / trips_file.name
        new_routes_file = temporary_dir / routes_file.name

        command = [
            sys.executable, str(random_trips),
            "--net-file", str(net_file),
            "--output-trip-file", str(new_trips_file),
            "--route-file", str(new_routes_file),
            "--begin", "0",
            "--end", str(duration),
            "--period", str(period),
            "--seed", str(seed),
            "--vehicle-class", "passenger",
            "--validate",
        ]
        subprocess.run(command, check=True)

        _validate_xml_output(new_trips_file, "trip")
        _validate_xml_output(new_routes_file, "vehicle")
        new_trips_file.replace(trips_file)
        new_routes_file.replace(routes_file)

    return routes_file


def main(argv: list[str] | None = None) -> int:
    """Executa o gerador pelo terminal."""
    parser = argparse.ArgumentParser(
        description="Gera random.trips.xml e random.rou.xml sem simular."
    )
    parser.add_argument("--net-file", type=Path, default=DEFAULT_NET_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION)
    parser.add_argument("--period", type=float, default=DEFAULT_PERIOD)
    args = parser.parse_args(argv)

    try:
        routes_file = generate_random_demand(**vars(args))
        vehicle_count = _validate_xml_output(routes_file, "vehicle")
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Erro ao gerar demanda random: {exc}", file=sys.stderr)
        return 1

    requested = args.duration / args.period
    print(
        f"Geração concluída: aproximadamente {requested:g} viagens solicitadas; "
        f"{vehicle_count} veículos com rota."
    )
    print(f"Demanda para o SUMO: {routes_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
