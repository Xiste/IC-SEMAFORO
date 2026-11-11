"""Resumo de resultados com as mesmas execuções completas em cada comparação."""
import pandas as pd
import streamlit as st
from pathlib import Path


@st.cache_data(show_spinner=False, max_entries=4)
def _results_excel_snapshot(output, signature):
    from semaforos.relatorios.tabela_treino import training_metrics_table, metrics_excel
    return metrics_excel(training_metrics_table(Path(output)))


def render_training_metrics(output, key, running=False):
    """Resumo e um Excel completo, sem tabelas ou arquivos repetidos na tela."""
    from semaforos.arquivos import read_json
    output = Path(output)
    if not output.exists():
        return
    summary = read_json(output / 'summary.json') or {}
    if 'timesteps' in summary:
        st.subheader('Resumo do treinamento')
        a, b, c = st.columns(3)
        a.metric('Simulações concluídas', summary.get('episodes_completed', 0))
        b.metric('Decisões de treino', summary['timesteps'])
        c.metric('Tempo de treinamento', f"{summary.get('real_seconds', 0):g} s")
        if summary.get('partial_episode_saved'):
            st.caption('O Excel também inclui uma simulação parcial, identificada como parcial.')
    paths = sorted([*output.glob('*.csv'), *output.glob('episodes/*/episode_metrics.json'),
                    *output.glob('episodes/*/live_history.csv'), *output.glob('episodes/*/actions.csv'),
                    *output.glob('optimizer/*.csv')])
    if not paths:
        return
    if running:
        st.caption('O Excel completo ficará disponível quando a execução terminar ou for interrompida.')
        return
    signature = tuple((str(path.relative_to(output)), path.stat().st_mtime_ns, path.stat().st_size) for path in paths if path.is_file())
    with st.spinner('Organizando os resultados...'):
        data = _results_excel_snapshot(str(output), signature)
    st.download_button('Baixar resultados em Excel', data,
        file_name=f'resultados_{output.name}.xlsx',
        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', key=f'{key}_excel_download')
    st.caption('Uma planilha com todas as métricas registradas. Dados indisponíveis ficam vazios e simulações parciais são identificadas.')


def render_technical_files(folder, key):
    folder = Path(folder)
    files = sorted(p.name for p in folder.iterdir() if p.is_file() and p.suffix in ('.csv', '.json', '.md', '.xlsx'))
    with st.expander('Arquivos técnicos', expanded=False):
        selected = st.selectbox('Arquivo para baixar', [''] + files,
            format_func=lambda name: 'Selecione um arquivo' if not name else name,
            key=f'{key}_file_{folder}')
        if selected:
            st.download_button('Baixar arquivo selecionado', (folder / selected).read_bytes(),
                               file_name=selected, key=f'{key}_file_download')


def comparison_table(runs, candidate):
    complete = runs[runs['episode_complete'].fillna(False)] if 'episode_complete' in runs else runs
    reference = complete[complete['controller'] == 'network_reference']
    evaluated = complete[complete['controller'] == candidate]
    paired = reference.merge(evaluated, on='seed', suffixes=('_before', '_after'), validate='one_to_one')
    metrics = [('mean_trip_waiting_seconds', 'Espera média nas viagens concluídas', 's'),
               ('mean_travel_time_seconds', 'Tempo médio das viagens concluídas', 's'),
               ('arrived', 'Veículos que concluíram a viagem', 'veículos'),
               ('unfinished', 'Veículos ainda em viagem', 'veículos'),
               ('pending_departure', 'Veículos aguardando entrar na rede', 'veículos')]
    rows = []
    for metric, label, unit in metrics:
        before, after = f'{metric}_before', f'{metric}_after'
        values = paired.dropna(subset=[before, after]) if before in paired and after in paired else pd.DataFrame()
        old, new = (values[before].mean(), values[after].mean()) if not values.empty else (None, None)
        rows.append({'Indicador': label, 'Tempos iniciais': old, 'Controle avaliado': new,
                     'Diferença': new - old if old is not None else None, 'Unidade': unit})
    return pd.DataFrame(rows), len(paired)


def result_overview(output, key):
    path = output / 'runs.csv'
    if not path.is_file():
        return
    try:
        runs = pd.read_csv(path)
        if not {'controller', 'seed'} <= set(runs):
            return
        candidates = [c for c in runs['controller'].dropna().unique() if c != 'network_reference']
        if not candidates:
            st.info('Simulação com os tempos iniciais concluída. Treine um modelo ou compare o controle por filas para medir as diferenças.')
            return
        names = {'queue_actuated': 'Controle por filas (sem aprendizado)'}
        st.subheader('O que mudou no trânsito?')
        selected = st.selectbox('Controle para comparar', candidates,
            format_func=lambda c: names.get(c, f'Modelo {c}'), key=f'{key}_simple_controller')
        table, pairs = comparison_table(runs, selected)
        if not pairs:
            st.info('Aguardando simulações completas dos dois controles para comparar.')
            return
        cards = st.columns(3)
        for column, index, title, lower_is_better in (
                (cards[0], 0, 'Espera média', True),
                (cards[1], 1, 'Tempo médio de viagem', True),
                (cards[2], 2, 'Viagens concluídas', False)):
            row = table.iloc[index]
            value, difference = row['Controle avaliado'], row['Diferença']
            available = pd.notna(value) and pd.notna(difference)
            suffix = ' s' if row['Unidade'] == 's' else ''
            column.metric(title, f'{value:.1f}{suffix}' if available else 'Sem dados',
                delta=f'{difference:+.1f}{suffix}' if available else None,
                delta_color='inverse' if lower_is_better else 'normal',
                help='O número principal é a média do controle avaliado. A diferença abaixo compara com os tempos iniciais da simulação.')
        st.caption(f'Comparação de {pairs} simulação(ões) completas e pareadas. Confira no Excel as perdas e ganhos por cruzamento. Diferenças observadas não comprovam melhora estatística.')
    except (OSError, ValueError, pd.errors.ParserError, pd.errors.EmptyDataError) as error:
        st.caption(f'O resumo ainda não está disponível: {error}')
