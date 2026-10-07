"""Interface Streamlit do piloto PPO/SUMO.

Inicie com: streamlit run interface.py
"""
from semaforos.caminhos import PROJECT_ROOT

import json
import math
import re
import subprocess
import sys
import uuid
from pathlib import Path

import pandas as pd
import streamlit as st
import sumolib
import matplotlib.pyplot as plt

from semaforos.cenario.configuracao import read_config
from semaforos.cenario.rede import inventory
from semaforos.cenario.mapeamento import mapping_report
from semaforos.cenario.experimental import prepare_experimental, validate_experimental, preview_experimental
from semaforos.relatorios.catalogos import sumo_options, traci_getters, parameter_rows, metric_rows, training_workload
from semaforos.relatorios.legendas import parameter_legend, metric_legend, metric_column_label, metric_legend_rows, portuguese_metric_table, SUMO_CATEGORIES
from semaforos.algoritmos.registro import available_algorithms, get_algorithm


ROOT = PROJECT_ROOT
DEFAULT = ROOT / "config" / "cenario.json"
CORRECTED_NETWORK = ROOT / "dados" / "rede" / "uberlandia.rondon_norte_corrigida.net.xml"
RESULTS = ROOT / "resultados"


@st.cache_data(show_spinner=False)
def installed_catalogs():
    version, options = sumo_options()
    return version, options, traci_getters()


def downloadable_table(rows, name, label):
    table = pd.DataFrame(rows)
    st.dataframe(table, hide_index=True, width="stretch")
    st.download_button(label, table.to_csv(index=False).encode("utf-8-sig"),
                       file_name=name, mime="text/csv", key=name)


def config_help(name):
    return parameter_legend(name)[1]


def render_result_metrics(path, key):
    try:
        table = pd.read_csv(path)
    except (pd.errors.EmptyDataError, FileNotFoundError):
        st.caption("A tabela está sendo gravada; aguarde a próxima atualização.")
        return
    st.dataframe(table, hide_index=True, width="stretch", column_config={
        name: st.column_config.Column(metric_column_label(name), help=metric_legend(name)[1])
        for name in table.columns})
    legend = pd.DataFrame(metric_legend_rows(table.columns))
    with st.expander(f"Legenda em português — {path.name}"):
        st.dataframe(legend, hide_index=True, width="stretch")
        st.download_button("Exportar legenda das colunas (.csv)", legend.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"{path.stem}_legenda_pt.csv", mime="text/csv", key=f"{key}_legend")
    st.download_button("Exportar métricas em português (.csv)",
                       portuguese_metric_table(table).to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"{path.stem}_pt.csv", mime="text/csv", key=f"{key}_pt")


@st.cache_data(show_spinner=False)
def road_options(network_path, target_ids):
    network_data = sumolib.net.readNet(network_path)
    edges = network_data.getEdges(withInternal=False)
    ids = sorted(edge.getID() for edge in edges if edge.allows("passenger"))
    exits = sorted(edge.getID() for edge in edges if not edge.getOutgoing() and edge.allows("passenger"))
    incoming = sorted({connection[0].getEdge().getID()
                       for light in network_data.getTrafficLights() if light.getID() in target_ids
                       for connection in light.getConnections()
                       if connection[0].getEdge().allows("passenger")})
    return ids, exits, incoming


@st.cache_data(show_spinner=False)
def road_labels(network_path, targets, names_version=0):
    network_data = sumolib.net.readNet(network_path)
    names_file = ROOT / "dados/auditoria/nomes_vias_osm.json"
    osm_names = json.loads(names_file.read_text(encoding="utf-8"))["ways"] if names_file.exists() else {}
    names = dict(targets)
    approaches = {}
    for light in network_data.getTrafficLights():
        if light.getID() in names:
            for connection in light.getConnections():
                approaches[connection[0].getEdge().getID()] = names[light.getID()]
    labels = {}
    for edge in network_data.getEdges(withInternal=False):
        match = re.match(r"^-?(\d+)(?:#|$)", edge.getID())
        name = edge.getName() or (osm_names.get(match.group(1), {}).get("name", "") if match else "")
        shape = edge.getShape()
        dx, dy = shape[-1][0] - shape[0][0], shape[-1][1] - shape[0][1]
        direction = ["leste", "nordeste", "norte", "noroeste", "oeste", "sudoeste", "sul", "sudeste"][round(math.atan2(dy, dx) / (math.pi / 4)) % 8]
        labels[edge.getID()] = f"{name or 'Via sem nome cadastrado'} — sentido {direction} [{edge.getID()}]"
        if edge.getID() in approaches:
            labels[edge.getID()] += f" | Cruzamento: {approaches[edge.getID()]}"
    return labels


