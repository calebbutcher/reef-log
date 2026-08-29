import html
import logging
import sqlite3
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .parameters import PARAMETERS
from .store import Store

MAX_BODY = 4096

log = logging.getLogger("reeflog")

STYLE = """
:root { color-scheme: light dark; }
body { font-family: system-ui, sans-serif; margin: 0 auto; max-width: 44rem;
       padding: 2rem 1rem; line-height: 1.5; }
h1 { font-size: 1.3rem; margin-bottom: 0.2rem; }
p.sub { margin-top: 0; opacity: 0.7; font-size: 0.9rem; }
form { display: grid; gap: 0.75rem; grid-template-columns: 1fr 1fr;
       align-items: end; margin: 1.5rem 0; }
label { display: grid; gap: 0.25rem; font-size: 0.85rem; }
input, select, button { font: inherit; padding: 0.45rem 0.5rem; }
button { grid-column: 1 / -1; cursor: pointer; }
table { border-collapse: collapse; width: 100%; font-size: 0.9rem; }
th, td { text-align: left; padding: 0.35rem 0.5rem;
         border-bottom: 1px solid rgba(128,128,128,0.3); }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
.note { padding: 0.6rem 0.8rem; border-radius: 4px; margin-bottom: 1rem; }
.ok { background: rgba(60,160,90,0.18); }
.bad { background: rgba(200,70,70,0.18); }
"""


def render(store: Store, message: str = "", error: str = "") -> bytes:
    options = "".join(
        f'<option value="{p.key}">{html.escape(p.name)} ({html.escape(p.basis)})</option>'
        for p in PARAMETERS.values()
    )
    rows = "".join(
        f"<tr><td>{html.escape(PARAMETERS[r.parameter].name)}</td>"
        f'<td class="num">{r.value:g}</td>'
        f"<td>{html.escape(r.basis)}</td>"
        f"<td>{_stamp(r.measured_at)}</td></tr>"
        for r in store.recent()
    )
    banner = ""
    if message:
        banner = f'<p class="note ok">{html.escape(message)}</p>'
    elif error:
        banner = f'<p class="note bad">{html.escape(error)}</p>'

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>reef-log</title><style>{STYLE}</style></head><body>
<h1>reef-log</h1>
<p class="sub">Hand-entered tank readings. Published to Prometheus under the same
metric names the HYDROS exporter would use.</p>
{banner}
<form method="post" action="/">
  <label>Parameter<select name="parameter">{options}</select></label>
  <label>Value<input name="value" type="number" step="any" min="0" required
    autofocus></label>
  <label>Measured at<input name="measured_at" type="datetime-local"
    value="{_local_now()}"></label>
  <button type="submit">Record reading</button>
</form>
<table><thead><tr><th>Parameter</th><th class="num">Value</th><th>Basis</th>
<th>Measured</th></tr></thead><tbody>{rows or
  '<tr><td colspan="4">No readings yet.</td></tr>'}</tbody></table>
</body></html>
""".encode()


def _stamp(epoch: int) -> str:
    return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M")


def _local_now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M")


def parse_measured_at(raw: str) -> int | None:
    """The form posts naive local time, so the container's TZ decides the offset."""
    raw = (raw or "").strip()
    if not raw:
        return None
    return int(datetime.fromisoformat(raw).timestamp())


def build_handler(store: Store, registry):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _send(self, code, body, content_type):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _html(self, code=200, message="", error=""):
            self._send(code, render(store, message, error), "text/html; charset=utf-8")

        def do_GET(self):
            path = self.path.split("?", 1)[0].rstrip("/") or "/"
            if path == "/metrics":
                self._send(200, generate_latest(registry), CONTENT_TYPE_LATEST)
            elif path == "/healthz":
                ok = store.healthy()
                self._send(200 if ok else 503, b"ok\n" if ok else b"unhealthy\n",
                           "text/plain; charset=utf-8")
            elif path == "/":
                self._html()
            else:
                self._send(404, b"not found\n", "text/plain; charset=utf-8")

        def do_POST(self):
            if self.path.split("?", 1)[0].rstrip("/") not in ("", "/"):
                self._send(404, b"not found\n", "text/plain; charset=utf-8")
                return
            if not self._same_origin():
                self._send(403, b"cross-origin post rejected\n",
                           "text/plain; charset=utf-8")
                return

            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                self._send(413, b"too large\n", "text/plain; charset=utf-8")
                return
            form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8", "replace"))

            try:
                key = (form.get("parameter") or [""])[0]
                value = float((form.get("value") or [""])[0])
                measured_at = parse_measured_at((form.get("measured_at") or [""])[0])
                reading = store.add(key, value, measured_at)
            except (ValueError, KeyError) as exc:
                self._html(400, error=str(exc) or "could not read that entry")
                return
            except sqlite3.Error as exc:
                # Letting this escape drops the connection mid-request, which
                # the ingress reports as a bad gateway rather than an error.
                log.exception("write failed")
                self._send(500, f"could not save that reading: {exc}\n".encode(),
                           "text/plain; charset=utf-8")
                return
            parameter = PARAMETERS[reading.parameter]
            self._html(200, message=f"Recorded {parameter.name} {reading.value:g} "
                                    f"{parameter.basis}.")

        def _same_origin(self) -> bool:
            """
            The ingress sits behind Authentik, whose session cookie would
            otherwise ride along on a cross-site POST.
            """
            host = self.headers.get("Host", "")
            origin = self.headers.get("Origin")
            if origin:
                return urllib.parse.urlsplit(origin).netloc == host
            referer = self.headers.get("Referer")
            if referer:
                return urllib.parse.urlsplit(referer).netloc == host
            return True

        def log_message(self, *args):
            pass

    return Handler
