"""Interface HTTP local sobre run_episodes.

Uso: python3 -B -m SistemaDeSemaforos.simulation.web_interface
O único lote ativo fica numa thread; os resultados continuam pertencendo ao runner.
"""

import argparse
import codecs
from contextlib import contextmanager
import errno
import gzip
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import threading
from urllib.parse import parse_qs, quote, unquote, urlsplit
import zlib

from . import episode_runner as runner


RESULT_PROFILES = ("outputs-random", "outputs-metasettran")
STYLE = "body { background: white; color: black; font-family: 'Times New Roman', serif; } a { color: black; } pre { font-family: inherit; white-space: pre; overflow: auto; max-height: 75vh; }"
PREVIEW_LIMIT = 16 * 1024 * 1024
STREAM_LIMIT = 1024 * 1024
READ_SIZE = 64 * 1024


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
        "signal_profile": choice("signal_profile", {"current", "gpt"}),
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
            options.update(selected_sections=selected, consecutive_grouping_enabled=grouping)
            count = len(selected)
        else:
            if set(fields) & {"selected_sections", "consecutive_grouping_enabled"}:
                raise ValueError("Grade semanal e agrupamento se aplicam somente à seleção livre.")
            options.update(day=fields.get("day", ""), start=fields.get("start", ""),
                           sections=integer("sections"))
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
        runner.prepare_metasettran_plans(**{key: options[key] for key in meta_fields if key in options})
    return options


class BatchState:
    def __init__(self):
        self.lock = threading.Lock()
        self.state = {"status": "idle", "results_url": "/results/"}
        self.worker = None
        self.stopping = False

    def snapshot(self):
        with self.lock:
            return dict(self.state)

    def start(self, options):
        with self.lock:
            if self.stopping:
                raise RuntimeError("A interface está encerrando; não aceita novos lotes.")
            if self.state["status"] == "running":
                raise RuntimeError("Já existe um lote em execução. Aguarde sua conclusão.")
            self.state = {"status": "running", "results_url":
                          f'/results/outputs-{options["demand_profile"]}/'}
            # O lote não depende da aba do navegador; a thread não daemon permite
            # que o encerramento aguarde a publicação dos resultados.
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
        # O mesmo lock serializa a limpeza e o início de um lote. Ele permanece
        # adquirido até a exclusão terminar, incluindo a chamada Python isolada.
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
    project_stat = project.stat()
    tracked = set()
    try:
        # HEAD também protege arquivos cuja exclusão foi apenas colocada no índice.
        for arguments in (("ls-files", "--cached", "-z"), ("ls-tree", "-r", "--name-only", "-z", "HEAD")):
            data = subprocess.check_output(["git", "-C", str(project), *arguments, "--",
                                            *(path.relative_to(project).as_posix() for path in roots)],
                                           stderr=subprocess.PIPE)
            tracked.update(project / os.fsdecode(name) for name in data.split(b"\0") if name)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("Não foi possível consultar o Git. Nenhum resultado foi apagado.") from exc

    # CWD ancora operações por nome nos dois sistemas. Como ele é compartilhado
    # pelas threads, só o processo curto de exclusão pode mudá-lo; o servidor não muda.
    command = [sys.executable, "-B", "-c",
               "import json, sys; "
               "from SistemaDeSemaforos.simulation.web_interface import _delete_output_tree; "
               "print(json.dumps(_delete_output_tree(json.load(sys.stdin))))"]
    payload = {"project": str(project), "identity": [project_stat.st_dev, project_stat.st_ino],
               "output_parts": list(runner.OUTPUT_ROOT.relative_to(project).parts),
               "tracked": [str(path.relative_to(project)) for path in tracked]}
    result = subprocess.run(command, input=json.dumps(payload), capture_output=True,
                            text=True, encoding="utf-8", cwd=Path(__file__).resolve().parents[2])
    if result.returncode:
        raise ValueError("Não foi possível concluir a exclusão dos resultados.")
    result = json.loads(result.stdout)
    if "error" in result:
        if result["errno"] is not None:
            raise OSError(result["errno"], result["strerror"], result["filename"])
        raise ValueError(result["error"])
    return result["deleted_files"]


