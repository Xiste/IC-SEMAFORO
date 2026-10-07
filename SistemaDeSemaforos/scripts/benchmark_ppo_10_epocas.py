"""Mede o piloto padrão com 10 épocas; não avalia convergência nem nove sinais."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from semaforos.cenario.configuracao import read_config
from semaforos.relatorios.catalogos import training_workload
from semaforos.experimentos.rl import train_rl, evaluate_rl


def main():
    config = read_config(ROOT / "config/cenario.json")
    config["ppo"]["gui"] = False
    config["ppo"]["n_epochs"] = 10
    config["metrics"]["collect_emissions"] = True
    folder = ROOT / "resultados/benchmark_10_epocas_20261006"
    summary = train_rl(config, folder)
    result = {"scope": "Piloto: um controlador nominal, demanda sintética, SUMO-GUI desligado, emissões ligadas. Não comprova convergência.",
              "measurement_conditions": "Tempo de parede local; depende da carga de outras aplicações. Na medição de 06/10, testes de regressão executaram simultaneamente no início.",
              "config": config, "workload": training_workload(config), "training": summary,
              "result_folder": str(folder)}
    path = ROOT / "dados/auditoria/benchmark_ppo_10_epocas.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    evaluation = evaluate_rl(config, folder.parent / (folder.name + "_avaliacao"),
                              folder / "ppo_model.zip", seeds=[101])
    print(json.dumps({"evaluation_runs": len(evaluation["runs"]),
                      "same_demand": evaluation["same_planned_demand_per_seed"]}), flush=True)


if __name__ == "__main__":
    main()
