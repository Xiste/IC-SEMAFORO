"""Comandos para inspecionar, simular e treinar cenários SUMO."""

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path

from semaforos.configuracao import read_config, sumo_executable
from semaforos.rede import inventory
from semaforos.simulacao import run
from semaforos.treinamento import train


ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inspect", "options", "run", "train"))
    parser.add_argument("--config", default=str(ROOT / "config" / "cenario.json"))
    parser.add_argument("--candidate", help="JSON com durações das fases por ID:índice")
    parser.add_argument("--output", help="Pasta de saída da execução")
    args = parser.parse_args()
    if args.command == "options":
        print(subprocess.run([str(sumo_executable()), "--help"], check=True,
                             capture_output=True, text=True).stdout)
        return
    config = read_config(args.config)
    if args.command == "inspect":
        print(json.dumps(inventory(config), ensure_ascii=False, indent=2))
        return
    output = Path(args.output).resolve() if args.output else ROOT / "resultados" / datetime.now().strftime("%Y%m%d_%H%M%S")
    if output.exists():
        raise ValueError(f"A pasta de saída já existe: {output}")
    if args.command == "run":
        run(config, output, args.candidate)
    else:
        train(config, output)


if __name__ == "__main__":
    main()
