"""Construção do PPO; o ciclo SUMO, os relatórios e a avaliação são compartilhados."""

from stable_baselines3 import PPO
from .registro import Algorithm


def constructor_parameters(config):
    params = config.get("ppo", {})
    n_steps = int(params.get("n_steps", 128))
    batch_size = int(params.get("batch_size", 64))
    n_epochs = int(params.get("n_epochs", 10))
    if min(n_steps, batch_size) < 2 or n_epochs < 1 or batch_size > n_steps:
        raise ValueError("Parâmetros PPO inválidos: confira coleta, minibatch e épocas")
    if n_steps % batch_size:
        raise ValueError("n_steps deve ser múltiplo de batch_size no piloto")
    return dict(policy="MlpPolicy", n_steps=n_steps, batch_size=batch_size,
                n_epochs=n_epochs, seed=config["seeds"][0], verbose=0,
                learning_rate=0.0003, gamma=0.99, gae_lambda=0.95,
                clip_range=0.2, ent_coef=0.0, vf_coef=0.5, max_grad_norm=0.5,
                policy_kwargs={"net_arch": {"pi": [64, 64], "vf": [64, 64]}})


PPO_ALGORITHM = Algorithm("PPO", PPO, "ppo", constructor_parameters)
