"""Leitura de contagens e OD com unidades explícitas e associação revisável."""
import io
import math
import unicodedata

import pandas as pd


def identifier(value):
    if pd.isna(value):
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def read_table(data, filename):
    if filename.lower().endswith('.xlsx'):
        table = pd.read_excel(io.BytesIO(data))
    else:
        table = pd.read_csv(io.BytesIO(data), sep=None, engine='python', encoding='utf-8-sig', dtype=str)
    table.columns = [''.join(c for c in unicodedata.normalize('NFKD', str(n)) if not unicodedata.combining(c)).strip().lower() for n in table.columns]
    return table.dropna(how='all')


def count_period(data, filename, start=None, end=None):
    """Seleciona janelas completas; não inventa contagens para frações de janela."""
    table = read_table(data, filename)
    metadata = {'source_file': filename, 'source_rows': len(table), 'selected_rows': len(table)}
    has_time = {'hora_inicio', 'hora_fim'} <= set(table)
    if bool(start) != bool(end):
        raise ValueError('Informe início e fim do período juntos')
    if has_time:
        starts = pd.to_datetime(table['hora_inicio'], errors='raise')
        ends = pd.to_datetime(table['hora_fim'], errors='raise')
        if (ends <= starts).any():
            raise ValueError('Há janelas com fim anterior ou igual ao início')
        metadata.update(available_start=starts.min().isoformat(), available_end=ends.max().isoformat())
    if start and end:
        if not has_time:
            raise ValueError('Seleção de período exige hora_inicio e hora_fim')
        begin, finish = pd.Timestamp(start), pd.Timestamp(end)
        if finish <= begin:
            raise ValueError('O fim do período deve ser posterior ao início')
        mask = (starts >= begin) & (ends <= finish)
        metadata.update(period_start=begin.isoformat(), period_end=finish.isoformat(),
                        boundary_windows_excluded=int(((starts < finish) & (ends > begin) & ~mask).sum()))
        table = table.loc[mask].copy()
        if table.empty:
            raise ValueError('Nenhuma janela completa no período selecionado')
    metadata['selected_rows'] = len(table)
    return table, metadata


def parse_counts(data, filename, start=None, end=None):
    table, _ = count_period(data, filename, start, end)
    table = table.rename(columns={'from_edge': 'edge_id', 'vlink_id': 'sensor_id',
        'vehicle_total': 'vehicles', 'descricao_linha': 'label', 'veiculos_h': 'vehicles_per_hour'})
    location = 'edge_id' if 'edge_id' in table else 'sensor_id' if 'sensor_id' in table else None
    if location is None or table.empty:
        raise ValueError('Contagens exigem edge_id ou sensor_id (vlink_id) e ao menos uma linha')
    table[location] = table[location].map(identifier)
    if (table[location] == '').any():
        raise ValueError('Há contagens sem identificador do trecho/sensor')
    if 'vehicles_per_hour' in table:
        table['rate'] = pd.to_numeric(table['vehicles_per_hour'], errors='raise')
        if table[location].duplicated().any():
            raise ValueError('Taxas repetidas por trecho: forneça uma taxa ou contagens com duração da janela')
    else:
        if 'vehicles' not in table:
            raise ValueError('Informe vehicles_per_hour ou vehicles com window_seconds / hora_inicio e hora_fim')
        if 'hora_inicio' in table and 'hora_fim' in table:
            starts, ends = pd.to_datetime(table['hora_inicio']), pd.to_datetime(table['hora_fim'])
            table['window_seconds'] = (ends - starts).dt.total_seconds()
            for _, group in table.assign(start=starts, end=ends).groupby(location):
                ordered = group.sort_values('start')
                if any(a > b for a, b in zip(ordered['end'].iloc[:-1], ordered['start'].iloc[1:])):
                    raise ValueError('Janelas sobrepostas no mesmo sensor duplicam contagens; revise o arquivo')
        if 'window_seconds' not in table:
            raise ValueError('Contagem sem duração: informe window_seconds')
        table['vehicles'] = pd.to_numeric(table['vehicles'], errors='raise')
        table['window_seconds'] = pd.to_numeric(table['window_seconds'], errors='raise')
        if any(not math.isfinite(float(v)) or v <= 0 for v in table['window_seconds']) or any(not math.isfinite(float(v)) or v < 0 for v in table['vehicles']):
            raise ValueError('Contagens devem ser finitas e não negativas; duração deve ser positiva')
        labels = table.groupby(location)['label'].first().to_dict() if 'label' in table else {}
        table = table.groupby(location)[['vehicles', 'window_seconds']].sum().reset_index()
        table['label'] = table[location].map(labels).fillna('')
        table['rate'] = table['vehicles'] * 3600 / table['window_seconds']
    if any(not math.isfinite(float(v)) or v < 0 for v in table['rate']):
        raise ValueError('Veículos/h deve ser finito e não negativo')
    return [{'source_id': row[location], 'label': str(row.get('label', '')), 'edge_id': row[location] if location == 'edge_id' else '',
             'vehicles_per_hour': float(row['rate'])} for row in table.to_dict('records')]


def parse_od(data, filename):
    table = read_table(data, filename).rename(columns={'origin': 'from_edge', 'destination': 'to_edge', 'origem': 'from_edge', 'destino': 'to_edge'})
    if not {'from_edge', 'to_edge', 'vehicles_per_hour'} <= set(table) or table.empty:
        raise ValueError('OD exige from_edge, to_edge e vehicles_per_hour')
    rows = []
    for row in table.to_dict('records'):
        rate = float(row['vehicles_per_hour'])
        if not math.isfinite(rate) or rate <= 0 or pd.isna(row['from_edge']) or pd.isna(row['to_edge']):
            raise ValueError('Preencha origem, destino e veículos/h positivos em cada par OD')
        rows.append({'from_edge': identifier(row['from_edge']), 'to_edge': identifier(row['to_edge']), 'vehicles_per_hour': rate})
    if len({(r['from_edge'], r['to_edge']) for r in rows}) != len(rows):
        raise ValueError('Pares OD repetidos; informe uma taxa por par')
    return rows
