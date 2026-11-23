"""Duração de cores consecutivas por movimento do programa semafórico."""

from math import isclose, isfinite

from semaforos.simulacao.janela import MeasurementWindow

COLORS = {'g': 'green', 'y': 'yellow', 'r': 'red'}


class SignalColorTimes:
    def __init__(self, programs):
        self.states = {tls: [phase['state'].lower() for phase in phases]
                       for tls, phases in programs.items()}
        self.starts = {}
        self.samples = {}

    def transition(self, tls, previous, current, now, window):
        before, after = self.states[tls][previous], self.states[tls][current]
        if not window.start - 1e-8 <= now <= window.end + 1e-8:
            return
        for link, (old, new) in enumerate(zip(before, after)):
            if old == new:
                continue
            key = tls, link
            start = self.starts.get(key)
            if old in COLORS and start is not None and now > start:
                sample = self.samples.setdefault((tls, link, old), [0., 0])
                sample[0] += now - start
                sample[1] += 1
            self.starts[key] = now

    def metrics(self, tls):
        result = {}
        for link, states in enumerate(zip(*self.states[tls])):
            for color, name in COLORS.items():
                total, count = self.samples.get((tls, link, color), (0., 0))
                result[f'link_{link}_{name}_mean_seconds'] = total / count if count else 0. if color not in states else None
        return result


def programmed_color_times(phases, link):
    """Duração média de uma passagem por cor no ciclo original."""
    states = [phase['state'][link].lower() for phase in phases]
    times = {}
    start = next((i for i, color in enumerate(states) if color != states[i - 1]), None)
    if start is not None:
        previous = None
        for i in [*range(start, len(phases)), *range(start)]:
            color = states[i]
            durations = times.setdefault(color, [])
            if color != previous:
                durations.append(0.)
            durations[-1] += phases[i]['duration']
            previous = color
    return {name: sum(times[color]) / len(times[color]) if color in times else 0. if color not in states else None
            for color, name in COLORS.items()}


def colors_from_trace(tls, phases, events, phase_totals, start, end, step):
    """Recupera uma série antiga apenas se ela reproduz os totais registrados."""
    if not events or not all(map(isfinite, (start, end, step))) or end <= start or step <= 0:
        return {}
    totals = [0.] * len(phases)
    previous = int(events[0]['previous_phase'])
    if not 0 <= previous < len(phases):
        return {}
    start_of_phase = start
    last_event = -float('inf')
    colors = SignalColorTimes({tls: phases})
    window = MeasurementWindow(start, start, end)
    for event in events:
        time = float(event['time_seconds'])
        phase = int(event['phase_index'])
        if (not isfinite(time) or time <= last_event or int(event['previous_phase']) != previous
                or not 0 <= phase < len(phases) or not isclose(time / step, round(time / step), abs_tol=1e-7)):
            return {}
        # A amostragem da fase durava um passo e usava o estado já atualizado.
        boundary = min(end, max(start, time - step))
        totals[previous] += max(0., boundary - start_of_phase)
        colors.transition(tls, previous, phase, time, window)
        previous, start_of_phase, last_event = phase, boundary, time
    totals[previous] += end - start_of_phase
    if any(not isclose(total, expected, abs_tol=1e-6) for total, expected in zip(totals, phase_totals)):
        return {}
    return colors.metrics(tls)