def _delete_output_tree(payload):
    """Rotina comum de exclusão; chamada somente num processo com CWD próprio."""
    tracked = {Path(name) for name in payload["tracked"]}

    def protected(path):
        return any(item == path or item in path.parents for item in tracked)

    def linked(info):
        # Junctions do Windows também redirecionam diretórios, sem serem symlinks.
        return (stat.S_ISLNK(info.st_mode)
                or bool(getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT))

    def enter(name, info):
        if linked(info) or not stat.S_ISDIR(info.st_mode) or not info.st_ino:
            raise ValueError("Diretório de resultados não pode ser acessado com segurança.")
        try:
            os.chdir(name)
        except OSError:
            # fwalk não percorria diretórios que não conseguia abrir para leitura.
            # Manter esse caso preserva seus arquivos e permite limpar os demais.
            try:
                os.listdir(name)
            except OSError:
                return False
            raise
        # Se trocaram o diretório por um link entre lstat e chdir, não apagar nada nele.
        if not os.path.samestat(info, os.stat(".")):
            raise ValueError("Diretório de resultados foi substituído durante a exclusão.")
        return True

    def walk(directory):
        deleted = 0
        dirs, files = [], []
        try:
            names = os.listdir(".")
        except OSError:
            return 0  # Mesmo tratamento de falhas de leitura do fwalk anterior.
        for name in names:
            info = os.lstat(name)
            if not linked(info):
                (dirs if stat.S_ISDIR(info.st_mode) else files).append(name)
        for name in dirs:
            info = os.lstat(name)
            if linked(info) or not stat.S_ISDIR(info.st_mode):
                continue
            parent = os.stat(".")
            if not enter(name, info):
                continue
            deleted += walk(directory / name)
            os.chdir("..")
            if not os.path.samestat(parent, os.stat(".")):
                raise ValueError("Diretório pai foi substituído durante a exclusão.")
        # Manter a ordem de baixo para cima e remover somente entradas regulares.
        # Nomes sem separadores ficam ancorados no CWD, mesmo se um ancestral mudar.
        for name in files:
            info = os.lstat(name)
            if not protected(directory / name) and not linked(info) and stat.S_ISREG(info.st_mode):
                os.unlink(name)
                deleted += 1
        for name in dirs:
            info = os.lstat(name)
            if protected(directory / name) or linked(info) or not stat.S_ISDIR(info.st_mode):
                continue
            try:
                os.rmdir(name)
            except OSError as exc:
                if exc.errno not in {errno.ENOTEMPTY, errno.EEXIST}:
                    raise
        return deleted

    try:
        os.chdir(payload["project"])
        info = os.stat(".")
        if [info.st_dev, info.st_ino] != payload["identity"] or not info.st_ino:
            raise ValueError("Diretório do projeto foi substituído durante a exclusão.")
        parts = payload["output_parts"]
        for name in parts:
            try:
                os.mkdir(name)
            except FileExistsError:
                pass
            if not enter(name, os.lstat(name)):
                return {"deleted_files": 0}
        deleted = 0
        for name in RESULT_PROFILES:
            try:
                os.mkdir(name)
            except FileExistsError:
                pass
            parent = os.stat(".")
            if not enter(name, os.lstat(name)):
                continue
            deleted += walk(Path(*parts) / name)
            os.chdir("..")
            if not os.path.samestat(parent, os.stat(".")):
                raise ValueError("Diretório de outputs foi substituído durante a exclusão.")
        return {"deleted_files": deleted}
    except (OSError, ValueError) as exc:
        # Falhas de permissão/bloqueio interrompem a operação, sem forçar chmod,
        # seguir links ou tentar excluir dados de outro perfil para compensar.
        return {"error": str(exc), "errno": getattr(exc, "errno", None),
                "strerror": getattr(exc, "strerror", None), "filename": getattr(exc, "filename", None)}


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