def show_road_map(network_path, edge_id, labels):
    """Mapa local sem serviço externo; a seta segue a geometria SUMO."""
    net = sumolib.net.readNet(network_path)
    selected = net.getEdge(edge_id)
    cx, cy = selected.getToNode().getCoord()
    fig, ax = plt.subplots(figsize=(7, 5))
    for edge in net.getEdges(withInternal=False):
        shape = edge.getShape()
        if not any(abs(x - cx) < 200 and abs(y - cy) < 200 for x, y in shape):
            continue
        ax.plot([p[0] for p in shape], [p[1] for p in shape], color="#b5b5b5", linewidth=1)
    shape = selected.getShape()
    ax.plot([p[0] for p in shape], [p[1] for p in shape], color="#1565c0", linewidth=4, label="Entrada selecionada")
    if len(shape) > 1:
        ax.annotate("", xy=shape[-1], xytext=shape[-2], arrowprops={"arrowstyle": "->", "color": "#d32f2f", "lw": 2})
    ax.scatter([cx], [cy], color="#d32f2f", label="Chegada ao cruzamento")
    ax.set(xlim=(cx - 200, cx + 200), ylim=(cy - 200, cy + 200), xlabel="Leste–oeste (m)", ylabel="Sul–norte (m)", title="Localização da entrada — norte para cima")
    ax.set_aspect("equal")
    ax.legend()
    st.pyplot(fig)
    plt.close(fig)
    match = re.match(r"^-?(\d+)(?:#|$)", edge_id)
    if match:
        st.link_button("Abrir esta via no OpenStreetMap", f"https://www.openstreetmap.org/way/{match.group(1)}")


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
st.caption("Selecione o piloto ou prepare o controle conjunto experimental dos nove cruzamentos. Programas experimentais não representam os planos reais.")

base = read_config(DEFAULT)
scope = st.radio("Cruzamentos controlados", ["Piloto: um cruzamento", "Nove cruzamentos: cenário experimental"], horizontal=True)
joint = scope.startswith("Nove")
if joint:
    st.info("Preparação automática de 17 controladores: um movimento por vez em cada controlador, com travessias, amarelo e limpeza. É uma referência conservadora; ciclos longos podem aumentar filas. Não é validação dos planos reais.")
    saved_scenarios = sorted(RESULTS.glob("cenario_nove_*/cenario.json"), key=lambda p: p.stat().st_mtime, reverse=True) if RESULTS.exists() else []
    saved_scenario = st.selectbox("Cenário conjunto salvo", [""] + [str(p) for p in saved_scenarios], format_func=lambda p: Path(p).parent.name if p else "Preparar um novo cenário")
    if saved_scenario and st.button("Usar cenário salvo"):
        try:
            prepared = read_config(saved_scenario)
            rows = validate_experimental(prepared)
            st.session_state.experimental_config = prepared
            st.session_state.experimental_rows = rows
        except Exception as error:
            st.error(str(error))
    if st.button("Preparar e verificar os nove cruzamentos", type="primary"):
        try:
            with st.spinner("Preparando rede e verificando atendimento dos movimentos…"):
                prepared, rows = prepare_experimental(base, RESULTS / f"cenario_nove_{uuid.uuid4().hex[:12]}")
                st.session_state.experimental_config = prepared
                st.session_state.experimental_rows = rows
            st.success("Cenário experimental preparado. Os nove cruzamentos estão selecionados para treino.")
        except Exception as error:
            st.error(str(error))
    if "experimental_config" in st.session_state:
        base = st.session_state.experimental_config
        st.dataframe(pd.DataFrame(st.session_state.experimental_rows), hide_index=True)
        st.caption("17 controladores selecionados. A verificação confere atendimento e exclusão simultânea de movimentos; não certifica segurança em campo.")
        st.warning("Para atender ao menos um ciclo completo de todos os sinais, use duração maior que o maior ciclo inicial mostrado na tabela. Compare com a referência experimental; ela é conservadora.")
    else:
        st.warning("Clique em Preparar e verificar antes de iniciar o treinamento.")
