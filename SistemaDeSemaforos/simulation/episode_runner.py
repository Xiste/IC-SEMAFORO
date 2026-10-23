"""Executa uma ou mais simulações SUMO.

Entrada principal: rede, demanda pronta e opções de execução.
Saída principal: episódios concluídos e seus resultados em outputs/.
Uso normal: ``make run-random``, que gera uma demanda nova por episódio.
Coordena validação, geração da demanda, execução, coleta e gravação dos resultados.
Cada episódio recebe uma seed de demanda; entradas temporárias são removidas após sucesso.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import secrets
import shutil
import subprocess
import sys
import tempfile
from time import perf_counter
from uuid import uuid4
import xml.etree.ElementTree as ET

from ..demand.random_demand_generator import (
    DEFAULT_DURATION,
    DEFAULT_NET_FILE,
    DEFAULT_PERIOD,
    generate_random_demand,
)
from ..metrics.metrics_storage import save_entities, save_episode
from ..metrics.sumo_output_configuration import prepare_outputs


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = PROJECT_ROOT / "outputs"
DEFAULT_EPISODE_DIR = OUTPUT_ROOT / "outputs-random"
SETTRAN_PROGRAMS_FILE = PROJECT_ROOT / "docs" / "settran_programs.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_sumo_configuration(binary: str) -> dict:
    """Consulta versão e defaults como dados, sem copiar ferramentas ou entradas."""
    version = subprocess.run([binary, "--version"], check=True,
                             capture_output=True, text=True).stdout.strip()
    template = subprocess.run([binary, "--save-template", "-"], check=True,
                              capture_output=True, text=True).stdout
    return {
        "sumo_version": version,
        "sumo_defaults": {item.tag: item.get("value")
                          for group in ET.fromstring(template) for item in group
                          if item.get("value") is not None},
    }


def _validate_signal_profile(signal_profile: str, settran_plan: str | None = None,
                             net_file=DEFAULT_NET_FILE, settran_intersections=None,
                             document=None) -> dict | None:
    """Valida a seleção inteira antes da seed; current não lê dados SETTRAN."""
    if signal_profile not in {"current", "settran"}:
        raise ValueError("signal_profile deve ser current ou settran.")
    if signal_profile == "current":
        if settran_plan is not None or settran_intersections is not None:
            raise ValueError("--settran-plan/--settran-intersection exige --signal-profile settran.")
        return
    if settran_plan is None:
        raise ValueError(
            "Escolha explicitamente --settran-plan para testar um plano SETTRAN fixo; "
            "nenhum plano foi presumido. Consulte docs/GUIA_DE_FUNCIONAMENTO.md."
        )

    from scripts.audit_settran import validate_source_document
    from .settran_configuration import prepare_selection

    if document is None:
        document = json.loads(SETTRAN_PROGRAMS_FILE.read_text(encoding="utf-8"))
    validate_source_document(document)
    return prepare_selection(document, settran_plan, net_file, settran_intersections)


def run_simulation(
    *,
    net_file: Path | str,
    demand_file: Path | str,
    gui: bool = False,
    end: float | None = None,
    recording_dir: Path | None = None,
    metadata: dict | None = None,
    metrics_profile: str = "core",
    sumo_defaults: dict | None = None,
    signal_profile: str = "current",
    settran_plan: str | None = None,
    settran_intersections: list[str] | None = None,
    _settran_document: dict | None = None,
    demand_observation_edges: tuple[str, ...] = (),
    track_teleported_vehicles: bool = False,
) -> None:
    """Executa demanda pronta; recording_dir habilita arquivos de observação."""
    selection = _validate_signal_profile(signal_profile, settran_plan, net_file,
                                         settran_intersections, _settran_document)
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
        "--aggregate-warnings", "-1" if track_teleported_vehicles else "5",
    ]
    if end is not None:
        command.extend(["--end", str(end)])
    if gui:
        command.extend(["--start", "--quit-on-end"])

    if selection is not None:
        from .settran_configuration import compile_selection
        if recording_dir is None:
            with tempfile.TemporaryDirectory(prefix="settran-fixed-") as temporary:
                additional = compile_selection(selection, Path(temporary) / "settran.add.xml")
                subprocess.run(command + ["--additional-files", str(additional)], check=True)
            return
        inputs = recording_dir / "inputs"
        inputs.mkdir(parents=True, exist_ok=True)
        additional = compile_selection(selection, inputs / "settran.add.xml")
    elif recording_dir is None:
        subprocess.run(command, check=True)
        return

    preparation_started = perf_counter()
    observation_options = ({"demand_observation_edges": demand_observation_edges}
                           if demand_observation_edges else {})
    output_options = prepare_outputs(recording_dir, profile=metrics_profile, **observation_options)
    if selection is not None:
        # Uma única opção mantém programas e observações; repetir a flag pode
        # substituir o arquivo de coleta já usado pelo pipeline.
        if "--additional-files" in output_options:
            index = output_options.index("--additional-files") + 1
            output_options[index] = f"{additional},{output_options[index]}"
        else:
            output_options.extend(["--additional-files", str(additional)])
    command.extend(output_options)
    if metadata is None:
        metadata = {}
    if selection is not None:
        metadata["signal_configuration"] = {
            "mode": "explicit_fixed_plan", "plan_id": selection["plan_id"],
            "intersections": selection["intersections"], "tls_ids": selection["tls_ids"],
            "current_tls_ids": selection["current_tls_ids"],
            "programs": [
                {**logic.attrib, "phases": [phase.attrib for phase in logic.findall("phase")],
                 "parameters": [param.attrib for param in logic.findall("param")]}
                for logic in ET.parse(additional).getroot().findall("tlLogic")
            ],
        }
    if sumo_defaults is None:
        sumo_defaults = read_sumo_configuration(binary)["sumo_defaults"]
    metadata["command"] = command
    with (recording_dir / "sumo.log").open("w", encoding="utf-8") as log:
        # Guarda os valores aplicados. O arquivo SUMO é apenas uma entrada
        # temporária; defaults são consultados em memória e a versão fica no resultado.
        subprocess.run(command + ["--save-configuration",
                                 str(recording_dir / "inputs" / "sumo_config.sumocfg")],
                       check=True, stdout=log, stderr=subprocess.STDOUT)
        configured = ET.parse(recording_dir / "inputs" / "sumo_config.sumocfg").getroot()
        metadata["configured_options"] = {
            item.tag: item.get("value") for group in configured for item in group
            if item.get("value") is not None
        }
        effective = sumo_defaults | metadata["configured_options"]
        metadata["seed"] = int(effective["seed"])
        metadata["step_length"] = float(effective["step-length"])
        metadata["configuration_time_seconds"] = perf_counter() - preparation_started
        started = perf_counter()
        try:
            subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)
        finally:
            metadata["duration_seconds"] = perf_counter() - started


def run_episodes(
    *,
    net_file: Path | str = DEFAULT_NET_FILE,
    output_dir: Path | str = DEFAULT_EPISODE_DIR,
    episodes: int = 1,
    gui: bool = False,
    duration: float = DEFAULT_DURATION,
    period: float = DEFAULT_PERIOD,
    end: float | None = None,
    metrics_profile: str = "core",
    signal_profile: str = "current",
    settran_plan: str | None = None,
    settran_intersections: list[str] | None = None,
    demand_profile: str = "random",
    day: str | None = None,
    start: str | None = None,
    sections: int | None = None,
    variation: int | None = None,
    master_seed: int | None = None,
    variations: list[int] | None = None,
    drain_limit: float | None = None,
    spatial_scenario: str | None = None,
) -> Path:
    """Gera episódios em um lote exclusivo e grava os resultados de cada um."""
    # Validar antes de sortear seed, gerar demanda ou criar qualquer episódio.
    selection = _validate_signal_profile(signal_profile, settran_plan, net_file,
                                         settran_intersections)
    if demand_profile not in {"random", "metasettran"}:
        raise ValueError("demand_profile deve ser random ou metasettran.")
    demand_options = None
    if demand_profile == "random":
        if any(value is not None for value in (day, start, sections, variation, master_seed,
                                               variations, drain_limit, spatial_scenario)):
            raise ValueError("Dia, seção, variação e escoamento exigem --demand-profile metasettran.")
    else:
        from ..demand.metasettran_demand_generator import SPATIAL_SCENARIOS, resolve_contexts
        demand_options = {"day": "tuesday" if day is None else day,
                          "start": "15:00" if start is None else start,
                          "sections": 1 if sections is None else sections,
                          "variation": variation,
                          "master_seed": master_seed, "variations": variations}
        # Uma faixa sem opções mantém a variação histórica; uma sequência sorteia
        # cada contexto. A validação não consome aleatoriedade nem cria saídas.
        if demand_options["sections"] == 1 and all(
                value is None for value in (variation, master_seed, variations)):
            demand_options["variation"] = 1
        validation_options = dict(demand_options)
        if demand_options["variation"] is None and master_seed is None and variations is None:
            validation_options["master_seed"] = 0
        resolve_contexts(**validation_options)
        spatial_scenario = "regional-integrated" if spatial_scenario is None else spatial_scenario
        if spatial_scenario not in SPATIAL_SCENARIOS:
            raise ValueError("Cenário regional inválido ou pertencente a um modelo de demanda retirado.")
        demand_options["spatial_scenario"] = spatial_scenario
        if duration != DEFAULT_DURATION or period != DEFAULT_PERIOD or end is not None:
            raise ValueError("MetaSettran define a janela de partidas; use apenas --drain-limit para o horizonte.")
        drain_limit = 2700.0 if drain_limit is None else drain_limit
        if (isinstance(drain_limit, bool) or not math.isfinite(drain_limit)
                or drain_limit < 0 or drain_limit != int(drain_limit)):
            raise ValueError("drain_limit deve ser um número inteiro de segundos, finito e não negativo.")
        duration = 10800.0 * demand_options["sections"]
        end = duration + drain_limit
    if isinstance(episodes, bool) or not isinstance(episodes, int) or episodes < 1:
        raise ValueError("episodes deve ser um inteiro maior que zero.")
    if (demand_options is not None and demand_options["variation"] is not None
            and demand_options["variation"] + episodes - 1 > 25):
        raise ValueError("O lote excede as 25 variações; não há retorno automático à variação 1.")
    if metrics_profile not in {"core", "full"}:
        raise ValueError("metrics_profile deve ser core ou full.")
    if end is not None and (not math.isfinite(end) or end <= 0):
        raise ValueError("end deve ser um número finito maior que zero.")
    for name, value in (("duration", duration), ("period", period)):
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} deve ser finito e maior que zero.")

    if demand_profile == "metasettran" and Path(output_dir) == DEFAULT_EPISODE_DIR:
        output_dir = OUTPUT_ROOT / "outputs-metasettran"
    output_dir = Path(output_dir).expanduser().resolve()
    expected_root = (OUTPUT_ROOT / f"outputs-{demand_profile}").resolve()
    if not output_dir.is_relative_to(expected_root):
        raise ValueError(f"output_dir deve ficar dentro de outputs/outputs-{demand_profile}/.")
    net_file = Path(net_file).expanduser().resolve()
    if not net_file.is_file():
        raise FileNotFoundError(f"Rede SUMO não encontrada: {net_file}")
    batch_master_seed = None
    if demand_options is not None and demand_options["variation"] is None:
        batch_master_seed = master_seed
        if batch_master_seed is None and variations is None:
            batch_master_seed = secrets.randbits(63)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    batch_dir = output_dir / f"{timestamp}_{uuid4().hex[:8]}"
    batch_dir.mkdir(parents=True, exist_ok=False)
    context = {}
    for episode in range(1, episodes + 1):
        episode_demand = None
        if demand_options is not None:
            episode_demand = dict(demand_options)
            if demand_options["variation"] is not None:
                episode_demand["variation"] += episode - 1
            else:
                # A primeira execução usa a seed informada. As demais recebem
                # seeds derivadas, sem depender de estado global ou de semáforos.
                episode_master = batch_master_seed
                if episode > 1 and variations is None:
                    digest = hashlib.sha256(
                        f"metasettran-batch-v1:{batch_master_seed}:{episode}".encode()).digest()
                    episode_master = int.from_bytes(digest[:8], "big") & (2**63 - 1)
                episode_demand["master_seed"] = episode_master
            resolved = resolve_contexts(**{key: episode_demand[key] for key in (
                "day", "start", "sections", "variation", "master_seed", "variations")})
            if episode_demand["variation"] is None:
                episode_demand["variations"] = [item["variation"] for item in resolved["contexts"]]
            episode_demand["_context_selection"] = {
                **resolved, "batch_master_seed": batch_master_seed, "batch_episode": episode}
        _run_episode(net_file, batch_dir, episode, episodes, gui, duration, period,
                     end, metrics_profile, context, signal_profile, selection, episode_demand)
    return batch_dir


def run_random_episodes(**kwargs) -> Path:
    """Mantém a interface Python e os defaults do executor random existente."""
    return run_episodes(**kwargs)


def _run_episode(net_file, output_dir, episode, episodes, gui, duration, period,
                 end, metrics_profile, context, signal_profile, selection=None, demand_options=None):
    """Mantém juntos o ciclo de vida, o contexto e o tratamento de falhas."""
    started = perf_counter()
    started_at = _utc_now()
    if demand_options is None:
        seed = random.randint(0, 2**31 - 1)
    else:
        seed = demand_options["_context_selection"]["seed"]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    episode_id = f"{timestamp}_seed-{seed}_{uuid4().hex[:8]}"
    directory = output_dir / episode_id
    # exist_ok=False também protege contra a improvável colisão de identificadores.
    directory.mkdir(parents=True, exist_ok=False)
    inputs = directory / "inputs"
    inputs.mkdir()
    metrics = {
        "episode_id": episode_id, "demand_model": "random" if demand_options is None else "metasettran", "seed": seed,
        "episode_index": episode, "batch_episodes": episodes,
        "started_at_utc": started_at, "gui": gui,
        "demand_duration_seconds": float(duration), "demand_period_seconds": float(period),
        "simulation_begin_seconds": 0.0, "simulation_end_limited": end is not None,
        "vehicles_requested": math.ceil(duration / period), "status": "running",
        "metrics_profile": metrics_profile,
    }
    if demand_options is not None:
        metrics.pop("demand_period_seconds")
        metrics.pop("vehicles_requested")
    if end is not None:
        metrics["simulation_end_requested_seconds"] = float(end)
    execution = {
        "signal_profile": signal_profile,
        "source_network": str(net_file), "generation": {}, "simulation": {},
        "status": "running", "timings_seconds": {},
        "collection": {"profile": metrics_profile},
    }
    entities = {}
    if demand_options is not None:
        execution["context_selection"] = demand_options["_context_selection"]
    if selection is not None:
        execution["signal_configuration"] = {
            "mode": "explicit_fixed_plan", "plan_id": selection["plan_id"],
            "intersections": selection["intersections"], "tls_ids": selection["tls_ids"],
            "current_tls_ids": selection["current_tls_ids"],
        }
    save_episode(directory, metrics, execution, include_entities=metrics_profile == "full")
    try:
        configuration_started = perf_counter()
        if "configuration" not in context:
            binary = shutil.which("sumo-gui" if gui else "sumo")
            if binary is None:
                raise FileNotFoundError("Executável SUMO não encontrado no PATH.")
            context["configuration"] = read_sumo_configuration(binary)
        configuration = context["configuration"]
        execution["sumo_version"] = configuration["sumo_version"].splitlines()[0]
        execution["timings_seconds"]["configuration_preparation_time_seconds"] = (
            perf_counter() - configuration_started)
        generation = execution["generation"]
        if demand_options is None:
            demand_file = generate_random_demand(
                net_file=net_file, output_dir=inputs, duration=duration, period=period,
                seed=seed, metadata=generation, log_file=directory / "generation.log",
            )
        else:
            from ..demand.metasettran_demand_generator import generate_metasettran_demand
            demand_file = generate_metasettran_demand(
                net_file=net_file, output_dir=inputs, metadata=generation,
                log_file=directory / "generation.log",
                **{key: value for key, value in demand_options.items() if not key.startswith("_")},
            )
            # Uma rota reutilizável é parte do experimento MetaSettran. As viagens
            # intermediárias e configurações SUMO continuam temporárias.
            retained_route = directory / "metasettran.rou.xml"
            demand_file.replace(retained_route)
            demand_file = retained_route
            generation["routes_file"] = str(retained_route)
            generation["clearance_limit_seconds"] = end - duration
            metrics["vehicles_requested"] = generation["vehicles_generated"]
        for name in ("vehicles_generated", "trips_generated"):
            metrics[name] = generation[name]
        # Uma semana pode conter centenas de milhares de rotas: estes três
        # agregados não precisam carregar novamente o XML inteiro na memória.
        departure_count, departure_sum = 0, 0.0
        first_departure, last_departure = math.inf, -math.inf
        with demand_file.open("rb") as source:
            parsed = ET.iterparse(source, events=("start", "end"))
            _, route_root = next(parsed)
            for event, vehicle in parsed:
                if event != "end" or vehicle.tag != "vehicle":
                    continue
                depart = float(vehicle.get("depart"))
                departure_count += 1
                departure_sum += depart
                first_departure = min(first_departure, depart)
                last_departure = max(last_departure, depart)
                route_root.clear()
        if departure_count:
            metrics["demand_first_departure_seconds"] = first_departure
            metrics["demand_last_departure_seconds"] = last_departure
            metrics["demand_departure_mean_seconds"] = departure_sum / departure_count
        metrics["generation_time_seconds"] = generation["duration_seconds"]
        signal_options = {} if selection is None else {
            "settran_plan": selection["plan_id"],
            "settran_intersections": selection["intersections"],
            "_settran_document": selection["document_snapshot"],
        }
        if demand_options is not None:
            from ..metrics.episode_metrics_collector import metasettran_observation_edges
            signal_options.update(
                demand_observation_edges=metasettran_observation_edges(generation["spatial_model"]),
                track_teleported_vehicles=True,
            )
        run_simulation(net_file=net_file, demand_file=demand_file, gui=gui, end=end,
                       recording_dir=directory, metadata=execution["simulation"],
                       metrics_profile=metrics_profile, sumo_defaults=configuration["sumo_defaults"],
                       signal_profile=signal_profile, **signal_options)
        simulation = execution["simulation"]
        metrics["simulation_execution_time_seconds"] = simulation["duration_seconds"]
        metrics["simulation_seed"] = simulation["seed"]
        metrics["simulation_step_length_seconds"] = simulation["step_length"]
        metrics["sumo_configuration_time_seconds"] = simulation["configuration_time_seconds"]
        # Importação local mantém o executor simples utilizável sem pós-processamento.
        from ..metrics.episode_metrics_collector import collect_episode
        aggregation_started = perf_counter()
        collected = collect_episode(directory / "raw", net_file, profile=metrics_profile)
        metrics.update(collected["metrics"])
        entities = collected["entities"]
        if demand_options is not None:
            from ..metrics.episode_metrics_collector import collect_metasettran_validation
            validation = collect_metasettran_validation(
                directory, generation, summary_metrics=collected["metrics"],
                vehicles=entities.get("vehicles") if metrics_profile == "full" else None)
            metrics.update(validation.pop("metrics"))
            execution["demand_validation"] = validation
        metrics["aggregation_time_seconds"] = perf_counter() - aggregation_started
        metrics["status"] = "completed"
    except BaseException as exc:
        metrics["status"] = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        metrics["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        # Resultados e diagnósticos são preservados também em uma falha parcial.
        persistence_started = perf_counter()
        if metrics_profile == "full":
            save_entities(directory, entities)
        metrics["entity_persistence_time_seconds"] = perf_counter() - persistence_started
        execution["collection"]["native_outputs"] = sorted(
            path.name for path in (directory / "raw").glob("*") if path.is_file())
        execution["collection"]["entity_counts"] = {
            scope: len(values) for scope, values in entities.items()}
        execution["timings_seconds"].update({
            name: value for name, value in metrics.items()
            if name.endswith("_time_seconds") or name.startswith("collection_")
        })
        if metrics_profile == "core":
            for name in execution["timings_seconds"]:
                metrics.pop(name, None)
        metrics["finished_at_utc"] = _utc_now()
        metrics["execution_time_seconds"] = perf_counter() - started
        execution.update({name: metrics[name] for name in (
            "status", "finished_at_utc", "execution_time_seconds")})
        temporary_sources = []
        if metrics_profile == "core" and metrics["status"] == "completed":
            for name in ("summary.xml.gz", "trips.xml.gz", "statistics.xml", "queues.xml.gz",
                         "metasettran_counts.xml.gz", "vehicle_routes.xml.gz"):
                path = directory / "raw" / name
                if path.is_file():
                    temporary_sources.append(path)
        execution["collection"]["retention"] = (
            "aggregates" if metrics_profile == "core" and metrics["status"] == "completed"
            else "raw_and_aggregates")
        # A medida vai do início do episódio até a publicação final; exclui apenas
        # escrita de metrics.json e remoção de entradas/observações temporárias.
        save_episode(directory, metrics, execution, include_entities=metrics_profile == "full")
        # Dados consolidados não dependem das entradas geradas. Falhas anteriores
        # preservam esses arquivos; full conserva somente suas observações úteis.
        if metrics["status"] == "completed":
            shutil.rmtree(inputs)
        for path in temporary_sources:
            path.unlink()
        if temporary_sources:
            raw = directory / "raw"
            if raw.is_dir() and not any(raw.iterdir()):
                raw.rmdir()


def main(argv: list[str] | None = None) -> int:
    """Executa episódios pelo terminal, com eixos de demanda e semáforos independentes."""
    parser = argparse.ArgumentParser(
        description="Executa episódios random ou MetaSettran, com semáforos independentes."
    )
    parser.add_argument("--episodes", type=int, default=1)
    parser.add_argument("--gui", action="store_true")
    parser.add_argument("--net-file", type=Path, default=DEFAULT_NET_FILE)
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_EPISODE_DIR,
        help="Destino dentro de outputs/outputs-random ou outputs/outputs-metasettran, conforme a demanda.",
    )
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION)
    parser.add_argument("--period", type=float, default=DEFAULT_PERIOD)
    parser.add_argument("--end", type=float)
    parser.add_argument("--demand-profile", choices=("random", "metasettran"), default="random")
    parser.add_argument("--day", help="Dia inicial de monday a sunday; MetaSettran: tuesday por padrão.")
    parser.add_argument("--start", help="Início civil de seção: 00:00, 03:00, ..., 21:00; padrão 15:00.")
    parser.add_argument("--sections", type=int, help="Número de seções consecutivas de três horas, em uma simulação.")
    parser.add_argument("--variation", type=int,
                        help="Variação 1–25 de uma faixa; episódios seguintes usam índices consecutivos.")
    parser.add_argument("--master-seed", type=int,
                        help="Seed mestra para sortear uma variação independente em cada faixa (0 a 2^63−1).")
    parser.add_argument("--variations", type=int, nargs="+",
                        help="Lista explícita de variações 1–25, uma por faixa, para reproduzir uma sequência.")
    parser.add_argument("--drain-limit", type=float, help="Escoamento após a janela de partidas; MetaSettran: 2700 s.")
    from ..demand.metasettran_demand_generator import SPATIAL_SCENARIOS
    parser.add_argument("--spatial-scenario", choices=SPATIAL_SCENARIOS,
                        help="Modelo regional integrado; regional-midpoint é alias de compatibilidade, sem orçamento lateral independente.")
    parser.add_argument("--metrics-profile", choices=("core", "full"), default="core",
                        help="core: observações padrão; full: inclui séries por via/faixa/veículo.")
    parser.add_argument("--signal-profile", choices=("current", "settran"), default="current",
                        help="current: programas do mapa; settran: plano fixo validado por interseção/TLS.")
    parser.add_argument("--settran-plan", type=str,
                        help="ID oficial para testar um plano SETTRAN fixo; sem escolha presumida.")
    parser.add_argument("--settran-intersection", dest="settran_intersections", action="append",
                        help="Nome exato da interseção na fonte; repetível. Sem essa opção, "
                             "todas as interseções do plano devem estar prontas.")
    args = parser.parse_args(argv)

    try:
        options = vars(args)
        if options["demand_profile"] == "random":
            if any(options[key] is not None for key in ("day", "start", "sections", "variation", "master_seed",
                                                       "variations", "drain_limit", "spatial_scenario")):
                raise ValueError("Seleção temporal e variação exigem --demand-profile metasettran.")
            for key in ("demand_profile", "day", "start", "sections", "variation", "master_seed", "variations",
                        "drain_limit", "spatial_scenario"):
                options.pop(key)
            run_random_episodes(**options)
        else:
            if any(option.split("=", 1)[0] in {"--duration", "--period", "--end"}
                   for option in (sys.argv[1:] if argv is None else argv)):
                raise ValueError("MetaSettran usa janela própria; não combine --duration/--period/--end.")
            run_episodes(**options)
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Erro ao executar episódios: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Execução interrompida pelo usuário.", file=sys.stderr)
        return 130

    return 0


if __name__ == "__main__":
    sys.exit(main())