def format_json(chunks):
    """Formata em fluxo, preservando as letras dos números e das strings."""
    depth = 0
    quoted = escaped = False
    for chunk in chunks:
        result = []
        for char in chunk:
            if quoted:
                result.append(char)
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
                result.append(char)
            elif char in "[{":
                depth += 1
                result.extend((char, "\n", " " * min(depth * 2, 128)))
            elif char in "]}":
                depth = max(depth - 1, 0)
                result.extend(("\n", " " * min(depth * 2, 128), char))
            elif char == ",":
                result.extend((char, "\n", " " * min(depth * 2, 128)))
            elif char == ":":
                result.append(": ")
            elif char not in " \t\r\n":
                result.append(char)
        yield "".join(result)


def gzip_size(raw, *, text=False):
    """Confere o GZIP até o fim antes de enviar cabeçalhos ou conteúdo."""
    size = 0
    decoder = codecs.getincrementaldecoder("utf-8")() if text else None
    with gzip.GzipFile(fileobj=raw, mode="rb") as stream:
        for chunk in iter(lambda: stream.read(READ_SIZE), b""):
            size += len(chunk)
            if decoder is not None:
                decoder.decode(chunk)
    if decoder is not None:
        decoder.decode(b"", final=True)
    raw.seek(0)
    return size


