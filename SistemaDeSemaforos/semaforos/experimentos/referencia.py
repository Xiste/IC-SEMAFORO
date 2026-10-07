"""Executa o programa da rede e relata métricas sem treinar um algoritmo."""
import time
from pathlib import Path

import pandas as pd
import numpy as np

from semaforos.cenario.configuracao import control_parameters
from semaforos.simulacao.ambiente import SemaforosEnv
from semaforos.relatorios.catalogos import export_catalogs
from semaforos.relatorios.metricas import trip_summary
from semaforos.relatorios.exportacao import write_evaluation_report
from semaforos.arquivos import write_json
from .proveniencia import versions


def run_reference(config, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    export_catalogs(output, config)
    env = SemaforosEnv(config, output / "episodes", gui=bool(control_parameters(config).get("gui", False)))
    rows, signals, flows = [], [], []
    started = time.perf_counter()
    try:
        for seed in config["seeds"]:
            env.reset(seed=seed)
            done = False
            reward = 0.0
            while not done:
                _, value, done, _, info = env.step(np.ones(len(env.action_spec), dtype=np.int64))
                reward += value
                write_json(output / "progress.json", {"seed": seed, "simulated_seconds_current_episode": info["simulated_seconds"],
                                                        "real_seconds": round(time.perf_counter() - started, 2)})
                if (output / "cancel.flag").exists():
                    write_json(output / "summary.json", {"cancelled": True, "simulated_seconds": info["simulated_seconds"]})
                    return
            env.close()
            for row in info.pop("flow_counts", []):
                flows.append({"controller": "network_reference", "seed": seed, **row})
            for tls, row in info.pop("signals").items():
                signals.append({"controller": "network_reference", "seed": seed, "tls_id": tls,
                                **{k: v for k, v in row.items() if k != "phase_seconds"},
                                **{f"phase_{i}_seconds": t for i, t in row["phase_seconds"].items()}})
            rows.append({"controller": "network_reference", "seed": seed, "reward": reward,
                         **info, **trip_summary(env.current_output / "tripinfo.xml")})
        if flows:
            pd.DataFrame(flows).to_csv(output / "flow_counts.csv", index=False)
        return write_evaluation_report(output, rows, signals, {"algorithm": "Referência", "config": config,
                                                               "versions": versions(), "real_seconds": round(time.perf_counter() - started, 2)})
    finally:
        env.close()
