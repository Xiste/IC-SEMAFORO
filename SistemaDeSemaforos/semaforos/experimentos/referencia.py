"""Executa o programa da rede e relata métricas sem treinar um algoritmo."""
import time
from pathlib import Path

import numpy as np

from semaforos.cenario.configuracao import control_parameters
from semaforos.simulacao.ambiente import SemaforosEnv
from semaforos.relatorios.catalogos import export_catalogs
from semaforos.relatorios.exportacao import write_evaluation_report
from semaforos.arquivos import write_json
from .proveniencia import versions
from semaforos.relatorios.episodios import append_episode, export_details
from semaforos.arquivos import read_json
from .tarefas import cancellation_requested


def run_reference(config, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    export_catalogs(output, config)
    env = SemaforosEnv(config, output / "episodes", gui=bool(control_parameters(config).get("gui", False)))
    rows, signals, flows = [], [], []
    intersections, crossings = [], []
    cancelled = False
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
                if cancellation_requested(output):
                    cancelled = True
                    break
            env.close()
            info = read_json(env.current_output / 'episode_metrics.json')
            append_episode(rows, signals, intersections, crossings, flows, info, 'network_reference', seed, reward)
            if cancelled:
                break
        export_details(output, intersections, crossings, flows)
        return write_evaluation_report(output, rows, signals, {"algorithm": "Referência", "config": config,
                                                               "cancelled": cancelled, "versions": versions(), "real_seconds": round(time.perf_counter() - started, 2)})
    finally:
        env.close()
