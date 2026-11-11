"""Controladores simples de referência, independentes do algoritmo treinado."""

import numpy as np
import traci


def queue_actuated_action(env):
    """Heurística reativa: favorece o verde com maior fila de entrada."""
    if getattr(env, 'action_mode', '') == 'adaptive_signals':
        actions = []
        for spec in env.action_spec:
            links = traci.trafficlight.getControlledLinks(spec['tls_id'])
            scores = []
            for index in spec['green_indices']:
                lanes = {c[0] for i, color in enumerate(env.programs[spec['tls_id']][index]['state'])
                         if color in 'Gg' and i < len(links) for c in (links[i] or ())}
                scores.append(sum(traci.lane.getLastStepHaltingNumber(lane) for lane in lanes))
            actions.append(int(np.argmax(scores)))
        return np.asarray(actions, dtype=np.int64)
    actions = []
    phase_actions = {}
    duration_mode = getattr(env, "action_mode", "green_extension") == "phase_durations"
    for target in env.targets:
        tls_id = target["tls_id"]
        current = traci.trafficlight.getPhase(tls_id)
        phases = env.programs[tls_id]
        if not duration_mode and current not in target["phase_indices"]:
            actions.append(1)
            continue
        controlled_links = traci.trafficlight.getControlledLinks(tls_id)

        def halted(index):
            lanes = {connection[0] for link_index, color in enumerate(phases[index]["state"])
                     if color in "Gg" and link_index < len(controlled_links)
                     for connection in (controlled_links[link_index] or ())}
            return sum(traci.lane.getLastStepHaltingNumber(lane) for lane in lanes)

        for phase_index in target["phase_indices"] if duration_mode else [current]:
            following = next((index for offset in range(1, len(phases) + 1)
                              if (index := (phase_index + offset) % len(phases)) in target["phase_indices"]),
                             phase_index)
            current_queue, next_queue = halted(phase_index), halted(following)
            choice = 0 if current_queue < next_queue else 2 if current_queue > next_queue else 1
            phase_actions[(tls_id, phase_index)] = choice
            if not duration_mode:
                actions.append(choice)
    if duration_mode:
        actions = [phase_actions.get((item["tls_id"], item["phase_index"]), 1)
                   if item["kind"] == "green" else 1 for item in env.action_spec]
    return np.asarray(actions, dtype=np.int64)


