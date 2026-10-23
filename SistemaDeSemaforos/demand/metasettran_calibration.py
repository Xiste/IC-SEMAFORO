"""Curvas locais de carros e referências semanais, sem extrapolação regional.

``calibrate`` preserva o piloto histórico; ``calibrate_weekly`` compartilha
um modelo entre os 56 contextos, convertendo UTC para o relógio civil de Brasília.
A origem UTC é uma convenção experimental do projeto, não um fato do equipamento.
"""

from bisect import bisect_right
from collections import defaultdict
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import math
from pathlib import Path
import statistics
from zoneinfo import ZoneInfo


VERSION = "metasettran-tuesday-car-v1"
DEFAULT_CSV = Path(__file__).resolve().parents[2] / "docs" / "Medicoes_5_6.csv"
SENSORS = ("5", "6")
BIN_SECONDS = 900
MAX_INTERVAL_SECONDS = 120
MIN_COVERAGE = 0.95
MIN_TRAINING_DATES = 3
TRAIN_BEFORE = date(2026, 8, 24)
PRIMARY_VALIDATION_DATE = date(2026, 8, 25)
SUPPORT_START = 14 * 3600 + 45 * 60
SUPPORT_END = 18 * 3600 + 15 * 60
START_WEEK_SECOND = 86400 + 15 * 3600
END_WEEK_SECOND = 86400 + 18 * 3600
COUNTS = ("car", "bike", "motorcycle", "bus", "truck", "person", "vehicle_total")
HOLIDAYS = frozenset((date(2026, 8, 15), date(2026, 8, 31), date(2026, 9, 7)))
WEEKLY_VERSION = "metasettran-weekly-car-v1"
WEEK_SECONDS = 7 * 86400
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
CIVIL_TIMEZONE = ZoneInfo("America/Sao_Paulo")


def _source_to_civil(stamp, source_time_convention):
    """Converte uma vez o timestamp original; os bins internos usam hora civil.

    Rejeitar entradas aware evita reaplicar a conversão a dados já tratados.
    A remoção de tzinfo ocorre somente após astimezone, para compatibilidade
    com a álgebra civil semanal existente. Não se subtraem três horas à mão.
    """
    if stamp.tzinfo is not None:
        raise ValueError("A conversão requer o timestamp original sem fuso; não reconverter horários tratados.")
    if source_time_convention == "utc":
        return stamp.replace(tzinfo=timezone.utc).astimezone(CIVIL_TIMEZONE).replace(tzinfo=None)
    if source_time_convention == "legacy_civil":
        return stamp
    raise ValueError("source_time_convention deve ser 'utc' ou 'legacy_civil'.")


def _quantile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _statistics(values):
    median = statistics.median(values)
    return {
        "n_dates": len(values),
        "median": median,
        "q25": _quantile(values, 0.25),
        "q75": _quantile(values, 0.75),
        "mad": statistics.median(abs(value - median) for value in values),
        "min": min(values),
        "max": max(values),
    }


def interpolate_rate(knots, week_second):
    """Interpola linearmente car/s, sem extrapolar além do suporte observado."""
    times = [knot["week_second"] for knot in knots]
    if not times or not math.isfinite(week_second) or not times[0] <= week_second <= times[-1]:
        raise ValueError("Horário fora do suporte da calibração MetaSettran.")
    right = bisect_right(times, week_second)
    if right == len(times):
        return knots[-1]["rate_per_second"]
    left = right - 1
    fraction = (week_second - times[left]) / (times[right] - times[left])
    return knots[left]["rate_per_second"] * (1 - fraction) + knots[right]["rate_per_second"] * fraction


def integrate_rate(knots, begin, end):
    """Integra a curva linear; o resultado é uma contagem esperada de carros."""
    if begin > end:
        raise ValueError("Intervalo de integração invertido.")
    interpolate_rate(knots, begin)
    interpolate_rate(knots, end)
    cuts = [begin] + [k["week_second"] for k in knots if begin < k["week_second"] < end] + [end]
    return sum(
        (right - left) * (interpolate_rate(knots, left) + interpolate_rate(knots, right)) / 2
        for left, right in zip(cuts, cuts[1:])
    )


