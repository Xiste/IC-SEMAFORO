"""Definição única do aquecimento e da janela usada pelas métricas."""
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class MeasurementWindow:
    warmup: float
    start: float
    end: float

    def elapsed(self, now):
        return max(0.0, min(float(now), self.end) - self.start)

    def contains_step(self, previous, now):
        return previous >= self.start - 1e-8 and now <= self.end + 1e-8 and now > previous

    def metadata(self, now):
        return {'warmup_seconds': self.warmup, 'measurement_start_seconds': self.start,
                'measurement_end_seconds': self.end, 'measured_seconds': self.elapsed(now),
                'measurement_complete': bool(now >= self.end)}


def measurement_window(config):
    settings = config.get('measurement', {})
    warmup = float(settings.get('warmup_seconds', 0))
    start = float(settings.get('start_seconds', warmup))
    end = float(settings.get('end_seconds', config['duration_seconds']))
    horizon, step = float(config['duration_seconds']), float(config['step_seconds'])
    if not all(math.isfinite(v) for v in (warmup, start, end, horizon, step)) or step <= 0:
        raise ValueError('Tempos de medição devem ser finitos e o passo positivo')
    if not 0 <= warmup <= start < end <= horizon:
        raise ValueError('Use 0 ≤ aquecimento ≤ início da medição < fim da medição ≤ duração total')
    if any(abs(v / step - round(v / step)) > 1e-7 for v in (warmup, start, end)):
        raise ValueError('Aquecimento e limites da medição devem ser múltiplos do passo SUMO')
    return MeasurementWindow(warmup, start, end)
