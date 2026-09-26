"""Compara observação mínima, core e full sobre a mesma demanda random.

Entrada: duração/período/seed e repetições; saída: medições e evidências em
outputs/benchmarks/. Uso: python3 scripts/benchmark_pipeline.py --repetitions 2.
O observador mínimo grava apenas tripinfo para conferir a dinâmica das viagens.
"""

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
from time import perf_counter
from uuid import uuid4
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from SistemaDeSemaforos.demand.generator import DEFAULT_NET_FILE, generate_random_demand
from SistemaDeSemaforos.metrics.collector import collect_episode
from SistemaDeSemaforos.metrics.storage import file_info, save_entities, write_json
from SistemaDeSemaforos.simulation.baseline import prepare_baseline
from SistemaDeSemaforos.simulation.runner import run_simulation


def trip_signature(path):
    """Compara todos os atributos de viagem, exceto a lista de observadores."""
    with gzip.open(path, "rb") as stream:
        rows = [{k: v for k, v in trip.attrib.items() if k != "devices"}
                for trip in ET.parse(stream).getroot().findall("tripinfo")]
    rows.sort(key=lambda row: row["id"])
    return len(rows), hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


def benchmark(duration=600.0, period=1.5, seed=None, repetitions=2):
    """Alterna a ordem para reduzir viés de cache; não muda parâmetros físicos."""
    if repetitions < 1:
        raise ValueError("repetitions deve ser positivo")
    seed = random.randint(0, 2**31 - 1) if seed is None else seed
    identifier = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
    directory = ROOT / "outputs" / "benchmarks" / identifier
    (directory / "inputs").mkdir(parents=True, exist_ok=False)
    binary = shutil.which("sumo")
    if binary is None:
        raise FileNotFoundError("sumo não encontrado")
    baseline = prepare_baseline(DEFAULT_NET_FILE, binary, ROOT / "outputs")
    network = baseline["directory"] / "network.net.xml"
    generation = {}
    routes = generate_random_demand(net_file=network, output_dir=directory / "inputs",
                                    duration=duration, period=period, seed=seed,
                                    metadata=generation, log_file=directory / "generation.log")
    report = {"schema_version": 1, "seed": seed, "generation": generation,
              "baseline": str(baseline["directory"] / "baseline.json"),
              "benchmark_script": file_info(Path(__file__)), "runs": [],
              "method": "mesma rede/rotas/seed SUMO; término natural; ordem invertida na repetição par; mínimo inclui tripinfo"}
    reference_signature = None
    for repetition in range(repetitions):
        profiles = ("minimal", "core", "full") if repetition % 2 == 0 else ("full", "core", "minimal")
        for profile in profiles:
            destination = directory / f"repeat_{repetition + 1}_{profile}"
            (destination / "inputs").mkdir(parents=True)
            started = perf_counter()
            metadata = {}
            aggregation_seconds = persistence_seconds = 0.0
            if profile == "minimal":
                (destination / "raw").mkdir()
                command = [binary, "--net-file", str(network), "--route-files", str(routes),
                           "--begin", "0", "--no-step-log", "true", "--aggregate-warnings", "5",
                           "--precision", "8", "--tripinfo-output", str(destination / "raw/trips.xml.gz"),
                           "--tripinfo-output.write-unfinished", "true",
                           "--tripinfo-output.write-undeparted", "true"]
                with (destination / "sumo.log").open("w") as log:
                    simulation_started = perf_counter()
                    subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)
                    metadata["duration_seconds"] = perf_counter() - simulation_started
                metadata["command"] = command
                collected = {"metrics": {}, "entities": {}}
            else:
                run_simulation(net_file=network, demand_file=routes, recording_dir=destination,
                               metadata=metadata, metrics_profile=profile, baseline=baseline)
                aggregation_started = perf_counter()
                collected = collect_episode(destination / "raw", network, profile=profile)
                aggregation_seconds = perf_counter() - aggregation_started
                persistence_started = perf_counter()
                save_entities(destination, collected["entities"])
                persistence_seconds = perf_counter() - persistence_started
            total_seconds = perf_counter() - started
            count, signature = trip_signature(destination / "raw/trips.xml.gz")
            reference_signature = signature if reference_signature is None else reference_signature
            result = {"repetition": repetition + 1, "profile": profile,
                      "simulation_seconds": metadata["duration_seconds"],
                      "configuration_seconds": metadata.get("configuration_time_seconds", 0.0),
                      "aggregation_seconds": aggregation_seconds,
                      "persistence_seconds": persistence_seconds, "total_seconds": total_seconds,
                      "trips": count, "trip_signature": signature,
                      "same_trip_attributes_as_minimal": signature == reference_signature,
                      "bytes": sum(p.stat().st_size for p in destination.rglob("*") if p.is_file()),
                      "collector_phases": {k: v for k, v in collected["metrics"].items()
                                           if k.startswith("collection_")},
                      "directory": str(destination), "simulation": metadata}
            write_json(destination / "measurement.json", result)
            report["runs"].append(result)
            write_json(directory / "benchmark.json", report)
            print(f"{profile} repetição {repetition + 1}: {total_seconds:.3f} s; viagens iguais={signature == reference_signature}", flush=True)
            if signature != reference_signature:
                raise ValueError("Observadores produziram viagens diferentes: verificar evidências antes de continuar.")
    print(f"Benchmark: {directory / 'benchmark.json'}", flush=True)
    return directory / "benchmark.json"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=600.0)
    parser.add_argument("--period", type=float, default=1.5)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--repetitions", type=int, default=2)
    benchmark(**vars(parser.parse_args()))
