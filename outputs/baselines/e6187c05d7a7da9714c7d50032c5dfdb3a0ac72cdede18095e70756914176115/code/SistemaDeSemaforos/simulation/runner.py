"""Executa uma ou mais simulações SUMO.

Entrada principal: rede, demanda pronta e opções de execução.
Saída principal: episódios concluídos e seus resultados em outputs/.
Uso normal: ``make run-random``, que gera uma demanda nova por episódio.
"""

import argparse
from datetime import datetime, timezone
import math
from pathlib import Path
import random
import shutil
import subprocess
import sys
from time import perf_counter
from uuid import uuid4
import xml.etree.ElementTree as ET

from ..demand.generator import (
    DEFAULT_DURATION,
    DEFAULT_NET_FILE,
    DEFAULT_PERIOD,
    generate_random_demand,
)
from ..metrics.storage import file_info, save_entities, save_episode
from ..metrics.sumo_outputs import prepare_outputs
from .baseline import prepare_baseline


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = PROJECT_ROOT / "outputs"
DEFAULT_EPISODE_DIR = OUTPUT_ROOT / "outputs-random"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_simulation(
    *,
    net_file: Path | str,
    demand_file: Path | str,
    gui: bool = False,
    end: float | None = None,
    recording_dir: Path | None = None,
    metadata: dict | None = None,
    metrics_profile: str = "core",
    baseline: dict | None = None,
) -> None:
    """Executa demanda pronta; recording_dir habilita arquivos de observação."""
    if end is not None and (not math.isfinite(end) or end <= 0):
        raise ValueError("end deve ser um número finito maior que zero.")

    net_file = Path(net_file).expanduser().resolve()
    demand_file = Path(demand_file).expanduser().resolve()
    if not net_file.is_file():
        raise FileNotFoundError(f"Rede SUMO não encontrada: {net_file}")
    if not demand_file.is_file():
        raise FileNotFoundError(f"Demanda não encontrada: {demand_file}")

    program = "sumo-gui" if gui else "sumo"
    binary = shutil.which(program)
    if binary is None:
        raise FileNotFoundError(f"{program} não encontrado no PATH.")

    command = [
        binary,
        "--net-file", str(net_file),
        "--route-files", str(demand_file),
        "--begin", "0",
        "--no-step-log", "true",
        # Mostra exemplos e depois agrupa avisos repetidos de congestionamento.
        "--aggregate-warnings", "5",
    ]
    if end is not None:
        command.extend(["--end", str(end)])
    if gui:
        command.extend(["--start", "--quit-on-end"])

    if recording_dir is None:
        subprocess.run(command, check=True)
        return

    preparation_started = perf_counter()
    command.extend(prepare_outputs(recording_dir, profile=metrics_profile))
    if metadata is None:
        metadata = {}
    if baseline is None:
        baseline = prepare_baseline(net_file, binary, OUTPUT_ROOT)
    metadata["command"] = command
    with (recording_dir / "sumo.log").open("w", encoding="utf-8") as log:
        # Apenas diferenças explícitas são salvas por episódio. Defaults e
        # versão estão no baseline compartilhado, verificado pelo conteúdo.
        subprocess.run(command + ["--save-configuration",
                                 str(recording_dir / "inputs" / "sumo_config.sumocfg")],
                       check=True, stdout=log, stderr=subprocess.STDOUT)
        configured = ET.parse(recording_dir / "inputs" / "sumo_config.sumocfg").getroot()
        metadata["configured_options"] = {
            item.tag: item.get("value") for group in configured for item in group
            if item.get("value") is not None
        }
        effective = baseline["manifest"]["sumo_defaults"] | metadata["configured_options"]
        metadata["seed"] = int(effective["seed"])
        metadata["step_length"] = float(effective["step-length"])
        metadata["configuration_time_seconds"] = perf_counter() - preparation_started
        started = perf_counter()
        try:
            subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)
        finally:
            metadata["duration_seconds"] = perf_counter() - started