with st.expander("Arquivos e mapeamento", expanded=False):
    network_profile = st.selectbox("Rede", ("Original (piloto)", "Rondon Norte corrigida"))
    selected_network = base["network"] if joint else (CORRECTED_NETWORK if network_profile == "Rondon Norte corrigida" else base["network"])
    network = st.text_input("Rede SUMO (.net.xml)", str(selected_network), key=f"network_{network_profile}_{joint}_{selected_network}", help=config_help("network"), disabled=joint)
    plans = st.text_input("Planilha (.xlsx)", str(base["plans"]), help=config_help("plans"))
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
            st.info("Para controle conjunto sintético, use Preparar e verificar os nove cruzamentos. A auditoria abaixo trata da correspondência com planos reais.")
        except Exception as error:
            st.error(str(error))
    if st.button("Verificar correspondência dos nove com planos reais"):
        try:
            probe = dict(base, network=Path(network), plans=Path(plans))
            report = mapping_report(probe, base.get("mapping_path"))
            st.write(f"Validados: {report['validated_count']} de {report['total']}")
            st.dataframe(pd.DataFrame([{"cruzamento": item["name"], "id_sumo": item["tls_id"],
                                        "ids_candidatos": ", ".join(c["tls_id"] for c in item["candidate_controllers"]),
                                        "validado": item["validated"],
                                        "pendências": "; ".join(item["issues"])}
                                       for item in report["intersections"]]), hide_index=True)
        except Exception as error:
            st.error(str(error))

with st.expander("Conferência visual dos nove cruzamentos"):
    evidence_path = ROOT / "dados/auditoria/conferencia_visual_maps.json"
    if evidence_path.is_file():
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        st.info("O usuário confirmou que os cruzamentos do mapa são reais e geograficamente válidos. A auditoria dos planos reais continua em 0/9. O cenário experimental conjunto é preparado e verificado separadamente, sem exigir reprodução desses planos.")
        st.dataframe(pd.DataFrame([{"cruzamento": row["mapping_name"],
                                   "imagem": row["image_date"],
                                   "observações": "; ".join(row["observations"]),
                                   "pendências": "; ".join(row["limitations"]),
                                   "Street View": row["panorama_url"]}
                                  for row in evidence["intersections"]]), hide_index=True,
                     column_config={"Street View": st.column_config.LinkColumn("Street View")})
        image_path = ROOT / "dados/auditoria/geometria_nove_cruzamentos.png"
        if image_path.is_file():
            st.image(str(image_path), caption="Geometria dos candidatos SUMO; confira as aproximações com o cadastro operacional.")

with st.expander("Cadastro dos controladores, faixas, movimentos e estágios"):
    register_folder = ROOT / "dados/auditoria/cadastro_nove"
    if (register_folder / "summary.json").is_file():
        register = json.loads((register_folder / "summary.json").read_text(encoding="utf-8"))
        st.write(f"{register['intersections']} cruzamentos associados a {register['controllers_assigned']} controladores; {register['connections']} conexões, incluindo {register['pedestrian_connections']} de pedestres.")
        st.caption("Extração da rede aceita pelo usuário. Os grupos reais e estágios ainda precisam de correspondência; este cadastro não muda o cenário de treino ativo.")
        register_choice = st.selectbox("Tabela do cadastro", ["controladores.csv", "movimentos.csv", "estagios_a_associar.csv", "fases_por_movimento.csv"])
        register_file = register_folder / register_choice
        st.dataframe(pd.read_csv(register_file), hide_index=True)
        st.download_button("Baixar tabela do cadastro", register_file.read_bytes(), file_name=register_choice, key="register_csv")
    else:
        st.caption("Gere o cadastro com scripts/preparar_cadastro_nove.py.")