def browse_results(relative, raw=False):
    if not relative:
        return page("Outputs", "<ul>" + "".join(
            f'<li><a href="/results/{name}/">{label}</a></li>'
            for name, label in zip(RESULT_PROFILES, ("Random", "MetaSettran"))) + "</ul>")
    path = result_path(relative)
    if path.is_file():
        if raw:
            return path
        if path.name.lower().endswith((".json.gz", ".xml.gz", ".log.gz", ".txt.gz")):
            return ("preview", path)
        with path.open("rb") as stream:
            if b"\0" in stream.read(8192):
                return path
        if path.stat().st_size > STREAM_LIMIT:
            return ("preview", path)
        try:
            contents = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return path
        note = ""
        if path.suffix.lower() == ".json":
            try:
                json.loads(contents)
                contents = "".join(format_json([contents]))
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
    def handle(self):
        try:
            super().handle()
        except ConnectionError:
            # Trocar de página ou cancelar um download fecha a conexão do
            # navegador. Não tentar enviar uma página de erro por esse socket.
            self.close_connection = True

    def local_request(self):
        port = self.server.server_port
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if port == 80:
            allowed.update({"127.0.0.1", "localhost"})
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        return (host in allowed and (origin is None or origin == f"http://{host}")
                and self.headers.get("Sec-Fetch-Site") != "cross-site")

    def headers_for(self, code, content_type, length, download=False, filename=None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        if length is not None:
            self.send_header("Content-Length", str(length))
        else:
            self.send_header("Connection", "close")
            self.close_connection = True
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        if download:
            disposition = "attachment"
            if filename is not None:
                disposition += "; filename*=UTF-8''" + quote(filename, safe="")
            self.send_header("Content-Disposition", disposition)
        self.end_headers()

    def reply(self, contents, code=200, content_type="text/html; charset=utf-8"):
        data = contents.encode("utf-8")
        self.headers_for(code, content_type, len(data))
        self.wfile.write(data)

    def json_reply(self, data, code=200):
        self.reply(json.dumps(data, ensure_ascii=False), code, "application/json; charset=utf-8")

    def stream_result(self, path, *, unpacked=False, show_large=False):
        compressed = path.suffix.lower() == ".gz"
        # A validação e a transmissão usam o mesmo arquivo aberto: uma nova
        # publicação atômica de metrics.json.gz não troca o conteúdo no meio.
        with path.open("rb") as raw:
            size = gzip_size(raw, text=not unpacked) if compressed else os.fstat(raw.fileno()).st_size
            if unpacked:
                self.headers_for(200, "application/octet-stream", size, download=True,
                                 filename=path.with_suffix("").name)
                try:
                    with gzip.GzipFile(fileobj=raw, mode="rb") as stream:
                        shutil.copyfileobj(stream, self.wfile, READ_SIZE)
                except (OSError, EOFError, zlib.error):
                    self.close_connection = True
                return
            url = result_url(path)
            links = (f'<p><a href="{result_url(path.parent)}">Voltar à pasta</a> | '
                     f'<a href="{url}?raw=1">Baixar original</a>')
            if compressed:
                links += f' | <a href="{url}?unpacked=1">Baixar descomprimido</a>'
            links += "</p>"
            if size > PREVIEW_LIMIT and not show_large:
                self.reply(page(path.name, links + f"<p>O conteúdo tem {size} bytes. "
                                f'<a href="{url}?view=1">Abrir o conteúdo completo</a> '
                                "pode exigir muita memória no navegador.</p>"))
                return
            opening = page(path.name, links + "<pre>")
            self.headers_for(200, "text/html; charset=utf-8", None)
            self.wfile.write(opening.removesuffix("</body></html>").encode("utf-8"))
            try:
                binary = gzip.GzipFile(fileobj=raw, mode="rb") if compressed else raw
                with io.TextIOWrapper(binary, encoding="utf-8", newline="") as stream:
                    chunks = iter(lambda: stream.read(READ_SIZE), "")
                    if path.name.lower().endswith((".json", ".json.gz")):
                        chunks = format_json(chunks)
                    for chunk in chunks:
                        self.wfile.write(escape(chunk).encode("utf-8"))
            except ConnectionError:
                raise
            except (OSError, EOFError, UnicodeError, zlib.error) as exc:
                self.wfile.write(("</pre><p>Falha ao ler o conteúdo completo: " +
                                  escape(str(exc)) + "</p></body></html>").encode("utf-8"))
                return
            self.wfile.write(b"</pre></body></html>")

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
                query = parse_qs(url.query)
                result = browse_results(unquote(url.path[len("/results/"):]), raw=query.get("raw") == ["1"])
                if query.get("unpacked") == ["1"]:
                    path = result[1] if isinstance(result, tuple) else result
                    if not isinstance(path, Path) or path.suffix.lower() != ".gz":
                        raise ValueError("O arquivo solicitado não é GZIP.")
                    self.stream_result(path, unpacked=True)
                elif isinstance(result, tuple):
                    self.stream_result(result[1], show_large=query.get("view") == ["1"])
                elif isinstance(result, Path):
                    # Downloads são transmitidos em blocos e nunca executados como HTML.
                    with result.open("rb") as stream:
                        self.headers_for(200, "application/octet-stream", os.fstat(stream.fileno()).st_size,
                                         download=True)
                        try:
                            shutil.copyfileobj(stream, self.wfile)
                        except OSError:
                            self.close_connection = True
                else:
                    self.reply(result)
            else:
                self.reply("Página não encontrada.", 404)
        except ConnectionError:
            raise
        except (OSError, ValueError, EOFError, UnicodeError, zlib.error) as exc:
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
                # A confirmação é o único campo aceito: o navegador não escolhe
                # pastas, perfis ou arquivos para a exclusão.
                if fields != {"confirmation": "delete"}:
                    raise ValueError("Confirme explicitamente a exclusão permanente dos resultados.")
                self.json_reply(self.server.batch.delete_results())
            else:
                self.json_reply(self.server.batch.start(form_options(fields)), 202)
        except ConnectionError:
            raise
        except (ValueError, OSError) as exc:
            self.json_reply({"error": str(exc)}, 400)
        except RuntimeError as exc:
            self.json_reply({"error": str(exc)}, 409)

    def log_message(self, format, *args):
        pass  # Polling não precisa preencher o terminal; erros são exibidos na página.


class InterfaceServer(ThreadingHTTPServer):
    # No Windows, SO_REUSEADDR pode compartilhar a porta de outro servidor.
    allow_reuse_address = os.name != "nt"


def make_server(port=8000):
    server = InterfaceServer(("127.0.0.1", port), Handler)
    server.batch = BatchState()
    return server


@contextmanager
def instance_lock(runtime):
    """Lock do sistema, liberado ao fechar o arquivo, inclusive após falha do processo."""
    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    # O arquivo permanece: apagá-lo permitiria locks em arquivos diferentes.
    with (runtime / "interface.lock").open("a+b") as lock:
        lock.seek(0, os.SEEK_END)
        if lock.tell() == 0:
            lock.write(b"\0")
            lock.flush()
        lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                raise
            acquired = False
        else:
            acquired = True
        yield acquired


def stop_interface(runtime):
    """Pede ao próprio servidor para parar; não usa PID, porta nem sinais."""
    with instance_lock(runtime) as acquired:
        if acquired:
            (runtime / "interface.json").unlink(missing_ok=True)
            (runtime / "interface.stop").unlink(missing_ok=True)
            print("Nenhuma interface em execução nesta cópia do projeto.", flush=True)
            return
        try:
            info = json.loads((runtime / "interface.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError("Interface iniciando ou controle indisponível. Tente novamente.") from exc
        instance = info.get("instance") if isinstance(info, dict) else None
        if not isinstance(instance, str) or not re.fullmatch(r"[0-9a-f]{32}", instance):
            raise ValueError("Controle de instância inválido; nenhum processo foi encerrado.")
        # O pedido leva a identidade atual; um arquivo de parada antigo não
        # deve encerrar uma instância iniciada depois dele.
        (runtime / "interface.stop").write_text(instance, encoding="utf-8")
        print("Encerramento solicitado. A interface aguarda o lote ativo terminar; "
              "mantenha o terminal do servidor aberto.", flush=True)


def serve_interface(port, runtime):
    # Manter o lock até o join impede iniciar outra instância enquanto o lote
    # anterior ainda grava resultados, mesmo com a porta web já liberada.
    with instance_lock(runtime) as acquired:
        if not acquired:
            raise ValueError("Já existe uma interface ativa nesta cópia do projeto, "
                             "possivelmente aguardando um lote terminar.")
        info_path = runtime / "interface.json"
        stop_path = runtime / "interface.stop"
        info_path.unlink(missing_ok=True)
        stop_path.unlink(missing_ok=True)
        try:
            with make_server(port) as server:
                instance = secrets.token_hex(16)
                info_path.write_text(json.dumps({"instance": instance, "port": server.server_port}),
                                     encoding="utf-8")
                server.timeout = 0.2
                print(f"Abra http://127.0.0.1:{server.server_port} no navegador.", flush=True)
                try:
                    while True:
                        try:
                            if stop_path.read_text(encoding="utf-8") == instance:
                                break
                        except (FileNotFoundError, UnicodeError):
                            pass
                        server.handle_request()
                except KeyboardInterrupt:
                    pass
                finally:
                    # Um segundo Ctrl+C não deve interromper a publicação dos resultados.
                    previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
                    try:
                        with server.batch.lock:
                            server.batch.stopping = True
                            worker = server.batch.worker
                        server.server_close()
                        print("Servidor encerrado. Aguardando o lote ativo terminar, se houver.", flush=True)
                        if worker is not None:
                            worker.join()
                    finally:
                        signal.signal(signal.SIGINT, previous)
        finally:
            info_path.unlink(missing_ok=True)
            stop_path.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--stop", action="store_true", help="Encerra somente a interface desta cópia do EDI.")
    args = parser.parse_args(argv)
    runtime = runner.PROJECT_ROOT / ".runtime"
    try:
        if args.stop:
            stop_interface(runtime)
        else:
            serve_interface(args.port, runtime)
    except (OSError, ValueError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
