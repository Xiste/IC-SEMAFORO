"""Registro explícito de algoritmos compatíveis com o ciclo SB3/Gymnasium."""

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Algorithm:
    name: str
    model_class: type
    config_key: str
    constructor_parameters: Callable[[dict], dict]

    def create(self, env, config):
        return self.model_class(env=env, **self.constructor_parameters(config))

    def load(self, path):
        return self.model_class.load(str(path))


_ALGORITHMS = {}


def register_algorithm(algorithm):
    name = algorithm.name.upper()
    if name in _ALGORITHMS:
        raise ValueError(f"Algoritmo já registrado: {name}")
    for method in ("learn", "predict", "save", "load"):
        if not callable(getattr(algorithm.model_class, method, None)):
            raise TypeError(f"O modelo {name} precisa implementar {method}")
    _ALGORITHMS[name] = algorithm


def _ensure_builtins():
    if "PPO" not in _ALGORITHMS:
        from .ppo import PPO_ALGORITHM
        register_algorithm(PPO_ALGORITHM)


def available_algorithms():
    _ensure_builtins()
    return sorted(_ALGORITHMS)


def get_algorithm(name="PPO"):
    _ensure_builtins()
    try:
        return _ALGORITHMS[name.upper()]
    except KeyError:
        raise ValueError(f"Algoritmo desconhecido: {name}. Disponíveis: {', '.join(available_algorithms())}") from None