left, right = st.columns(2)
with left:
    st.subheader("Demanda sintética")
    demand_mode = st.radio("Modelo", ("Taxa pela rede", "Volume por via", "Pares origem–destino"), horizontal=True, help=config_help("demand.mode"))
    rate = st.number_input("Volume total (veículos/h)", min_value=1,
                           value=int(base["demand"].get("vehicles_per_hour", 360)),
                           disabled=demand_mode != "Taxa pela rede", help=config_help("vehicles_per_hour"))
    flows_text = st.text_area("Fluxos JSON: from_edge, to_edge, vehicles_per_hour",
                              value=json.dumps(base["demand"].get("flows", []), ensure_ascii=False, indent=2),
                              disabled=demand_mode != "Pares origem–destino", help=config_help("flows"))
    road_table = None
    destination_text = "{}"
    profile_text = "[]"
    vehicle_types_text = "[]"
    if demand_mode == "Volume por via":
        try:
            if joint and "experimental_config" not in st.session_state:
                raise ValueError("Prepare ou carregue o cenário dos nove cruzamentos no topo da página para listar suas entradas.")
            edge_ids, exit_ids, incoming_ids = road_options(network, tuple(t["tls_id"] for t in base["targets"]))
            initial = base["demand"].get("edge_volumes") or [
                {"from_edge": edge, "vehicles_per_hour": 0.0, "to_edge": ""}
                for edge in incoming_ids]
            names_file = ROOT / "dados/auditoria/nomes_vias_osm.json"
            labels = road_labels(network, tuple((t["tls_id"], t["name"]) for t in base["targets"]), names_file.stat().st_mtime_ns if names_file.exists() else 0)
            edge_by_label = {label: edge for edge, label in labels.items()}
            automatic_destination = "Automático: sortear uma saída alcançável"
            st.markdown("**Quantos veículos entram por cada trecho?**")
            if not joint:
                st.warning("Modo piloto ativo: esta tabela lista apenas as entradas de Rondon Pacheco × Paraná. Para listar os nove locais, selecione ‘Nove cruzamentos: cenário experimental’ no topo e prepare ou carregue o cenário.")
            st.write(f"**Escopo atual:** {len({t['name'] for t in base['targets']})} cruzamento(s), {len(base['targets'])} controlador(es), {len(incoming_ids)} trechos de entrada para automóveis.")
            st.write("Cada linha representa um trecho de entrada, em um sentido da via. Uma rua pode aparecer em mais de uma linha. Preencha o volume de cada trecho separadamente.")
            st.info("Exemplo: 600 veículos por hora = cerca de 10 veículos por minuto nesse trecho. O valor 0 não gera veículos a partir dessa entrada; ela ainda pode receber veículos vindos de outros trechos.")
            st.caption("Cada entrada mostra rua, sentido aproximado de deslocamento e código do trecho. Uma avenida pode aparecer em vários sentidos e cruzamentos. Nomes recuperados de © contribuidores do OpenStreetMap; o sentido segue a geometria da rede.")
            display_rows = [{"from_edge": labels.get(row["from_edge"], row["from_edge"]),
                             "vehicles_per_hour": row.get("vehicles_per_hour", 0),
                             "to_edge": labels.get(row.get("to_edge"), automatic_destination)} for row in initial]
            edited_roads = st.data_editor(pd.DataFrame(display_rows), num_rows="dynamic", hide_index=True, width="stretch",
                column_config={
                    "from_edge": st.column_config.SelectboxColumn("Trecho por onde os veículos entram", options=[labels[e] for e in edge_ids], required=True, width="large", help="Cada código de trecho identifica uma entrada. Várias entradas podem atender o mesmo cruzamento. Nome da via e cruzamento são informações distintas."),
                    "vehicles_per_hour": st.column_config.NumberColumn("Veículos por hora", min_value=0.0, step=10.0, required=True, help="Volume gerado nesta entrada. Exemplo: 600 = aproximadamente 10 veículos por minuto. Zero = sem geração nesta entrada."),
                    "to_edge": st.column_config.SelectboxColumn("Para onde vão?", options=[automatic_destination] + [labels[e] for e in exit_ids], default=automatic_destination, width="large", help="Automático sorteia uma saída que o veículo consegue alcançar. Escolha uma saída específica quando souber o destino."),
                }, key=f"road_volumes_named_{network}_{tuple(incoming_ids)}")
            road_table = edited_roads.copy()
            road_table["from_edge"] = road_table["from_edge"].map(edge_by_label)
            road_table["to_edge"] = road_table["to_edge"].map(edge_by_label).fillna("")
            st.caption(f"{len(incoming_ids)} trechos de entrada dos {len(base['targets'])} controladores selecionados estão pré-listados. Use a linha vazia no fim para adicionar outro trecho.")
            st.write("**Destino automático:** o simulador escolhe uma saída alcançável para cada veículo. Isso cria destinos sintéticos. Você pode manter essa opção até ter dados reais de origem e destino.")
            with st.expander("Conferir uma entrada no mapa"):
                checked_edge = st.selectbox("Entrada a localizar", incoming_ids, format_func=lambda edge: labels[edge])
                if checked_edge:
                    st.write(labels[checked_edge])
                    show_road_map(network, checked_edge, labels)
        except Exception as error:
            st.error(f"Não foi possível listar as vias: {error}")
    duration = st.number_input("Duração simulada do episódio (s)", min_value=10,
                               value=int(base["duration_seconds"]), step=10, help=config_help("duration_seconds"))
    step_seconds = st.number_input("Passo do SUMO (s)", min_value=0.1,
                                   value=float(base["step_seconds"]), step=0.1, help=config_help("step_seconds"))
    if demand_mode == "Volume por via":
        with st.expander("Perfil, destinos e tipos"):
            destination_text = st.text_area("Destinos por origem (JSON: ID para lista de {to_edge, share})", value="{}", help=config_help("destinations"))
            profile_text = st.text_area("Perfil temporal (JSON: begin, end, multiplier)", value="[]", help=config_help("time_profile"))
            vehicle_types_text = st.text_area("Tipos de veículo (JSON: id, vClass, share)", value="[]", help=config_help("vehicle_types"))
    if road_table is not None:
        rates = pd.to_numeric(road_table["vehicles_per_hour"], errors="coerce").fillna(0)
        planned = sum(int(value * duration / 3600 + 0.5) for value in rates)
        st.metric("Veículos planejados pelas vias", planned)
        st.caption(f"Para um episódio de {duration} segundos, os volumes preenchidos geram aproximadamente {planned} veículos no total.")
        if rates.sum() == 0:
            st.warning("Todos os volumes estão em zero. Preencha pelo menos uma entrada para gerar tráfego neste cenário.")
    seed = st.number_input("Semente", min_value=0, value=int(base["seeds"][0]), help=config_help("seeds"))
    evaluation_seeds = st.text_input("Sementes de avaliação (separadas por vírgula)",
                                     value=", ".join(map(str, base.get("evaluation", {}).get("seeds", [101, 102, 103]))), help=config_help("evaluation.seeds"))
    st.caption("Os valores são exemplos sintéticos; não representam contagem medida em Uberlândia.")
