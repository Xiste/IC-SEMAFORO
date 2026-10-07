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
                trips = trip_summary(Path(item["episode_output"]) / "tripinfo.xml") if item.get("episode_output") else {}
                self.episode_rows.append({"episode": self.episodes, "timesteps": self.num_timesteps,
                                          "reward": item.get("episode", {}).get("r"),
                                          **trips,
                                          **{key: value for key, value in item.items() if key not in ("signals", "flow_counts", "terminal_observation", "episode")}})
                import pandas as pd
                write_text(self.output / "training_episodes.csv", pd.DataFrame(self.episode_rows).to_csv(index=False))
        if self.num_timesteps % 10 == 0 or (self.output / "cancel.flag").exists():
            progress = {"timesteps": self.num_timesteps, "episodes_completed": self.episodes,
                        "simulated_seconds_current_episode": infos[0].get("simulated_seconds") if infos else None,
                        "real_seconds": round(time.perf_counter() - self.started, 2)}
            write_json(self.output / "progress.json", progress)
        if (self.output / "cancel.flag").exists():
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
        model_name = f"{algorithm.name.lower()}_model"
        model.save(str(output / model_name))
        summary = {"algorithm": algorithm.name, "timesteps": model.num_timesteps,
                   "episodes_completed": callback.episodes, "cancelled": callback.cancelled,
                   "real_seconds": round(time.perf_counter() - started, 2),
                   "model": str(output / f"{model_name}.zip")}
        write_json(output / "summary.json", summary)
        return summary
    finally:
        env.close()


def evaluate_rl(config, output, model_path, seeds=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    model_path = Path(model_path)
    training_manifest_path = model_path.parent / "manifest.json"
    training_manifest = json.loads(training_manifest_path.read_text(encoding="utf-8")) if training_manifest_path.is_file() else {}
    model_algorithm = training_manifest.get("algorithm", "PPO")
    if config.get("algorithm", model_algorithm).upper() != model_algorithm.upper():
        raise ValueError("O algoritmo selecionado difere do algoritmo do modelo")
    algorithm = get_algorithm(model_algorithm)
    action_mode, action_spec = phase_action_spec(config, network_programs(config["network"]))
    if training_manifest.get("action_mode", "green_extension") != action_mode:
        raise ValueError("O modo de ação mudou; treine um novo modelo PPO")
    if action_mode == "phase_durations" and training_manifest.get("action_spec") != action_spec:
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
    model = algorithm.load(model_path)
    seeds = seeds or config.get("evaluation", {}).get("seeds") or config["seeds"]
    if training_manifest.get("training_seed") in seeds:
        raise ValueError("Use sementes de avaliação diferentes da semente do treino")
    export_catalogs(output, config)
    rows = []
    signal_rows = []
    flow_rows = []
    started = time.perf_counter()
    control = config.get("control", config.get("ppo", {}))
    env = SemaforosEnv(config, output / "episodes", gui=bool(control.get("gui", False)))
    try:
        for seed in seeds:
            for controller in ("network_reference", "queue_actuated", algorithm.name):
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
                    if done or truncated:
                        env.close()
                        trips = trip_summary(env.current_output / "tripinfo.xml")
                        signals = info.pop("signals")
                        flow_rows.extend({"controller": controller, "seed": seed, **row} for row in info.pop("flow_counts", []))
                        rows.append({"controller": controller, "seed": seed,
                                     "reward": episode_reward, **info, **trips})
                        for tls_id, values in signals.items():
                            signal_rows.append({"controller": controller, "seed": seed,
                                                "tls_id": tls_id, **{key: value for key, value in values.items()
                                                                     if key != "phase_seconds"},
                                                **{f"phase_{index}_seconds": seconds for index, seconds
                                                   in values["phase_seconds"].items()}})
                        break
        if flow_rows:
            import pandas as pd
            pd.DataFrame(flow_rows).to_csv(output / "flow_counts.csv", index=False)
        summary = write_evaluation_report(output, rows, signal_rows, {
            "real_seconds": round(time.perf_counter() - started, 2),
            "versions": versions(), "model_path": str(model_path),
            "network_sha256": file_hash(config["network"]),
            "plans_sha256": file_hash(config["plans"]),
            "mapping_sha256": file_hash(config["mapping_path"]) if config.get("mapping_path") else None,
            "evaluation_config": config,
            "evaluation_demand": config["demand"],
            "training_manifest": training_manifest,
            "algorithm": algorithm.name,
        })
        return summary
    finally:
        env.close()
