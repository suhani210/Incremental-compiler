"""
benchmark.py  -  Phase 3 performance evaluation.
   A. time vs file size            (100 ... 10,000 lines)       -> benchmark_scaling.png / .csv
   B. time vs edit type            (5,000-line file)            -> benchmark_edit_types.png / .csv
   C. memory used by one edit      (5,000-line file, tracemalloc)
   D. accuracy                     (see tests.py: 6,000 random edits, incremental == full)
Run:  python benchmark.py        (needs: pip install matplotlib)
"""
import sys, time, statistics, csv, tracemalloc
sys.setrecursionlimit(20000)
from lexer import tokenize
from parser import parse
from semantic import analyze_full
from incremental import IncrementalSession

SIZES = [100, 500, 1000, 2000, 5000, 10000]
REPS = 9


def make_source(n_lines):
    out = ["// generated benchmark program", "int g = 1;"]
    i = 0
    while len(out) + 11 <= n_lines:        # whole blocks only, so the program stays valid
        out += [f"// block {i}",
                f"int v{i} = {i} + 1;",
                f"if (v{i} < 100 && v{i} > 0) {{",
                f"    v{i} = v{i} * 2 - g;",
                "} else {",
                f"    v{i} = v{i} - 1;",
                "}",
                f"while (v{i} < 50) {{",
                f"    v{i} = v{i} + 1;",
                f"    print(v{i});",
                "}"]
        i += 1
    return "\n".join(out) + "\n"


def full_compile(src):
    ast = parse(tokenize(src))
    analyze_full(ast)


def ms(fn):
    t = time.perf_counter(); fn(); return (time.perf_counter() - t) * 1e3


def med(xs):
    return statistics.median(xs)


