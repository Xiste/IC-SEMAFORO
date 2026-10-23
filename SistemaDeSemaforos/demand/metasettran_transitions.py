"""Integração cronológica sem recalibrar os volumes das seções MetaSettran.

Cada fronteira modifica somente 15 minutos de cada lado, resolução sustentada
pelas curvas de origem. As duas integrais são preservadas separadamente. O
transporte por quantis reposiciona as partidas existentes: não sorteia viagens,
não remove viagens e não muda a seção à qual cada partida pertence.
"""

from bisect import bisect_right
import math


def _knot(second, rate):
    return {"week_second": second, "rate_per_second": rate}


class _Curve:
    """Integral e inversa analíticas de uma taxa linear por partes."""

    def __init__(self, knots):
        self.times = [float(row["week_second"]) for row in knots]
        self.rates = [float(row["rate_per_second"]) for row in knots]
        if (len(self.times) < 2 or
                any(not math.isfinite(value) for value in self.times + self.rates) or
                any(rate < 0 for rate in self.rates) or
                any(right <= left for left, right in zip(self.times, self.times[1:]))):
            raise ValueError("Curva temporal requer suporte crescente e taxas finitas não negativas.")
        self.mass = [0.0]
        for index, (left, right) in enumerate(zip(self.times, self.times[1:])):
            self.mass.append(self.mass[-1] + (right - left) *
                             (self.rates[index] + self.rates[index + 1]) / 2)

    def _index(self, second):
        if not math.isfinite(second) or not self.times[0] <= second <= self.times[-1]:
            raise ValueError("Horário fora do suporte da transição MetaSettran.")
        return min(bisect_right(self.times, second) - 1, len(self.times) - 2)

    def rate(self, second):
        index = self._index(second)
        fraction = (second - self.times[index]) / (self.times[index + 1] - self.times[index])
        return self.rates[index] + (self.rates[index + 1] - self.rates[index]) * fraction

    def cumulative(self, second):
        index = self._index(second)
        elapsed = second - self.times[index]
        return self.mass[index] + elapsed * (self.rates[index] + self.rate(second)) / 2

    def integral(self, begin, end):
        if begin > end:
            raise ValueError("Intervalo temporal invertido.")
        return self.cumulative(end) - self.cumulative(begin)

    def inverse(self, mass):
        if not math.isfinite(mass) or not 0 <= mass <= self.mass[-1]:
            raise ValueError("Quantil fora da integral da curva temporal.")
        if mass == 0:
            return self.times[0]
        if mass == self.mass[-1]:
            return self.times[-1]
        index = min(bisect_right(self.mass, mass) - 1, len(self.times) - 2)
        local_mass = mass - self.mass[index]
        width = self.times[index + 1] - self.times[index]
        slope = (self.rates[index + 1] - self.rates[index]) / width
        # A forma racionalizada evita cancelamento quando a inclinação é pequena.
        discriminant = max(0.0, self.rates[index] ** 2 + 2 * slope * local_mass)
        denominator = self.rates[index] + math.sqrt(discriminant)
        elapsed = 2 * local_mass / denominator if denominator else 0.0
        return self.times[index] + min(width, max(0.0, elapsed))

    def clip(self, begin, end):
        return ([_knot(begin, self.rate(begin))] +
                [_knot(second, rate) for second, rate in zip(self.times, self.rates)
                 if begin < second < end] + [_knot(end, self.rate(end))])


def _bridge(begin, end, start_rate, end_rate, mass, ramp=None):
    """Ponte positiva com extremos fixos e integral exata.

    Com dados de 15 minutos, um nó central basta. O fallback com patamar
    interior também aceita curvas futuras com quedas mais estreitas, sem
    produzir taxa negativa nem criar massa para satisfazer os extremos.
    """
    width = end - begin
    ramp = width / 2 if ramp is None else ramp
    endpoint_sum = start_rate + end_rate
    if mass < ramp * endpoint_sum / 2:
        if mass == 0:
            raise ValueError("Janela de massa zero não pode ter extremos positivos.")
        ramp = mass / endpoint_sum
    center_rate = max(0.0, (mass - ramp * endpoint_sum / 2) / (width - ramp))
    result = [_knot(begin, start_rate), _knot(begin + ramp, center_rate)]
    if end - ramp > begin + ramp:
        result.append(_knot(end - ramp, center_rate))
    result.append(_knot(end, end_rate))
    return result


