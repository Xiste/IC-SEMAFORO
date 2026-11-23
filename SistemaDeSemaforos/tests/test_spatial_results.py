import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from openpyxl import load_workbook
from streamlit.testing.v1 import AppTest
from semaforos.apresentacao.resultados import _results_excel_snapshot, signal_color_table, signal_green_comparison
from semaforos.arquivos import write_json
from semaforos.caminhos import PROJECT_ROOT
from semaforos.cenario.rede import network_programs


class SpatialResultsTest(unittest.TestCase):
    def test_color_table_accepts_cached_movements_without_static_cycle_flag(self):
        network = PROJECT_ROOT / 'dados/rede/uberlandia.rondon_norte_corrigida.net.xml'
        targets = [{'name': 'Cruzamento A', 'tls_id': 'signal'}]
        old_movements = {'signal': [{'_link_index': 0, 'Via': 'Rua A',
                                     'Sentido': 'norte', 'Movimento': 'Em frente'}]}
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            write_json(output / 'summary.json', {'config': {'network': str(network), 'targets': targets}})
            pd.DataFrame([{'controller': 'PPO', 'seed': 101, 'tls_id': 'signal', 'link_0_green_mean_seconds': 20},
                          {'controller': 'network_reference', 'seed': 101, 'tls_id': 'signal',
                           'link_0_green_mean_seconds': 15}]).to_csv(output / 'signals.csv', index=False)
            with patch('semaforos.apresentacao.resultados._signal_report_geometry',
                       return_value=({}, {}, {}, old_movements)):
                table = signal_color_table(output, 'PPO', [101])
            self.assertEqual(table.set_index('Controle')['Verde (s)'].to_dict(), {'PPO': 20, 'network_reference': 15})

    def test_excel_reports_phase_duration_and_mixed_traffic_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            paired = pd.DataFrame({'seed': [101, 101], 'controller': ['network_reference', 'PPO'],
                                   'demand_sha256': ['same', 'same']})
            paired.to_csv(output / 'runs.csv', index=False)
            paired.assign(intersection='Rondon x Paraná', wait_vehicle_seconds=[90, 60],
                          queue_vehicle_seconds=[100, 140], peak_halted_vehicles=[10, 10]
                          ).to_csv(output / 'intersections.csv', index=False)
            paired.assign(tls_id='001', phase_0_seconds=[60, 75],
                          phase_0_mean_duration_seconds=[20, 25], phase_0_completed_count=[3, 3]
                          ).to_csv(output / 'signals.csv', index=False)
            workbook = load_workbook(io.BytesIO(_results_excel_snapshot(str(output), ())), read_only=True)
            self.assertEqual(workbook.sheetnames, ['Métricas', 'Comparação da rede',
                                                   'Resultado por cruzamento', 'Fases (dados técnicos)'])
            rows = workbook['Resultado por cruzamento'].values
            header = next(rows)
            self.assertEqual([row[header.index('Resultado')] for row in rows], ['Melhorou', 'Piorou', 'Estável'])
            rows = workbook['Fases (dados técnicos)'].values
            phase = dict(zip(next(rows), next(rows)))
            self.assertEqual(phase['ID do semáforo'], '001')
            self.assertEqual(phase['Duração média avaliada (s)'], 25)
            self.assertEqual(phase['Total avaliado (s)'], 75)
            workbook.close()

            for name in ('runs.csv', 'intersections.csv', 'signals.csv'):
                path = output / name
                table = pd.read_csv(path)
                table['controller'] = table['controller'].replace('network_reference', 'model_reference')
                table.to_csv(path, index=False)
            write_json(output / 'summary.json', {'reference_controller': 'model_reference', 'algorithm': 'PPO',
                                                  'reference_model_algorithm': 'PPO',
                                                  'model_path': 'a/ppo_model.zip',
                                                  'reference_model_path': 'b/ppo_model.zip'})
            workbook = load_workbook(io.BytesIO(_results_excel_snapshot(str(output), ('models',))), read_only=True)
            rows = workbook['Resultado por cruzamento'].values
            comparison = dict(zip(next(rows), next(rows)))
            self.assertEqual(comparison['Valor do modelo B'], 90)
            self.assertEqual(comparison['Valor do modelo A'], 60)
            self.assertEqual(comparison['Modelo B (referência)'], 'b/ppo_model.zip')
            workbook.close()

    def test_green_seconds_compare_only_complete_pairs_and_keep_zero(self):
        rows = [
            [101, 'network_reference', True, 15, 8],
            [101, 'PPO', True, 19, 0],
            [102, 'network_reference', True, 14, 5],
            [102, 'PPO', False, 10, 5],
            [103, 'network_reference', True, 24, 9],
            [103, 'PPO', True, 30, 4],
            [104, 'network_reference', True, 17, 10],
            [104, 'PPO', True, 19, 8],
        ]
        signals = pd.DataFrame(rows, columns=['seed', 'controller', 'episode_complete', 'phase_0_seconds', 'phase_3_seconds'])
        signals['tls_id'] = 'signal'
        targets = [{'tls_id': 'signal', 'name': 'Cruzamento A'}]
        stages = {'signal': [(0, 'Rua A'), (3, 'Rua B')]}
        table = signal_green_comparison(signals, 'PPO', [101, 102, 104], targets, stages)
        self.assertEqual(table['Tempos iniciais (s)'].tolist(), [16., 9.])
        self.assertEqual(table['Controle avaliado (s)'].tolist(), [19., 4.])
        self.assertEqual(table['Diferença (s)'].tolist(), [3., -5.])

    def test_map_and_details_use_completed_pairs_with_matching_demand(self):
        def case(controller, seed, actual_demand, arrivals, complete=True):
            return {'controller': controller, 'seed': seed, 'demand_sha256': actual_demand,
                    'episode_complete': complete, 'arrived': arrivals}

        runs = [
            case('network_reference', 101, 'same', 12),
            case('PPO', 101, 'same', 14),
            case('network_reference', 102, 'same', 20),
            case('PPO', 102, 'same', 15, complete=False),
            case('network_reference', 103, 'different-base', 30),
            case('PPO', 103, 'different-candidate', 33),
            case('queue_actuated', 101, 'same', 40),
        ]
        runs[0].update(mean_trip_waiting_seconds=78.3, mean_travel_time_seconds=259.1)
        runs[1].update(mean_trip_waiting_seconds=95.4, mean_travel_time_seconds=271.1)
        for run in runs:
            run.update(simulated_seconds=650, measured_seconds=600)
        # Local rows marked complete must still respect the global paired runs.
        intersections = [
            {'intersection': 'Rondon x Paraná', 'controller': run['controller'], 'seed': run['seed'],
             'episode_complete': True, 'wait_vehicle_seconds': wait}
            for run, wait in zip(runs, (75, 50, 90, 0, 110, 0))
        ]
        intersections[0].update(queue_vehicle_seconds=4441, peak_halted_vehicles=16)
        intersections[1].update(queue_vehicle_seconds=7623, peak_halted_vehicles=24)
        intersections.extend([
            {'intersection': 'Rondon x Niterói', 'controller': 'network_reference', 'seed': 101,
             'episode_complete': True, 'wait_vehicle_seconds': 25},
            {'intersection': 'Rondon x Niterói', 'controller': 'PPO', 'seed': 101,
             'episode_complete': True, 'wait_vehicle_seconds': None},
        ])
        coordinates = [
            {'intersection': 'Rondon x Paraná', 'latitude': -18.899, 'longitude': -48.265},
            {'intersection': 'Rondon x Niterói', 'latitude': -18.907, 'longitude': -48.267},
        ]
        network = PROJECT_ROOT / 'dados/rede/uberlandia.rondon_norte_corrigida.net.xml'
        tls = 'FAM_CESARIO_PARANA'
        programs = network_programs(network)
        signals = [{'tls_id': tls, 'intersection': 'Rondon x Paraná', 'seed': 101, 'controller': 'PPO',
                    **{f'link_{index}_{color}_mean_seconds': seconds
                       for index in range(len(programs[tls][0]['state']))
                       for color, seconds in (('green', 25), ('yellow', 3), ('red', 45))}}]
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            write_json(output / 'summary.json', {'config': {'network': str(network), 'targets': [
                {'name': 'Rondon x Paraná', 'tls_id': tls, 'phase_indices': [0]}]}})
            for file, rows in (('runs.csv', runs), ('intersections.csv', intersections),
                               ('gargalos.csv', coordinates), ('signals.csv', signals)):
                pd.DataFrame(rows).to_csv(output / file, index=False)
            app = AppTest.from_string(
                f"import streamlit as st\n"
                f"from semaforos.apresentacao.resultados import render_execution_results\n"
                "view = st.radio('Visualiza\\u00e7\\u00e3o', ['Resumo', 'M\\u00e9tricas'])\n"
                f"render_execution_results({str(output)!r}, 'spatial', view)"
            ).run()
            self.assertFalse(app.exception, str(app.exception))
            arrivals = next(metric for metric in app.metric if metric.label == 'Viagens concluídas na rede')
            self.assertEqual(arrivals.value, '14')
            self.assertTrue(any('resultados mistos' in item.value for item in app.info))
            self.assertIn('Melhorou', arrivals.delta)
            self.assertFalse(app.get('deck_gl_json_chart'))
            self.assertFalse(app.get('download_button'))
            self.assertFalse(app.selectbox)
            app.radio[0].set_value('Métricas').run()
            self.assertFalse(app.exception, str(app.exception))
            self.assertTrue(app.get('deck_gl_json_chart'))
            self.assertEqual(len(app.get('download_button')), 1)
            detail = next(widget for widget in app.selectbox if widget.label == 'Cruzamento para detalhar')
            self.assertEqual(len(app.selectbox), 1)
            detail.select('Rondon x Paraná').run()
            self.assertFalse(app.exception, str(app.exception))
            local = next(frame.value for frame in app.dataframe if 'O que mudou' in frame.value)
            self.assertEqual(list(local), ['Indicador', 'Programa original', 'Com PPO', 'O que mudou'])
            self.assertEqual(local.iloc[0]['Programa original'], '7,4 veículos')
            self.assertEqual(local.iloc[0]['Com PPO'], '12,7 veículos')
            self.assertEqual(local.iloc[0]['O que mudou'], 'Piorou · +5,3 veículos (+71,7%)')
            self.assertEqual(local.iloc[1]['Programa original'], '16 veículos')
            self.assertEqual(local.iloc[1]['Com PPO'], '24 veículos')
            times = next(frame.value for frame in app.dataframe if 'Verde (s)' in frame.value)
            self.assertEqual(list(times.iloc[0][['Verde (s)', 'Amarelo (s)', 'Vermelho (s)']]), [25, 3, 45])
            self.assertNotIn('Fase', times.columns)
            self.assertNotIn('ID do semáforo', times.columns)
            detail.select('Rondon x Niterói').run()
            self.assertFalse(app.exception, str(app.exception))
            self.assertFalse(any('Verde (s)' in frame.value for frame in app.dataframe))
            local = next(frame.value for frame in app.dataframe if 'O que mudou' in frame.value)
            self.assertEqual(local.iloc[0]['O que mudou'], 'Sem dados')
            runs[0]['arrived'], runs[1]['arrived'] = 376, 281
            pd.DataFrame(runs).to_csv(output / 'runs.csv', index=False)
            app.radio[0].set_value('Resumo').run()
            self.assertFalse(app.exception, str(app.exception))
            self.assertTrue(any('PPO piorou em 3 de 3' in item.value for item in app.warning))
            self.assertTrue(all('Piorou' in metric.delta for metric in app.metric))
