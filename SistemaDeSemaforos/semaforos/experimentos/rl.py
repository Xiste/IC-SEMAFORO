"""Treinamento e avaliação compartilhados por algoritmos registrados."""

import json
import time
from pathlib import Path

import numpy as np
from stable_baselines3.common.callbacks import BaseCallback

from semaforos.simulacao.ambiente import SemaforosEnv
from semaforos.algoritmos.registro import get_algorithm
from semaforos.algoritmos.heuristicas import queue_actuated_action
from .proveniencia import file_hash, versions
from semaforos.relatorios.metricas import trip_summary
from semaforos.relatorios.catalogos import export_catalogs
from semaforos.relatorios.exportacao import write_evaluation_report
from semaforos.cenario.rede import network_programs, phase_action_spec
from semaforos.arquivos import write_json, write_text
from semaforos.arquivos import read_json
from semaforos.relatorios.episodios import scalar_metrics, append_episode, export_details, export_training_details
from .tarefas import cancellation_requested


class ProgressCallback(BaseCallback):
    def __init__(self, output):
        super().__init__()
        self.output = Path(output)
        self.episodes = 0
        self.started = time.perf_counter()
        self.cancelled = False
        self.episode_rows = []

    def _on_step(self):
        infos = self.locals.get("infos", [])
        for item in infos:
            if "unfinished" in item:
                self.episodes += 1
                trips = trip_summary(Path(item["episode_output"]) / "tripinfo.xml", item.get('measurement_start_seconds'),
                                     item.get('measurement_end_seconds')) if item.get("episode_output") else {}
                self.episode_rows.append({"episode": self.episodes, "timesteps": self.num_timesteps,
                                          "reward": item.get("episode", {}).get("r"),
                                          **trips,
                                          **scalar_metrics(item)})
                import pandas as pd
                write_text(self.output / "training_episodes.csv", pd.DataFrame(self.episode_rows).to_csv(index=False))
        if self.num_timesteps % 10 == 0 or cancellation_requested(self.output):
            progress = {"timesteps": self.num_timesteps, "episodes_completed": self.episodes,
                        "simulated_seconds_current_episode": infos[0].get("simulated_seconds") if infos else None,
                        "real_seconds": round(time.perf_counter() - self.started, 2)}
            write_json(self.output / "progress.json", progress)
        if cancellation_requested(self.output):
            self.cancelled = True
            return False
        return True


