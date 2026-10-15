"""
compiler_cli.py  -  ONE entry point for the whole integrated system.

  python compiler_cli.py check  FILE [--tokens] [--ast]     full pipeline: lex -> parse -> semantic
  python compiler_cli.py diff   OLD NEW                      incremental update OLD -> NEW with reuse statistics
  python compiler_cli.py repl   FILE                         interactive "live editor" (edits are applied incrementally)
  python compiler_cli.py tests                               run the documented test suite
  python compiler_cli.py bench                               run the benchmarks (graphs + CSV)
"""
import argparse, os, sys, subprocess
sys.setrecursionlimit(20000)
os.system("")                                   # enables ANSI colors in the Windows terminal

from lexer import tokenize, print_tokens, LexError
from parser import print_ast, ParseError
from pipeline import compile_source
from incremental import IncrementalSession
from incremental_parser import count_nodes
from errors import describe_exception, describe_diagnostic

COLOR = sys.stdout.isatty()
def c(code, s): return f"\033[{code}m{s}\033[0m" if COLOR else s
RED, GREEN, YELLOW, DIM, BOLD = (lambda s: c(91, s)), (lambda s: c(92, s)), (lambda s: c(93, s)), (lambda s: c(90, s)), (lambda s: c(1, s))


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------- check
def cmd_check(a):
    src = read(a.file)
    res = compile_source(src, os.path.basename(a.file))
    if a.tokens and res.tokens:
        print_tokens(res.tokens)
    if a.ast and res.ast:
        print_ast(res.ast)
    if res.status == "ok":
        print(GREEN(f"OK: {a.file}: {len(res.tokens)} tokens, {count_nodes(res.ast)} AST nodes, no errors"))
        return 0
    for b in res.blocks:
        print(RED(b) + "\n")
    print(RED(f"{len(res.messages)} {res.status} error(s) in {a.file}"))
    return 1


# ---------------------------------------------------------------- diff
def has_rebuilt(node, rebuilt):
    return id(node) in rebuilt or any(has_rebuilt(ch, rebuilt) for _, ch in node.children())


def print_reuse_tree(node, rebuilt, indent=0, prefix=""):
    new = id(node) in rebuilt
    tag = RED("[REBUILT]") if new else GREEN("[reused] ")
    print(f"{tag} {'  ' * indent}{prefix + ': ' if prefix else ''}{node.label()} [{node.start}:{node.end}]")
    if not has_rebuilt(node, rebuilt) and indent >= 1 and node.children():
        print(f"{'':10} {'  ' * (indent + 1)}{DIM('... ' + str(count_nodes(node) - 1) + ' descendant nodes, all reused')}")
        return
    for p, ch in node.children():
        print_reuse_tree(ch, rebuilt, indent + 1, p)


def print_stats(st):
    if st.get("noop"):
        print(DIM("no change"))
        return
    print(BOLD("incremental update"))
    print(f"  tokens re-lexed      : {st['tokens_relexed']} of {st['tokens_total']}")
    print(f"  AST nodes rebuilt    : {st['nodes_rebuilt']}   (full re-parse fallback: {st['fallback']})")
    print(f"  statements re-checked: {st['stmts_rechecked']} of {st['stmts_total']}  (semantic stage)")
    print(DIM(f"  time: diff {st['diff_ms']:.3f} | lex {st['lex_ms']:.3f} | parse {st['parse_ms']:.3f} | semantic {st['sem_ms']:.3f} | total {st['total_ms']:.3f} ms"))


def print_diags(sess):
    ds = sess.diagnostics()
    if not ds:
        print(GREEN("no semantic errors"))
    for d in ds:
        print(RED(describe_diagnostic(d, sess.src)))


def cmd_diff(a):
    old, new = read(a.old), read(a.new)
    sess = IncrementalSession(old)
    print(f"cached {a.old}: {len(sess.tokens)} tokens, {count_nodes(sess.ast)} AST nodes\n")
    try:
        st = sess.update(new)
    except (LexError, ParseError) as e:
        print(RED(describe_exception(e, new, os.path.basename(a.new))[1]))
        return 1
    print_stats(st)
    print()
    print_diags(sess)
    if a.tree:
        print("\nAST after the edit (green = reused from cache, red = rebuilt):")
        print_reuse_tree(sess.ast, sess.last_rebuilt)
    return 0


