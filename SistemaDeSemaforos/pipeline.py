"""Comandos para inspecionar, simular e treinar cenários SUMO."""

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from semaforos.configuracao import read_config, sumo_executable
from semaforos.rede import inventory
from semaforos.mapeamento import mapping_report, export_mapping_review
from semaforos.simulacao import run
from semaforos.treinamento import train


ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inspect", "mapping", "mapping-review", "measurements", "options", "run", "train", "ppo-train", "ppo-eval"))
    parser.add_argument("--config", default=str(ROOT / "config" / "cenario.json"))
    parser.add_argument("--candidate", help="JSON com durações das fases por ID:índice")
    parser.add_argument("--output", help="Pasta de saída da execução")
    parser.add_argument("--model", help="Arquivo ppo_model.zip para ppo-eval")
    parser.add_argument("--measurements-file", help="CSV de contagens para o comando measurements")
    args = parser.parse_args()
    if args.command == "options":
        print(subprocess.run([str(sumo_executable()), "--help"], check=True,
                             capture_output=True, text=True).stdout)
        return
    if args.command == "measurements":
        from semaforos.medicoes import DEFAULT_MEASUREMENTS, measurement_report
        print(json.dumps(measurement_report(args.measurements_file or DEFAULT_MEASUREMENTS),
                         ensure_ascii=False, indent=2))
        return
    config = read_config(args.config)
    if args.command == "inspect":
        print(json.dumps(inventory(config), ensure_ascii=False, indent=2))
        return
    if args.command == "mapping":
        print(json.dumps(mapping_report(config, config.get("mapping_path")), ensure_ascii=False, indent=2))
        return
    output = Path(args.output).resolve() if args.output else ROOT / "resultados" / (datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:8])
    if output.exists():
        raise ValueError(f"A pasta de saída já existe: {output}")
    if args.command == "mapping-review":
        print(json.dumps(export_mapping_review(config, output), ensure_ascii=False, indent=2))
    elif args.command == "run":
        run(config, output, args.candidate)
    elif args.command == "train":
        train(config, output)
    elif args.command == "ppo-train":
        from semaforos.ppo import train_ppo
        print(json.dumps(train_ppo(config, output), indent=2))
    else:
        if not args.model:
            parser.error("ppo-eval requer --model")
        from semaforos.ppo import evaluate_ppo
        print(json.dumps(evaluate_ppo(config, output, args.model), indent=2, default=str))


if __name__ == "__main__":
    main()