def train_rl(config, output):
    algorithm = get_algorithm(config.get("algorithm", "PPO"))
    constructor = algorithm.constructor_parameters(config)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    params = config.get(algorithm.config_key, {})
    control = config.get("control", config.get("ppo", {}))
    n_steps = constructor.get("n_steps")
    batch_size = constructor.get("batch_size")
    n_epochs = constructor.get("n_epochs")
    total_steps = int(params.get("total_timesteps", 2048))
    if total_steps < 1:
        raise ValueError("total_timesteps deve ser positivo")
    export_catalogs(output, config)
    manifest = {"algorithm": algorithm.name, "algorithm_parameters": constructor,
                "network": str(config["network"]),
                "plans": str(config["plans"]), "targets": config["targets"],
                "demand": config["demand"], "objectives": config.get("objectives"),
                "config": config, "versions": versions(),
                "network_sha256": file_hash(config["network"]),
                "plans_sha256": file_hash(config["plans"]),
                "mapping_sha256": file_hash(config["mapping_path"]) if config.get("mapping_path") else None,
                "simulation": {"duration_seconds": config["duration_seconds"],
                               "step_seconds": config["step_seconds"]},
                "ppo": {"n_steps": n_steps, "batch_size": batch_size,
                        "n_epochs": n_epochs, "total_timesteps": total_steps,
                        "decision_seconds": control.get("decision_seconds", 5)},
                "control": control,
                "training_seed": config["seeds"][0],
                "evaluation_seeds": config.get("evaluation", {}).get("seeds", [])}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    env = SemaforosEnv(config, output / "episodes", gui=bool(control.get("gui", False)))
    manifest.update(action_mode=env.action_mode, action_spec=env.action_spec)
    callback = ProgressCallback(output)
    started = time.perf_counter()
    try:
        model = algorithm.create(env, config)
        if algorithm.name == "PPO":
            manifest["ppo_effective"] = {**constructor,
                "normalize_advantage": model.normalize_advantage,
                "device": str(model.device),
                "network_architecture": constructor["policy_kwargs"]["net_arch"],
                **manifest["ppo"]}
        else:
            manifest.pop("ppo")
        manifest["algorithm_effective"] = {**constructor, "device": str(model.device)}
        (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        model.learn(total_timesteps=total_steps, callback=callback)
        env.close()
        partial = read_json(env.current_output / 'episode_metrics.json') if env.current_output else None
        if partial and not partial.get('episode_complete', True):
            import pandas as pd
            callback.episode_rows.append({'episode': callback.episodes + 1, 'timesteps': model.num_timesteps,
                                          **scalar_metrics(partial)})
            write_text(output / 'training_episodes.csv', pd.DataFrame(callback.episode_rows).to_csv(index=False))
            write_json(output / 'partial_episode.json', partial)
        export_training_details(output, algorithm.name)
        model_name = f"{algorithm.name.lower()}_model"
        model.save(str(output / model_name))
        summary = {"algorithm": algorithm.name, "timesteps": model.num_timesteps,
                   "episodes_completed": callback.episodes, "cancelled": callback.cancelled,
                   "partial_episode_saved": bool(partial and not partial.get('episode_complete', True)),
                   "real_seconds": round(time.perf_counter() - started, 2),
                   "model": str(output / f"{model_name}.zip")}
        write_json(output / "summary.json", summary)
        return summary
    finally:
        env.close()


def evaluate_rl(config, output, model_path=None, seeds=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    model_path = Path(model_path) if model_path else None
    training_manifest_path = model_path.parent / "manifest.json" if model_path else None
    training_manifest = json.loads(training_manifest_path.read_text(encoding="utf-8")) if training_manifest_path and training_manifest_path.is_file() else {}
    model_algorithm = training_manifest.get("algorithm", config.get("algorithm", "PPO"))
    if config.get("algorithm", model_algorithm).upper() != model_algorithm.upper():
        raise ValueError("O algoritmo selecionado difere do algoritmo do modelo")
    algorithm = get_algorithm(model_algorithm)
    action_mode, action_spec = phase_action_spec(config, network_programs(config["network"]))
    if model_path and training_manifest.get("action_mode", "green_extension") != action_mode:
        raise ValueError("O modo de ação mudou; treine um novo modelo PPO")
    if model_path and action_mode == "phase_durations" and training_manifest.get("action_spec") != action_spec:
        raise ValueError("As fases ou os limites de duração mudaram; treine um novo modelo PPO")
    if training_manifest.get("targets") and training_manifest["targets"] != config["targets"]:
        raise ValueError("O modelo foi treinado com outros semáforos/fases")
    if training_manifest.get("objectives") and training_manifest["objectives"] != config.get("objectives"):
        raise ValueError("Pesos dos objetivos diferentes; treine outro modelo")
    if training_manifest.get("network_sha256") and training_manifest["network_sha256"] != file_hash(config["network"]):
        raise ValueError("A rede difere da usada no treinamento")
    if (training_manifest.get("mapping_sha256") and config.get("mapping_path")
            and training_manifest["mapping_sha256"] != file_hash(config["mapping_path"])):
        raise ValueError("O mapeamento difere do usado no treinamento")
    model = algorithm.load(model_path) if model_path else None
    seeds = seeds or config.get("evaluation", {}).get("seeds") or config["seeds"]
    if len(set(seeds)) != len(seeds):
        raise ValueError('Sementes de avaliação devem ser distintas')
    if training_manifest.get("training_seed") in seeds:
        raise ValueError("Use sementes de avaliação diferentes da semente do treino")
    export_catalogs(output, config)
    rows = []
    signal_rows = []
    flow_rows = []
    intersection_rows, crossing_rows = [], []
    cancelled = False
    started = time.perf_counter()
    control = config.get("control", config.get("ppo", {}))
    env = SemaforosEnv(config, output / "episodes", gui=bool(control.get("gui", False)))
    try:
        for seed in seeds:
            for controller in (("network_reference", "queue_actuated", algorithm.name) if model else ("network_reference", "queue_actuated")):
                observation, _ = env.reset(seed=int(seed))
                episode_reward = 0.0
                while True:
                    if controller == algorithm.name:
                        action, _ = model.predict(observation, deterministic=True)
                    elif controller == "queue_actuated":
                        action = queue_actuated_action(env)
                    else:
                        action = np.ones(len(env.action_spec), dtype=np.int64)
                    observation, reward, done, truncated, info = env.step(action)
                    episode_reward += reward
                    cancelled = cancellation_requested(output)
                    if done or truncated or cancelled:
                        env.close()
                        info = read_json(env.current_output / 'episode_metrics.json')
                        append_episode(rows, signal_rows, intersection_rows, crossing_rows, flow_rows,
                                       info, controller, seed, episode_reward)
                        break
                if cancelled:
                    break
            if cancelled:
                break
        export_details(output, intersection_rows, crossing_rows, flow_rows)
        summary = write_evaluation_report(output, rows, signal_rows, {
            "real_seconds": round(time.perf_counter() - started, 2),
            "versions": versions(), "model_path": str(model_path) if model_path else None,
            "network_sha256": file_hash(config["network"]),
            "plans_sha256": file_hash(config["plans"]),
            "mapping_sha256": file_hash(config["mapping_path"]) if config.get("mapping_path") else None,
            "evaluation_config": config,
            "evaluation_demand": config["demand"],
            "evaluation_seeds": list(seeds),
            "training_manifest": training_manifest,
            "algorithm": algorithm.name if model else "Comparação sem treinamento",
            "cancelled": cancelled,
        })
        return summary
    finally:
        env.close()