def _read_measurements(csv_path, class_offset_hours=0, source_time_convention=None):
    if source_time_convention is not None and class_offset_hours:
        raise ValueError("Não combinar conversão de fuso com deslocamento legado de composição.")
    contents = Path(csv_path).read_bytes()
    reader = csv.DictReader(io.StringIO(contents.decode("utf-8-sig")))
    required = {"hora_inicio", "hora_fim", "vlink_id", "descricao_linha", "speed_pxm", "speed_pxm_max", *COUNTS}
    if not required.issubset(reader.fieldnames or ()):
        raise ValueError("CSV MetaSettran sem todas as colunas de medição necessárias.")
    records = {sensor: [] for sensor in SENSORS}
    quality = {
        "rows": 0, "intervals_60_seconds": 0, "excluded_long_intervals": 0,
        "excluded_long_interval_seconds": 0, "speed_nonzero_rows": 0,
        "sensor_labels": {sensor: set() for sensor in SENSORS},
        "class_sums": {sensor: {name: 0 for name in COUNTS} for sensor in SENSORS},
        "training_tuesday_class_sums": {sensor: {} for sensor in SENSORS},
    }
    for line, row in enumerate(reader, 2):
        try:
            sensor = row["vlink_id"]
            if sensor not in records:
                raise ValueError("sensor diferente de 5/6")
            begin, end = (datetime.fromisoformat(row[name]) for name in ("hora_inicio", "hora_fim"))
            if begin.tzinfo is not None or end.tzinfo is not None:
                raise ValueError("timestamps com fuso explícito exigem revisão da convenção")
            duration = (end - begin).total_seconds()
            if duration <= 0:
                raise ValueError("intervalo sem duração positiva")
            counts = {name: int(row[name]) for name in COUNTS}
            if any(value < 0 for value in counts.values()):
                raise ValueError("contagem negativa")
            if counts["vehicle_total"] != counts["car"] + counts["bus"] + counts["truck"]:
                raise ValueError("vehicle_total difere de car+bus+truck")
            speeds = [float(row[name]) for name in ("speed_pxm", "speed_pxm_max")]
            if not all(math.isfinite(value) and value >= 0 for value in speeds):
                raise ValueError("velocidade inválida")
        except (TypeError, ValueError, KeyError) as exc:
            raise ValueError(f"Medição inválida na linha {line}: {exc}") from exc
        records[sensor].append((begin, end, counts["car"], duration))
        quality["rows"] += 1
        quality["intervals_60_seconds"] += duration == 60
        quality["excluded_long_intervals"] += duration > MAX_INTERVAL_SECONDS
        if duration > MAX_INTERVAL_SECONDS:
            quality["excluded_long_interval_seconds"] += duration
        quality["speed_nonzero_rows"] += any(speeds)
        quality["sensor_labels"][sensor].add(row["descricao_linha"])
        for name, value in counts.items():
            quality["class_sums"][sensor][name] += value
        if duration <= MAX_INTERVAL_SECONDS:
            # Composição e curvas devem usar o mesmo dia civil, inclusive na
            # sensibilidade UTC. Os timestamps originais em records não mudam.
            cursor = (_source_to_civil(begin, source_time_convention) if source_time_convention is not None
                      else begin + timedelta(hours=class_offset_hours))
            class_end = (_source_to_civil(end, source_time_convention) if source_time_convention is not None
                         else end + timedelta(hours=class_offset_hours))
            while cursor < class_end:
                stop = min(class_end, datetime.combine(cursor.date() + timedelta(days=1), datetime.min.time()))
                if cursor.weekday() == 1 and cursor.date() < TRAIN_BEFORE and cursor.date() not in HOLIDAYS:
                    daily = quality["training_tuesday_class_sums"][sensor].setdefault(
                        cursor.date().isoformat(), {name: 0.0 for name in COUNTS})
                    for name, value in counts.items():
                        daily[name] += value * (stop - cursor).total_seconds() / duration
                cursor = stop
    quality["gaps"] = {}
    for sensor, values in records.items():
        if not values:
            raise ValueError(f"CSV sem medições do sensor {sensor}.")
        values.sort()
        gaps = []
        for previous, current in zip(values, values[1:]):
            difference = (current[0] - previous[1]).total_seconds()
            if difference < 0:
                raise ValueError(f"Duplicata ou sobreposição no sensor {sensor}, {current[0].isoformat()}.")
            if difference > 0:
                gaps.append(difference)
        quality["gaps"][sensor] = {"n": len(gaps), "seconds": sum(gaps), "max_seconds": max(gaps, default=0)}
        quality["sensor_labels"][sensor] = sorted(quality["sensor_labels"][sensor])
    return records, quality, hashlib.sha256(contents).hexdigest()


