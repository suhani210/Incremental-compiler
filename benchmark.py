"""
benchmark.py  -  incremental vs full recompile, time-vs-file-size graph.
Run:  python benchmark.py          (needs: pip install matplotlib)
"""
import time, statistics
from lexer import tokenize
from parser import parse
from incremental import IncrementalSession

SIZES = [100, 500, 1000, 2000, 5000, 10000]
REPS = 15


def make_source(n_lines):
    """Valid program of ~n_lines lines, with a marker number in the middle to edit."""
    out, i = [], 0
    while len(out) < n_lines:
        out.append(f"int v{i} = {i} + 1;")
        out.append(f"if (v{i} < 100 && v{i} > 0) {{")
        out.append(f"    v{i} = v{i} * 2 - 1;")
        out.append("} else {")
        out.append(f"    v{i} = v{i} - 1;")
        out.append("}")
        out.append(f"while (v{i} < 50) {{")
        out.append(f"    v{i} = v{i} + 1;")
        out.append(f"    print(v{i});")
        out.append("}")
        i += 1
    return "\n".join(out[:n_lines]) + "\n"


def timeit(fn):
    t = time.perf_counter(); fn(); return (time.perf_counter() - t) * 1e3


def bench(n_lines):
    src = make_source(n_lines)
    mid = src.index("\n", len(src) // 2)                  # end of a line in the middle
    a = src.rindex("v", 0, mid)                           # a token inside that line
    # two versions that differ by one character, so we can flip A <-> B forever
    ver_a = src
    ver_b = src[:a] + "w" + src[a + 1:]
    versions = [ver_a, ver_b]

    full_times = [timeit(lambda s=versions[i % 2]: parse(tokenize(s))) for i in range(REPS)]

    sess = IncrementalSession(ver_a)
    inc_diff, inc_range = [], []
    for i in range(REPS):                                 # incremental, editor sends no range -> we diff
        inc_diff.append(timeit(lambda s=versions[(i + 1) % 2]: sess.update(s)))
    for i in range(REPS):                                 # incremental, editor sends (start,end,replacement)
        ch = "w" if sess.src[a] == "v" else "v"
        inc_range.append(timeit(lambda c=ch: sess.apply_edit(a, a + 1, c)))
    return (statistics.median(full_times), statistics.median(inc_diff), statistics.median(inc_range))


if __name__ == "__main__":
    rows = []
    print(f"{'lines':>7} {'full (ms)':>11} {'incr+diff (ms)':>15} {'incr, range (ms)':>17} {'speedup':>9}")
    for n in SIZES:
        f, d, r = bench(n)
        rows.append((n, f, d, r))
        print(f"{n:>7} {f:>11.2f} {d:>15.2f} {r:>17.2f} {f / d:>8.1f}x")

    import csv
    with open("benchmark_results.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["lines", "full_ms", "incremental_with_diff_ms", "incremental_with_range_ms"]); w.writerows(rows)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        xs = [r[0] for r in rows]
        plt.figure(figsize=(8, 5))
        plt.plot(xs, [r[1] for r in rows], "o-", label="Full recompile (lex + parse)")
        plt.plot(xs, [r[2] for r in rows], "s-", label="Incremental (diff + re-lex + re-parse)")
        plt.plot(xs, [r[3] for r in rows], "^-", label="Incremental (edit range given)")
        plt.xlabel("File size (lines)"); plt.ylabel("Time per edit (ms)")
        plt.title("Single-line edit: full vs incremental"); plt.grid(alpha=.3); plt.legend()
        plt.tight_layout(); plt.savefig("benchmark.png", dpi=150)
        print("saved benchmark.png and benchmark_results.csv")
    except ImportError:
        print("matplotlib not installed -> pip install matplotlib   (CSV was still saved)")
