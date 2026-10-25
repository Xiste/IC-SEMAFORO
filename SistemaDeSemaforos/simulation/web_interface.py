"""Interface HTTP local, sem dependências, sobre run_episodes.

Uso: python3 -B -m SistemaDeSemaforos.simulation.web_interface
O único lote ativo fica numa thread; os resultados continuam pertencendo ao runner.
"""

import argparse
import errno
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
import threading
from urllib.parse import parse_qs, quote, unquote, urlsplit

from ..demand.metasettran_demand_generator import resolve_contexts
from . import episode_runner as runner
from .metasettran_selection import group_sections


RESULT_PROFILES = ("outputs-random", "outputs-metasettran")
STYLE = "body { background: white; color: black; font-family: 'Times New Roman', serif; } a { color: black; } pre { font-family: inherit; white-space: pre; overflow: auto; max-height: 75vh; }"


def parse_variations(text, sections):
    """Valida o campo manual sem escolher ou substituir variações."""
    if not text.strip():
        return None
    variations = []
    for value in text.split(","):
        value = value.strip()
        if not re.fullmatch(r"[0-9]+", value):
            raise ValueError("Informe somente números inteiros de 1 a 25 separados por vírgula, sem campos vazios.")
        number = int(value)
        if not 1 <= number <= 25:
            raise ValueError(f"A variação {value} é inválida. Utilize valores entre 1 e 25.")
        variations.append(number)
    if len(variations) != sections:
        raise ValueError(f"Você selecionou {sections} faixa(s), mas informou {len(variations)} variação(ões). "
                         f"Informe exatamente {sections} valores entre 1 e 25.")
    return variations


def form_options(fields):
    """Converte somente os campos permitidos; o runner mantém sua validação final."""
    common = {"signal_profile", "demand_profile", "episodes", "metrics_profile", "gui"}
    random_fields = {"duration", "period", "termination", "end"}
    meta_fields = {"day", "start", "sections", "master_seed", "variations",
                   "selection_mode", "selected_sections", "consecutive_grouping_enabled"}
    if set(fields) - common - random_fields - meta_fields:
        raise ValueError("Campo não permitido no formulário.")

    def choice(name, allowed, default=""):
        value = fields.get(name, default)
        if value not in allowed:
            raise ValueError(f"{name}: escolha uma opção válida.")
        return value

    def integer(name):
        value = fields.get(name, "").strip()
        if not re.fullmatch(r"[0-9]+", value):
            raise ValueError(f"{name}: informe um número inteiro.")
        return int(value)

    def positive(name):
        try:
            value = float(fields.get(name, ""))
        except ValueError:
            raise ValueError(f"{name}: informe um número em segundos.") from None
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name}: informe um número finito maior que zero.")
        return value

    options = {
        "signal_profile": choice("signal_profile", {"current"}),
        "demand_profile": choice("demand_profile", {"random", "metasettran"}),
        "metrics_profile": choice("metrics_profile", {"core", "full"}),
        "episodes": integer("episodes"),
        "gui": choice("gui", {"no", "yes"}, "no") == "yes",
    }
    if options["episodes"] < 1:
        raise ValueError("Quantidade de episódios deve ser maior que zero.")
    if options["demand_profile"] == "random":
        if set(fields) & meta_fields:
            raise ValueError("Configurações MetaSettran não se aplicam a random.")
        options.update(duration=positive("duration"), period=positive("period"))
        termination = choice("termination", {"natural", "defined"})
        if termination == "defined":
            options["end"] = positive("end")
        elif fields.get("end", "").strip():
            raise ValueError("Encerramento natural não aceita instante final.")
    else:
        if set(fields) & random_fields:
            raise ValueError("Duração, intervalo e encerramento random não se aplicam a MetaSettran.")
        mode = choice("selection_mode", {"consecutive", "free"}, "consecutive")
        if mode == "free":
            if set(fields) & {"day", "start", "sections"}:
                raise ValueError("Seleção livre não aceita início e quantidade de faixas do modo consecutivo.")
            raw_sections = fields.get("selected_sections", "").split(",")
            if any(not re.fullmatch(r"[0-9]+", value.strip()) for value in raw_sections):
                raise ValueError("Selecione pelo menos uma faixa válida na grade semanal.")
            selected = [int(value) for value in raw_sections]
            grouping = choice("consecutive_grouping_enabled", {"true", "false"}, "false") == "true"
            groups = group_sections(selected, grouping)
            options.update(selected_sections=selected, consecutive_grouping_enabled=grouping)
            count = len(selected)
        else:
            if set(fields) & {"selected_sections", "consecutive_grouping_enabled"}:
                raise ValueError("Grade semanal e agrupamento se aplicam somente à seleção livre.")
            options.update(day=fields.get("day", ""), start=fields.get("start", ""),
                           sections=integer("sections"))
            groups = [{key: options[key] for key in ("day", "start", "sections")}]
            count = options["sections"]
        master = fields.get("master_seed", "").strip()
        sequence = fields.get("variations", "").strip()
        if master and sequence:
            raise ValueError("Escolha seed mestra OU sequência explícita de variações.")
        if master:
            options["master_seed"] = integer("master_seed")
        variations = parse_variations(sequence, count)
        if variations is not None:
            options["variations"] = variations
        offset = 0
        for group in groups:
            selection = {key: group[key] for key in ("day", "start", "sections")}
            if master:
                selection["master_seed"] = options["master_seed"]
            if variations is not None:
                selection["variations"] = variations[offset:offset + group["sections"]]
            # Zero só valida; não é usado como seed automática de uma execução.
            if not master and not sequence:
                selection["master_seed"] = 0
            resolve_contexts(**selection)
            offset += group["sections"]
    return options


