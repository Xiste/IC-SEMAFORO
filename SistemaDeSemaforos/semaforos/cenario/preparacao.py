"""Preparação da cópia experimental com grupos protegidos e auditoria."""
import copy
import hashlib
import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from semaforos.caminhos import PROJECT_ROOT
from .grupos import build_program, audit_program, signal_links
from .configuracao import sumo_executable


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare_grouped(config, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    source = PROJECT_ROOT / "dados/rede/uberlandia.rondon_norte_corrigida.net.xml"
    mapping_path = PROJECT_ROOT / "config/mapeamento_associado.json"
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    names = {c["tls_id"]: entry["name"] for entry in mapping["intersections"] for c in entry["controllers"]}
    binary = shutil.which("netconvert")
    if not binary:
        candidate = sumo_executable().with_name("netconvert.exe" if sys.platform == "win32" else "netconvert")
        if not candidate.is_file():
            raise ValueError("netconvert não encontrado no PATH ou junto do SUMO")
        binary = str(candidate)
    network = output / "nove_experimental.net.xml"
    result = subprocess.run([binary, "-s", str(source), "-o", str(network), "--tls.rebuild", "--tls.ungroup-signals"],
                            capture_output=True, text=True, timeout=120,
                            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    (output / "netconvert.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        raise ValueError("Falha no netconvert; consulte o log da preparação")
    root, original = ET.parse(network).getroot(), ET.parse(source).getroot()
    key = lambda c: tuple(c.get(x) for x in ("tl", "from", "to", "fromLane", "toLane"))
    old_links = {key(c): int(c.get("linkIndex")) for c in original.findall("connection") if c.get("tl")}
    repair = set()
    for logic in list(root.findall("tlLogic")):
        tls = logic.get("id")
        if tls in names:
            continue
        root.remove(logic)
        connections = signal_links(root, tls)
        for old in original.findall("tlLogic"):
            if old.get("id") != tls:
                continue
            restored = copy.deepcopy(old)
            for phase in restored.findall("phase"):
                states = [None] * (max(int(c.get("linkIndex")) for c in connections) + 1)
                for c in connections:
                    if key(c) not in old_links:
                        raise ValueError(f"Conexão original não encontrada em {tls}")
                    index, color = int(c.get("linkIndex")), phase.get("state")[old_links[key(c)]]
                    if states[index] not in (None, color):
                        raise ValueError(f"Estados incompatíveis em {tls}:{index}")
                    states[index] = color
                phase.set("state", "".join(x or "r" for x in states))
            root.append(restored)
            phases = restored.findall("phase")
            if any(not any(p.get("state")[int(c.get("linkIndex"))] in "Gg" for p in phases) for c in connections) or any(set(p.get("state")) - set("GgryY") for p in phases):
                repair.add(tls)
    durations, floors, bounds, groups = {}, {}, {}, {}
    rows = []
    for tls in sorted(set(names) | repair):
        group, times, minima, limits = build_program(root, tls)
        groups[tls] = group
        row = audit_program(root, tls)
        row.update(cruzamento=names.get(tls, "Controlador externo corrigido"), controlado=tls in names)
        rows.append(row)
        if tls in names:
            durations.update(times)
            floors.update(minima)
            bounds.update(limits)
    for logic in list(root.findall("tlLogic")):
        root.remove(logic)
        root.insert(0, logic)
    ET.ElementTree(root).write(network, encoding="utf-8", xml_declaration=True)
    prepared = copy.deepcopy(config)
    prepared.update(network=network.resolve(), targets_from_mapping=False,
                    targets=[{"name": name, "tls_id": tls, "phase_indices": list(range(0, len(groups[tls]) * 3, 3))} for tls, name in names.items()],
                    experimental={"method": "compatible_groups_v2", "synthetic": True,
                                  "network_sha256": file_digest(network), "source_sha256": file_digest(source),
                                  "mapping_sha256": file_digest(mapping_path), "groups": groups,
                                  "external_repaired": sorted(repair), "minimum_durations": durations, "green_floors": floors})
    params = copy.deepcopy(prepared.get("control", prepared.get("ppo", {})))
    params.update(action_mode="phase_durations", phase_types=["green", "yellow", "all_red"],
                  phase_duration_bounds=bounds, duration_limits={},
                  maximum_cycle_seconds=max(sum(v["maximum_seconds"] for k, v in bounds.items() if k.startswith(tls + ":")) for tls in names))
    prepared["control"] = params
    prepared["ppo"] = {**prepared["ppo"], **params}
    prepared["duration_seconds"] = max(int(config["duration_seconds"]), int(params["maximum_cycle_seconds"] * 2))
    from .experimental import validate_experimental
    validate_experimental(prepared)
    (output / "verificacao.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "cenario.json").write_text(json.dumps(prepared, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return prepared, rows
