"""Preserva uma única cópia verificável das entradas fixas do experimento.

Entrada: rede e executável SUMO; saída: baseline identificado pelo conteúdo.
O runner reutiliza esse baseline entre episódios, sem copiar a rede a cada vez.
"""

import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import xml.etree.ElementTree as ET

from ..metrics.storage import file_info, write_json
from ..metrics.sumo_outputs import describe_network


def prepare_baseline(net_file: Path, binary: str, output_root: Path) -> dict:
    """Cria snapshot imutável ou valida/reutiliza outro com o mesmo conteúdo."""
    project = Path(__file__).resolve().parents[2]
    code = {str(path.relative_to(project)): file_info(path)
            for path in sorted((project / "SistemaDeSemaforos").rglob("*.py"))}
    toolchain = {"sumo": {"path": binary, **file_info(Path(binary))}}
    random_trips = Path(os.environ.get("SUMO_HOME", "/usr/share/sumo")) / "tools/randomTrips.py"
    for name, path in (("randomTrips", random_trips),
                       ("duarouter", Path(shutil.which("duarouter") or "/nonexistent"))):
        if path.is_file():
            toolchain[name] = {"path": str(path.resolve()), **file_info(path)}
    identity = {"schema_version": 1, "network_file": file_info(net_file),
                "code": code, "toolchain": toolchain,
                "environment": {"python": sys.version, "platform": platform.platform(),
                                "executable": sys.executable}}
    baseline_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    destination = output_root / "baselines" / baseline_id
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".baseline-", dir=destination.parent) as temporary:
            staging = Path(temporary) / "snapshot"
            staging.mkdir()
            shutil.copy2(net_file, staging / "network.net.xml")
            for name in code:
                target = staging / "code" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(project / name, target)
            version = subprocess.run([binary, "--version"], check=True,
                                     capture_output=True, text=True).stdout.strip()
            subprocess.run([binary, "--save-template", str(staging / "sumo_options.xml")],
                           check=True, capture_output=True, text=True)
            options = ET.parse(staging / "sumo_options.xml").getroot()
            defaults = {item.tag: item.get("value") for group in options for item in group
                        if item.get("value") is not None}
            manifest = {**identity, "baseline_id": baseline_id, "sumo_version": version,
                        "network": describe_network(staging / "network.net.xml"),
                        "sumo_defaults": defaults,
                        "files": {str(path.relative_to(staging)): file_info(path)
                                  for path in sorted(staging.rglob("*")) if path.is_file()}}
            write_json(staging / "baseline.json", manifest)
            try:
                staging.rename(destination)
            except OSError:
                # Outra execução pode ter publicado o mesmo snapshot primeiro.
                if not destination.is_dir():
                    raise
    manifest = json.loads((destination / "baseline.json").read_text(encoding="utf-8"))
    if manifest["baseline_id"] != baseline_id:
        raise ValueError("Identificação do baseline não corresponde ao conteúdo esperado.")
    for name, expected in manifest["files"].items():
        if file_info(destination / name) != expected:
            raise ValueError(f"Baseline modificado: {destination / name}")
    return {"directory": destination, "manifest": manifest}
