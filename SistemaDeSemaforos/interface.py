"""Interface Streamlit do piloto PPO/SUMO.

Inicie com: streamlit run interface.py
"""

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pandas as pd
import streamlit as st
import sumolib

from semaforos.configuracao import read_config
from semaforos.rede import inventory
from semaforos.mapeamento import mapping_report


ROOT = Path(__file__).resolve().parent
DEFAULT = ROOT / "config" / "cenario.json"
RESULTS = ROOT / "resultados"


@st.cache_data(show_spinner=False)
def road_options(network_path, target_ids):
    network_data = sumolib.net.readNet(network_path)
    edges = network_data.getEdges(withInternal=False)
    ids = sorted(edge.getID() for edge in edges if edge.allows("passenger"))
    exits = sorted(edge.getID() for edge in edges if not edge.getOutgoing() and edge.allows("passenger"))
    incoming = sorted({connection[0].getEdge().getID()
                       for light in network_data.getTrafficLights() if light.getID() in target_ids
                       for connection in light.getConnections()})
    return ids, exits, incoming


def start_job(command, config, model=None):
    RESULTS.mkdir(exist_ok=True)
    folder = RESULTS / f"ui_{uuid.uuid4().hex[:12]}"
    folder.mkdir()
    config_path = folder / "cenario.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    read_config(config_path)
    output = folder / "execucao"
    args = [sys.executable, str(ROOT / "pipeline.py"), command,
            "--config", str(config_path), "--output", str(output)]
    if model:
        args.extend(("--model", str(model)))
    log_path = folder / "processo.log"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(args, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    st.session_state.job = {"process": process, "folder": folder, "output": output,
                            "log": log_path, "command": command}


st.set_page_config(page_title="Semáforos Rondon Norte", layout="wide")
st.title("Controle semafórico — Rondon Norte")
st.caption("Piloto PPO com SUMO/TraCI. O mapeamento validado atual contém apenas FAM_RONDON_PARANA.")

base = read_config(DEFAULT)
with st.expander("Arquivos e mapeamento", expanded=False):
    network = st.text_input("Rede SUMO (.net.xml)", str(base["network"]))
    plans = st.text_input("Planilha (.xlsx)", str(base["plans"]))
    if st.button("Inspecionar arquivos"):
        try:
            probe = dict(base, network=Path(network), plans=Path(plans))
            report = inventory(probe)
            st.write("Cruzamentos na planilha:", len(report["spreadsheet_intersections"]))
            st.write("Elementos da rede:", report["network_element_counts"])
            st.dataframe(pd.DataFrame([
                {"nome": t["name"], "id_sumo": t["tls_id"],
                 "fases_ajustáveis": str(t["phase_indices"])} for t in base["targets"]]),
                hide_index=True)
            st.info("Confirme links, estágios e pedestres antes de incluir os outros oito sinais.")
        except Exception as error:
            st.error(str(error))
    if st.button("Verificar correspondência dos nove cruzamentos"):
        try:
            probe = dict(base, network=Path(network), plans=Path(plans))
            report = mapping_report(probe, base.get("mapping_path"))
            st.write(f"Validados: {report['validated_count']} de {report['total']}")
            st.dataframe(pd.DataFrame([{"cruzamento": item["name"], "id_sumo": item["tls_id"],
                                        "validado": item["validated"],
                                        "pendências": "; ".join(item["issues"])}
                                       for item in report["intersections"]]), hide_index=True)
        except Exception as error:
            st.error(str(error))

left, right = st.columns(2)
with left:
    st.subheader("Demanda sintética")
    demand_mode = st.radio("Modelo", ("Taxa pela rede", "Volume por via", "Pares origem–destino"), horizontal=True)
    rate = st.number_input("Volume total (veículos/h)", min_value=1,
                           value=int(base["demand"].get("vehicles_per_hour", 360)),
                           disabled=demand_mode != "Taxa pela rede")
    flows_text = st.text_area("Fluxos JSON: from_edge, to_edge, vehicles_per_hour",
                              value=json.dumps(base["demand"].get("flows", []), ensure_ascii=False, indent=2),
                              disabled=demand_mode != "Pares origem–destino")
    road_table = None
    destination_text = "{}"
    profile_text = "[]"
    vehicle_types_text = "[]"
    if demand_mode == "Volume por via":
        try:
            edge_ids, exit_ids, incoming_ids = road_options(network, tuple(t["tls_id"] for t in base["targets"]))
            initial = base["demand"].get("edge_volumes") or [
                {"from_edge": edge, "vehicles_per_hour": 0.0, "to_edge": ""}
                for edge in incoming_ids]
            st.caption("Preencha veículos/h para cada via. A rede não traz nomes de rua nessas entradas; use o ID SUMO até o mapeamento nominal ser validado. Destino vazio = saída alcançável sorteada, identificada como sintética.")
            road_table = st.data_editor(pd.DataFrame(initial), num_rows="dynamic", hide_index=True,
                column_config={
                    "from_edge": st.column_config.SelectboxColumn("Via de entrada (ID SUMO)", options=edge_ids, required=True),
                    "vehicles_per_hour": st.column_config.NumberColumn("Veículos/h", min_value=0.0, step=10.0, required=True),
                    "to_edge": st.column_config.SelectboxColumn("Saída opcional (ID SUMO)", options=[""] + exit_ids),
                }, key="road_volumes")
            st.caption(f"{len(incoming_ids)} vias de entrada do sinal mapeado estão pré-listadas. Você pode adicionar outras vias da rede.")
        except Exception as error:
            st.error(f"Não foi possível listar as vias: {error}")
    duration = st.number_input("Duração simulada do episódio (s)", min_value=10,
                               value=int(base["duration_seconds"]), step=10)
    if demand_mode == "Volume por via":
        with st.expander("Perfil, destinos e tipos"):
            destination_text = st.text_area("Destinos por origem (JSON: ID para lista de {to_edge, share})", value="{}")
            profile_text = st.text_area("Perfil temporal (JSON: begin, end, multiplier)", value="[]")
            vehicle_types_text = st.text_area("Tipos de veiculo (JSON: id, vClass, share)", value="[]")
    if road_table is not None:
        rates = pd.to_numeric(road_table["vehicles_per_hour"], errors="coerce").fillna(0)
        planned = sum(int(value * duration / 3600 + 0.5) for value in rates)
        st.metric("Veículos planejados pelas vias", planned)
    seed = st.number_input("Semente", min_value=0, value=int(base["seeds"][0]))
    evaluation_seeds = st.text_input("Sementes de avaliação (separadas por vírgula)",
                                     value=", ".join(map(str, base.get("evaluation", {}).get("seeds", [101, 102, 103]))))
    st.caption("Os valores são exemplos sintéticos; não representam contagem medida em Uberlândia.")
with right:
    st.subheader("Objetivos e PPO")
    w_wait = st.number_input("Prioridade: espera", min_value=0.0, value=1.0, step=0.1)
    w_queue = st.number_input("Prioridade: filas", min_value=0.0, value=1.0, step=0.1)
    w_travel = st.number_input("Prioridade: tempo de viagem (aproximação)", min_value=0.0, value=1.0, step=0.1)
    decision = st.number_input("Intervalo de decisão (s)", min_value=1, value=int(base["ppo"]["decision_seconds"]))
    n_epochs = st.number_input("Épocas por lote", min_value=1, value=int(base["ppo"]["n_epochs"]))
    n_steps = st.number_input("Passos por coleta", min_value=2, value=int(base["ppo"]["n_steps"]))
    batch_size = st.number_input("Tamanho do minibatch", min_value=1, value=int(base["ppo"]["batch_size"]))
    total_steps = st.number_input("Total de passos de treinamento", min_value=2,
                                  value=int(base["ppo"]["total_timesteps"]), step=128)
    gui = st.checkbox("Mostrar SUMO-GUI (mais lento)", value=False)
    with st.expander("Métricas opcionais"):
        collect_lane = st.checkbox("Velocidade e ocupação das faixas", value=True)
        collect_emissions = st.checkbox("CO₂ e combustível por veículo (coleta mais lenta)", value=False)
        collect_events = st.checkbox("Teletransportes e colisões", value=True)
        collect_resources = st.checkbox("CPU e memória", value=True)

model_path = st.text_input("Modelo salvo para avaliação (.zip)", value="")

def configured():
    config = dict(base)
    config["network"] = str(Path(network).resolve())
    config["plans"] = str(Path(plans).resolve())
    if demand_mode == "Taxa pela rede":
        config["demand"] = {"mode": "random", "vehicles_per_hour": int(rate), "flows": []}
    elif demand_mode == "Volume por via":
        if road_table is None:
            raise ValueError("Selecione uma rede válida para preencher as vias")
        destinations = json.loads(destination_text)
        profile = json.loads(profile_text)
        vehicle_types = json.loads(vehicle_types_text)
        if not isinstance(destinations, dict) or not isinstance(profile, list) or not isinstance(vehicle_types, list):
            raise ValueError("Destinos devem ser objeto JSON; perfil e tipos devem ser listas JSON")
        entries = []
        for row in road_table.to_dict("records"):
            if not row.get("from_edge"):
                continue
            entry = {"from_edge": row["from_edge"],
                            "vehicles_per_hour": float(row.get("vehicles_per_hour") or 0),
                            "to_edge": row.get("to_edge") or ""}
            if row["from_edge"] in destinations:
                entry["destinations"] = destinations[row["from_edge"]]
            entries.append(entry)
        unknown = set(destinations) - {entry["from_edge"] for entry in entries}
        if unknown:
            raise ValueError(f"Destinos informados para origem fora da tabela: {', '.join(sorted(unknown))}")
        config["demand"] = {"mode": "edge_volumes", "edge_volumes": entries}
        if profile:
            config["demand"]["time_profile"] = profile
        if vehicle_types:
            config["demand"]["vehicle_types"] = vehicle_types
    else:
        flows = json.loads(flows_text)
        if not isinstance(flows, list):
            raise ValueError("Fluxos devem ser uma lista JSON")
        config["demand"] = {"mode": "flows", "flows": flows}
    if w_wait + w_queue + w_travel <= 0:
        raise ValueError("Escolha ao menos uma prioridade positiva")
    config["objectives"] = {"waiting": float(w_wait), "queues": float(w_queue), "travel": float(w_travel)}
    config["duration_seconds"] = int(duration)
    config["seeds"] = [int(seed)]
    parsed_seeds = [int(item.strip()) for item in evaluation_seeds.split(",") if item.strip()]
    if not parsed_seeds or int(seed) in parsed_seeds:
        raise ValueError("Informe sementes de avaliação diferentes da semente do treino")
    config["evaluation"] = {"seeds": parsed_seeds}
    config["metrics"] = {"collect_lane_details": collect_lane,
                         "collect_emissions": collect_emissions,
                         "collect_events": collect_events,
                         "collect_resources": collect_resources,
                         "collect_actions": True}
    config["ppo"] = {"decision_seconds": int(decision), "n_epochs": int(n_epochs),
                     "n_steps": int(n_steps), "batch_size": int(batch_size),
                     "total_timesteps": int(total_steps), "gui": bool(gui)}
    return config


active = "job" in st.session_state and st.session_state.job["process"].poll() is None
train_col, eval_col = st.columns(2)
with train_col:
    if st.button("Iniciar treinamento PPO", disabled=active, type="primary"):
        try:
            start_job("ppo-train", configured())
            st.rerun()
        except Exception as error:
            st.error(str(error))
with eval_col:
    if st.button("Avaliar PPO e referência", disabled=active):
        try:
            model = Path(model_path).resolve()
            if not model.is_file():
                raise ValueError("Informe um arquivo ppo_model.zip existente")
            start_job("ppo-eval", configured(), model)
            st.rerun()
        except Exception as error:
            st.error(str(error))


@st.fragment(run_every="2s")
def progress_panel():
    job = st.session_state.get("job")
    if not job:
        return
    process = job["process"]
    code = process.poll()
    st.subheader("Execução")
    st.write("Pasta:", str(job["folder"]))
    st.write("Estado:", "em andamento" if code is None else ("concluída" if code == 0 else f"falhou ({code})"))
    if code is None and job["command"] == "ppo-train" and st.button("Interromper treinamento"):
        job["output"].mkdir(exist_ok=True)
        (job["output"] / "cancel.flag").touch()
        st.info("Cancelamento solicitado; o modelo parcial será salvo ao encerrar o passo atual.")
    progress = job["output"] / "progress.json"
    if progress.is_file():
        st.json(json.loads(progress.read_text(encoding="utf-8")))
    summary = job["output"] / "summary.json"
    if summary.is_file():
        st.json(json.loads(summary.read_text(encoding="utf-8")))
    csv = job["output"] / "runs.csv"
    if csv.is_file():
        st.dataframe(pd.read_csv(csv), hide_index=True)
        st.download_button("Exportar CSV", csv.read_bytes(), file_name="comparacao.csv", mime="text/csv")
    aggregate = job["output"] / "aggregate.csv"
    if aggregate.is_file():
        st.dataframe(pd.read_csv(aggregate), hide_index=True)
    plot = job["output"] / "comparison.png"
    if plot.is_file():
        st.image(str(plot), caption="Médias por controlador; veja dispersão em aggregate.csv")
    if job["log"].is_file():
        st.code(job["log"].read_text(encoding="utf-8", errors="replace")[-8000:])


progress_panel()
