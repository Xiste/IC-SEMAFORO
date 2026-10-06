"""Exportação comparativa das avaliações PPO e programa de referência."""

import json
import os
from pathlib import Path

import pandas as pd


def write_evaluation_report(output, rows, signal_rows, metadata):
    output = Path(output)
    runs = pd.DataFrame(rows)
    signals = pd.DataFrame(signal_rows)
    runs.to_csv(output / "runs.csv", index=False)
    signals.to_csv(output / "signals.csv", index=False)

    numeric = [name for name in runs.select_dtypes(include="number").columns if name != "seed"]
    grouped = runs.groupby("controller")[numeric].agg(["mean", "std", "count"])
    grouped.columns = [f"{metric}_{stat}" for metric, stat in grouped.columns]
    grouped.reset_index().to_csv(output / "aggregate.csv", index=False)

    pairs = runs.pivot(index="seed", columns="controller", values="planned_vehicles")
    same_demand = bool((pairs.nunique(axis=1) == 1).all())
    if not same_demand:
        raise ValueError("Avaliação inválida: demanda planejada difere entre controladores")

    os.environ.setdefault("MPLCONFIGDIR", str(output / "matplotlib_cache"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    metrics = [name for name in ("arrived", "unfinished", "wait_vehicle_seconds",
                                 "queue_vehicle_seconds", "mean_travel_time_seconds")
               if name in runs and runs[name].notna().any()]
    figure, axes = plt.subplots(1, len(metrics), figsize=(4 * len(metrics), 4))
    if len(metrics) == 1:
        axes = [axes]
    for axis, metric in zip(axes, metrics):
        means = runs.groupby("controller")[metric].mean()
        axis.bar(means.index, means.values)
        axis.set_title(metric.replace("_", " "))
        axis.tick_params(axis="x", rotation=20)
    figure.tight_layout()
    figure.savefig(output / "comparison.png", dpi=140)
    plt.close(figure)

    summary = {"runs": rows, "aggregate": json.loads(grouped.reset_index().to_json(orient="records")),
               "same_planned_demand_per_seed": same_demand, **metadata}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    lines = ["# Comparação PPO × programa da rede", "",
             f"Sementes de avaliação: {', '.join(map(str, sorted(runs['seed'].unique())))}.",
             "A demanda planejada foi igual entre controladores em cada semente.",
             "A referência é o programa da rede, ainda não o plano da planilha.",
             "Viagens incompletas e sem chegada não entram na média de tempo de viagem.",
             "Não se declara superioridade automática; examine repetições, dispersão e pendências.",
             "", "Arquivos: `runs.csv`, `signals.csv`, `aggregate.csv`, `comparison.png` e `summary.json`."]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary
