"""Tabela única de métricas registradas, com exportação Excel pelo aplicativo."""
import io
import math
from numbers import Real
from pathlib import Path

import pandas as pd

from semaforos.arquivos import read_json
from semaforos.relatorios.legendas import metric_legend


COLUMNS = ['Métrica', 'Valor', 'Unidade', 'Escopo', 'Episódio', 'Semente',
           'Situação do episódio', 'Identificação', 'Tempo simulado (s)',
           'Disponibilidade', 'Código', 'Descrição', 'Origem']
CONTEXT = {'episode', 'episode_number', 'seed', 'episode_complete', 'controller',
           'episode_output', 'demand_sha256', 'intersection', 'tls_id', 'lane_id',
           'edge_id', 'crossing_id', 'movement_id', 'vehicle_class', 'incoming_lanes',
           'outgoing_lanes', 'shape', 'direction', 'from_edge', 'to_edge'}
DETAILS = {'signals': 'Controlador', 'intersections': 'Cruzamento',
           'pedestrian_crossings': 'Travessia', 'flow_counts': 'Contagem',
           'lanes': 'Faixa', 'movements': 'Movimento', 'vehicle_classes': 'Classe de veículo'}
OPTIMIZER = {
    'train/loss': ('Perda total do aprendizado', ''),
    'train/value_loss': ('Perda da estimativa de valor', ''),
    'train/policy_gradient_loss': ('Perda da política', ''),
    'train/entropy_loss': ('Perda de entropia da política', ''),
    'train/approx_kl': ('Divergência KL aproximada', ''),
    'train/clip_fraction': ('Proporção de atualizações limitadas', 'fração'),
    'train/clip_range': ('Limite de atualização da política', 'fração'),
    'train/explained_variance': ('Variância explicada pela estimativa de valor', ''),
    'train/learning_rate': ('Taxa de aprendizado', ''),
    'train/n_updates': ('Atualizações do modelo', 'atualizações'),
    'rollout/ep_rew_mean': ('Recompensa média dos episódios', ''),
    'rollout/ep_len_mean': ('Duração média dos episódios em decisões', 'decisões'),
    'time/total_timesteps': ('Decisões acumuladas no treinamento', 'decisões'),
    'time/iterations': ('Coletas de treinamento', 'coletas'),
    'time/time_elapsed': ('Tempo real acumulado do treino', 's'),
    'time/fps': ('Velocidade do treinamento', 'decisões/s'),
}


