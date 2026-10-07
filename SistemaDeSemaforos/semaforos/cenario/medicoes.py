"""Resumo descritivo das contagens locais, sem convertê-las em demanda SUMO."""
from semaforos.caminhos import PROJECT_ROOT

import csv
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median


DEFAULT_MEASUREMENTS = PROJECT_ROOT / "dados" / "medicoes" / "Medicoes_5_6.csv"


def measurement_report(path=DEFAULT_MEASUREMENTS):
    path = Path(path)
    sensors = defaultdict(lambda: {"labels": Counter(), "rows": 0, "minute_rates": [],
                                   "vehicle_total": 0, "motorcycle": 0, "bike": 0,
                                   "person": 0, "window_seconds": Counter(),
                                   "first": None, "last": None})
    with path.open(newline="", encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            sensor = sensors[row["vlink_id"]]
            start = datetime.fromisoformat(row["hora_inicio"])
            end = datetime.fromisoformat(row["hora_fim"])
            seconds = int((end - start).total_seconds())
            if seconds <= 0:
                raise ValueError(f"Janela inválida para vlink_id={row['vlink_id']}: {start} a {end}")
            sensor["rows"] += 1
            sensor["labels"][row["descricao_linha"]] += 1
            sensor["window_seconds"][seconds] += 1
            sensor["first"] = min(sensor["first"], start) if sensor["first"] else start
            sensor["last"] = max(sensor["last"], end) if sensor["last"] else end
            for field in ("vehicle_total", "motorcycle", "bike", "person"):
                sensor[field] += int(row[field])
            if seconds == 60:
                sensor["minute_rates"].append(int(row["vehicle_total"]) * 60)
    result = []
    for sensor_id, values in sorted(sensors.items(), key=lambda item: item[0]):
        rates = values["minute_rates"]
        result.append({"vlink_id": sensor_id, "labels": dict(values["labels"]),
                       "rows": values["rows"], "first_local_timestamp": values["first"].isoformat(),
                       "last_local_timestamp": values["last"].isoformat(),
                       "window_seconds": dict(values["window_seconds"]),
                       "observed_vehicle_total": values["vehicle_total"],
                       "observed_motorcycle": values["motorcycle"],
                       "observed_bike": values["bike"], "observed_person": values["person"],
                       "complete_minute_rows": len(rates),
                       "mean_vehicles_per_hour_in_observed_minutes": round(mean(rates), 2) if rates else None,
                       "median_vehicles_per_hour_in_observed_minutes": median(rates) if rates else None})
    return {"source": str(path.resolve()), "sensors": result,
            "caution": "IDs vlink não estão associados a arestas SUMO; fusos, cobertura e direção dos detectores não foram comprovados. Taxas descrevem apenas janelas observadas de 60 s."}
