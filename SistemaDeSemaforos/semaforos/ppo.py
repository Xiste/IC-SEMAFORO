"""Treinamento e avaliação do PPO com o ambiente TraCI."""

import json
import hashlib
import platform
import subprocess
import sys
import time
from importlib.metadata import version
from pathlib import Path

import numpy as np
import traci
import sumolib
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback

from .ambiente_ppo import SemaforosEnv
from .configuracao import sumo_executable
from .metricas import trip_summary
from .relatorios import write_evaluation_report


def file_hash(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def versions():
    return {"python": sys.version.split()[0], "platform": platform.platform(),
            "sumo": subprocess.run([str(sumo_executable()), "--version"],
                                   capture_output=True, text=True, check=True).stdout.splitlines()[0],
            "stable_baselines3": version("stable-baselines3"),
            "gymnasium": version("gymnasium"),
            "traci_module": str(Path(traci.__file__).resolve()),
            "sumolib": getattr(sumolib, "__version__", "unknown")}


def queue_actuated_action(env):
    """Heurística reativa: favorece o verde com maior fila de entrada."""
    actions = []
    for target in env.targets:
        tls_id = target["tls_id"]
        current = traci.trafficlight.getPhase(tls_id)
        phases = env.programs[tls_id]
        if current not in target["phase_indices"]:
            actions.append(1)
            continue
        following = next((index for offset in range(1, len(phases) + 1)
                          if (index := (current + offset) % len(phases)) in target["phase_indices"]),
                         current)
        controlled_links = traci.trafficlight.getControlledLinks(tls_id)

        def halted(index):
            lanes = {connection[0] for link_index, color in enumerate(phases[index]["state"])
                     if color in "Gg" and link_index < len(controlled_links)
                     for connection in (controlled_links[link_index] or ())}
            return sum(traci.lane.getLastStepHaltingNumber(lane) for lane in lanes)

        current_queue, next_queue = halted(current), halted(following)
        actions.append(0 if current_queue < next_queue else
                       2 if current_queue > next_queue else 1)
    return np.asarray(actions, dtype=np.int64)


class ProgressCallback(BaseCallback):
    def __init__(self, output):
        super().__init__()
        self.output = Path(output)
        self.episodes = 0
        self.started = time.perf_counter()
        self.cancelled = False

    def _on_step(self):
        infos = self.locals.get("infos", [])
        for item in infos:
            if "unfinished" in item:
                self.episodes += 1
        if self.num_timesteps % 10 == 0 or (self.output / "cancel.flag").exists():
            progress = {"timesteps": self.num_timesteps, "episodes_completed": self.episodes,
                        "simulated_seconds_current_episode": infos[0].get("simulated_seconds") if infos else None,
                        "real_seconds": round(time.perf_counter() - self.started, 2)}
            (self.output / "progress.json").write_text(json.dumps(progress, indent=2), encoding="utf-8")
        if (self.output / "cancel.flag").exists():
            self.cancelled = True
            return False
        return True


def train_ppo(config, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    params = config.get("ppo", {})
    n_steps = int(params.get("n_steps", 128))
    batch_size = int(params.get("batch_size", 64))
    n_epochs = int(params.get("n_epochs", 10))
    total_steps = int(params.get("total_timesteps", 2048))
    if min(n_steps, batch_size, n_epochs, total_steps) < 1 or batch_size > n_steps:
        raise ValueError("Parâmetros PPO inválidos: verifique coleta, minibatch, épocas e total")
    if n_steps % batch_size:
        raise ValueError("n_steps deve ser múltiplo de batch_size no piloto")
    manifest = {"algorithm": "PPO", "network": str(config["network"]),
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
                        "decision_seconds": params.get("decision_seconds", 5)},
                "training_seed": config["seeds"][0],
                "evaluation_seeds": config.get("evaluation", {}).get("seeds", [])}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    env = SemaforosEnv(config, output / "episodes", gui=bool(params.get("gui", False)))
    callback = ProgressCallback(output)
    started = time.perf_counter()
    try:
        model = PPO("MlpPolicy", env, n_steps=n_steps, batch_size=batch_size,
                    n_epochs=n_epochs, seed=config["seeds"][0], verbose=0,
                    learning_rate=0.0003, gamma=0.99, gae_lambda=0.95,
                    clip_range=0.2, ent_coef=0.0, vf_coef=0.5,
                    max_grad_norm=0.5,
                    policy_kwargs={"net_arch": {"pi": [64, 64], "vf": [64, 64]}})
        manifest["ppo_effective"] = {"learning_rate": 0.0003, "gamma": 0.99,
            "gae_lambda": 0.95, "clip_range": 0.2, "ent_coef": 0.0,
            "vf_coef": 0.5, "max_grad_norm": 0.5, "normalize_advantage": True,
            "device": str(model.device), "policy": "MlpPolicy",
            "network_architecture": {"pi": [64, 64], "vf": [64, 64]},
            **manifest["ppo"]}
        (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        model.learn(total_timesteps=total_steps, callback=callback)
        model.save(str(output / "ppo_model"))
        summary = {"algorithm": "PPO", "timesteps": model.num_timesteps,
                   "episodes_completed": callback.episodes, "cancelled": callback.cancelled,
                   "real_seconds": round(time.perf_counter() - started, 2),
                   "model": str(output / "ppo_model.zip")}
        (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return summary
    finally:
        env.close()


def evaluate_ppo(config, output, model_path, seeds=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    model_path = Path(model_path)
    training_manifest_path = model_path.parent / "manifest.json"
    training_manifest = json.loads(training_manifest_path.read_text(encoding="utf-8")) if training_manifest_path.is_file() else {}
    if training_manifest.get("targets") and training_manifest["targets"] != config["targets"]:
        raise ValueError("O modelo foi treinado com outros semáforos/fases")
    if training_manifest.get("objectives") and training_manifest["objectives"] != config.get("objectives"):
        raise ValueError("Pesos dos objetivos diferentes; treine outro modelo")
    if training_manifest.get("network_sha256") and training_manifest["network_sha256"] != file_hash(config["network"]):
        raise ValueError("A rede difere da usada no treinamento")
    if (training_manifest.get("mapping_sha256") and config.get("mapping_path")
            and training_manifest["mapping_sha256"] != file_hash(config["mapping_path"])):
        raise ValueError("O mapeamento difere do usado no treinamento")
    model = PPO.load(str(model_path))
    seeds = seeds or config.get("evaluation", {}).get("seeds") or config["seeds"]
    if training_manifest.get("training_seed") in seeds:
        raise ValueError("Use sementes de avaliação diferentes da semente do treino")
    rows = []
    signal_rows = []
    started = time.perf_counter()
    env = SemaforosEnv(config, output / "episodes", gui=bool(config.get("ppo", {}).get("gui", False)))
    try:
        for seed in seeds:
            for controller in ("network_reference", "queue_actuated", "PPO"):
                observation, _ = env.reset(seed=int(seed))
                episode_reward = 0.0
                while True:
                    if controller == "PPO":
                        action, _ = model.predict(observation, deterministic=True)
                    elif controller == "queue_actuated":
                        action = queue_actuated_action(env)
                    else:
                        action = np.ones(len(env.targets), dtype=np.int64)
                    observation, reward, done, truncated, info = env.step(action)
                    episode_reward += reward
                    if done or truncated:
                        env.close()
                        trips = trip_summary(env.current_output / "tripinfo.xml")
                        signals = info.pop("signals")
                        rows.append({"controller": controller, "seed": seed,
                                     "reward": episode_reward, **info, **trips})
                        for tls_id, values in signals.items():
                            signal_rows.append({"controller": controller, "seed": seed,
                                                "tls_id": tls_id, **{key: value for key, value in values.items()
                                                                     if key != "phase_seconds"},
                                                **{f"phase_{index}_seconds": seconds for index, seconds
                                                   in values["phase_seconds"].items()}})
                        break
        summary = write_evaluation_report(output, rows, signal_rows, {
            "real_seconds": round(time.perf_counter() - started, 2),
            "versions": versions(), "model_path": str(model_path),
            "network_sha256": file_hash(config["network"]),
            "plans_sha256": file_hash(config["plans"]),
            "mapping_sha256": file_hash(config["mapping_path"]) if config.get("mapping_path") else None,
            "evaluation_config": config,
            "evaluation_demand": config["demand"],
            "training_manifest": training_manifest,
        })
        return summary
    finally:
        env.close()
