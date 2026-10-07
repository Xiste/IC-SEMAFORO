"""Verificação direta da interface e dos catálogos instalados."""

import sys
import io
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest
import pandas as pd
from semaforos.relatorios.catalogos import sumo_options, traci_getters, training_workload, metric_rows, parameter_rows
from semaforos.cenario.configuracao import read_config
from semaforos.relatorios.legendas import metric_legend, portuguese_metric_table

version, options = sumo_options()
assert len(options) == len({row["opção"] for row in options})
assert {"net-file", "step-length", "tripinfo-output"} <= {row["opção"] for row in options}
queries = traci_getters()
assert any(row["consulta"] == "getElectricityConsumption" for row in queries)
work = training_workload(read_config(ROOT / "config/cenario.json"))
assert work["atualizações de gradiente previstas"] == 320
config = read_config(ROOT / "config/cenario.json")
assert all(row["nome em português"] != row["métrica"] for row in metric_rows(config))
assert all(row["nome em português"] != row["parâmetro"] for row in parameter_rows(config))
assert all(row["legenda em português"] for row in metric_rows(config) + parameter_rows(config))
runs = pd.DataFrame([{"controller": "PPO", "seed": 101, "arrived": 10, "wait_vehicle_seconds": 32.0},
                     {"controller": "network_reference", "seed": 101, "arrived": 9, "wait_vehicle_seconds": 40.0}])
results = ROOT / "resultados"
results.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix="ui_verificacao_", dir=results) as temporary:
    folder = Path(temporary)
    assert folder.resolve().is_relative_to(results.resolve())
    (folder / "summary.json").write_text(json.dumps({"scope": "dados fictícios para verificar a interface"}), encoding="utf-8")
    runs.to_csv(folder / "runs.csv", index=False)
    app = AppTest.from_file(str(ROOT / "interface.py"), default_timeout=60).run()
    assert not app.exception, str(app.exception)
    assert len(app.tabs) == 3
    assert all(item.help for item in app.number_input)
    saved = next(item for item in app.selectbox if item.label == "Resultado salvo")
    saved.set_value(folder.name).run()
    assert not app.exception, str(app.exception)
    downloads = [item.label for item in app.get("download_button")]
    assert "Exportar métricas em português (.csv)" in downloads
    assert "Exportar legenda das colunas (.csv)" in downloads
assert all(metric_legend(name)[0] != name for name in runs.columns)
translated = portuguese_metric_table(runs)
csv_bytes = translated.to_csv(index=False).encode("utf-8-sig")
assert csv_bytes.startswith(b"\xef\xbb\xbf")
restored = pd.read_csv(io.BytesIO(csv_bytes))
assert len(restored) == len(runs)
assert "Veículos que chegaram [veículos] (arrived)" in restored.columns
assert restored["Veículos que chegaram [veículos] (arrived)"].tolist() == runs["arrived"].tolist()
print(version)
print(f"{len(options)} opções / {len({row['categoria'] for row in options})} categorias / {len(queries)} consultas TraCI; AppTest sem exceções")