with right:
    st.subheader("Objetivos e otimização")
    algorithm_names = available_algorithms()
    selected_algorithm = st.selectbox("Algoritmo de aprendizado", algorithm_names,
        index=algorithm_names.index(base.get("algorithm", "PPO")),
        help="Algoritmos registrados compartilham ambiente SUMO, avaliação e relatórios. Novos algoritmos aparecem após serem registrados.")
    algorithm_parameters_text = "{}"
    if selected_algorithm != "PPO":
        algorithm_parameters_text = st.text_area("Parâmetros específicos do algoritmo (JSON)", value="{}",
            help="Objeto com parâmetros aceitos pelo adaptador do algoritmo. Épocas e minibatches abaixo são específicos do PPO.")
    w_wait = st.number_input("Prioridade: espera", min_value=0.0, value=1.0, step=0.1, help=config_help("objectives.waiting"))
    w_queue = st.number_input("Prioridade: filas", min_value=0.0, value=1.0, step=0.1, help=config_help("objectives.queues"))
    w_travel = st.number_input("Prioridade: tempo de viagem (aproximação)", min_value=0.0, value=1.0, step=0.1, help=config_help("objectives.travel"))
    decision = st.number_input("Intervalo de decisão (s)", min_value=1, value=int(base["ppo"]["decision_seconds"]), help=config_help("decision_seconds"))
    n_epochs = st.number_input("Épocas por lote", min_value=1, value=int(base["ppo"]["n_epochs"]), help=config_help("n_epochs"), disabled=selected_algorithm != "PPO")
    n_steps = st.number_input("Passos por coleta", min_value=2, value=int(base["ppo"]["n_steps"]), help=config_help("n_steps"), disabled=selected_algorithm != "PPO")
    batch_size = st.number_input("Tamanho do minibatch", min_value=2, value=int(base["ppo"]["batch_size"]), help=config_help("batch_size"), disabled=selected_algorithm != "PPO")
    total_steps = st.number_input("Total de passos de treinamento", min_value=2,
                                  value=int(base["ppo"]["total_timesteps"]), step=128, help=config_help("total_timesteps"))
    all_phase_control = st.checkbox("PPO ajusta verde, amarelo e vermelho de limpeza",
                                    value=base["ppo"].get("action_mode") == "phase_durations", help=config_help("action_mode"), key=f"all_phase_{joint}", disabled=joint)
    with st.expander("Limites das durações PPO"):
        limits = base["ppo"].get("duration_limits", {})
        max_yellow = st.number_input("Máximo do amarelo (s)", min_value=3.0,
            value=float(limits.get("yellow", {}).get("maximum_seconds", 6)), step=1.0, help=config_help("ppo.duration_limits.yellow.maximum_seconds"))
        max_clearance = st.number_input("Máximo do vermelho de limpeza (s)", min_value=1.0,
            value=float(limits.get("all_red", {}).get("maximum_seconds", 3)), step=1.0, help=config_help("ppo.duration_limits.all_red.maximum_seconds"))
        phase_bounds_text = st.text_area("Limites por fase (JSON: ID:índice para minimum_seconds/maximum_seconds)",
            value=json.dumps(base["ppo"].get("phase_duration_bounds", {}), indent=2), help=config_help("phase_duration_bounds"))
        st.caption("O amarelo e a limpeza não podem ser reduzidos abaixo dos tempos originais. Estes limites são parâmetros experimentais; precisam de validação operacional.")
    gui = st.checkbox("Mostrar SUMO-GUI (mais lento)", value=False, help=config_help("gui"))
    with st.expander("Métricas opcionais"):
        collect_lane = st.checkbox("Velocidade e ocupação das faixas", value=True, help=config_help("collect_lane_details"))
        collect_emissions = st.checkbox("CO₂, CO, HC, NOx, partículas, combustível e eletricidade", value=False, help=config_help("collect_emissions"))
        collect_events = st.checkbox("Teletransportes e colisões", value=True, help=config_help("collect_events"))
        collect_resources = st.checkbox("CPU e memória", value=True, help=config_help("collect_resources"))

