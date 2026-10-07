"""Exportação comparativa das avaliações PPO e programa de referência."""

import json
import os
from pathlib import Path

import pandas as pd
from semaforos.relatorios.legendas import metric_column_label
from semaforos.arquivos import write_json


def write_evaluation_report(output, rows, signal_rows, metadata):
    output = Path(output)
    runs = pd.DataFrame(rows)
    signals = pd.DataFrame(signal_rows)
    if not signals.empty and "tls_id" in signals:
        names = {target["tls_id"]: target["name"] for target in metadata.get("config", {}).get("targets", [])}
        signals["intersection"] = signals["tls_id"].map(names)
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
        deviations = runs.groupby("controller")[metric].std().reindex(means.index).fillna(0)
        axis.bar(means.index, means.values, yerr=deviations.values, capsize=4)
        axis.set_title(metric_column_label(metric), wrap=True)
        axis.tick_params(axis="x", rotation=20)
    figure.tight_layout()
    figure.savefig(output / "comparison.png", dpi=140)
    plt.close(figure)

    summary = {"runs": rows, "aggregate": json.loads(grouped.reset_index().to_json(orient="records")),
               "same_planned_demand_per_seed": same_demand, **metadata}
    write_json(output / "summary.json", summary)
    lines = ["# Comparação PPO × programa da rede", "",
             f"Sementes de avaliação: {', '.join(map(str, sorted(runs['seed'].unique())))}.",
             "A demanda planejada foi igual entre controladores em cada semente.",
             "A referência é o programa da rede, ainda não o plano da planilha.",
             "Viagens incompletas e sem chegada não entram na média de tempo de viagem.",
             "Barras de erro mostram desvio padrão amostral entre sementes; com uma semente não há estimativa de dispersão.",
             "Não se declara superioridade automática; examine repetições, dispersão e pendências.",
             "", "Arquivos: `runs.csv`, `signals.csv`, `aggregate.csv`, `comparison.png` e `summary.json`."]
    lines[0] = f"# Resultados: {', '.join(sorted(runs['controller'].unique()))}"
    if "queue_actuated" in set(runs["controller"]):
        lines.append("`queue_actuated` reage a filas; não implementa max-pressure.")
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary
