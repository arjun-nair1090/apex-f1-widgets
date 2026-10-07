"""Plumbing shared by the app and the desktop host: a WebKit view that speaks the WebView2 message protocol the pages
already use, a crash log, and launching the other process."""
import json
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from gi.repository import Gdk, GLib, WebKit2

from .config import data_dir

# The pages talk to their host through window.chrome.webview (WebView2). Provide the same API on WebKit, so
# app.html and desktop.html run unchanged: postMessage → script message handler "apex", host → page via
# window.__apexDispatch, delivered to "message" listeners as {data}.
BRIDGE = """(() => {
  const listeners = [];
  window.chrome = window.chrome || {};
  window.chrome.webview = {
    apexHost: "linux",
    postMessage: m => window.webkit.messageHandlers.apex.postMessage(JSON.stringify(m)),
    addEventListener: (type, fn) => { if (type === "message") listeners.push(fn); },
  };
  window.__apexDispatch = data => listeners.forEach(fn => fn({ data }));
})();"""


def log_error(text: str) -> None:
    """crash.log next to the settings files, like %LOCALAPPDATA%\\APEX\\crash.log on Windows."""
    data_dir().mkdir(parents=True, exist_ok=True)
    with open(data_dir() / "crash.log", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%SZ} {text}\n")


def spawn(*args: str) -> None:
    """Start `python -m apexlinux <args>` detached (GLib reaps it, so no zombies under a long-running host)."""
    package_root = str(Path(__file__).resolve().parent.parent)
    GLib.spawn_async([sys.executable, "-m", "apexlinux", *args], working_directory=package_root)


class HostedPage:
    """A WebKit view showing one page from the data server. Retries while the server is still starting (logon)."""

    def __init__(self, on_message: Callable[[object], None], background: str, retry_seconds: int,
                 waiting_html: str | None = None) -> None:
        self.on_message = on_message
        self.retry_seconds = retry_seconds
        self.waiting_html = waiting_html
        self.url: str | None = None
        self.retry = 0

        content = WebKit2.UserContentManager()
        content.add_script(WebKit2.UserScript(BRIDGE, WebKit2.UserContentInjectedFrames.TOP_FRAME,
                                              WebKit2.UserScriptInjectionTime.START, None, None))
        content.connect("script-message-received::apex", self._received)
        content.register_script_message_handler("apex")
        self.view = WebKit2.WebView.new_with_user_content_manager(content)
        self.view.get_settings().set_enable_developer_extras(False)
        color = Gdk.RGBA()
        color.parse(background)
        self.view.set_background_color(color)  # no white flash at the edges or while loading
        self.view.connect("context-menu", lambda *_: True)  # the pages draw their own menus
        self.view.connect("load-failed", self._load_failed)

    def load(self, url: str) -> None:
        self.url = url
        if self.retry:
            GLib.source_remove(self.retry)
            self.retry = 0
        self.view.load_uri(url)

    def send(self, value: object) -> None:
        self.view.evaluate_javascript(f"window.__apexDispatch({json.dumps(value)})", -1, None, None, None, None, None)

    def _received(self, _content: WebKit2.UserContentManager, result: WebKit2.JavascriptResult) -> None:
        try:
            message = json.loads(result.get_js_value().to_string())
        except json.JSONDecodeError:
            return  # not from our bridge
        self.on_message(message)

    def _load_failed(self, _view: WebKit2.WebView, _event: WebKit2.LoadEvent, _uri: str, error: GLib.Error) -> bool:
        if error.matches(WebKit2.network_error_quark(), WebKit2.NetworkError.CANCELLED):
            return False  # replaced by a newer navigation
        if self.waiting_html:
            self.view.load_html(self.waiting_html, None)
        if not self.retry and self.url:
            self.retry = GLib.timeout_add_seconds(self.retry_seconds, self._retry)
        return True

    def _retry(self) -> bool:
        self.retry = 0
        if self.url:
            self.load(self.url)
        return False
