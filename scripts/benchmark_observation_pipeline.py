"""Compara minimal (referência interna), core e full sobre a mesma demanda.

Uso de manutenção: python3 scripts/benchmark_observation_pipeline.py --duration 7200
--repetitions 1. Cada perfil roda em um processo isolado, sem mudar o tempo ou a
física da simulação. O observador mínimo grava apenas tripinfo para a comparação.
Mede o custo de tempo e memória dos perfis e grava os resultados em arquivos.
Também confere a igualdade das viagens e das métricas comuns entre observadores.
"""

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
import multiprocessing
from pathlib import Path
import random
import resource
import shutil
import subprocess
import sys
from time import perf_counter
import traceback
from uuid import uuid4
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from SistemaDeSemaforos.demand.random_demand_generator import DEFAULT_NET_FILE, generate_random_demand
from SistemaDeSemaforos.metrics.episode_metrics_collector import collect_episode
from SistemaDeSemaforos.metrics.metrics_storage import save_entities, write_json
from SistemaDeSemaforos.simulation.episode_runner import read_sumo_configuration, run_simulation


def trip_signature(path):
    """Compara todos os atributos de viagem, exceto a lista de observadores."""
    with gzip.open(path, "rb") as stream:
        rows = [{k: v for k, v in trip.attrib.items() if k != "devices"}
                for trip in ET.parse(stream).getroot().findall("tripinfo")]
    rows.sort(key=lambda row: row["id"])
    return len(rows), hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


def compare_traffic_metrics(core, full):
    """Exige todos os resultados do core no full, com valores exatamente iguais."""
    expected = {name: value for name, value in core.items()
                if name != "metrics_profile" and not name.startswith("collection_")}
    differences = {name: {"core": value, "full": full.get(name)}
                   for name, value in expected.items()
                   if name not in full or value != full[name]}
    return {"count": len(expected), "equal": bool(expected) and not differences,
            "metrics": sorted(expected), "differences": differences}


def _size(directory):
    files = [path for path in directory.rglob("*") if path.is_file()]
    return {"files": len(files), "bytes": sum(path.stat().st_size for path in files)}


def _peak_rss_bytes(who):
    # getrusage usa bytes no macOS e KiB no Linux. Cada medição vive em um
    # processo novo, pois ru_maxrss não pode ser zerado entre perfis.
    return int(resource.getrusage(who).ru_maxrss * (1 if sys.platform == "darwin" else 1024))


def _measure_profile(destination, profile, binary, network, routes, sumo_defaults):
    """Mede um único perfil; chamada pelo processo isolado do benchmark."""
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
                       metadata=metadata, metrics_profile=profile, sumo_defaults=sumo_defaults)
        aggregation_started = perf_counter()
        collected = collect_episode(destination / "raw", network, profile=profile)
        aggregation_seconds = perf_counter() - aggregation_started
        persistence_started = perf_counter()
        if profile == "full":
            save_entities(destination, collected["entities"])
        # Resultado técnico do benchmark, sem fingir ser um episódio do runner.
        write_json(destination / "observation.json", {
            "profile": profile, "metrics": collected["metrics"],
            "entity_metrics_file": "entities.json.gz" if profile == "full" else None,
        })
        persistence_seconds = perf_counter() - persistence_started
    pipeline_seconds = perf_counter() - started
    proof_started = perf_counter()
    count, signature = trip_signature(destination / "raw/trips.xml.gz")
    produced = _size(destination)
    raw = _size(destination / "raw")
    # O JSON e a assinatura já foram obtidos com sucesso. Aplicamos a mesma
    # retenção do runner; falhas anteriores preservam os XML para diagnóstico.
    if profile == "core":
        shutil.rmtree(destination / "raw")
    shutil.rmtree(destination / "inputs")
    retained = _size(destination)
    traffic_metrics = {k: v for k, v in collected["metrics"].items()
                       if k != "metrics_profile" and not k.startswith("collection_")}
    return {
        "profile": profile,
        "simulation_seconds": metadata["duration_seconds"],
        "simulation_duration_seconds": collected["metrics"].get("simulation_duration_seconds"),
        "configuration_seconds": metadata.get("configuration_time_seconds", 0.0),
        "aggregation_seconds": aggregation_seconds,
        "persistence_seconds": persistence_seconds,
        "total_seconds": pipeline_seconds,
        "verification_seconds": perf_counter() - proof_started,
        "trips": count, "trip_signature": signature,
        "produced": produced, "raw_produced": raw, "retained": retained,
        "raw_retained": profile != "core",
        "python_peak_rss_bytes": _peak_rss_bytes(resource.RUSAGE_SELF),
        "sumo_peak_rss_bytes": _peak_rss_bytes(resource.RUSAGE_CHILDREN),
        "global_metric_count": len(traffic_metrics),
        "entity_metric_count": sum(len(values) for objects in collected["entities"].values()
                                   for values in objects.values()),
        "collector_phases": {k: v for k, v in collected["metrics"].items()
                             if k.startswith("collection_")},
        "directory": str(destination), "simulation": metadata,
        "traffic_metrics": traffic_metrics,
    }