class BatchState:
    def __init__(self):
        self.lock = threading.Lock()
        self.state = {"status": "idle", "results_url": "/results/"}
        self.worker = None

    def snapshot(self):
        with self.lock:
            return dict(self.state)

    def start(self, options):
        with self.lock:
            if self.state["status"] == "running":
                raise RuntimeError("Já existe um lote em execução. Aguarde sua conclusão.")
            self.state = {"status": "running", "results_url":
                          f'/results/outputs-{options["demand_profile"]}/'}
            self.worker = threading.Thread(target=self._run, args=(dict(options),), daemon=False)
            self.worker.start()
            return dict(self.state)

    def _run(self, options):
        try:
            if (options["demand_profile"] == "metasettran"
                    and "master_seed" not in options and "variations" not in options):
                # Mesmo mecanismo do runner; explicitar a seed habilita sorteio
                # também numa faixa, cujo default histórico seria a variação 1.
                options["master_seed"] = secrets.randbits(63)
            batch = runner.run_episodes(**options)
            result = {"status": "completed", "results_url": result_url(batch)}
        except BaseException as exc:
            result = {"status": "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                      "error": f"{type(exc).__name__}: {exc}"}
        with self.lock:
            self.state.update(result)

    def delete_results(self):
        # O mesmo lock serializa a limpeza e o início de um lote.
        with self.lock:
            if self.state["status"] == "running":
                raise RuntimeError("Não é possível apagar resultados durante uma simulação.")
            deleted = delete_outputs()
            self.state = {"status": "idle", "results_url": "/results/"}
            return {"deleted_files": deleted, "message":
                    f"{deleted} arquivo(s) apagado(s). Arquivos versionados e links simbólicos foram preservados."}


def delete_outputs():
    """Remove só outputs não versionados; nunca percorre links simbólicos."""
    roots = [result_path(name) for name in RESULT_PROFILES]
    project = runner.PROJECT_ROOT
    tracked = set()
    try:
        # HEAD também protege arquivos cuja exclusão foi apenas colocada no índice.
        for arguments in (("ls-files", "--cached", "-z"), ("ls-tree", "-r", "--name-only", "-z", "HEAD")):
            data = subprocess.check_output(["git", "-C", str(project), *arguments, "--",
                                            *(str(path.relative_to(project)) for path in roots)],
                                           stderr=subprocess.PIPE)
            tracked.update(project / os.fsdecode(name) for name in data.split(b"\0") if name)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("Não foi possível consultar o Git. Nenhum resultado foi apagado.") from exc

    def protected(path):
        return any(item == path or item in path.parents for item in tracked)

    deleted = 0
    for root in roots:
        root.mkdir(parents=True, exist_ok=True)
        # Descritores e follow_symlinks=False evitam percorrer links, inclusive
        # se uma entrada for trocada enquanto os diretórios são examinados.
        for directory, dirs, files, fd in os.fwalk(root, topdown=False, follow_symlinks=False):
            for name in files:
                if not protected(Path(directory) / name) and stat.S_ISREG(
                        os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode):
                    os.unlink(name, dir_fd=fd)
                    deleted += 1
            for name in dirs:
                if protected(Path(directory) / name) or not stat.S_ISDIR(
                        os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode):
                    continue
                try:
                    os.rmdir(name, dir_fd=fd)
                except OSError as exc:
                    if exc.errno not in {errno.ENOTEMPTY, errno.EEXIST}:
                        raise
    return deleted


def result_url(path):
    return "/results/" + quote(Path(path).relative_to(runner.OUTPUT_ROOT).as_posix(), safe="/")


def result_path(relative):
    """Navega só nas duas árvores previstas, recusando travessia e links simbólicos."""
    parts = relative.rstrip("/").split("/")
    if (parts[0] not in RESULT_PROFILES or any(part in {"", ".", ".."} for part in parts)
            or "\\" in relative or "\x00" in relative):
        raise ValueError("Caminho de resultado não permitido.")
    root = runner.OUTPUT_ROOT
    if root.is_symlink():
        raise ValueError("Links simbólicos não são publicados.")
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("Links simbólicos não são publicados.")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Caminho fora dos resultados.")
    return path


def page(title, contents):
    return (f'<!doctype html><html lang="pt-BR"><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{escape(title)}</title><style>{STYLE}</style>"
            f'<body><p><a href="/" target="_top">Configuração da simulação</a> | '
            f'<a href="/results/">Outputs</a></p><h1>{escape(title)}</h1>'
            f"{contents}</body></html>")


def browse_results(relative, raw=False):
    if not relative:
        return page("Outputs", "<ul>" + "".join(
            f'<li><a href="/results/{name}/">{label}</a></li>'
            for name, label in zip(RESULT_PROFILES, ("Random", "MetaSettran"))) + "</ul>")
    path = result_path(relative)
    if path.is_file():
        if raw:
            return path
        with path.open("rb") as stream:
            if b"\0" in stream.read(8192):
                return path
        try:
            contents = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return path
        note = ""
        if path.suffix.lower() == ".json":
            try:
                contents = json.dumps(json.loads(contents), ensure_ascii=False, indent=2)
            except ValueError:
                note = "<p>JSON inválido ou incompleto; mostrando o texto original.</p>"
        return page(path.name, f'<p><a href="{result_url(path.parent)}">Voltar à pasta</a> | '
                    f'<a href="{result_url(path)}?raw=1">Baixar original</a></p>'
                    + note + "<pre>" + escape(contents) + "</pre>")
    is_profile = path.parent == runner.OUTPUT_ROOT
    if not path.is_dir() and not is_profile:
        raise FileNotFoundError("Resultado não encontrado.")
    parent_url = "/results/" if is_profile else result_url(path.parent)
    contents = f'<p><a href="{parent_url}">Voltar</a></p>'
    children = sorted(path.iterdir(), key=lambda item: item.name, reverse=True) if path.exists() else []
    links = []
    for child in children:
        if child.is_symlink() or not (child.is_dir() or child.is_file()):
            continue
        links.append(f'<li><a href="{result_url(child)}">{escape(child.name)}'
                     f'{"/" if child.is_dir() else ""}</a></li>')
    contents += "<ul>" + "".join(links) + "</ul>" if links else "<p>Nenhum resultado disponível.</p>"
    return page("Outputs — " + path.relative_to(runner.OUTPUT_ROOT).as_posix(), contents)


class Handler(BaseHTTPRequestHandler):
    def local_request(self):
        port = self.server.server_port
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if port == 80:
            allowed.update({"127.0.0.1", "localhost"})
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        return (host in allowed and (origin is None or origin == f"http://{host}")
                and self.headers.get("Sec-Fetch-Site") != "cross-site")

    def headers_for(self, code, content_type, length, download=False):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        if download:
            self.send_header("Content-Disposition", "attachment")
        self.end_headers()

    def reply(self, contents, code=200, content_type="text/html; charset=utf-8"):
        data = contents.encode("utf-8")
        self.headers_for(code, content_type, len(data))
        self.wfile.write(data)

    def json_reply(self, data, code=200):
        self.reply(json.dumps(data, ensure_ascii=False), code, "application/json; charset=utf-8")

    def do_GET(self):
        if not self.local_request():
            self.reply("Acesso permitido somente pela origem local.", 403)
            return
        url = urlsplit(self.path)
        try:
            if url.path == "/":
                self.reply(Path(__file__).with_suffix(".html").read_text(encoding="utf-8"))
            elif url.path == "/status":
                self.json_reply(self.server.batch.snapshot())
            elif url.path.startswith("/results/"):
                result = browse_results(unquote(url.path[len("/results/"):]), raw=url.query == "raw=1")
                if isinstance(result, Path):
                    # Downloads são transmitidos em blocos e nunca executados como HTML.
                    with result.open("rb") as stream:
                        self.headers_for(200, "application/octet-stream", result.stat().st_size, download=True)
                        shutil.copyfileobj(stream, self.wfile)
                else:
                    self.reply(result)
            else:
                self.reply("Página não encontrada.", 404)
        except (OSError, ValueError) as exc:
            self.reply(page("Erro ao ler resultados", f"<p>{escape(str(exc))}</p>"), 404)

    def do_POST(self):
        if not self.local_request():
            self.json_reply({"error": "Origem não permitida."}, 403)
            return
        if self.path not in {"/run", "/delete-results"}:
            self.json_reply({"error": "Página não encontrada."}, 404)
            return
        try:
            if self.headers.get_content_type() != "application/x-www-form-urlencoded":
                raise ValueError("Envie um formulário HTML.")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 16384:
                raise ValueError("Tamanho de formulário inválido.")
            self.connection.settimeout(10)
            fields = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True,
                              max_num_fields=20, errors="strict")
            if any(len(values) != 1 for values in fields.values()):
                raise ValueError("Campos duplicados não são permitidos.")
            fields = {key: values[0] for key, values in fields.items()}
            if self.path == "/delete-results":
                if fields != {"confirmation": "delete"}:
                    raise ValueError("Confirme explicitamente a exclusão permanente dos resultados.")
                self.json_reply(self.server.batch.delete_results())
            else:
                self.json_reply(self.server.batch.start(form_options(fields)), 202)
        except (ValueError, OSError) as exc:
            self.json_reply({"error": str(exc)}, 400)
        except RuntimeError as exc:
            self.json_reply({"error": str(exc)}, 409)

    def log_message(self, format, *args):
        pass  # Polling não precisa preencher o terminal; erros são exibidos na página.


def make_server(port=8000):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.batch = BatchState()
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    with make_server(args.port) as server:
        print(f"Abra http://127.0.0.1:{server.server_port} no navegador.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("Servidor encerrado. Aguardando o lote ativo terminar, se houver.", flush=True)
        finally:
            if server.batch.worker is not None:
                server.batch.worker.join()


if __name__ == "__main__":
    main()
