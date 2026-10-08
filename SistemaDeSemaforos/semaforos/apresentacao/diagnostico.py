"""Painel legível de calibração e resultados comparados à referência."""
from pathlib import Path

import pandas as pd
import streamlit as st

from semaforos.arquivos import read_json
from semaforos.apresentacao.gargalos import render_bottlenecks


def render_diagnostics(output, key):
    output = Path(output)
    report = read_json(output / 'diagnostico.json')
    if not report:
        return
    st.subheader('Calibração e evidência de melhoria')
    st.caption(report['scope'])
    if report.get('partial_episodes') or report.get('cancelled'):
        st.warning('Execução interrompida ou com episódios parciais. Estes resultados não comprovam uma comparação completa.')
    if report.get('measurement_source'):
        source = report['measurement_source']
        if source.get('synthetic'):
            st.info('Demonstração com contagens sintéticas. Estes volumes não são medições do trânsito real.')
        st.caption(f"Medição: {source.get('source_file', '')} — período {source.get('period_start', source.get('available_start', 'não informado'))} até {source.get('period_end', source.get('available_end', 'não informado'))}.")
    if report['calibration']:
        valid = report['calibration_valid_in_reference']
        if valid:
            st.success(f"Fluxos realizados da referência dentro da tolerância de {report['calibration_tolerance_percent']:g}% em todos os trechos medidos.")
        else:
            st.warning('A referência ainda não reproduz todos os fluxos medidos na tolerância escolhida. Confira associação, rotas, duração e tempo para veículos alcançarem os detectores.')
        st.dataframe(pd.DataFrame(report['calibration']).rename(columns={
            'controller': 'Controle', 'edge_id': 'Trecho', 'seeds': 'Sementes',
            'measured_vehicles_per_hour': 'Medido (veículos/h)', 'fitted_vehicles_per_hour': 'Ajustado nas rotas (veículos/h)',
            'realized_vehicles_per_hour': 'Realizado no SUMO (veículos/h)',
            'maximum_fitted_error_percent': 'Maior erro do ajuste (%)',
            'maximum_realized_error_percent': 'Maior erro realizado (%)', 'within_tolerance': 'Dentro da tolerância'}), hide_index=True)
    elif report['demand_mode'] != 'observed_counts':
        st.info('Esta execução não usa contagens observadas para calibrar a demanda.')
    else:
        st.warning('Nenhum episódio completo com fluxos medidos disponível para validar a demanda.')
    for conclusion in report['conclusions']:
        text = f"{conclusion['controller']}: {conclusion['status']} ({conclusion['paired_seeds']} sementes)."
        (st.success if conclusion['consistent_simulated_improvement'] else st.warning)(text)
    if report['comparisons']:
        controllers = sorted({row['controller'] for row in report['comparisons']})
        selected = st.selectbox('Controle para comparar com a referência', controllers, key=f'{key}_controller')
        table = pd.DataFrame([row for row in report['comparisons'] if row['controller'] == selected])
        cards = st.columns(3)
        for card, metric in zip(cards, ('global_halted_vehicle_seconds', 'wait_vehicle_seconds', 'arrived')):
            values = table[table.metric == metric]
            if not values.empty:
                row = values.iloc[0]
                percent = row['improvement_percent']
                card.metric(row['label'], f"{row['candidate_mean']:,.1f}",
                            delta=f"{percent:+.1f}% de melhoria" if pd.notna(percent) else None,
                            help=f"Referência: {row['reference_mean']:,.1f}. Valores médios nas sementes pareadas; confira a conclusão e os intervalos abaixo.")
        st.caption('Benefício positivo = melhora. Percentual vazio indica referência igual a zero; compare os valores absolutos. O intervalo de confiança mede a diferença pareada, não o percentual.')
        st.dataframe(table[['label', 'pairs', 'reference_mean', 'candidate_mean', 'benefit_mean', 'improvement_percent',
                            'benefit_ci95_low', 'benefit_ci95_high', 'improved_seeds', 'worsened_seeds']].rename(columns={
            'label': 'Métrica', 'pairs': 'Sementes pareadas', 'reference_mean': 'Referência', 'candidate_mean': 'Controle avaliado',
            'benefit_mean': 'Benefício médio', 'improvement_percent': 'Melhoria (%)',
            'benefit_ci95_low': 'Benefício: IC95% inferior', 'benefit_ci95_high': 'Benefício: IC95% superior',
            'improved_seeds': 'Sementes com melhora', 'worsened_seeds': 'Sementes com piora'}), hide_index=True)
        percentages = table.dropna(subset=['improvement_percent'])
        if not percentages.empty:
            st.bar_chart(percentages[['label', 'improvement_percent']].rename(columns={'label': 'Métrica', 'improvement_percent': 'Melhoria (%)'}).set_index('Métrica'))
        local = [row for row in report['intersections'] if row['controller'] == selected]
        if local:
            st.write('**Onde melhorou e onde piorou**')
            st.dataframe(pd.DataFrame(local).sort_values('benefit_mean')[['intersection', 'label', 'pairs', 'reference_mean',
                'candidate_mean', 'improvement_percent']].rename(columns={'intersection': 'Cruzamento', 'label': 'Métrica',
                'pairs': 'Sementes', 'reference_mean': 'Referência', 'candidate_mean': 'Controle avaliado', 'improvement_percent': 'Melhoria (%)'}), hide_index=True)
    elif not report['conclusions']:
        st.info('Ainda não há pares completos de referência e controle. Execute uma comparação para medir melhoria.')
    st.caption(report['method'])
    st.caption(report['limitations'])
    render_bottlenecks(report, key)
    for name in ('diagnostico.json', 'melhorias.csv', 'melhorias_cruzamentos.csv', 'validacao_demanda.csv', 'lanes.csv', 'movements.csv', 'vehicle_classes.csv', 'gargalos.csv'):
        path = output / name
        if path.is_file():
            st.download_button(f'Exportar {name}', path.read_bytes(), file_name=name, key=f'{key}_{name}')