# ---------------------------------------------------------------- repl
HELP = """commands:
  show                    print the source with line numbers
  replace N <text>        replace line N with <text>
  insert  N <text>        insert <text> as a new line before line N (N = last+1 appends)
  delete  N               delete line N
  undo                    undo the last accepted edit
  diag                    show semantic errors of the current version
  tokens | ast            print tokens / AST (AST shows reused vs rebuilt after the last edit)
  help | quit"""


def cmd_repl(a):
    sess = IncrementalSession(read(a.file))
    history = []
    print(BOLD(f"incremental live editor  -  {a.file}") + "   (type 'help')")
    def show():
        for i, ln in enumerate(sess.src.split("\n"), 1):
            print(f"{DIM(f'{i:>3} |')} {ln}")
    show()
    last = None
    while True:
        try:
            line = input(BOLD("\n> ")).rstrip("\n")
        except (EOFError, KeyboardInterrupt):
            print(); return 0
        parts = line.strip().split(" ", 2)
        cmd = parts[0].lower() if parts and parts[0] else ""
        lines = sess.src.split("\n")
        try:
            if cmd in ("quit", "exit", "q"):
                return 0
            elif cmd == "help":
                print(HELP)
            elif cmd == "show":
                show()
            elif cmd == "diag":
                print_diags(sess)
            elif cmd == "tokens":
                print_tokens(sess.tokens)
            elif cmd == "ast":
                print_reuse_tree(sess.ast, sess.last_rebuilt)
            elif cmd == "undo":
                if not history:
                    print("nothing to undo"); continue
                prev = history.pop()
                last = sess.update(prev); print_stats(last); print_diags(sess)
            elif cmd in ("replace", "insert", "delete"):
                n = int(parts[1])
                text = parts[2] if len(parts) > 2 else ""
                offs = [0]
                for ln in lines:
                    offs.append(offs[-1] + len(ln) + 1)
                if cmd == "insert":
                    if not 1 <= n <= len(lines) + 1: raise ValueError("line number out of range")
                    start = offs[n - 1] if n <= len(lines) else len(sess.src)
                    ins = text + "\n" if n <= len(lines) else ("\n" + text if sess.src and not sess.src.endswith("\n") else text + "\n")
                    edit = (start, start, ins)
                else:
                    if not 1 <= n <= len(lines): raise ValueError("line number out of range")
                    s, e = offs[n - 1], offs[n - 1] + len(lines[n - 1])
                    edit = (s, e, text) if cmd == "replace" else (s, min(e + 1, len(sess.src)), "")
                prev = sess.src
                try:
                    st = sess.apply_edit(*edit)
                    history.append(prev)
                    print_stats(st); print_diags(sess)
                except LexError as e:
                    print(RED(describe_exception(e, sess.src if False else prev[:edit[0]] + edit[2] + prev[edit[1]:])[1]))
                    print(YELLOW("edit rejected (source unchanged)"))
                except ParseError as e:
                    bad = prev[:edit[0]] + edit[2] + prev[edit[1]:]
                    print(RED(describe_exception(e, bad)[1]))
                    sess.update(prev)                  # revert: resync tokens, tree and semantic cache
                    print(YELLOW("edit rejected: syntax error, reverted to the previous version"))
            elif cmd == "":
                continue
            else:
                print("unknown command, type 'help'")
        except (ValueError, IndexError) as e:
            print(YELLOW(f"usage problem: {e}   (type 'help')"))


# ---------------------------------------------------------------- main
def main():
    p = argparse.ArgumentParser(description="Incremental lexical, syntax and semantic analyzer")
    sub = p.add_subparsers(dest="cmd", required=True)
    pc = sub.add_parser("check"); pc.add_argument("file"); pc.add_argument("--tokens", action="store_true"); pc.add_argument("--ast", action="store_true")
    pd = sub.add_parser("diff"); pd.add_argument("old"); pd.add_argument("new"); pd.add_argument("--tree", action="store_true")
    pr = sub.add_parser("repl"); pr.add_argument("file")
    sub.add_parser("tests"); sub.add_parser("bench")
    a = p.parse_args()
    here = os.path.dirname(os.path.abspath(__file__))
    if a.cmd == "check": return cmd_check(a)
    if a.cmd == "diff": return cmd_diff(a)
    if a.cmd == "repl": return cmd_repl(a)
    if a.cmd == "tests":
        r1 = subprocess.call([sys.executable, os.path.join(here, "test_suite.py")])
        r2 = subprocess.call([sys.executable, os.path.join(here, "tests.py")])
        return r1 or r2
    if a.cmd == "bench": return subprocess.call([sys.executable, os.path.join(here, "benchmark.py")])


if __name__ == "__main__":
    sys.exit(main())
