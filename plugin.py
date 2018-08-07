import os
import shutil
import sublime_plugin
import sublime
from LSP.plugin.core.handlers import LanguageHandler
from LSP.plugin.core.settings import ClientConfig, LanguageConfig
from LSP.plugin.core.protocol import Request, Point
from LSP.plugin.references import ensure_references_panel
from LSP.plugin.core.registry import session_for_view
from LSP.plugin.core.documents import is_at_word, get_position, get_document_position
from LSP.plugin.core.workspace import get_project_path
from LSP.plugin.core.url import uri_to_filename


config_name = 'rls'
server_name = 'rls'
rls_config = ClientConfig(
    name=config_name,
    binary_args=[
        "rustup", "run", "nightly", "rls"
    ],
    tcp_port=None,
    languages=[
        LanguageConfig("rust", ["source.rust"], ["Rust"])
    ],
    enabled=False,
    init_options=dict(),
    settings=dict(),
    env=dict())


def rustup_is_installed() -> bool:
    return shutil.which("rustup") is not None


class LspRlsPlugin(LanguageHandler):
    def __init__(self):
        self._name = config_name
        self._config = rls_config

    @property
    def name(self) -> str:
        return self._name

    @property
    def config(self) -> ClientConfig:
        return self._config

    def on_start(self, window) -> bool:
        if not rustup_is_installed():
            window.status_message(
                "Rustup must be installed to run {}".format(server_name))
            return False
        return True

    def on_initialized(self, client) -> None:
        register_client(client)


class LspRustImplementationsCommand(sublime_plugin.TextCommand):
    def is_enabled(self, event=None):
        session = session_for_view(self.view)
        if session and session.has_capability('implementationProvider'):
            return is_at_word(self.view, event)
        return False

    def run(self, edit, event=None):
        session = session_for_view(self.view)
        if session and session.client:
            pos = get_position(self.view, event)
            document_position = get_document_position(self.view, pos)
            if document_position:
                request = RustRequest.implementations(document_position)
                session.client.send_request(
                    request, lambda response: self.handle_response(response, pos))

    def handle_response(self, response, pos):
        window = self.view.window()
        word = self.view.substr(self.view.word(pos))
        base_dir = get_project_path(window)
        file_path = self.view.file_name()
        relative_file_path = os.path.relpath(file_path, base_dir) if base_dir else file_path

        implementations = list(format_reference(item, base_dir) for item in response)

        if (len(implementations)) > 0:
            panel = ensure_references_panel(window)
            panel.settings().set("result_base_dir", base_dir)
            panel.set_read_only(False)
            panel.run_command("lsp_clear_panel")
            panel.run_command('append', {
                'characters': 'Implementations of "' + word + '" at ' + relative_file_path + ':\n'
            })
            window.run_command("show_panel", {"panel": "output.references"})
            for implementation in implementations:
                panel.run_command('append', {
                    'characters': implementation + "\n",
                    'force': True,
                    'scroll_to_end': True
                })
            panel.set_read_only(True)

        else:
            window.run_command("hide_panel", {"panel": "output.references"})
            window.status_message("No implementations found")

    def want_event(self):
        return True


def format_reference(reference, base_dir):
    start = Point.from_lsp(reference.get('range').get('start'))
    file_path = uri_to_filename(reference.get("uri"))
    relative_file_path = os.path.relpath(file_path, base_dir)
    return " ◌ {} {}:{}".format(relative_file_path, start.row + 1, start.col + 1)


class RustRequest(Request):

    def implementations(params) -> Request:
        return Request("rustDocument/implementations", params)


def register_client(client):
    print("received client")
    client.on_notification(
        "rustDocument/beginBuild",
        lambda params: on_begin_build(params))
    client.on_notification(
        "rustDocument/diagnosticsBegin",
        lambda params: on_begin_build(params))
    client.on_notification(
        "rustDocument/diagnosticsEnd",
        lambda params: on_begin_build(params))


def on_begin_build(params):
    print("rustDocument/beginBuild")
    sublime.status_message("Rust build started...")


def on_diagnostics_begin(params):
    print("rustDocument/diagnosticsBegin")
    sublime.status_message("Rust diagnostics started...")


def on_diagnostics_end(params):
    print("rustDocument/diagnosticsEnd")
    sublime.status_message("Rust diagnostics done.")