st.button("Atualizar lista de modelos treinados", help="Após o treino, atualiza os modelos disponíveis para avaliação.")
models = sorted(RESULTS.glob("**/*_model.zip"), key=lambda p: p.stat().st_mtime, reverse=True) if RESULTS.exists() else []
selected_model = st.selectbox("Selecionar modelo treinado", [""] + [str(p) for p in models], format_func=lambda p: str(Path(p).relative_to(RESULTS)) if p else "Escolher depois do treinamento")
model_path = selected_model

def configured():
    if joint and "experimental_config" not in st.session_state:
        raise ValueError("Prepare os nove cruzamentos antes de executar")
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
            if not row.get("from_edge") or pd.isna(row["from_edge"]):
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
    config["step_seconds"] = float(step_seconds)
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
    config["ppo"] = {**base["ppo"], "decision_seconds": int(decision), "n_epochs": int(n_epochs),
                     "n_steps": int(n_steps), "batch_size": int(batch_size),
                     "total_timesteps": int(total_steps), "gui": bool(gui),
                     "action_mode": "phase_durations" if all_phase_control else "green_extension",
                     "phase_types": ["green", "yellow", "all_red"],
                     "duration_limits": {"yellow": {"maximum_seconds": float(max_yellow)},
                                         "all_red": {"maximum_seconds": float(max_clearance)}},
                     "phase_duration_bounds": json.loads(phase_bounds_text)}
    config["algorithm"] = selected_algorithm
    config["control"] = {key: config["ppo"][key] for key in (
        "decision_seconds", "gui", "action_mode", "phase_types", "duration_limits", "phase_duration_bounds")}
    if joint:
        # Os pisos geométricos não são removidos por ajustes avançados na interface.
        floors = base["experimental"]["minimum_durations"]
        for key, floor in base["experimental"]["green_floors"].items():
            bounds = config["control"]["phase_duration_bounds"].setdefault(key, {})
            bounds["minimum_seconds"] = max(floor, bounds.get("minimum_seconds", floor))
        largest_clearance = max(value for key, value in floors.items() if int(key.rsplit(":", 1)[1]) % 3 == 2)
        config["control"]["duration_limits"]["all_red"]["maximum_seconds"] = max(float(max_clearance), largest_clearance)
        config["ppo"].update(config["control"])
    if selected_algorithm != "PPO":
        parameters = json.loads(algorithm_parameters_text)
        if not isinstance(parameters, dict):
            raise ValueError("Parâmetros específicos devem ser um objeto JSON")
        key = get_algorithm(selected_algorithm).config_key
        config[key] = {**base.get(key, {}), **parameters, "total_timesteps": int(total_steps)}
    if joint:
        validate_experimental(config)
    return config