def run_random_episodes(
    *,
    net_file: Path | str = DEFAULT_NET_FILE,
    output_dir: Path | str = DEFAULT_EPISODE_DIR,
    episodes: int = 1,
    gui: bool = False,
    duration: float = DEFAULT_DURATION,
    period: float = DEFAULT_PERIOD,
    end: float | None = None,
    metrics_profile: str = "core",
) -> None:
    """Gera, simula e consolida cada episódio em uma pasta que nunca se repete."""
    if isinstance(episodes, bool) or not isinstance(episodes, int) or episodes < 1:
        raise ValueError("episodes deve ser um inteiro maior que zero.")
    if metrics_profile not in {"core", "full"}:
        raise ValueError("metrics_profile deve ser core ou full.")
    if end is not None and (not math.isfinite(end) or end <= 0):
        raise ValueError("end deve ser um número finito maior que zero.")
    for name, value in (("duration", duration), ("period", period)):
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} deve ser finito e maior que zero.")

    output_dir = Path(output_dir).expanduser().resolve()
    if not output_dir.is_relative_to((OUTPUT_ROOT / "outputs-random").resolve()):
        raise ValueError("output_dir deve ficar dentro de outputs/outputs-random/.")
    net_file = Path(net_file).expanduser().resolve()
    if not net_file.is_file():
        raise FileNotFoundError(f"Rede SUMO não encontrada: {net_file}")
    context = {}
    for episode in range(1, episodes + 1):
        _run_random_episode(net_file, output_dir, episode, episodes, gui, duration, period,
                            end, metrics_profile, context)


