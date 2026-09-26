"""Gera uma demanda random para o SUMO.

Entrada principal: rede, duração, período, diretório e seed opcional.
Saída principal: random.trips.xml e random.rou.xml; metadados opcionais em memória.
Uso normal: ``make demand-random`` ou uma chamada do runner de simulação.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import math
import os
from pathlib import Path
import random
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import xml.etree.ElementTree as ET


DEFAULT_NET_FILE = (
    Path(__file__).resolve().parents[1]
    / "network"
    / "uberlandia.vehicular.families.16_2_4.net.xml"
)
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "demandas"
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
    seed: int | None = None,
    metadata: dict | None = None,
    log_file: Path | str | None = None,
) -> Path:
    """Gera os XMLs e retorna random.rou.xml; sem seed explícita, sorteia uma.

    O runner pode fornecer um dicionário para receber a origem e os parâmetros
    da geração. ``log_file`` guarda a saída da ferramenta quando solicitado;
    sem ele, a saída continua no terminal.
    """
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("duration deve ser um número finito maior que zero.")
    if not math.isfinite(period) or period <= 0:
        raise ValueError("period deve ser um número finito maior que zero.")
    if seed is not None and (
        isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**31
    ):
        raise ValueError("seed deve ser um inteiro entre 0 e 2147483647.")

    net_file = Path(net_file).expanduser().resolve()
    if not net_file.is_file():
        raise FileNotFoundError(f"Rede SUMO não encontrada: {net_file}")

    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    trips_file = output_dir / "random.trips.xml"
    routes_file = output_dir / "random.rou.xml"

    if seed is None:
        seed = random.randint(0, 2**31 - 1)
    started = time.perf_counter()
    if metadata is not None:
        metadata.update(
            seed=seed,
            demand_model="random",
            begin=0.0,
            duration=duration,
            period=period,
            vehicle_class="passenger",
            validate=True,
            vehicles_requested=math.ceil(duration / period),
            net_file=str(net_file),
            trips_file=str(trips_file),
            routes_file=str(routes_file),
            started_at_utc=datetime.now(timezone.utc).isoformat(),
        )

    try:
        random_trips = _find_random_trips()
        if metadata is not None:
            metadata.update(
                random_trips_file=str(random_trips),
                random_trips_sha256=hashlib.sha256(random_trips.read_bytes()).hexdigest(),
            )

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
            if metadata is not None:
                metadata["command"] = command
            if log_file is None:
                subprocess.run(command, check=True)
            else:
                log_file = Path(log_file).expanduser().resolve()
                log_file.parent.mkdir(parents=True, exist_ok=True)
                with log_file.open("w", encoding="utf-8") as log:
                    subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)

            trip_count = _validate_xml_output(new_trips_file, "trip")
            vehicle_count = _validate_xml_output(new_routes_file, "vehicle")
            new_trips_file.replace(trips_file)
            new_routes_file.replace(routes_file)
            if metadata is not None:
                metadata.update(trips_generated=trip_count, vehicles_generated=vehicle_count)
    finally:
        if metadata is not None:
            metadata.update(
                finished_at_utc=datetime.now(timezone.utc).isoformat(),
                duration_seconds=time.perf_counter() - started,
            )

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
    parser.add_argument("--seed", type=int, help="Seed explícita; por padrão, sorteia uma nova.")
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