# ---------------------------------------------------------------- A
def scaling():
    rows = []
    print("A. time vs file size (one-character edit in the middle of the file)")
    print(f"{'lines':>7} {'full (ms)':>10} {'incr+diff (ms)':>15} {'incr, range (ms)':>17} {'speedup':>9}")
    for n in SIZES:
        src = make_source(n)
        k = (n // 22)                                           # a block near the middle
        pos = src.index(f"v{k} = v{k} + 1;") + len(f"v{k} = v{k} + ")
        a_src, b_src = src, src[:pos] + "2" + src[pos + 1:]
        full_t = [ms(lambda s=(a_src, b_src)[i % 2]: full_compile(s)) for i in range(REPS)]
        sess = IncrementalSession(a_src)
        d = [ms(lambda s=(a_src, b_src)[(i + 1) % 2]: sess.update(s)) for i in range(REPS)]
        r = []
        for i in range(REPS):
            ch = "2" if sess.src[pos] == "1" else "1"
            r.append(ms(lambda c=ch: sess.apply_edit(pos, pos + 1, c)))
        rows.append((n, med(full_t), med(d), med(r)))
        print(f"{n:>7} {med(full_t):>10.2f} {med(d):>15.2f} {med(r):>17.2f} {med(full_t) / med(d):>8.1f}x")
    return rows


# ---------------------------------------------------------------- B
def edit_types(n=5000):
    src = make_source(n)
    k = n // 22
    lit = src.index(f"v{k} = v{k} + 1;") + len(f"v{k} = v{k} + ")
    decl_start = src.index(f"int v{k} = ")
    decl_end = src.index("\n", decl_start) + 1
    cmt = src.index(f"// block {k}") + len("// block ")
    g = src.index("int g") + 4
    edits = [   # name, forward edit (start, end, text), backward edit
        ("change a literal in a loop body", (lit, lit + 1, "2"), (lit, lit + 1, "1")),
        ("insert a new statement", (decl_start, decl_start, "int extra = 7;\n"), (decl_start, decl_start + 15, "")),
        ("delete a declaration (its users break)", (decl_start, decl_end, ""), (decl_start, decl_start, src[decl_start:decl_end])),
        ("edit inside a comment", (cmt, cmt + len(str(k)), "x" + str(k)), (cmt, cmt + len(str(k)) + 1, str(k))),
        ("rename a widely used global", (g, g + 1, "h"), (g, g + 1, "g")),
    ]
    print(f"\nB. time vs edit type  ({n}-line file)")
    print(f"{'edit type':<42}{'full':>9}{'incr':>8}{'speedup':>9}{'relexed':>9}{'rebuilt':>9}{'rechecked':>11}")
    rows = []
    for name, fw, bw in edits:
        sess = IncrementalSession(src)
        times, st = [], None
        for _ in range(REPS):
            t = time.perf_counter(); st = sess.apply_edit(*fw); times.append((time.perf_counter() - t) * 1e3)
            sess.apply_edit(*bw)
        new_src = src[:fw[0]] + fw[2] + src[fw[1]:]
        full_ms = med([ms(lambda: full_compile(new_src)) for _ in range(5)])
        rows.append((name, full_ms, med(times), st["tokens_relexed"], st["nodes_rebuilt"], st["stmts_rechecked"]))
        print(f"{name:<42}{full_ms:>9.1f}{med(times):>8.2f}{full_ms / med(times):>8.0f}x{st['tokens_relexed']:>9}{st['nodes_rebuilt']:>9}{st['stmts_rechecked']:>7}/{st['stmts_total']}")
    return rows


# ---------------------------------------------------------------- C
def memory(n=5000):
    src = make_source(n)
    lit = src.index("v100 = v100 + 1;") + len("v100 = v100 + ")
    new_src = src[:lit] + "2" + src[lit + 1:]
    sess = IncrementalSession(src)                              # cache already built
    tracemalloc.start()
    tracemalloc.clear_traces(); base = tracemalloc.get_traced_memory()[0]
    full_compile(new_src)
    full_peak = tracemalloc.get_traced_memory()[1] - base
    tracemalloc.clear_traces(); base = tracemalloc.get_traced_memory()[0]
    sess.apply_edit(lit, lit + 1, "2")
    inc_peak = tracemalloc.get_traced_memory()[1] - base
    tracemalloc.stop()
    print(f"\nC. peak extra memory for ONE edit ({n} lines): full recompile {full_peak / 1e6:.2f} MB | incremental {inc_peak / 1e6:.3f} MB  ({full_peak / max(inc_peak, 1):.0f}x less)")
    return full_peak, inc_peak


if __name__ == "__main__":
    A, B, (fm, im) = scaling(), edit_types(), memory()
    with open("benchmark_scaling.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["lines", "full_ms", "incremental_with_diff_ms", "incremental_with_range_ms"]); w.writerows(A)
    with open("benchmark_edit_types.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["edit_type", "full_ms", "incremental_ms", "tokens_relexed", "nodes_rebuilt", "stmts_rechecked"]); w.writerows(B)
    with open("benchmark_memory.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["full_peak_bytes", "incremental_peak_bytes"]); w.writerow([fm, im])
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.figure(figsize=(8, 5))
        xs = [r[0] for r in A]
        plt.plot(xs, [r[1] for r in A], "o-", label="Full recompile (lex + parse + semantic)")
        plt.plot(xs, [r[2] for r in A], "s-", label="Incremental (diff + lex + parse + semantic)")
        plt.plot(xs, [r[3] for r in A], "^-", label="Incremental (edit range given)")
        plt.xlabel("File size (lines)"); plt.ylabel("Time per edit (ms)"); plt.title("Single-character edit: full vs incremental")
        plt.grid(alpha=.3); plt.legend(); plt.tight_layout(); plt.savefig("benchmark_scaling.png", dpi=150)
        plt.figure(figsize=(9, 5))
        names = [r[0] for r in B]
        import numpy as np
        x = np.arange(len(names)); wd = 0.38
        plt.bar(x - wd / 2, [r[1] for r in B], wd, label="Full recompile")
        plt.bar(x + wd / 2, [r[2] for r in B], wd, label="Incremental")
        plt.yscale("log"); plt.ylim(1, max(r[1] for r in B) * 4); plt.ylabel("Time (ms, log scale)")
        plt.xticks(x, [n.replace(" (", "\n(").replace(" a ", " a\n") for n in names], fontsize=7)
        plt.title("5,000-line file: time by edit type"); plt.legend(); plt.grid(axis="y", alpha=.3); plt.tight_layout()
        plt.savefig("benchmark_edit_types.png", dpi=150)
        print("\nsaved benchmark_scaling.png, benchmark_edit_types.png and 3 CSV files")
    except ImportError:
        print("\nmatplotlib/numpy not installed -> pip install matplotlib   (CSV files were still saved)")