def _bounded_join(width, masses, outers, preferred, peak, floor=0.0):
    """Maior rampa viável sem taxa negativa nem pico superior aos dados vizinhos.

    M = r*(a+b)/2 + (w-r)*c, com 0 <= b,c <= pico. A interseção
    dos limites de b nas duas meias-janelas define uma busca escalar monotônica.
    Não há percentual de atenuação ou novo orçamento de veículos.
    """
    def interval(ramp):
        lower = max([floor] + [2 * (mass - peak * width) / ramp + 2 * peak - outer
                            for mass, outer in zip(masses, outers)])
        upper = min([peak] + [2 * (mass - floor * width) / ramp + 2 * floor - outer
                              for mass, outer in zip(masses, outers)])
        return lower, upper
    low, high = 1e-6, width / 2
    lower, upper = interval(low)
    if lower > upper:
        raise ValueError("Fronteira sem ponte contínua que conserve massa e não crie pico: "
                         "uma meia-janela vazia adjacente a outra constante positiva exige revisão explícita.")
    for _ in range(60):
        midpoint = (low + high) / 2
        lower, upper = interval(midpoint)
        if lower <= upper:
            low = midpoint
        else:
            high = midpoint
    lower, upper = interval(low)
    return max(lower, min(upper, preferred)), low


def compose_rate_curves(section_knots, starts, duration=10800, half_window=900):
    """Une taxas absolutas de seções consecutivas e conserva cada orçamento.

    Retorna ``(knots, diagnostics)``. Não altera as listas recebidas. O relógio
    absoluto pode ultrapassar o fim da semana; não há módulo aplicado aqui.
    """
    if (not section_knots or len(section_knots) != len(starts) or
            not math.isfinite(duration) or not math.isfinite(half_window) or
            half_window <= 0 or duration < 2 * half_window):
        raise ValueError("Seções e janelas de transição inválidas.")
    if any(not math.isfinite(start) for start in starts) or any(
            not math.isclose(right, left + duration, rel_tol=0, abs_tol=1e-8)
            for left, right in zip(starts, starts[1:])):
        raise ValueError("As seções devem ser cronológicas, contíguas e sem sobreposição.")
    originals = [_Curve(knots) for knots in section_knots]
    sections = [curve.clip(begin, begin + duration) for curve, begin in zip(originals, starts)]
    boundaries = []
    for index, boundary in enumerate(starts[1:]):
        left, right = originals[index], originals[index + 1]
        begin, end = boundary - half_window, boundary + half_window
        left_mass, right_mass = left.integral(begin, boundary), right.integral(boundary, end)
        outer_left, outer_right = left.rate(begin), right.rate(end)
        old_left, old_right = left.rate(boundary), right.rate(boundary)
        harmonic = 2 * old_left * old_right / (old_left + old_right) if old_left + old_right else 0.0
        # Para os três nós [extremo, centro, junção], M = w*(a+2*c+b)/4.
        # Limitar b conserva a não negatividade de c em ambas as meias-janelas.
        feasible = max(0.0, min(4 * left_mass / half_window - outer_left,
                                4 * right_mass / half_window - outer_right))
        common = min(harmonic, feasible)
        peak_bound_applied = False
        floor_bound_relaxed = False
        changed = not math.isclose(old_left, old_right, rel_tol=1e-12, abs_tol=1e-15)
        if changed:
            left_bridge = _bridge(begin, boundary, outer_left, common, left_mass)
            right_bridge = _bridge(boundary, end, common, outer_right, right_mass)
            peak = max(row["rate_per_second"] for curve in (left, right)
                       for row in curve.clip(begin if curve is left else boundary,
                                             boundary if curve is left else end))
            floor = min(row["rate_per_second"] for curve in (left, right)
                        for row in curve.clip(begin if curve is left else boundary,
                                              boundary if curve is left else end))
            if (max(row["rate_per_second"] for row in left_bridge + right_bridge) > peak * (1 + 1e-12) or
                    min(row["rate_per_second"] for row in left_bridge + right_bridge) < floor - 1e-12):
                peak_bound_applied = True
                try:
                    common, ramp = _bounded_join(half_window, (left_mass, right_mass),
                                                 (outer_left, outer_right), common, peak, floor)
                except ValueError:
                    floor_bound_relaxed = True
                    common, ramp = _bounded_join(half_window, (left_mass, right_mass),
                                                 (outer_left, outer_right), common, peak)
                left_bridge = _bridge(begin, boundary, outer_left, common, left_mass, ramp)
                right_bridge = _bridge(boundary, end, common, outer_right, right_mass, ramp)
            sections[index] = [row for row in sections[index] if row["week_second"] < begin] + left_bridge
            sections[index + 1] = right_bridge + [row for row in sections[index + 1] if row["week_second"] > end]
        else:
            # Não deformar uma curva que já chega contínua à fronteira.
            common = old_left
            sections[index + 1][0]["rate_per_second"] = common
        new_left, new_right = _Curve(sections[index]), _Curve(sections[index + 1])
        peak_before = max(row["rate_per_second"] for row in
                          left.clip(begin, boundary) + right.clip(boundary, end))
        peak_after = max(row["rate_per_second"] for row in
                         new_left.clip(begin, boundary) + new_right.clip(boundary, end))
        boundaries.append({
            "week_second": boundary,
            "original_left_rate_per_second": old_left,
            "original_right_rate_per_second": old_right,
            "joined_rate_per_second": common,
            "harmonic_join_rate_per_second": harmonic,
            "join_limited_for_nonnegative_rate": changed and common < harmonic,
            "join_adjusted_to_preserve_peak_envelope": peak_bound_applied,
            "lower_envelope_relaxed_for_feasibility": floor_bound_relaxed,
            "changed": changed,
            # Conservação de massa pode compensar uma queda local por uma
            # elevação próxima. Explicitar o pico permite avaliar esse efeito.
            "peak_rate_before_per_second": peak_before,
            "peak_rate_after_per_second": peak_after,
            "peak_rate_ratio_after_before": peak_after / peak_before if peak_before else None,
            "minimum_rate_before_per_second": min(row["rate_per_second"] for row in
                left.clip(begin, boundary) + right.clip(boundary, end)),
            "minimum_rate_after_per_second": min(row["rate_per_second"] for row in
                new_left.clip(begin, boundary) + new_right.clip(boundary, end)),
            "expected_left_half_window_before": left_mass,
            "expected_left_half_window_after": new_left.integral(begin, boundary),
            "expected_right_half_window_before": right_mass,
            "expected_right_half_window_after": new_right.integral(boundary, end),
            "windows": [{
                "seconds": width,
                "before_left": left.integral(boundary - width, boundary),
                "before_right": right.integral(boundary, boundary + width),
                "after_left": new_left.integral(boundary - width, boundary),
                "after_right": new_right.integral(boundary, boundary + width),
            } for width in (300, 900) if width <= half_window],
        })
    section_diagnostics = []
    combined = []
    for index, (original, knots, begin) in enumerate(zip(originals, sections, starts)):
        before, after = original.integral(begin, begin + duration), _Curve(knots).mass[-1]
        if not math.isclose(before, after, rel_tol=1e-11, abs_tol=1e-8):
            raise ValueError("A harmonização alterou o orçamento esperado da seção.")
        section_diagnostics.append({"index": index, "begin_week_second": begin,
                                    "expected_before": before, "expected_after": after,
                                    "difference": after - before})
        if combined and not math.isclose(combined[-1]["rate_per_second"], knots[0]["rate_per_second"],
                                         rel_tol=1e-12, abs_tol=1e-15):
            raise ValueError("Junção temporal descontínua após harmonização.")
        combined.extend(knots if not combined else knots[1:])
    return combined, {
        "method": "positive_peak_bounded_piecewise_linear_mass_conserving_boundary_bridge",
        "half_window_seconds": half_window,
        "sections": section_diagnostics,
        "boundaries": boundaries,
        "expected_before": math.fsum(row["expected_before"] for row in section_diagnostics),
        "expected_after": math.fsum(row["expected_after"] for row in section_diagnostics),
    }


