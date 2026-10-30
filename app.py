"""
app.py - local web interface for the incremental compiler front end.
Put this file and index.html in the project folder (next to compiler_cli.py), then run:   python app.py
No packages needed (standard library only).
"""
import os, sys, json, subprocess, traceback, webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.setrecursionlimit(20000)
HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)

from lexer import LexError
from parser import ParseError
from pipeline import compile_source
from incremental import IncrementalSession
from incremental_parser import count_nodes
from diff_tool import compute_edit_span
from errors import describe_exception, describe_diagnostic, line_col

S = {"sess": None, "hist": []}          # one live session (this is a single-user demo tool)


def node_json(n, rebuilt, prefix=""):
    return {"label": n.label(), "start": n.start, "end": n.end, "prefix": prefix,
            "new": rebuilt is not None and id(n) in rebuilt,
            "kids": [node_json(c, rebuilt, p) for p, c in n.children()]}


def dirty_span(old, new):
    """Same whole-line growth the incremental lexer uses, so the UI can highlight re-lexed tokens."""
    es, oe, ne = compute_edit_span(old, new)
    ds = new.rfind("\n", 0, es) + 1
    nl = new.find("\n", ne)
    return [ds, len(new) if nl == -1 else nl]


def state(sess, stats=None, dirty=None, edit=False):
    return {"ok": True, "src": sess.src, "stats": stats, "dirty": dirty,
            "can_undo": bool(S["hist"]), "nodes": count_nodes(sess.ast),
            "tokens": [{"type": t.type, "value": t.value, "start": t.start, "end": t.end, "line": t.line}
                       for t in sess.tokens],
            "ast": node_json(sess.ast, sess.last_rebuilt if edit else None),
            "diags": [{"msg": d.message, "line": line_col(sess.src, d.node.start)[0],
                       "block": describe_diagnostic(d, sess.src)} for d in sess.diagnostics()]}


def rejected(kind, block, msg):
    return {"ok": False, "kind": kind, "block": block, "msg": msg}


def do_compile(src):
    res = compile_source(src)
    if res.status in ("lexical", "syntax"):
        return rejected(res.status, res.blocks[0], f"{res.status} error: nothing was cached")
    S["sess"], S["hist"] = IncrementalSession(src), []
    return state(S["sess"])


def do_edit(new):
    sess = S["sess"]
    if sess is None:
        return rejected("state", "", "Compile the source first, so there is a cached version to update.")
    prev = sess.src
    if new == prev:
        return dict(state(sess), stats={"noop": True})
    dirty = dirty_span(prev, new)
    try:
        st = sess.update(new)
    except LexError as e:                                   # nothing was changed
        return rejected("lexical", describe_exception(e, new)[1], "Edit rejected (lexical error). Previous version kept.")
    except ParseError as e:
        block = describe_exception(e, new)[1]
        sess.update(prev)                                   # revert, same as the CLI repl
        return rejected("syntax", block, "Edit rejected (syntax error). Reverted to the previous version.")
    S["hist"].append(prev)
    return state(sess, st, dirty, edit=True)


def do_undo():
    sess = S["sess"]
    if sess is None or not S["hist"]:
        return rejected("state", "", "Nothing to undo.")
    cur, prev = sess.src, S["hist"].pop()
    st = sess.update(prev)
    return state(sess, st, dirty_span(cur, prev), edit=True)


def read_text(name):
    p = os.path.join(HERE, name)
    return open(p, encoding="utf-8", errors="replace").read() if os.path.isfile(p) else ""


def do_run(what):
    if what not in ("tests", "bench"):
        return {"ok": False, "msg": "unknown job"}
    env = dict(os.environ, PYTHONIOENCODING="utf-8", MPLBACKEND="Agg")
    r = subprocess.run([sys.executable, "compiler_cli.py", what], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env, timeout=900)
    return {"ok": True, "code": r.returncode, "out": r.stdout + r.stderr}


def results():
    return {"tests": read_text("test_results.txt"),
            "csv": {n: read_text(n + ".csv") for n in ("benchmark_scaling", "benchmark_edit_types", "benchmark_memory")},
            "images": [n for n in ("benchmark_scaling.png", "benchmark_edit_types.png") if os.path.isfile(n)]}


class H(BaseHTTPRequestHandler):
    def send(self, body, ctype="application/json", code=200):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode("utf-8") if ctype == "application/json" else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path == "/":
                self.send(read_text("index.html"), "text/html; charset=utf-8")
            elif u.path == "/api/samples":
                names = sorted(os.listdir("samples")) if os.path.isdir("samples") else []
                self.send([n for n in names if os.path.isfile(os.path.join("samples", n))])
            elif u.path == "/api/sample":
                name = os.path.basename(q.get("name", [""])[0])
                self.send({"src": read_text(os.path.join("samples", name))})
            elif u.path == "/api/results":
                self.send(results())
            elif u.path.startswith("/img/"):
                name = os.path.basename(u.path)
                if name.startswith("benchmark_") and name.endswith(".png") and os.path.isfile(name):
                    self.send(open(name, "rb").read(), "image/png")
                else:
                    self.send({"ok": False}, code=404)
            else:
                self.send({"ok": False}, code=404)
        except Exception:
            self.send({"ok": False, "msg": traceback.format_exc()}, code=500)

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(n) or b"{}")
            p = urlparse(self.path).path
            if p == "/api/compile":
                self.send(do_compile(data.get("src", "")))
            elif p == "/api/edit":
                self.send(do_edit(data.get("src", "")))
            elif p == "/api/undo":
                self.send(do_undo())
            elif p == "/api/run":
                self.send(do_run(data.get("what", "")))
            else:
                self.send({"ok": False}, code=404)
        except Exception:
            self.send({"ok": False, "kind": "internal", "block": traceback.format_exc(), "msg": "Internal error"}, code=500)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = 8000
    print(f"Incremental compiler UI running at http://127.0.0.1:{port}   (Ctrl+C to stop)")
    try:
        webbrowser.open(f"http://127.0.0.1:{port}")
    except Exception:
        pass
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
