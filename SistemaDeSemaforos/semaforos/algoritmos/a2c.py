"""Adaptador A2C para o ambiente SUMO compartilhado."""

from stable_baselines3 import A2C

from .registro import Algorithm


DEFAULT_N_STEPS = 5


def constructor_parameters(config):
    n_steps = config.get("a2c", {}).get("n_steps", DEFAULT_N_STEPS)
    if type(n_steps) is not int or n_steps < 1:
        raise ValueError("Use pelo menos um passo por coleta no A2C")
    return {
        "policy": "MlpPolicy",
        "n_steps": n_steps,
        "seed": config["seeds"][0],
        "verbose": 0,
    }


A2C_ALGORITHM = Algorithm("A2C", A2C, "a2c", constructor_parameters)
