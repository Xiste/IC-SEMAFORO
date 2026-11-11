import io
import tempfile
import unittest
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from streamlit.testing.v1 import AppTest

from semaforos.arquivos import write_json
from semaforos.caminhos import PROJECT_ROOT
from semaforos.cenario.configuracao import read_config
from semaforos.experimentos.rl import train_rl
from semaforos.relatorios.tabela_treino import training_metrics_table, metrics_excel


class TrainingMetricsExportTest(unittest.TestCase):
    def test_streets_and_global_history_are_identified(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            self.fixture(output)
            network = output / 'network.net.xml'
            network.write_text('''<net>
              <edge id="in" name="Rua A"><lane id="laneA" shape="0,0 0,10"/></edge>
              <edge id="out" name="Rua B"><lane id="laneB" shape="0,10 10,10"/></edge>
              <connection tl="tls" linkIndex="0" from="in" to="out" fromLane="0" toLane="0"/>
            </net>''', encoding='utf-8')
            write_json(output / 'manifest.json', {'network': str(network),
                       'targets': [{'tls_id': 'tls', 'name': 'Rua A x Rua B'}]})
            table = training_metrics_table(output)
            lane = table[table['Escopo'] == 'Faixa'].iloc[0]
            self.assertEqual(lane['Rua de entrada'], 'Rua A')
            self.assertEqual(lane['Sentido'], 'Segue para norte')
            action = table[table['Escopo'] == 'Ação do controle'].iloc[0]
            self.assertEqual(action['Cruzamento'], 'Rua A x Rua B')
            self.assertEqual(action['Identificação'], 'Rua A x Rua B')
            self.assertEqual(set(table[table['Escopo'] == 'Histórico por decisão']['Identificação']), {'Toda a rede'})
            sheet = load_workbook(io.BytesIO(metrics_excel(table))).active
            self.assertIn('Rua de entrada', [cell.value for cell in sheet[1]])

    def fixture(self, output):
        episode = output / 'episodes/episode_1'
        episode.mkdir(parents=True)
        write_json(episode / 'episode_metrics.json', {
            'episode_number': 1, 'seed': 11, 'episode_complete': False, 'simulated_seconds': 20,
            'arrived': 0, 'mean_travel_time_seconds': None,
            'signals': {'tls': {'queue_vehicle_seconds': 12, 'phase_seconds': {'0': 10}}},
            'intersections': [{'intersection': '=Local', 'arrived': 0}],
            'lanes': [{'lane_id': 'laneA', 'mean_occupancy_percent': 45}],
            'movements': [{'movement_id': 'tls:0', 'passed_vehicles': None}],
            'vehicle_classes': [{'vehicle_class': 'passenger', 'observed_unique_vehicles': 4}],
            'pedestrian_crossings': [{'crossing_id': 'crossA', 'pedestrians_arrived': 2}]})
        pd.DataFrame([{'episode': 1, 'episode_complete': False, 'arrived': 0}]).to_csv(output / 'training_episodes.csv', index=False)
        pd.DataFrame([{'simulated_seconds': 5, 'queue_vehicles_now': 3}]).to_csv(episode / 'live_history.csv', index=False)
        pd.DataFrame([{'time_seconds': 5, 'tls_id': 'tls', 'requested_green': 3}]).to_csv(episode / 'actions.csv', index=False)
        (output / 'optimizer').mkdir()
        pd.DataFrame([{'train/value_loss': .25, 'train/learning_rate': .0003}]).to_csv(output / 'optimizer/progress.csv', index=False)
        pd.DataFrame([{'métrica': 'co2_grams', 'nome em português': 'CO2', 'unidade': 'g'}]).to_csv(output / 'metrics_catalog.csv', index=False)

    def test_all_scopes_missing_values_and_numeric_excel(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            self.fixture(output)
            table = training_metrics_table(output)
            self.assertTrue({'Rede', 'Controlador', 'Cruzamento', 'Faixa', 'Movimento',
                             'Travessia', 'Classe de veículo', 'Aprendizado', 'Histórico por decisão', 'Ação do controle'} <= set(table['Escopo']))
            arrived = table[(table['Código'] == 'arrived') & (table['Escopo'] == 'Rede')]
            self.assertEqual(len(arrived), 1)  # Sem duplicar o CSV de episódios.
            self.assertEqual(arrived.iloc[0]['Valor'], 0)
            self.assertEqual(arrived.iloc[0]['Situação do episódio'], 'Parcial')
            self.assertTrue(pd.isna(table[table['Código'] == 'mean_travel_time_seconds'].iloc[0]['Valor']))
            self.assertEqual(table[table['Código'] == 'co2_grams'].iloc[0]['Disponibilidade'], 'Não coletada nesta execução')
            workbook = load_workbook(io.BytesIO(metrics_excel(table)))
            sheet = workbook.active
            self.assertEqual(sheet.max_row, len(table) + 1)
            self.assertEqual(sheet.freeze_panes, 'C2')
            self.assertEqual(sheet.auto_filter.ref, sheet.dimensions)
            self.assertTrue(any(isinstance(row[1].value, (int, float)) for row in list(sheet)[1:]))
            self.assertFalse(any(cell.data_type == 'f' for row in sheet for cell in row))

    def test_interface_has_one_excel_download_without_tables(self):
        with tempfile.TemporaryDirectory() as folder:
            self.fixture(Path(folder))
            app = AppTest.from_string(f"from semaforos.apresentacao.resultados import render_training_metrics\nrender_training_metrics({folder!r}, 'test')").run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.dataframe), 0)
            self.assertEqual(len(app.selectbox), 0)
            app.run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.get('download_button')), 1)

    def test_short_real_training_records_optimizer_metrics_for_export(self):
        config = read_config(PROJECT_ROOT / 'config/cenario.json')
        config['duration_seconds'] = 20
        config['ppo'].update(total_timesteps=4, n_steps=4, batch_size=4, n_epochs=1)
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'train'
            train_rl(config, output)
            table = training_metrics_table(output)
            self.assertIn('train/value_loss', set(table['Código']))
            self.assertIn('reward', set(table['Código']))
            workbook = load_workbook(io.BytesIO(metrics_excel(table)))
            self.assertGreater(workbook.active.max_row, 10)