def _aggregate(records, offset_hours=0, source_time_convention=None):
    """Rateia somente intervalos aceitos; ausência permanece ausência."""
    if source_time_convention is not None and offset_hours:
        raise ValueError("Não combinar conversão de fuso com deslocamento legado de curvas.")
    bins = {sensor: defaultdict(lambda: [0.0, 0.0]) for sensor in SENSORS}
    shift = timedelta(hours=offset_hours)
    for sensor, values in records.items():
        for begin, end, cars, duration in values:
            if duration > MAX_INTERVAL_SECONDS:
                continue
            if source_time_convention is None:
                begin, end = begin + shift, end + shift
            else:
                begin, end = (_source_to_civil(stamp, source_time_convention) for stamp in (begin, end))
            while begin < end:
                bucket = begin.replace(minute=begin.minute // 15 * 15, second=0, microsecond=0)
                stop = min(end, bucket + timedelta(seconds=BIN_SECONDS))
                seconds = (stop - begin).total_seconds()
                item = bins[sensor][bucket]
                item[0] += seconds
                item[1] += cars * seconds / duration
                begin = stop
    return bins


def _curve_for_date(bins, day):
    midnight = datetime.combine(day, datetime.min.time())
    curve = []
    for second in range(SUPPORT_START, SUPPORT_END, BIN_SECONDS):
        exposure, cars = bins.get(midnight + timedelta(seconds=second), (0, 0))
        if exposure < BIN_SECONDS * MIN_COVERAGE:
            return None
        curve.append(cars / exposure)
    return curve


def _validate_dates(bins, knots, dates):
    observations = []
    daily_counts = []
    excluded = 0
    for day in dates:
        midnight = datetime.combine(day, datetime.min.time())
        daily = {"date": day.isoformat(), "counts": [], "exposure_seconds": [], "eligible": []}
        for second in range(15 * 3600, 18 * 3600, BIN_SECONDS):
            exposure, cars = bins.get(midnight + timedelta(seconds=second), (0, 0))
            eligible = exposure >= BIN_SECONDS * MIN_COVERAGE
            daily["counts"].append(cars if exposure else None)
            daily["exposure_seconds"].append(exposure)
            daily["eligible"].append(eligible)
            if not eligible:
                excluded += 1
                continue
            expected = integrate_rate(knots, 86400 + second, 86400 + second + BIN_SECONDS)
            observations.append({
                "date": day.isoformat(), "start": f"{second // 3600:02}:{second % 3600 // 60:02}",
                "exposure_seconds": exposure, "observed_cars": cars,
                "observed_cars_normalized_15min": cars * BIN_SECONDS / exposure,
                "predicted_cars_15min": expected,
            })
        daily_counts.append(daily)
    errors = [abs(row["predicted_cars_15min"] - row["observed_cars_normalized_15min"]) for row in observations]
    total = sum(row["observed_cars_normalized_15min"] for row in observations)
    return {
        "dates": [day.isoformat() for day in dates], "n_windows": len(observations), "excluded_windows": excluded,
        "mae_cars_per_15min": statistics.mean(errors) if errors else None,
        "wape": sum(errors) / total if total else None,
        "observations": observations,
        "daily_counts": daily_counts,
        "daily_counts_semantics": "12 unexpanded recorded car counts prorated at 15-minute boundaries; None means no accepted exposure, not zero traffic; eligibility is separate.",
        "meaning": "Temporal prediction against held-out car counts; not a validation of SUMO volumes or sensor-edge mapping.",
    }


def _time_diagnostic(bins):
    result = {}
    for sensor, values in bins.items():
        hourly = defaultdict(lambda: [0.0, 0.0])
        for stamp, (exposure, cars) in values.items():
            if stamp.date() not in HOLIDAYS:
                item = hourly[stamp.replace(minute=0)]
                item[0] += exposure
                item[1] += cars
        hours = defaultdict(list)
        for stamp, (exposure, cars) in hourly.items():
            if exposure >= 3600 * MIN_COVERAGE:
                hours[stamp.hour].append(cars * 3600 / exposure)
        medians = {str(hour): statistics.median(rates) for hour, rates in sorted(hours.items())}
        result[sensor] = {
            "median_cars_per_hour": medians,
            "peak_hour": int(max(medians, key=medians.get)) if medians else None,
            "minimum_hour": int(min(medians, key=medians.get)) if medians else None,
        }
    return result


def _daily_fraction(bins, training, classes):
    """Fração 15–18/24h apenas em terças de treino integralmente observadas."""
    rows = []
    for day in training:
        midnight = datetime.combine(day, datetime.min.time())
        values = [bins.get(midnight + timedelta(seconds=i * BIN_SECONDS), (0, 0)) for i in range(96)]
        if any(exposure != BIN_SECONDS for exposure, _ in values):
            continue
        daily = sum(cars for _, cars in values)
        selected = sum(cars for _, cars in values[60:72])
        if daily:
            classified = classes.get(day.isoformat(), {})
            motorized = sum(classified.get(c, 0) for c in ("car", "motorcycle", "bus", "truck"))
            rows.append({"date": day.isoformat(), "daily_cars": daily,
                         "cars_15_18": selected, "fraction": selected / daily,
                         "car_fraction_motorized": classified.get("car", 0) / motorized if motorized else None})
    return {"dates": rows, "median": statistics.median(r["fraction"] for r in rows) if rows else None,
            "min": min((r["fraction"] for r in rows), default=None),
            "max": max((r["fraction"] for r in rows), default=None),
            "car_fraction_motorized_median": statistics.median(r["car_fraction_motorized"] for r in rows)
                if rows and all(r["car_fraction_motorized"] is not None for r in rows) else None,
            "coverage": "96 complete 900-second bins; training Tuesdays only; no gap expansion",
            "transfer_status": "Measured locally; using this fraction on another corridor is an estimate."}


def calibrate(csv_path=DEFAULT_CSV, time_interpretation="brasilia"):
    """Retorna parâmetros/limitações JSON serializáveis, sem escrever arquivos.

    O piloto usa cinco terças com suporte 14:45–18:15 coberto nos dois
    sensores no CSV original; isso não exige nem afirma cobertura de 24 h.
    Datas posteriores ao corte nunca entram na curva nem na dispersão.
    ``utc`` é uma seleção explícita de sensibilidade, não uma inferência.
    """
    if time_interpretation not in ("brasilia", "utc"):
        raise ValueError("time_interpretation deve ser 'brasilia' ou 'utc'.")
    records, quality, digest = _read_measurements(
        csv_path, class_offset_hours=0 if time_interpretation == "brasilia" else -3)
    local = _aggregate(records, 0)
    shifted = _aggregate(records, -3)
    bins = local if time_interpretation == "brasilia" else shifted
    observed_dates = sorted({stamp.date() for values in bins.values() for stamp in values if stamp.weekday() == 1})
    candidates = [day for day in observed_dates if day < TRAIN_BEFORE and day not in HOLIDAYS]
    curves = {sensor: {day: _curve_for_date(bins[sensor], day) for day in candidates} for sensor in SENSORS}
    training = [day for day in candidates if all(curves[sensor][day] is not None for sensor in SENSORS)]
    if len(training) < MIN_TRAINING_DATES:
        raise ValueError("MetaSettran requer pelo menos três terças de treino com cobertura suficiente nos dois sensores.")
    validation = [PRIMARY_VALIDATION_DATE] if PRIMARY_VALIDATION_DATE in observed_dates else []
    post_validation = [day for day in observed_dates if day > PRIMARY_VALIDATION_DATE and day not in HOLIDAYS]
    profiles = {}
    for sensor in SENSORS:
        knots = []
        for index, second in enumerate(range(SUPPORT_START, SUPPORT_END, BIN_SECONDS)):
            stats = _statistics([curves[sensor][day][index] for day in training])
            center = second + BIN_SECONDS // 2
            knots.append({
                "week_second": 86400 + center,
                "civil_time": f"{center // 3600:02}:{center % 3600 // 60:02}:{center % 60:02}",
                "rate_per_second": stats["median"], "q25_rate_per_second": stats["q25"],
                "q75_rate_per_second": stats["q75"], "mad_rate_per_second": stats["mad"],
                "n_dates": stats["n_dates"],
            })
        training_curves = []
        for day in training:
            rate_values = curves[sensor][day]
            day_knots = [{**knot, "rate_per_second": rate} for knot, rate in zip(knots, rate_values)]
            training_curves.append({"date": day.isoformat(), "rates_per_second": rate_values,
                                    "cars_15_18_interpolated": integrate_rate(day_knots, START_WEEK_SECOND, END_WEEK_SECOND)})
        profiles[sensor] = {
            "knots": knots, "training_curves": training_curves,
            "daily_fraction_15_18": _daily_fraction(bins[sensor], training, quality["training_tuesday_class_sums"][sensor]),
            "expected_cars_15_18": integrate_rate(knots, START_WEEK_SECOND, END_WEEK_SECOND),
            "target_counts": [integrate_rate(knots, begin, begin + BIN_SECONDS)
                              for begin in range(START_WEEK_SECOND, END_WEEK_SECOND, BIN_SECONDS)],
            "training_cars_15_18_dispersion": _statistics([curve["cars_15_18_interpolated"] for curve in training_curves]),
            "validation": {"primary": _validate_dates(bins[sensor], knots, validation),
                           "post": _validate_dates(bins[sensor], knots, post_validation)},
        }
    return {
        "version": VERSION, "source": {"name": Path(csv_path).name, "sha256": digest, "count_column": "car"},
        "time": {
            "timezone": "America/Sao_Paulo", "interpretation": time_interpretation,
            "offset_applied_hours": 0 if time_interpretation == "brasilia" else -3,
            "status": "provisional_owner_attestation" if time_interpretation == "brasilia" else "explicit_unconfirmed_utc_sensitivity",
            "provenance": "User states timestamps are Brasilia time; CSV has no timezone metadata. Repository history documents only a Downloads copy, not the exporter clock.",
            "decision": "Keep the owner's civil clock; matching peak times at other sites cannot prove this sensor's timezone.",
            "independent_comparison": "https://repositorio.ufu.br/handle/123456789/49701",
        },
        "selection": {"day": "tuesday", "start": "15:00", "end": "18:00", "departure_seconds": 10800,
                      "start_week_second": START_WEEK_SECOND, "end_week_second": END_WEEK_SECOND},
        "method": {
            "class": "car_only_as_passenger", "bin_seconds": BIN_SECONDS, "maximum_accepted_interval_seconds": MAX_INTERVAL_SECONDS,
            "minimum_coverage": MIN_COVERAGE, "coverage_status": "conservative prototype quality threshold, not a calibrated detector health guarantee",
            "count_allocation": "uniform within each recorded interval; fractional counts at boundaries are estimates",
            "estimator": "median across common training Tuesdays with eligible 14:45-18:15 support in both sensors; no whole-day completeness requirement and no gap filling",
            "resolution_reason": "Predominantly one-minute source intervals support 15-minute aggregation, retaining within-section changes while reducing minute-level count noise; the independent UFU study also analyzes 15-minute windows.",
            "interpolation": "linear between adjacent 15-minute bin centers; one neighboring bin at each end, no additional smoothing window",
            "dispersion": "unscaled MAD and IQR across training dates; descriptive uncertainty, no fixed variation percentage",
            "sampling_limit": "A Poisson realization conditional on the median curve represents arrival randomness only, not all observed between-date variability.",
            "training_before": TRAIN_BEFORE.isoformat(), "holidays_excluded": sorted(day.isoformat() for day in HOLIDAYS),
        },
        "training_dates": [day.isoformat() for day in training],
        "excluded_training_dates": [day.isoformat() for day in candidates if day not in training],
        "validation_dates": [day.isoformat() for day in validation],
        "post_validation_dates": [day.isoformat() for day in post_validation],
        "sensors": profiles, "quality": quality,
        "diagnostics": {
            "time_sensitivity": {"brasilia": _time_diagnostic(local), "utc_minus_3": _time_diagnostic(shifted)},
            "time_sensitivity_usage": "Descriptive sensitivity only; no selection by peak matching and no contribution to training/validation parameters.",
        },
        "limitations": [
            "Prototype of one Tuesday section, not 56 calibrated weekly contexts.",
            "Sensor positions and directions are not established by these CSV labels; spatial mapping remains a separate assumption.",
            "Counts/classification are not independently ground-truthed; car-only does not reproduce the full vehicle mix.",
            "A few eligible Tuesdays cannot characterize seasonal changes or 25 independent observed scenarios.",
            "Linear interpolation can change integrated bin counts slightly; holdout predictions integrate the same interpolated curve.",
        ],
    }


def _cyclic_knots(knots):
    """Inclui os vizinhos reais da semana, sem repetir a taxa da fronteira."""
    return [{**knots[-1], "week_second": knots[-1]["week_second"] - WEEK_SECONDS},
            *knots,
            {**knots[0], "week_second": knots[0]["week_second"] + WEEK_SECONDS}]


def _window_knots(knots, begin, end):
    # O centro da primeira e última janela adjacente evita uma extrapolação
    # constante, inclusive quando a seleção ultrapassa domingo/meia-noite.
    central = [knot for knot in knots if 0 <= knot["week_second"] < WEEK_SECONDS]
    expanded = [dict(knot, week_second=knot["week_second"] + week * WEEK_SECONDS)
                for week in range(math.floor(begin / WEEK_SECONDS) - 1,
                                  math.floor(end / WEEK_SECONDS) + 2)
                for knot in central]
    times = [knot["week_second"] for knot in expanded]
    return expanded[bisect_right(times, begin) - 1:bisect_right(times, end) + 1]


def _weekly_date_rows(bins, observed_dates):
    rows = {}
    for day in observed_dates:
        midnight = datetime.combine(day, datetime.min.time())
        values = [bins.get(midnight + timedelta(seconds=index * BIN_SECONDS), (0, 0))
                  for index in range(96)]
        rows[day.isoformat()] = {
            "counts": [cars if exposure else None for exposure, cars in values],
            "exposure_seconds": [exposure for exposure, _ in values],
            "eligible": [exposure >= MIN_COVERAGE * BIN_SECONDS and day not in HOLIDAYS
                         for exposure, _ in values],
        }
    return rows


def _weekly_clock_evidence(date_rows, training):
    """Descreve o relógio registrado, sem deslocar picos para horas presumidas."""
    result = {}
    for sensor, observations in date_rows.items():
        weekdays = []
        for weekday in range(7):
            days = [day for day in training if day.weekday() == weekday
                    and all(observations[day.isoformat()]["eligible"])]
            hours = []
            for day in days:
                row = observations[day.isoformat()]
                hours.append([sum(row["counts"][index] * BIN_SECONDS /
                                  row["exposure_seconds"][index]
                                  for index in range(hour * 4, (hour + 1) * 4))
                              for hour in range(24)])
            minimums, peaks = defaultdict(int), defaultdict(int)
            for counts in hours:
                minimums[min(range(24), key=counts.__getitem__)] += 1
                peaks[max(range(24), key=counts.__getitem__)] += 1
            median_hours = [statistics.median(counts[hour] for counts in hours)
                            for hour in range(24)] if hours else []
            minimum = min(range(24), key=median_hours.__getitem__) if hours else None
            peak = max(range(24), key=median_hours.__getitem__) if hours else None
            weekdays.append({
                "day": WEEKDAYS[weekday], "complete_training_dates": len(days),
                "median_hourly_minimum_hour": minimum, "median_hourly_peak_hour": peak,
                "daily_minimum_hour_frequency": dict(sorted(minimums.items())),
                "daily_peak_hour_frequency": dict(sorted(peaks.items())),
                "morning_minimum_requires_civil_context_review": minimum in (6, 7, 8),
            })
        result[sensor] = weekdays
    return {
        "basis": "Training only; full days with all 96 quarters eligible at that sensor; hourly counts normalized by recorded exposure; earliest hour breaks ties.",
        "sensors": result,
        "interpretation": "Recurrence describes the civil clock under the explicitly selected source-time convention. A 06:00–09:00 minimum flags unresolved plausibility, not permission to alter observed peaks or infer the equipment timezone.",
    }


def _window_training_support(date_rows, knots, week_starts, training_dates, begin, duration):
    """Resume amostras reais da janela; não preenche interrupções com zero."""
    totals = []
    eligible_quarters = 0
    offset = begin % WEEK_SECONDS
    for week_start in week_starts:
        civil_start = datetime.combine(week_start, datetime.min.time()) + timedelta(seconds=offset)
        counts = []
        for relative in range(0, duration, BIN_SECONDS):
            stamp = civil_start + timedelta(seconds=relative)
            row = date_rows.get(stamp.date().isoformat())
            index = stamp.hour * 4 + stamp.minute // 15
            if (stamp.date().isoformat() not in training_dates or not row
                    or not row["eligible"][index]):
                continue
            counts.append(row["counts"][index] * BIN_SECONDS / row["exposure_seconds"][index])
        eligible_quarters += len(counts)
        if len(counts) == duration // BIN_SECONDS:
            totals.append(sum(counts))
    supported = [knot for knot in knots if begin <= knot["week_second"] < begin + duration]
    return {
        "joint_training_dates_per_quarter_min": min(knot["n_dates"] for knot in supported),
        "joint_training_dates_per_quarter_max": max(knot["n_dates"] for knot in supported),
        "eligible_observed_quarters": eligible_quarters,
        "complete_observed_windows": len(totals),
        "normalized_car_count_statistics": _statistics(totals) if totals else None,
        "meaning": "Local car observations on real consecutive training dates, normalized only for accepted exposure. Partial windows contribute exposure support but not complete-window dispersion. These counts neither identify regional demand nor validate the civil meaning of peak hours.",
    }


def _weekly_validation(date_rows, knots, week_starts, begin, duration):
    """Cada amostra percorre uma janela de datas realmente consecutivas."""
    observations, daily_counts, excluded = [], [], 0
    offset = begin % WEEK_SECONDS
    for week_start in week_starts:
        civil_start = datetime.combine(week_start, datetime.min.time()) + timedelta(seconds=offset)
        daily = {"date": civil_start.date().isoformat(),
                 "start": civil_start.isoformat(),
                 "end": (civil_start + timedelta(seconds=duration)).isoformat(),
                 "counts": [], "exposure_seconds": [], "eligible": []}
        for relative in range(0, duration, BIN_SECONDS):
            stamp = civil_start + timedelta(seconds=relative)
            row = date_rows.get(stamp.date().isoformat())
            index = stamp.hour * 4 + stamp.minute // 15
            exposure = row["exposure_seconds"][index] if row else 0
            count = row["counts"][index] if row else None
            eligible = bool(row and row["eligible"][index])
            daily["counts"].append(count)
            daily["exposure_seconds"].append(exposure)
            daily["eligible"].append(eligible)
            if not eligible:
                excluded += 1
                continue
            observations.append({
                "date": stamp.date().isoformat(), "start": stamp.strftime("%H:%M"),
                "window_index": relative // BIN_SECONDS,
                "exposure_seconds": exposure, "observed_cars": count,
                "observed_cars_normalized_15min": count * BIN_SECONDS / exposure,
                "predicted_cars_15min": integrate_rate(knots, begin + relative,
                                                       begin + relative + BIN_SECONDS),
            })
        daily_counts.append(daily)
    errors = [abs(item["predicted_cars_15min"] - item["observed_cars_normalized_15min"])
              for item in observations]
    total = sum(item["observed_cars_normalized_15min"] for item in observations)
    return {"dates": [row["date"] for row in daily_counts], "n_windows": len(observations),
            "excluded_windows": excluded, "mae_cars_per_15min": statistics.mean(errors) if errors else None,
            "wape": sum(errors) / total if total else None,
            "observations": observations, "daily_counts": daily_counts,
            "meaning": "Local temporal prediction only; spatial mapping and simulated passage validation are separate.",
            "daily_counts_semantics": "Recorded car counts and exposure on consecutive real dates; None is missing, not zero. Holidays are ineligible. Only explicitly normalized comparison counts expand accepted exposure."}


def calibrate_weekly(csv_path=DEFAULT_CSV, variation=1, seed=None, source_time_convention="utc"):
    """Estima curvas locais semanais e uma realização conjunta dos sensores.

    A divisão cronológica é fixada antes de inspecionar os valores. Cada
    weekday usa seus próprios quinze minutos; os dias integrais reamostrados
    preservam correlação intradia e entre sensores. A realização independe da
    janela solicitada. A falta de cobertura nunca é convertida em fluxo zero.
    UTC é a convenção metodológica ativa; ``legacy_civil`` existe somente
    para a referência controlada anterior, sem deslocar os dados originais.
    """
    if source_time_convention not in ("utc", "legacy_civil"):
        raise ValueError("source_time_convention deve ser 'utc' ou 'legacy_civil'.")
    if isinstance(variation, bool) or not isinstance(variation, int) or not 1 <= variation <= 25:
        raise ValueError("A variação semanal deve estar entre 1 e 25.")
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int) or seed < 0):
        raise ValueError("A seed semanal deve ser um inteiro não negativo.")
    effective_seed = seed if seed is not None else int.from_bytes(
        hashlib.sha256(f"{WEEKLY_VERSION}|{variation}".encode()).digest()[:4], "big")
    records, quality, digest = _read_measurements(csv_path, source_time_convention=source_time_convention)
    bins = _aggregate(records, source_time_convention=source_time_convention)
    observed_dates = sorted({stamp.date() for values in bins.values() for stamp in values})
    training = [day for day in observed_dates if day < TRAIN_BEFORE and day not in HOLIDAYS]
    if len(training) < MIN_TRAINING_DATES:
        raise ValueError("MetaSettran semanal requer ao menos três datas de treino.")
    date_rows = {sensor: _weekly_date_rows(bins[sensor], observed_dates) for sensor in SENSORS}
    eligible_dates = {}
    for weekday in range(7):
        for index in range(96):
            eligible_dates[weekday, index] = [day for day in training if day.weekday() == weekday
                and all(date_rows[sensor][day.isoformat()]["eligible"][index] for sensor in SENSORS)]
    profiles = {sensor: {"knots": [], "realization_knots": []} for sensor in SENSORS}
    for weekday in range(7):
        for index in range(96):
            common = eligible_dates[weekday, index]
            status = "measured_local_estimate" if len(common) >= MIN_TRAINING_DATES else "limited_local_estimate"
            donors = common
            if not donors:
                donors = [day for day in training if all(
                    date_rows[sensor][day.isoformat()]["eligible"][index] for sensor in SENSORS)]
                status = "hypothesis_other_weekdays_same_clock"
            if not donors:
                raise ValueError(f"Sem exposição de treino para o quarto de hora {index}; não é fluxo zero.")
            for sensor in SENSORS:
                values = [date_rows[sensor][day.isoformat()]["counts"][index] /
                          date_rows[sensor][day.isoformat()]["exposure_seconds"][index] for day in donors]
                stats = _statistics(values)
                profiles[sensor]["knots"].append({
                    "week_second": weekday * 86400 + index * BIN_SECONDS + BIN_SECONDS // 2,
                    "rate_per_second": stats["median"], "q25_rate_per_second": stats["q25"],
                    "q75_rate_per_second": stats["q75"], "mad_rate_per_second": stats["mad"],
                    "n_dates": len(common), "donor_dates": [day.isoformat() for day in donors],
                    "status": status,
                })
    sampled_days = []
    for weekday in range(7):
        candidates = [day for day in training if day.weekday() == weekday]
        complete = [day for day in candidates if all(day in eligible_dates[weekday, index]
                                                    for index in range(96))]
        pool = complete or candidates
        token = hashlib.sha256(f"{WEEKLY_VERSION}|{effective_seed}|{weekday}".encode()).digest()
        chosen = pool[int.from_bytes(token[:8], "big") % len(pool)] if pool else None
        observed_bins = 0
        for index in range(96):
            eligible = chosen is not None and chosen in eligible_dates[weekday, index]
            observed_bins += eligible
            for sensor in SENSORS:
                baseline = profiles[sensor]["knots"][weekday * 96 + index]
                row = date_rows[sensor][chosen.isoformat()] if eligible else None
                profiles[sensor]["realization_knots"].append({
                    "week_second": baseline["week_second"],
                    "rate_per_second": row["counts"][index] / row["exposure_seconds"][index]
                        if eligible else baseline["rate_per_second"],
                    "source_date": chosen.isoformat() if eligible else None,
                    "status": "joint_observed_day" if eligible else "baseline_fallback_missing_exposure",
                })
        sampled_days.append({"weekday": WEEKDAYS[weekday], "date": chosen.isoformat() if chosen else None,
                             "complete_candidate_dates": [day.isoformat() for day in complete],
                             "joint_observed_bins": observed_bins, "baseline_fallback_bins": 96 - observed_bins})
    for sensor in SENSORS:
        profile = profiles[sensor]
        profile["knots"] = _cyclic_knots(profile["knots"])
        profile["realization_knots"] = _cyclic_knots(profile["realization_knots"])
        profile["date_observations"] = date_rows[sensor]
        profile["baseline_reference_cars_15_18"] = integrate_rate(
            profile["knots"], START_WEEK_SECOND, END_WEEK_SECOND)
    week_starts = sorted({day - timedelta(days=day.weekday()) for day in observed_dates})
    return {
        "version": WEEKLY_VERSION,
        "source": {"name": Path(csv_path).name, "sha256": digest, "count_column": "car"},
        "time": {"timezone": CIVIL_TIMEZONE.key,
                 "source_time_convention": source_time_convention,
                 "source_timezone_assumed": "UTC" if source_time_convention == "utc" else CIVIL_TIMEZONE.key,
                 "interpretation": "utc" if source_time_convention == "utc" else "brasilia",
                 "offset_applied_hours": (datetime(2026, 1, 1, tzinfo=timezone.utc).astimezone(CIVIL_TIMEZONE).utcoffset().total_seconds() / 3600
                                          if source_time_convention == "utc" else 0),
                 "conversion": "Attach UTC to original naive timestamps, astimezone(America/Sao_Paulo), then aggregate local civil dates exactly once."
                               if source_time_convention == "utc" else "No conversion; controlled v4.3.1 original-clock reference only.",
                 "status": "project_methodological_hypothesis_not_device_confirmation" if source_time_convention == "utc" else "legacy_control_reference",
                 "decision": "UTC interpretation required by the project; do not select the clock convention by optimizing traffic indicators.",
                 "civil_peak_alignment": "not_independently_verified; inspect training_clock_evidence before naming a civil peak",
                 "provenance": "Project decision adopts UTC as source time. The CSV and exporter origin still provide no explicit timezone evidence; the device convention remains unconfirmed.",
                 "calendar": {"observed_civil_dates": len(observed_dates),
                              "first_observed_civil_date": observed_dates[0].isoformat(),
                              "last_observed_civil_date": observed_dates[-1].isoformat(),
                              "training_and_holidays": "Evaluated after conversion on local civil dates; cutoff remains local Monday 2026-08-24."}},
        "method": {
            "class": "car_only_as_passenger", "bin_seconds": BIN_SECONDS,
            "maximum_accepted_interval_seconds": MAX_INTERVAL_SECONDS, "minimum_coverage": MIN_COVERAGE,
            "training_before": TRAIN_BEFORE.isoformat(), "holidays_excluded": sorted(day.isoformat() for day in HOLIDAYS),
            "estimator": "Median per weekday and quarter-hour over jointly eligible training dates at both sensors.",
            "interpolation": "Cyclic linear interpolation between adjacent quarter-hour centers; no extra smoothing window.",
            "count_allocation": "Uniform within accepted recorded intervals; normalization by recorded exposure is an estimate.",
            "sampling": "One complete observed training day per weekday, shared by both sensors; empirical day bootstrap preserves intraday and intersensor dependence. Missing full days use explicitly flagged baseline fallback.",
            "split": "Fixed local-civil Monday 2026-08-24 cutoff after source-time conversion and before fit; primary is that week, post is all later weeks. Weekdays remain distinct.",
        },
        "training_dates": [day.isoformat() for day in training],
        "validation_dates": [day.isoformat() for day in observed_dates if day >= TRAIN_BEFORE and day not in HOLIDAYS],
        "observed_week_starts": [day.isoformat() for day in week_starts],
        "realization": {"variation": variation, "seed": effective_seed, "sampled_days": sampled_days,
                        "meaning": "25 reproducible realizations, not 25 independent observed weeks; choices do not depend on selected sections or signal profile."},
        "sensors": profiles, "quality": quality,
        "training_clock_evidence": _weekly_clock_evidence(date_rows, training),
        "limitations": [
            "UTC is a project methodological hypothesis, not a documented fact about the source equipment. The original CSV is unchanged; civil weekdays, holidays and train/verification membership follow the explicit conversion.",
            "Weekly local sensor estimates do not identify a regional OD matrix or establish sensor geography.",
            "Car-only; classifier reliability and omitted motorized classes are not independently validated.",
            "Resampling complete eligible days can favor well-monitored dates; rare events and seasonality are not established.",
            "Adjacent sampled weekdays need not be consecutive observed dates; linear interpolation removes artificial rate jumps, not uncertainty in cross-day correlation.",
            "Missing weekday support borrows the same civil quarter-hour from training weekdays only and is labeled a hypothesis; missing observations remain missing in validation.",
            "Interpolated passage-rate curves are observation references; using them as boundary departures is an explicitly separate modeling assumption.",
        ],
    }