def _run_random_episode(net_file, output_dir, episode, episodes, gui, duration, period,
                        end, metrics_profile, context):
    """Mantém juntos o ciclo de vida, o contexto e o tratamento de falhas."""
    started = perf_counter()
    started_at = _utc_now()
    seed = random.randint(0, 2**31 - 1)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    episode_id = f"{timestamp}_seed-{seed}_{uuid4().hex[:8]}"
    directory = output_dir / episode_id
    # exist_ok=False também protege contra a improvável colisão de identificadores.
    directory.mkdir(parents=True, exist_ok=False)
    inputs = directory / "inputs"
    inputs.mkdir()
    metrics = {
        "episode_id": episode_id, "demand_model": "random", "seed": seed,
        "episode_index": episode, "batch_episodes": episodes,
        "started_at_utc": started_at, "gui": gui,
        "demand_duration_seconds": float(duration), "demand_period_seconds": float(period),
        "simulation_begin_seconds": 0.0, "simulation_end_limited": end is not None,
        "vehicles_requested": math.ceil(duration / period), "status": "running",
        "metrics_profile": metrics_profile,
    }
    if end is not None:
        metrics["simulation_end_requested_seconds"] = float(end)
    manifest = {
        "schema_version": 2, "episode_id": episode_id, "demand_model": "random",
        "seed": seed, "started_at_utc": started_at,
        "source_network": str(net_file), "generation": {}, "simulation": {},
        "files": {}, "status": "running",
        "collection": {"profile": metrics_profile},
    }
    entities = {}
    save_episode(directory, metrics, manifest)
    print(f"Episódio {episode}/{episodes}: seed {seed}; resultados em {directory}", flush=True)
    try:
        baseline_started = perf_counter()
        if "baseline" not in context:
            binary = shutil.which("sumo-gui" if gui else "sumo")
            if binary is None:
                raise FileNotFoundError("Executável SUMO não encontrado no PATH.")
            context["baseline"] = prepare_baseline(net_file, binary, OUTPUT_ROOT)
        baseline = context["baseline"]
        metrics["baseline_preparation_time_seconds"] = perf_counter() - baseline_started
        snapshot = baseline["directory"] / "network.net.xml"
        manifest["baseline"] = {
            "id": baseline["manifest"]["baseline_id"],
            "manifest": str(baseline["directory"] / "baseline.json"),
            **file_info(baseline["directory"] / "baseline.json"),
        }
        generation = manifest["generation"]
        demand_file = generate_random_demand(
            net_file=snapshot, output_dir=inputs, duration=duration, period=period,
            seed=seed, metadata=generation, log_file=directory / "generation.log",
        )
        for name in ("vehicles_generated", "trips_generated"):
            metrics[name] = generation[name]
        departures = [float(vehicle.get("depart")) for vehicle in ET.parse(demand_file).getroot()
                      if vehicle.tag == "vehicle"]
        if departures:
            metrics["demand_first_departure_seconds"] = min(departures)
            metrics["demand_last_departure_seconds"] = max(departures)
            metrics["demand_departure_mean_seconds"] = sum(departures) / len(departures)
        metrics["generation_time_seconds"] = generation["duration_seconds"]
        print(f"Episódio {episode}/{episodes}: executando SUMO e registrando observações.", flush=True)
        run_simulation(net_file=snapshot, demand_file=demand_file, gui=gui, end=end,
                       recording_dir=directory, metadata=manifest["simulation"],
                       metrics_profile=metrics_profile, baseline=baseline)
        simulation = manifest["simulation"]
        metrics["simulation_execution_time_seconds"] = simulation["duration_seconds"]
        metrics["simulation_seed"] = simulation["seed"]
        metrics["simulation_step_length_seconds"] = simulation["step_length"]
        metrics["sumo_configuration_time_seconds"] = simulation["configuration_time_seconds"]
        print(f"Episódio {episode}/{episodes}: consolidando métricas.", flush=True)
        # Importação local mantém o executor simples utilizável sem pós-processamento.
        from ..metrics.collector import collect_episode
        aggregation_started = perf_counter()
        collected = collect_episode(directory / "raw", snapshot, profile=metrics_profile)
        metrics.update(collected["metrics"])
        entities = collected["entities"]
        metrics["aggregation_time_seconds"] = perf_counter() - aggregation_started
        metrics["status"] = "completed"
    except BaseException as exc:
        metrics["status"] = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        metrics["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        # Resultados e diagnósticos são preservados também em uma falha parcial.
        persistence_started = perf_counter()
        save_entities(directory, entities)
        metrics["entity_persistence_time_seconds"] = perf_counter() - persistence_started
        inventory_started = perf_counter()
        manifest["files"] = {
            str(path.relative_to(directory)): file_info(path)
            for path in sorted(directory.rglob("*"))
            if path.is_file() and path.name not in {"metrics.json", "manifest.json"}
        }
        metrics["file_inventory_time_seconds"] = perf_counter() - inventory_started
        manifest["collection"]["native_outputs"] = sorted(
            path.name for path in (directory / "raw").glob("*") if path.is_file())
        manifest["collection"]["entity_counts"] = {
            scope: len(values) for scope, values in entities.items()}
        metrics["finished_at_utc"] = _utc_now()
        metrics["execution_time_seconds"] = perf_counter() - started
        manifest.update({name: metrics[name] for name in (
            "status", "finished_at_utc", "execution_time_seconds")})
        # A duração inclui a exportação volumosa. Só estes dois JSONs pequenos
        # ficam fora da medida, pois precisam conter o próprio tempo final.
        save_episode(directory, metrics, manifest)


def main(argv: list[str] | None = None) -> int:
    """Executa episódios random pelo terminal."""
    parser = argparse.ArgumentParser(
        description="Executa episódios com uma demanda random nova em cada um."
    )
    parser.add_argument("--episodes", type=int, default=1)
    parser.add_argument("--gui", action="store_true")
    parser.add_argument("--net-file", type=Path, default=DEFAULT_NET_FILE)
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_EPISODE_DIR,
        help="Subpasta de outputs/outputs-random para guardar os episódios.",
    )
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION)
    parser.add_argument("--period", type=float, default=DEFAULT_PERIOD)
    parser.add_argument("--end", type=float)
    parser.add_argument("--metrics-profile", choices=("core", "full"), default="core",
                        help="core: observações padrão; full: inclui séries por via/faixa/veículo.")
    args = parser.parse_args(argv)

    try:
        run_random_episodes(**vars(args))
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Erro ao executar episódios random: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Execução interrompida pelo usuário.", file=sys.stderr)
        return 130

    print(f"Execução concluída: {args.episodes} episódio(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
