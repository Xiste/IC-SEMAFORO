"""Hashes e versões para reproduzir experimentos."""

import hashlib
import platform
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path
import traci
import sumolib
from semaforos.cenario.configuracao import sumo_executable


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


