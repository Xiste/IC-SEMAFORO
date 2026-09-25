"""Execução sem interface e registro de métricas de cada cenário."""

import copy
import json
from pathlib import Path

import sumolib
import traci

from .configuracao import sumo_executable, validate_reference_plan
from .demanda import create_demand
from .planos import read_plans
from .rede import baseline_values, network_programs, phase_bounds, phase_kind, validate_targets


def load_scenario(config):
    plans = read_plans(config["plans"])
    validate_reference_plan(config, plans)
    network = sumolib.net.readNet(str(config["network"]))
    programs = network_programs(config["network"])
    validate_targets(config, programs)
    return plans, network, programs


def apply_candidate(config, candidate):
    for target in config["targets"]:
        tls_id = target["tls_id"]
        logic = copy.deepcopy(traci.trafficlight.getAllProgramLogics(tls_id)[0])
        for index in target["phase_indices"]:
            if index >= len(logic.phases):
                raise ValueError(f"Fase inválida: {tls_id}, índice {index}")
            phase_kind(logic.phases[index].state)
            logic.phases[index].duration = candidate[f"{tls_id}:{index}"]
        traci.trafficlight.setProgramLogic(tls_id, logic)


def simulate(config, plans, network, candidate, output, seed):
    output.mkdir(parents=True, exist_ok=False)
    routes = create_demand(config, network, output, seed)
    cmd = [str(sumo_executable()), "-n", str(config["network"]), "-r", str(routes),
           "--begin", "0", "--end", str(config["duration_seconds"]),
           "--step-length", str(config["step_seconds"]), "--seed", str(seed),
           "--tripinfo-output", str(output / "tripinfo.xml"),
           "--summary-output", str(output / "summary.xml"),
           "--statistic-output", str(output / "statistics.xml"),
           "--no-step-log", "true"]
    (output / "inputs.json").write_text(json.dumps({
        "network": str(config["network"]), "plans": str(config["plans"]),
        "plan_id": config["plan_id"], "targets": config["targets"],
        "reference_plans": {
            target["name"]: plans[target["name"]]["plans"].get(str(config["plan_id"]))
            for target in config["targets"] if target.get("name") in plans
        },
        "candidate": candidate, "demand": config["demand"], "seed": seed,
        "duration_seconds": config["duration_seconds"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    started = False
    try:
        traci.start(cmd)
        started = True
        if candidate:
            apply_candidate(config, candidate)
        controlled_lanes = sorted({lane for target in config["targets"]
                                   for lane in traci.trafficlight.getControlledLanes(target["tls_id"])})
        halted_seconds = 0.0
        global_halted_seconds = 0.0
        departed = arrived = 0
        while traci.simulation.getTime() < config["duration_seconds"]:
            traci.simulationStep()
            departed += traci.simulation.getDepartedNumber()
            arrived += traci.simulation.getArrivedNumber()
            halted_seconds += config["step_seconds"] * sum(
                traci.lane.getLastStepHaltingNumber(lane) for lane in controlled_lanes)
            if not controlled_lanes:
                global_halted_seconds += config["step_seconds"] * sum(
                    traci.vehicle.getSpeed(vehicle) < 0.1 for vehicle in traci.vehicle.getIDList())
    finally:
        if started:
            traci.close()
    unfinished = max(0, departed - arrived)
    penalty = config["training"]["unfinished_penalty_seconds"]
    metrics = {"seed": seed, "departed": departed, "arrived": arrived,
               "unfinished": unfinished, "target_halted_vehicle_seconds": halted_seconds,
               "global_halted_vehicle_seconds": global_halted_seconds,
               "score": (halted_seconds if controlled_lanes else global_halted_seconds)
                        + unfinished * penalty}
    (output / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def run(config, output, candidate_path=None):
    plans, network, programs = load_scenario(config)
    candidate = baseline_values(config, programs)
    if candidate_path:
        changes = json.loads(Path(candidate_path).read_text(encoding="utf-8"))
        if set(changes) - set(candidate):
            raise ValueError("Candidato contém semáforo/fase fora de targets")
        if any(not isinstance(value, (int, float)) or value <= 0 for value in changes.values()):
            raise ValueError("Durações do candidato devem ser positivas")
        for key, value in changes.items():
            tls_id, index = key.rsplit(":", 1)
            phase = programs[tls_id][int(index)]
            lower, upper = phase_bounds(config, phase)
            if not lower <= value <= upper:
                raise ValueError(f"Duração {key} fora dos limites permitidos: {lower} a {upper} s")
        candidate.update(changes)
    results = [simulate(config, plans, network, candidate, output / f"seed_{seed}", seed)
               for seed in config["seeds"]]
    summary = {"mean_score": sum(item["score"] for item in results) / len(results),
               "runs": results}
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