def transport_times(times, old_knots, new_knots, begin, duration):
    """Transporta horários absolutos pelo mesmo quantil, sem trocar de seção.

    O total esperado deve ser conservado. Quantis e ordem são preservados; a
    implementação não cria aleatoriedade adicional nem modifica o número de IDs.
    """
    end = begin + duration
    old, new = (_Curve(_Curve(knots).clip(begin, end)) for knots in (old_knots, new_knots))
    if not math.isclose(old.mass[-1], new.mass[-1], rel_tol=1e-11, abs_tol=1e-8):
        raise ValueError("Transporte temporal requer conservação da expectativa da seção.")
    times = list(times)
    if times and old.mass[-1] == 0:
        raise ValueError("Não transportar partidas em uma seção de intensidade zero.")
    if old.times == new.times and old.rates == new.rates:
        result = times
    else:
        result = []
        for second in times:
            if not math.isfinite(second) or not begin <= second < end:
                raise ValueError("Partida fora do intervalo semiaberto da seção.")
            quantile = old.cumulative(second) / old.mass[-1]
            moved = new.inverse(min(new.mass[-1], quantile * new.mass[-1]))
            result.append(min(math.nextafter(end, begin), max(begin, moved)))
    if any(not math.isfinite(second) or not begin <= second < end for second in result):
        raise ValueError("Partida fora do intervalo semiaberto da seção.")
    if any(right < left for left, right in zip(result, result[1:])):
        raise ValueError("Partidas devem estar ordenadas cronologicamente.")
    return result
