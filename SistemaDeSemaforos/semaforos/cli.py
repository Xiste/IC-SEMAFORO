"""Comandos para inspecionar, simular e treinar cenários SUMO."""
from semaforos.caminhos import PROJECT_ROOT

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from semaforos.cenario.configuracao import read_config, sumo_executable
from semaforos.cenario.rede import inventory
from semaforos.cenario.mapeamento import mapping_report, export_mapping_review, export_mapping_scaffold
from semaforos.simulacao.execucao import run
from semaforos.algoritmos.busca_surrogate import train


ROOT = PROJECT_ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inspect", "mapping", "mapping-review", "mapping-scaffold", "measurements", "options", "algorithms", "run", "run-reference", "train", "rl-train", "rl-eval", "ppo-train", "ppo-eval"))
    parser.add_argument("--config", default=str(ROOT / "config" / "cenario.json"))
    parser.add_argument("--candidate", help="JSON com durações das fases por ID:índice")
    parser.add_argument("--output", help="Pasta de saída da execução")
    parser.add_argument("--model", help="Arquivo de modelo .zip para rl-eval/ppo-eval")
    parser.add_argument("--algorithm", help="Nome do algoritmo registrado; padrão PPO")
    parser.add_argument("--measurements-file", help="CSV de contagens para o comando measurements")
    args = parser.parse_args()
    if args.command == "algorithms":
        from semaforos.algoritmos.registro import available_algorithms
        print(json.dumps(available_algorithms()))
        return
    if args.command == "options":
        print(subprocess.run([str(sumo_executable()), "--help"], check=True,
                             capture_output=True, text=True).stdout)
        return
    if args.command == "measurements":
        from semaforos.cenario.medicoes import DEFAULT_MEASUREMENTS, measurement_report
        print(json.dumps(measurement_report(args.measurements_file or DEFAULT_MEASUREMENTS),
                         ensure_ascii=False, indent=2))
        return
    config = read_config(args.config)
    if args.algorithm:
        config["algorithm"] = args.algorithm.upper()
    if args.command in ("ppo-train", "ppo-eval"):
        if args.algorithm and args.algorithm.upper() != "PPO":
            parser.error("Use rl-train/rl-eval para selecionar outro algoritmo")
        config["algorithm"] = "PPO"
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
    elif args.command == "mapping-scaffold":
        print(json.dumps(export_mapping_scaffold(config, output), ensure_ascii=False, indent=2))
    elif args.command == "run":
        run(config, output, args.candidate)
    elif args.command == "run-reference":
        from semaforos.experimentos.referencia import run_reference
        run_reference(config, output)
    elif args.command == "train":
        train(config, output)
    elif args.command in ("ppo-train", "rl-train"):
        from semaforos.experimentos.rl import train_rl
        print(json.dumps(train_rl(config, output), indent=2))
    else:
        if not args.model:
            parser.error("rl-eval/ppo-eval requer --model")
        from semaforos.experimentos.rl import evaluate_rl
        print(json.dumps(evaluate_rl(config, output, args.model), indent=2, default=str))


if __name__ == "__main__":
    main()
