"""Executa uma ou mais simulações SUMO.

Entrada principal: rede, demanda pronta e opções de execução.
Saída principal: um processo SUMO concluído para cada episódio.
Uso normal: ``make run-random``, que gera uma demanda nova por episódio.
"""

import argparse
import math
from pathlib import Path
import shutil
import subprocess
import sys

from .demand import (
    DEFAULT_DURATION,
    DEFAULT_NET_FILE,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PERIOD,
    generate_random_demand,
)


def run_simulation(
    *,
    net_file: Path | str,
    demand_file: Path | str,
    gui: bool = False,
    end: float | None = None,
) -> None:
    """Executa um episódio com uma demanda pronta."""
    if end is not None and (not math.isfinite(end) or end <= 0):
        raise ValueError("end deve ser um número finito maior que zero.")

    net_file = Path(net_file).expanduser().resolve()
    demand_file = Path(demand_file).expanduser().resolve()
    if not net_file.is_file():
        raise FileNotFoundError(f"Rede SUMO não encontrada: {net_file}")
    if not demand_file.is_file():
        raise FileNotFoundError(f"Demanda não encontrada: {demand_file}")

    program = "sumo-gui" if gui else "sumo"
    binary = shutil.which(program)
    if binary is None:
        raise FileNotFoundError(f"{program} não encontrado no PATH.")

    command = [
        binary,
        "--net-file", str(net_file),
        "--route-files", str(demand_file),
        "--begin", "0",
        "--no-step-log", "true",
    ]
    if end is not None:
        command.extend(["--end", str(end)])
    if gui:
        command.extend(["--start", "--quit-on-end"])

    subprocess.run(command, check=True)


def run_random_episodes(
    *,
    net_file: Path | str = DEFAULT_NET_FILE,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR / "episodios",
    episodes: int = 1,
    gui: bool = False,
    duration: float = DEFAULT_DURATION,
    period: float = DEFAULT_PERIOD,
    end: float | None = None,
) -> None:
    """Gera uma demanda nova e executa o SUMO em cada episódio."""
    if isinstance(episodes, bool) or not isinstance(episodes, int) or episodes < 1:
        raise ValueError("episodes deve ser um inteiro maior que zero.")
    if end is not None and (not math.isfinite(end) or end <= 0):
        raise ValueError("end deve ser um número finito maior que zero.")

    output_dir = Path(output_dir).expanduser().resolve()
    for episode in range(1, episodes + 1):
        print(f"Episódio {episode}/{episodes}: gerando demanda random.", flush=True)
        demand_file = generate_random_demand(
            net_file=net_file,
            output_dir=output_dir / f"episodio_{episode:03d}",
            duration=duration,
            period=period,
        )

        print(f"Episódio {episode}/{episodes}: executando SUMO.", flush=True)
        run_simulation(
            net_file=net_file,
            demand_file=demand_file,
            gui=gui,
            end=end,
        )


def main(argv: list[str] | None = None) -> int:
    """Executa episódios random pelo terminal."""
    parser = argparse.ArgumentParser(
        description="Executa episódios com uma demanda random nova em cada um."
    )
    parser.add_argument("--episodes", type=int, default=1)
    parser.add_argument("--gui", action="store_true")
    parser.add_argument("--net-file", type=Path, default=DEFAULT_NET_FILE)
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR / "episodios"
    )
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION)
    parser.add_argument("--period", type=float, default=DEFAULT_PERIOD)
    parser.add_argument("--end", type=float)
    args = parser.parse_args(argv)

    try:
        run_random_episodes(**vars(args))
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Erro ao executar episódios random: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Execução interrompida pelo usuário.", file=sys.stderr)
        return 130

    print(f"Execução concluída: {args.episodes} episódio(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