def _worker(connection, arguments):
    try:
        connection.send({"result": _measure_profile(*arguments)})
    except BaseException:
        connection.send({"error": traceback.format_exc()})
    finally:
        connection.close()


def _isolated_measurement(*arguments):
    context = multiprocessing.get_context("spawn")
    receiving, sending = context.Pipe(duplex=False)
    worker = context.Process(target=_worker, args=(sending, arguments))
    worker.start()
    sending.close()
    try:
        payload = receiving.recv()
        worker.join()
        if worker.exitcode or "error" in payload:
            raise RuntimeError(payload.get("error", f"Benchmark encerrou com código {worker.exitcode}"))
        return payload["result"]
    except EOFError as exc:
        worker.join()
        raise RuntimeError(f"Processo de medição encerrou sem resultado (código {worker.exitcode}).") from exc
    finally:
        receiving.close()
        if worker.is_alive():
            worker.terminate()
            worker.join()


def benchmark(duration=600.0, period=1.5, seed=None, repetitions=2, output_dir=None):
    """Alterna a ordem para reduzir viés de cache; não muda parâmetros físicos."""
    if repetitions < 1:
        raise ValueError("repetitions deve ser positivo")
    if not math.isfinite(duration) or duration <= 0 or not math.isfinite(period) or period <= 0:
        raise ValueError("duration e period devem ser finitos e positivos")
    seed = random.randint(0, 2**31 - 1) if seed is None else seed
    identifier = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
    output_root = (ROOT / "outputs").resolve()
    directory = ((output_root / "benchmarks" / identifier) if output_dir is None
                 else Path(output_dir).expanduser().resolve())
    if directory == output_root or not directory.is_relative_to(output_root):
        raise ValueError("output-dir deve ser uma pasta nova dentro de outputs/")
    binary = shutil.which("sumo")
    if binary is None:
        raise FileNotFoundError("sumo não encontrado")
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "inputs").mkdir()
    configuration = read_sumo_configuration(binary)
    network = DEFAULT_NET_FILE
    generation = {}
    routes = generate_random_demand(net_file=network, output_dir=directory / "inputs",
                                    duration=duration, period=period, seed=seed,
                                    metadata=generation, log_file=directory / "generation.log")
    defaults = configuration["sumo_defaults"]
    report = {
        "schema_version": 2, "status": "running", "seed": seed, "generation": generation,
        "parameters": {"demand_duration_seconds": duration, "demand_period_seconds": period,
                       "simulation_begin_seconds": 0, "simulation_end_override_seconds": None,
                       "step_length_seconds": float(defaults["step-length"]),
                       "sumo_seed": int(defaults["seed"]), "termination": "natural"},
        "configuration": configuration, "network": str(network),
        "runs": [], "metric_comparisons": [],
        "method": {
            "dynamics": "mesma rede/rotas/seed SUMO; término natural; ordem invertida na repetição par",
            "memory": "RSS máximo em bytes; processo Python novo por perfil; SUMO subprocesso separado; máximos não simultâneos, não somar",
            "time": "total_seconds mede configuração/simulação/coleta/persistência; exclui geração compartilhada, inicialização do processo e verificação",
            "storage": "produced inclui XML e consolidados antes da retenção; retained após descarte das entradas temporárias e dos XML core; exclui measurement.json e entradas temporárias compartilhadas; observation.json guarda valores sem a apresentação semântica do runner, portanto não mede o tamanho completo de um episódio operacional",
            "minimal": "referência interna com tripinfo; sem agregação nem medição independente da duração simulada",
        },
    }
    reference_signature = None
    for repetition in range(repetitions):
        profiles = ("minimal", "core", "full") if repetition % 2 == 0 else ("full", "core", "minimal")
        results = {}
        for profile in profiles:
            destination = directory / f"repeat_{repetition + 1}_{profile}"
            result = _isolated_measurement(destination, profile, binary, network, routes, defaults)
            signature = result["trip_signature"]
            reference_signature = signature if reference_signature is None else reference_signature
            result.update(repetition=repetition + 1,
                          same_trip_attributes_as_minimal=signature == reference_signature)
            write_json(destination / "measurement.json", result)
            report["runs"].append(result)
            results[profile] = result
            write_json(directory / "benchmark.json", report)
            if signature != reference_signature:
                report["status"] = "failed"
                write_json(directory / "benchmark.json", report)
                raise ValueError("Observadores produziram viagens diferentes: verificar evidências antes de continuar.")
        comparison = compare_traffic_metrics(results["core"]["traffic_metrics"], results["full"]["traffic_metrics"])
        report["metric_comparisons"].append({"repetition": repetition + 1, **comparison})
        write_json(directory / "benchmark.json", report)
        if not comparison["equal"]:
            report["status"] = "failed"
            write_json(directory / "benchmark.json", report)
            raise ValueError("Métricas comuns core/full divergem: consulte benchmark.json.")
    report["status"] = "completed"
    write_json(directory / "benchmark.json", report)
    shutil.rmtree(directory / "inputs")
    return directory / "benchmark.json"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=600.0,
                        help="janela da demanda; use 7200 para comparar o padrão operacional")
    parser.add_argument("--period", type=float, default=1.5)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--output-dir", type=Path, help="pasta nova dentro de outputs/")
    benchmark(**vars(parser.parse_args()))
