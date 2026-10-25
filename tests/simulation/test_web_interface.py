"""Contratos HTTP, parâmetros e leitura segura, sem iniciar episódios SUMO."""

from http.client import HTTPConnection
from html import unescape
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from SistemaDeSemaforos.simulation import web_interface as web


RANDOM = dict(signal_profile="current", demand_profile="random", episodes="1",
              metrics_profile="core", duration="7200", period="1.5", termination="natural")
META = dict(signal_profile="current", demand_profile="metasettran", episodes="1",
            metrics_profile="core", day="tuesday", start="15:00", sections="1")
FREE = {key: value for key, value in META.items() if key not in {"day", "start", "sections"}} | {
    "selection_mode": "free", "selected_sections": "2,3,55,0"}


class FormTests(unittest.TestCase):
    def test_random_defaults_natural_and_defined_end(self):
        options = web.form_options(RANDOM)
        self.assertEqual(options, dict(signal_profile="current", demand_profile="random",
                                      episodes=1, metrics_profile="core", duration=7200, period=1.5, gui=False))
        self.assertEqual(web.form_options(RANDOM | {"termination": "defined", "end": "60"})["end"], 60)

    def test_invalid_numbers_profiles_and_arbitrary_parameters(self):
        cases = [dict(signal_profile="settran"), dict(metrics_profile="unknown"),
                 dict(demand_profile="other"), dict(episodes="0"), dict(episodes="1.5"),
                 dict(episodes="-1"), dict(termination="unknown"), dict(end="60"),
                 dict(termination="defined", end=""), dict(net_file="/tmp/network"),
                 dict(output_dir="/tmp/results"), dict(command="sumo"), dict(seed="7"), dict(day="monday"),
                 dict(gui="true"), dict(gui="sumo-gui"), dict(gui="")]
        for name in ("duration", "period", "end"):
            for value in ("0", "-1", "nan", "inf", "1e999", "no"):
                cases.append({name: value, "termination": "defined"} if name == "end" else {name: value})
        for values in cases:
            with self.subTest(values=values), self.assertRaises(ValueError):
                web.form_options(RANDOM | values)

    def test_meta_selection_uses_existing_validator_and_preserves_options(self):
        with patch.object(web, "resolve_contexts", wraps=web.resolve_contexts) as resolve:
            options = web.form_options(META | dict(sections="56", episodes="5", metrics_profile="full"))
        resolve.assert_called_once_with(day="tuesday", start="15:00", sections=56, master_seed=0)
        self.assertNotIn("master_seed", options)
        self.assertNotIn("end", options)
        self.assertNotIn("duration", options)
        self.assertNotIn("drain_limit", options)
        self.assertEqual(options["episodes"], 5)
        self.assertEqual(web.form_options(META | dict(master_seed=str(2**63 - 1)))["master_seed"], 2**63 - 1)
        self.assertEqual(web.form_options(META | dict(master_seed="0"))["master_seed"], 0)
        explicit = web.form_options(META | dict(sections="3", variations="1, 25, 7", episodes="5"))
        self.assertEqual(explicit["variations"], [1, 25, 7])
        self.assertEqual(explicit["episodes"], 5)

    def test_invalid_meta_selection_and_incompatible_replay(self):
        cases = [dict(day="unknown"), dict(start="01:00"), dict(sections="0"), dict(sections="57"),
                 dict(sections="1.5"), dict(master_seed="-1"), dict(master_seed=str(2**63)),
                 dict(master_seed="1.1"), dict(master_seed="1", variations="2"),
                 dict(variations="0"), dict(variations="26"), dict(variations="1.5"),
                 dict(variations="1,,"), dict(variations="1 2"), dict(end="60"),
                 dict(duration="7200"), dict(period="1.5"), dict(variation="1")]
        for values in cases:
            with self.subTest(values=values), self.assertRaises(ValueError):
                web.form_options(META | values)

    def test_manual_variations_require_exact_count_comma_syntax_and_range(self):
        for sections in (1, 8, 56):
            values = [index % 25 + 1 for index in range(sections)]
            self.assertEqual(web.parse_variations(', '.join(map(str, values)), sections), values)
            self.assertIsNone(web.parse_variations('  ', sections))
        for value in ('0', '26', '-1', '1.5', 'abc', '1 2', '1;2', '1,,2', '1,', ',1', '１', '+1'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                web.parse_variations(value, 1)
        with self.assertRaisesRegex(ValueError, 'exatamente 8 valores'):
            web.parse_variations('1,2,3,4,5', 8)
        with self.assertRaisesRegex(ValueError, 'exatamente 1 valores'):
            web.parse_variations('1,2', 1)
        with self.assertRaisesRegex(ValueError, 'variação 27 é inválida'):
            web.parse_variations('27', 1)

    def test_free_defaults_to_independent_and_manual_values_follow_group_order(self):
        options = web.form_options(FREE)
        self.assertEqual(options["selected_sections"], [2, 3, 55, 0])
        self.assertIs(options["consecutive_grouping_enabled"], False)
        self.assertFalse({"day", "start", "sections", "master_seed"} & set(options))
        with patch.object(web, "resolve_contexts", wraps=web.resolve_contexts) as resolve:
            options = web.form_options(FREE | dict(consecutive_grouping_enabled="true", variations="4,17,9,23"))
        # Segunda 06h/09h, depois domingo 21h/segunda 00h: mesma ordem do resumo.
        self.assertEqual([call.kwargs for call in resolve.call_args_list], [
            dict(day="monday", start="06:00", sections=2, variations=[4, 17]),
            dict(day="sunday", start="21:00", sections=2, variations=[9, 23]),
        ])
        self.assertEqual(options["variations"], [4, 17, 9, 23])

    def test_invalid_free_selection_or_manual_variations_rejected(self):
        cases = [dict(selected_sections=value) for value in (
            "", " ", "0,0", "-1", "56", "1.5", "1,,2", "1 2", "１", "true")]
        cases += [dict(day="monday"), dict(start="00:00"), dict(sections="1"),
                  dict(consecutive_grouping_enabled="on"), dict(variations="1,2"),
                  dict(variations="1,2,3,26"), dict(variations="1,2,3,4", master_seed="1"),
                  dict(master_seed=str(2**63)), dict(selection_mode="unknown")]
        for values in cases:
            with self.subTest(values=values), self.assertRaises(ValueError):
                web.form_options(FREE | values)
        for fields in (META | dict(selected_sections="0"),
                       META | dict(consecutive_grouping_enabled="false"),
                       RANDOM | dict(selection_mode="free")):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                web.form_options(fields)

    def test_explicit_consecutive_mode_preserves_all_existing_runner_options(self):
        self.assertEqual(web.form_options(META | dict(selection_mode="consecutive")), web.form_options(META))


class HTTPTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        self.git('init', '-q')
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                 'commit', '--allow-empty', '-qm', 'fixture')
        project_patch = patch.object(web.runner, "PROJECT_ROOT", self.project)
        project_patch.start()
        self.addCleanup(project_patch.stop)
        self.root = Path(temporary.name) / "outputs"
        patcher = patch.object(web.runner, "OUTPUT_ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.server = web.make_server(0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.batch = self.root / "outputs-random" / "batch"
        self.episode = self.batch / "episode"
        self.episode.mkdir(parents=True)
        self.document = {
            "schema_version": 3,
            "metrics": [
                {"metric_name": "seed", "value": 42},
                {"metric_name": "status", "value": "completed"},
                {"metric_name": "teleports", "value": 2, "unit": "eventos"},
                {"metric_name": "vehicles_generated", "value": 7, "label_pt": "Gerados"},
                {"metric_name": "error", "value": '<script>alert("bad")</script>'},
            ],
            "execution": {"signal_profile": "current", "context_selection": {"batch_master_seed": 123}},
        }
        (self.episode / "metrics.json").write_text(json.dumps(self.document), encoding="utf-8")
        (self.episode / "sumo.log").write_text("log parcial", encoding="utf-8")

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.project), *args], stderr=subprocess.PIPE)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        if self.server.batch.worker:
            self.server.batch.worker.join(5)

    def request(self, path, fields=None, headers=None, body=None, method=None, binary=False):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            if fields is not None:
                body = urlencode(fields)
            sent_headers = {"Content-Type": "application/x-www-form-urlencoded"} if body is not None else {}
            sent_headers.update(headers or {})
            connection.request(method or ("POST" if body is not None else "GET"), path,
                               body=body, headers=sent_headers)
            response = connection.getresponse()
            data = response.read()
            return response.status, data if binary else data.decode(), dict(response.getheaders())
        finally:
            connection.close()

    def test_form_status_and_existing_result_navigation(self):
        code, html, _ = self.request("/")
        self.assertEqual(code, 200)
        self.assertIn("EXECUTOR DE DEMANDAS INTEGRADO", html)
        self.assertNotIn('name="master_seed"', html)
        self.assertIn('id="outputs-random"', html)
        self.assertIn('id="outputs-metasettran"', html)
        self.assertEqual(json.loads(self.request("/status")[1])["status"], "idle")
        for path, expected in (("/results/", "outputs-random"),
                               ("/results/outputs-metasettran/", "Nenhum resultado"),
                               ("/results/outputs-random/", "batch"),
                               ("/results/outputs-random/batch", "episode"),
                               ("/results/outputs-random/batch/episode", "metrics.json")):
            with self.subTest(path=path):
                code, html, _ = self.request(path)
                self.assertEqual(code, 200)
                self.assertIn(expected, html)
        self.assertNotIn("<table", html)
        self.assertNotIn("batch_master_seed", html)

    def test_complete_json_and_text_viewers_escape_content_without_tables(self):
        url = "/results/outputs-random/batch/episode/metrics.json"
        code, html, _ = self.request(url)
        self.assertEqual(code, 200)
        contents = unescape(re.search(r'<pre>(.*?)</pre>', html, re.S)[1])
        self.assertEqual(json.loads(contents), self.document)
        self.assertIn('\n  "schema_version"', contents)
        self.assertNotIn("<table", html)
        self.assertNotIn("vehicles_not_inserted", html)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        code, raw, headers = self.request(url + "?raw=1")
        self.assertEqual(json.loads(raw), self.document)
        self.assertEqual(headers["Content-Disposition"], "attachment")
        code, log, _ = self.request("/results/outputs-random/batch/episode/sumo.log")
        self.assertEqual(code, 200)
        self.assertIn('<pre>log parcial</pre>', log)
        custom = {"any_schema": [None, True, {"seed": 2**63 - 1, "value": 1.5}], "text": "<unsafe>"}
        (self.episode / 'other.json').write_text(json.dumps(custom))
        code, html, _ = self.request('/results/outputs-random/batch/episode/other.json')
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(unescape(re.search(r'<pre>(.*?)</pre>', html, re.S)[1])), custom)
        self.assertEqual(json.loads((self.episode / 'other.json').read_text()), custom)
        (self.episode / 'binary.dat').write_bytes(b'\x00\x80binary')
        code, raw, headers = self.request('/results/outputs-random/batch/episode/binary.dat', binary=True)
        self.assertEqual((code, raw), (200, b'\x00\x80binary'))
        self.assertEqual(headers['Content-Disposition'], 'attachment')

    def test_traversal_symlinks_foreign_origins_and_writes_are_rejected(self):
        secret = self.root.parent / "secret.txt"
        secret.write_text("private content", encoding="utf-8")
        (self.episode / "escape").symlink_to(secret)
        (self.episode / "folder").symlink_to(secret.parent, target_is_directory=True)
        for path in ("/results/../secret.txt", "/results/outputs-random/%2e%2e/%2e%2e/secret.txt",
                     "/results/outputs-random/%2Fetc/passwd", "/results/outputs-random/%00",
                     "/results/outputs-random/..%5Csecret.txt", "/results/outputs-random/batch/episode/escape",
                     "/results/outputs-random/batch/episode/folder/secret.txt", "/results/benchmarks/"):
            with self.subTest(path=path):
                code, body, _ = self.request(path)
                self.assertEqual(code, 404)
                self.assertNotIn("private content", body)
        for headers in ({"Host": "attacker.invalid"}, {"Origin": "https://attacker.invalid"},
                        {"Sec-Fetch-Site": "cross-site"}):
            self.assertEqual(self.request("/run", RANDOM, headers)[0], 403)
        self.assertEqual(self.request("/results/outputs-random/batch/episode/sumo.log", body="changed")[0], 404)
        self.assertEqual(self.request("/results/outputs-random/batch", method="DELETE")[0], 501)
        self.assertEqual((self.episode / "sumo.log").read_text(), "log parcial")

    def test_post_validation_happens_before_runner_or_seed_draw(self):
        with patch.object(web.runner, "run_episodes") as run, patch.object(web.secrets, "randbits") as draw:
            for fields in (RANDOM | dict(episodes="0"), META | dict(variations="26"),
                           FREE | dict(selected_sections=""), FREE | dict(variations="1,2"),
                           FREE | dict(selected_sections="0,0")):
                self.assertEqual(self.request("/run", fields)[0], 400)
            self.assertEqual(self.request("/run", body=urlencode(RANDOM) + "&episodes=2")[0], 400)
            self.assertEqual(self.request("/run", body="x" * 16385)[0], 400)
            self.assertEqual(self.request("/run", body="{}", headers={"Content-Type": "application/json"})[0], 400)
            run.assert_not_called()
            draw.assert_not_called()

    def test_background_execution_excludes_other_submissions_and_recovers(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def run(**options):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("Teste não liberou o runner.")
            return self.batch

        with patch.object(web.runner, "run_episodes", side_effect=run) as execute:
            self.assertEqual(self.request("/run", RANDOM)[0], 202)
            self.assertTrue(entered.wait(2))
            self.assertEqual(json.loads(self.request("/status")[1])["status"], "running")
            self.assertEqual(self.request("/run", RANDOM)[0], 409)
            self.assertEqual(self.request('/delete-results', {'confirmation': 'delete'})[0], 409)
            self.assertTrue((self.episode / 'metrics.json').is_file())
            self.assertEqual(self.request("/")[0], 200)
            release.set()
            self.server.batch.worker.join(5)
            state = json.loads(self.request("/status")[1])
            self.assertEqual(state["status"], "completed")
            self.assertEqual(state["results_url"], "/results/outputs-random/batch")
            execute.assert_called_once_with(**web.form_options(RANDOM))
            self.assertEqual(self.request("/run", RANDOM)[0], 202)
            self.server.batch.worker.join(5)

    def test_meta_automatic_and_explicit_replay_pass_through_public_runner(self):
        for fields in (META, META | dict(sections="56", episodes="5"),
                       META | dict(master_seed="0"), META | dict(variations="25", episodes="5"),
                       FREE | dict(episodes="2", gui="yes"),
                       FREE | dict(consecutive_grouping_enabled="true", variations="4,17,9,23", episodes="2")):
            with self.subTest(fields=fields), patch.object(web.secrets, "randbits", return_value=917) as draw, \
                    patch.object(web.runner, "run_episodes", return_value=self.batch) as run:
                self.assertEqual(self.request("/run", fields)[0], 202)
                self.server.batch.worker.join(5)
                expected = web.form_options(fields)
                if "master_seed" not in expected and "variations" not in expected:
                    expected["master_seed"] = 917
                    draw.assert_called_once_with(63)
                else:
                    draw.assert_not_called()
                run.assert_called_once_with(**expected)

    def test_gui_choice_reaches_runner_for_the_whole_random_or_meta_batch(self):
        for fields in (RANDOM, META, FREE):
            for choice, expected in (("no", False), ("yes", True)):
                with self.subTest(demand=fields["demand_profile"], gui=choice), \
                        patch.object(web.runner, "run_episodes", return_value=self.batch) as run:
                    self.assertEqual(self.request("/run", fields | dict(gui=choice, episodes="3"))[0], 202)
                    self.server.batch.worker.join(5)
                    self.assertIs(run.call_args.kwargs["gui"], expected)
                    self.assertEqual(run.call_args.kwargs["episodes"], 3)

    def test_failure_and_interruption_keep_partial_results_accessible(self):
        for error, status in ((RuntimeError("SUMO indisponível"), "failed"),
                              (KeyboardInterrupt(), "interrupted")):
            with self.subTest(status=status), patch.object(web.runner, "run_episodes", side_effect=error):
                self.assertEqual(self.request("/run", RANDOM)[0], 202)
                self.server.batch.worker.join(5)
                state = json.loads(self.request("/status")[1])
                self.assertEqual(state["status"], status)
                self.assertIn(type(error).__name__, state["error"])
                self.assertEqual(self.request(state["results_url"])[0], 200)
                self.assertEqual(self.request("/results/outputs-random/batch/episode/sumo.log")[0], 200)

    def test_corrupt_metrics_do_not_hide_partial_logs(self):
        (self.episode / "metrics.json").write_text("{", encoding="utf-8")
        code, html, _ = self.request("/results/outputs-random/batch/episode")
        self.assertEqual(code, 200)
        self.assertIn("sumo.log", html)
        code, html, _ = self.request('/results/outputs-random/batch/episode/metrics.json')
        self.assertEqual(code, 200)
        self.assertIn('JSON inválido ou incompleto', html)
        self.assertIn('<pre>{</pre>', html)

    def test_delete_requires_confirmation_and_rejects_paths_and_foreign_origins(self):
        for fields in ({}, {'confirmation': 'no'}, {'confirmation': 'delete', 'path': '/tmp'},
                       {'confirmation': 'delete', 'profile': 'random'}):
            with self.subTest(fields=fields):
                self.assertEqual(self.request('/delete-results', fields)[0], 400)
                self.assertTrue((self.episode / 'metrics.json').is_file())
        self.assertEqual(self.request('/delete-results')[0], 404)
        self.assertEqual(self.request('/delete-results', {'confirmation': 'delete'},
                                      headers={'Origin': 'https://other.invalid'})[0], 403)
        self.assertEqual(json.loads((self.episode / 'metrics.json').read_text()), self.document)

    def test_delete_only_authorized_outputs_preserves_git_links_and_roots(self):
        other = self.root / 'outputs-metasettran' / 'batch' / 'episode'
        other.mkdir(parents=True)
        (other / 'generated.xml').write_text('generated')
        keep = self.root / 'outputs-random' / '.gitkeep'
        keep.write_text('keep')
        self.git('add', str(keep.relative_to(self.project)))
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'tracked')
        # Ainda versionado em HEAD, mesmo com a remoção somente no índice.
        self.git('rm', '--cached', str(keep.relative_to(self.project)))
        staged = other / 'tracked.json'
        staged.write_text('{}')
        self.git('add', str(staged.relative_to(self.project)))
        outside = self.project / 'inputs'
        outside.mkdir()
        (outside / 'source.xml').write_text('source')
        (self.episode / 'file-link').symlink_to(outside / 'source.xml')
        (self.episode / 'dir-link').symlink_to(outside, target_is_directory=True)
        unrelated = self.root / 'benchmarks'
        unrelated.mkdir()
        (unrelated / 'keep.txt').write_text('unrelated')
        code, body, _ = self.request('/delete-results', {'confirmation': 'delete'})
        self.assertEqual(code, 200, body)
        self.assertEqual(json.loads(body)['deleted_files'], 3)
        for path, value in ((keep, 'keep'), (staged, '{}'), (outside / 'source.xml', 'source'),
                            (unrelated / 'keep.txt', 'unrelated')):
            self.assertEqual(path.read_text(), value)
        self.assertTrue((self.episode / 'file-link').is_symlink())
        self.assertTrue((self.episode / 'dir-link').is_symlink())
        for name in web.RESULT_PROFILES:
            self.assertTrue((self.root / name).is_dir())
        self.assertFalse((self.episode / 'metrics.json').exists())
        self.assertFalse((other / 'generated.xml').exists())
        self.assertEqual(json.loads(self.request('/status')[1])['status'], 'idle')

    def test_delete_refuses_symlink_root_or_unavailable_git_before_any_removal(self):
        outside = self.project / 'outside'
        outside.mkdir()
        (outside / 'keep.txt').write_text('protected')
        meta = self.root / 'outputs-metasettran'
        meta.symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.request('/delete-results', {'confirmation': 'delete'})[0], 400)
        self.assertTrue((self.episode / 'metrics.json').exists())
        self.assertEqual((outside / 'keep.txt').read_text(), 'protected')
        meta.unlink()
        with patch.object(web.subprocess, 'check_output', side_effect=FileNotFoundError('git')):
            code, body, _ = self.request('/delete-results', {'confirmation': 'delete'})
        self.assertEqual(code, 400)
        self.assertIn('Nenhum resultado foi apagado', body)
        self.assertTrue((self.episode / 'metrics.json').exists())

    def test_delete_keeps_empty_profile_directories_and_allows_new_batches(self):
        self.assertEqual(self.request('/delete-results', {'confirmation': 'delete'})[0], 200)
        self.assertFalse(self.batch.exists())
        for name in web.RESULT_PROFILES:
            self.assertEqual(list((self.root / name).iterdir()), [])
            self.assertIn('Nenhum resultado', self.request('/results/' + name + '/')[1])
        with patch.object(web.runner, 'run_episodes', return_value=self.batch) as run:
            self.assertEqual(self.request('/run', RANDOM)[0], 202)
            self.server.batch.worker.join(5)
            run.assert_called_once_with(**web.form_options(RANDOM))


if __name__ == "__main__":
    unittest.main()