def training_metrics_table(output):
    output = Path(output)
    rows, seen = [], set()

    def append(values, context, scope, identity, source, prefix=''):
        for name, value in values.items():
            if name in CONTEXT or name in DETAILS or name == 'terminal_observation':
                continue
            code = f'{prefix}{name}'
            if isinstance(value, dict):
                append(value, context, scope, identity, source, code + '.')
                continue
            if value is not None and not isinstance(value, (Real, bool)):
                continue
            label, description, unit = metric_legend(code)
            if code in OPTIMIZER:
                label, unit = OPTIMIZER[code]
                description = 'Indicador registrado pelo algoritmo durante o aprendizado; não mede diretamente melhoria no trânsito.'
            finite = value is not None and (isinstance(value, bool) or math.isfinite(float(value)))
            rows.append({'Métrica': label, 'Valor': value if finite else None,
                         'Unidade': unit, 'Escopo': scope, **context,
                         'Identificação': identity, 'Código': code, 'Descrição': description,
                         'Disponibilidade': 'Coletada' if finite else 'Sem amostras', 'Origem': source})
            seen.add(code)

    def context_for(info):
        complete = info.get('episode_complete')
        return {'Episódio': info.get('episode_number', info.get('episode')),
                'Semente': info.get('seed'),
                'Situação do episódio': 'Completo' if complete is True else 'Parcial' if complete is False else 'Não informada',
                'Tempo simulado (s)': info.get('simulated_seconds')}

    episodes = list(sorted((output / 'episodes').glob('*/episode_metrics.json')))
    captured = {}
    for path in episodes:
        info = read_json(path)
        if not info:
            continue
        captured[info.get('episode_number')] = set(info)
        context = context_for(info)
        source = path.relative_to(output).as_posix()
        append(info, context, 'Rede', '', source)
        for name, scope in DETAILS.items():
            details = info.get(name, {} if name == 'signals' else [])
            if name == 'signals':
                details = [dict(values, tls_id=tls) for tls, values in details.items()]
            for detail in details:
                identity = ' · '.join(str(detail[k]) for k in ('intersection', 'tls_id', 'lane_id', 'movement_id', 'crossing_id', 'edge_id', 'vehicle_class') if detail.get(k) is not None)
                # Estados por fase preservam índices do programa para rastreabilidade.
                detail = dict(detail)
                phases = detail.pop('phase_seconds', {})
                detail.update({f'phase_{index}_seconds': seconds for index, seconds in phases.items()})
                append(detail, context, scope, identity, source)

    def read_csv(path):
        try:
            return pd.read_csv(path)
        except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError):
            return pd.DataFrame()

    # Fallback para registros antigos ou episódios completos recém-publicados.
    for record in read_csv(output / 'training_episodes.csv').to_dict('records'):
        episode = record.get('episode_number', record.get('episode'))
        if episode in captured:
            # A coleta do algoritmo acrescenta, por exemplo, timesteps ao episódio.
            extras = {k: v for k, v in record.items() if k not in captured[episode]}
            append(extras, context_for(record), 'Rede', '', 'training_episodes.csv')
            continue
        complete = record.get('episode_complete')
        if pd.notna(complete):
            record['episode_complete'] = bool(complete)
        append(record, context_for(record), 'Rede', '', 'training_episodes.csv')

    if not episodes:
        for name, scope in DETAILS.items():
            for record in read_csv(output / f'{name}.csv').to_dict('records'):
                identity = ' · '.join(str(record[k]) for k in ('intersection', 'tls_id', 'lane_id', 'movement_id', 'crossing_id', 'edge_id', 'vehicle_class') if k in record and pd.notna(record[k]))
                append(record, context_for(record), scope, identity, f'{name}.csv')

    for path in episodes:
        info = read_json(path) or {}
        context = context_for(info)
        for name, scope in (('live_history.csv', 'Histórico por decisão'), ('actions.csv', 'Ação do controle')):
            source = path.with_name(name)
            for index, record in enumerate(read_csv(source).to_dict('records'), 1):
                record_context = {**context, 'Tempo simulado (s)': record.get('simulated_seconds', record.get('time_seconds'))}
                append(record, record_context, scope, record.get('tls_id', f'Amostra {index}'), source.relative_to(output).as_posix())

    # Os logs SB3 registram perdas, entropia, KL, atualização e demais diagnósticos.
    manifest = read_json(output / 'manifest.json') or {}
    for index, record in enumerate(read_csv(output / 'optimizer/progress.csv').to_dict('records'), 1):
        append(record, {'Semente': manifest.get('training_seed'), 'Situação do episódio': 'Não se aplica'},
               'Aprendizado', f'Atualização {index}', 'optimizer/progress.csv')

    for record in read_csv(output / 'metrics_catalog.csv').to_dict('records'):
        code = record.get('métrica')
        if not isinstance(code, str) or not code or code in seen or code in CONTEXT or '.' in code:
            continue
        rows.append({'Métrica': record.get('nome em português', code), 'Valor': None,
                     'Unidade': record.get('unidade', ''), 'Escopo': record.get('escopo', ''),
                     'Código': code, 'Descrição': record.get('legenda em português', ''),
                     'Disponibilidade': 'Não coletada nesta execução', 'Origem': 'metrics_catalog.csv'})
    return pd.DataFrame(rows, columns=COLUMNS)


def metrics_excel(table):
    """Exportador do produto: números nativos, filtros e cabeçalho fixo."""
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    workbook = Workbook(write_only=True)
    body_font = Font(name='Calibri', size=11)
    header_font = Font(name='Calibri', bold=True, color='FFFFFF', size=11)
    header_fill = PatternFill('solid', fgColor='15354B')
    wrap = Alignment(wrap_text=True, vertical='top')
    widths = [48, 19, 19, 22, 12, 12, 23, 42, 23, 30, 44, 90, 65]
    # Escrita incremental para exportar treinos longos sem criar todas as células em memória.
    for start in range(0, max(1, len(table)), 1_048_575):
        sheet = workbook.create_sheet('Métricas' if start == 0 else f'Métricas {start // 1_048_575 + 1}')
        sheet.freeze_panes = 'C2'
        sheet.sheet_view.showGridLines = False
        for index, width in enumerate(widths, 1):
            sheet.column_dimensions[get_column_letter(index)].width = width
        header = []
        for name in table.columns:
            cell = WriteOnlyCell(sheet, name)
            cell.font, cell.fill = header_font, header_fill
            cell.data_type = 's'
            header.append(cell)
        sheet.row_dimensions[1].height = 28
        sheet.append(header)
        chunk = table.iloc[start:start + 1_048_575]
        for row_index, record in enumerate(chunk.itertuples(index=False, name=None), 2):
            cells, lines = [], 1
            for index, value in enumerate(record):
                value = None if pd.isna(value) else value.item() if hasattr(value, 'item') else value
                cell = WriteOnlyCell(sheet, value)
                cell.font = body_font
                if isinstance(value, str):
                    cell.data_type = 's'
                    cell.alignment = wrap
                    lines = max(lines, sum(max(1, math.ceil(len(line) / (widths[index] - 3))) for line in value.split('\n')))
                if index == 1:
                    cell.number_format = '0.########'
                cells.append(cell)
            sheet.row_dimensions[row_index].height = 15 * lines
            sheet.append(cells)
        sheet.auto_filter.ref = f'A1:{get_column_letter(len(table.columns))}{len(chunk) + 1}'
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