def weekly_window(calibration, begin_week_second, duration_seconds):
    """Recorta referências sem repetir sorteios nem juntar datas independentes.

    O tempo retornado é absoluto e pode ultrapassar 604800 na virada semanal.
    O chamador escolhe a curva central ou realizada, mantendo ambas rastreáveis.
    """
    if calibration.get("version") != WEEKLY_VERSION:
        raise ValueError("weekly_window requer uma calibração semanal.")
    if (isinstance(begin_week_second, bool) or not isinstance(begin_week_second, int)
            or begin_week_second < 0 or begin_week_second % BIN_SECONDS
            or isinstance(duration_seconds, bool) or not isinstance(duration_seconds, int)
            or duration_seconds <= 0 or duration_seconds % BIN_SECONDS or duration_seconds > WEEK_SECONDS):
        raise ValueError("Janela semanal requer início alinhado e duração positiva em quartos de hora, até sete dias.")
    begin, end = begin_week_second, begin_week_second + duration_seconds
    result = {key: value for key, value in calibration.items() if key not in ("sensors", "observed_week_starts")}
    local_start, local_end = begin % 86400, end % 86400
    result["selection"] = {
        "day": WEEKDAYS[(begin // 86400) % 7], "end_day": WEEKDAYS[(end // 86400) % 7],
        "start": f"{local_start // 3600:02}:{local_start % 3600 // 60:02}",
        "end": f"{local_end // 3600:02}:{local_end % 3600 // 60:02}",
        "start_week_second": begin, "end_week_second": end, "departure_seconds": duration_seconds,
    }
    week_starts = [date.fromisoformat(value) for value in calibration["observed_week_starts"]]
    training_dates = set(calibration["training_dates"])
    result["sensors"] = {}
    for sensor, profile in calibration["sensors"].items():
        knots = _window_knots(profile["knots"], begin, end)
        realized = _window_knots(profile["realization_knots"], begin, end)
        result["sensors"][sensor] = {
            "knots": knots, "realization_knots": realized,
            "baseline_reference_cars_15_18": profile["baseline_reference_cars_15_18"],
            "expected_cars": integrate_rate(knots, begin, end),
            "realized_expected_cars": integrate_rate(realized, begin, end),
            "target_counts": [integrate_rate(knots, offset, offset + BIN_SECONDS)
                              for offset in range(begin, end, BIN_SECONDS)],
            "realized_target_counts": [integrate_rate(realized, offset, offset + BIN_SECONDS)
                                       for offset in range(begin, end, BIN_SECONDS)],
            "training_support": _window_training_support(profile["date_observations"], knots,
                week_starts, training_dates, begin, duration_seconds),
            "validation": {
                "primary": _weekly_validation(profile["date_observations"], knots,
                    [week for week in week_starts if week == TRAIN_BEFORE], begin, duration_seconds),
                "post": _weekly_validation(profile["date_observations"], knots,
                    [week for week in week_starts if week > TRAIN_BEFORE], begin, duration_seconds),
            },
        }
    return result