st.subheader("Configurações, execução e métricas")
tab_options, tab_parameters, tab_metrics = st.tabs([
    "2 · Todas as opções SUMO", "3 · Parâmetros e 10 épocas", "4 · Métricas e relatórios"])
try:
    current_config = configured()
except (ValueError, TypeError) as error:
    current_config = None
    st.error(f"Corrija a configuração: {error}")

with tab_options:
    version, options, queries = installed_catalogs()
    st.caption(f"{version}: {len(options)} opções CLI em {len({row['categoria'] for row in options})} categorias. Catálogo gerado pelo executável instalado.")
    st.info("Esta tabela inclui todas as opções do executável SUMO. Atributos XML de redes, veículos e modelos e opções de outras ferramentas têm catálogos próprios. Apenas os campos da interface são editáveis aqui; o catálogo não aplica opções automaticamente.")
    category = st.selectbox("Categoria SUMO", ["Todas"] + sorted({row["categoria"] for row in options}),
                            format_func=lambda name: SUMO_CATEGORIES.get(name, name))
    with st.expander("Legenda das categorias e tipos SUMO"):
        st.dataframe(pd.DataFrame([{"categoria técnica": name, "significado em português": label}
                                  for name, label in SUMO_CATEGORIES.items()]), hide_index=True)
        st.write("BOOL = verdadeiro/falso; INT = inteiro; FLOAT = número decimal; TIME = tempo; STR = texto; FILE = arquivo. O nome da opção e a descrição original SUMO são preservados para consulta técnica.")
    search = st.text_input("Pesquisar opção ou descrição SUMO")
    selected = [row for row in options if (category == "Todas" or row["categoria"] == category)
                and search.casefold() in " ".join(str(value) for value in row.values()).casefold()]
    st.dataframe(pd.DataFrame(selected), hide_index=True, width="stretch")
    st.download_button("Baixar catálogo completo SUMO", pd.DataFrame(options).to_csv(index=False).encode("utf-8-sig"),
                       "sumo_options.csv", "text/csv")

with tab_parameters:
    st.caption("A coluna ‘legenda em português’ explica cada configuração. Passe o mouse no ícone de ajuda dos campos para ver seu significado.")
    st.write("`n_epochs=10` faz dez passagens de otimização por coleta. Episódios são execuções do SUMO; `total_timesteps` determina o orçamento do treino.")
    if current_config is not None:
        try:
            workload = training_workload(current_config)
            st.dataframe(pd.DataFrame([{"quantidade": name, "valor": value} for name, value in workload.items()]), hide_index=True)
            st.caption("Previsão para um ambiente, sem cancelamento ou interrupção por KL. Passos são arredondados para coletas completas; episódios dependem do horizonte e intervalo de decisão.")
        except ValueError as error:
            st.error(str(error))
        downloadable_table(parameter_rows(current_config), "effective_parameters.csv", "Baixar todos os parâmetros atuais")
        st.download_button("Baixar cenário atual", json.dumps(current_config, ensure_ascii=False, indent=2, default=str),
                           "cenario.json", "application/json")
        st.caption("Inclui cada campo do cenário, todos os argumentos do construtor PPO e opções enviadas ao SUMO. O comando e a semente reais de cada episódio ficam em run_config.json; manifest.json registra versões e hashes.")
    benchmark_path = ROOT / "dados/auditoria/benchmark_ppo_10_epocas.json"
    if benchmark_path.is_file():
        st.write("Medição local de viabilidade computacional")
        st.json(json.loads(benchmark_path.read_text(encoding="utf-8")))
    st.warning("Tempo de execução viável não demonstra convergência. Use demanda representativa e avaliação independente. O cenário conjunto usa programas sintéticos, sem reproduzir os planos reais.")

with tab_metrics:
    st.info("1 veículo·s equivale a um veículo durante um segundo. Exemplo: 10 veículos parados durante 30 s = 300 veículo·s. P95 é o percentil 95; uma célula vazia significa ausência de valor válido, não zero.")
    if current_config is not None:
        downloadable_table(metric_rows(current_config), "metrics_catalog.csv", "Baixar tabela de métricas coletadas")
    st.caption("A avaliação exporta runs.csv, signals.csv, aggregate.csv, comparison.png, report.md e summary.json. Viagens incompletas são contadas, mas ficam fora das estatísticas de viagem; std de viagens é populacional e std entre execuções é amostral.")
    with st.expander(f"Todas as consultas TraCI disponíveis na instalação ({len(queries)})"):
        st.write("Inventário da API, incluindo identificadores, geometria e estruturas. A disponibilidade de uma consulta não significa que ela esteja no relatório; detectores e pedestres dependem dos elementos da rede.")
        domain = st.selectbox("Domínio TraCI", ["Todos"] + sorted({row["domínio"] for row in queries}))
        st.dataframe(pd.DataFrame([row for row in queries if domain == "Todos" or row["domínio"] == domain]), hide_index=True)
        st.download_button("Baixar catálogo completo TraCI", pd.DataFrame(queries).to_csv(index=False).encode("utf-8-sig"),
                           "traci_queries.csv", "text/csv")

active = "job" in st.session_state and st.session_state.job["process"].poll() is None
if joint and st.button("Testar cenário no SUMO por 30 segundos", disabled=active or current_config is None):
    try:
        with st.spinner("Executando teste curto no SUMO…"):
            preview = preview_experimental(configured(), RESULTS / f"preview_nove_{uuid.uuid4().hex[:12]}")
        st.success("SUMO executou o cenário conjunto. O teste curto verifica funcionamento; não demonstra desempenho nem percorre todos os ciclos.")
        st.json({key: value for key, value in preview.items() if key != "signals"})
    except Exception as error:
        st.error(str(error))
train_col, eval_col = st.columns(2)
with train_col:
    if st.button(f"Iniciar treinamento {selected_algorithm}", disabled=active or current_config is None, type="primary"):
        try:
            start_job("rl-train", configured())
            st.rerun()
        except Exception as error:
            st.error(str(error))
with eval_col:
    if st.button(f"Avaliar {selected_algorithm} e referência", disabled=active):
        try:
            model = Path(model_path).resolve()
            if not model.is_file():
                raise ValueError("Informe um arquivo ppo_model.zip existente")
            start_job("rl-eval", configured(), model)
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
    if code is None and job["command"] in ("ppo-train", "rl-train") and st.button("Interromper treinamento"):
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
        render_result_metrics(csv, "result_runs")
        st.download_button("Exportar métricas com códigos técnicos (.csv)", csv.read_bytes(), file_name="comparacao.csv", mime="text/csv")
    aggregate = job["output"] / "aggregate.csv"
    if aggregate.is_file():
        render_result_metrics(aggregate, "result_aggregate")
    for name in ("training_episodes.csv", "signals.csv", "aggregate.csv", "report.md", "summary.json",
                 "manifest.json", "sumo_options.csv", "effective_parameters.csv", "metrics_catalog.csv", "traci_queries.csv"):
        file = job["output"] / name
        if file.is_file():
            if name in ("training_episodes.csv", "signals.csv"):
                render_result_metrics(file, f"result_{file.stem}")
            st.download_button(f"Baixar {name}", file.read_bytes(), file_name=name, key=f"result_{name}")
    plot = job["output"] / "comparison.png"
    if plot.is_file():
        st.image(str(plot), caption="Médias por controlador; veja dispersão em aggregate.csv")
    if job["log"].is_file():
        st.code(job["log"].read_text(encoding="utf-8", errors="replace")[-8000:])


progress_panel()

with st.expander("Abrir relatórios de execuções anteriores"):
    summaries = sorted(RESULTS.glob("**/summary.json"), key=lambda path: path.stat().st_mtime, reverse=True) if RESULTS.exists() else []
    if summaries:
        chosen = st.selectbox("Resultado salvo", [str(path.parent.relative_to(RESULTS)) for path in summaries])
        folder = RESULTS / chosen
        st.json(json.loads((folder / "summary.json").read_text(encoding="utf-8")))
        for name in ("runs.csv", "signals.csv", "aggregate.csv", "training_episodes.csv", "report.md", "summary.json",
                     "manifest.json", "sumo_options.csv", "effective_parameters.csv", "metrics_catalog.csv", "traci_queries.csv"):
            path = folder / name
            if path.is_file():
                if name in ("runs.csv", "aggregate.csv", "training_episodes.csv", "signals.csv"):
                    render_result_metrics(path, f"saved_{path.stem}")
                st.download_button(f"Exportar resultado salvo: {name}", path.read_bytes(), file_name=name, key=f"saved_{name}")
        if (folder / "comparison.png").is_file():
            st.image(str(folder / "comparison.png"))
    else:
        st.caption("Nenhuma execução concluída encontrada.")
