"""
test_suite.py  -  the documented TEST CASES + TEST RESULTS for the final report.

Categories:  Valid | Invalid syntax | Lexical error | Semantic error | Boundary | Complex | Incremental edit
Run:  python test_suite.py            -> prints a table, writes test_results.txt and test_results.csv
"""
import sys, csv, time
sys.setrecursionlimit(20000)
from pipeline import compile_source
from incremental import IncrementalSession
import tests as eq

OK = ("ok", "")

def sem(s): return ("semantic", s)
def syn(s): return ("syntax", s)
def lex(s): return ("lexical", s)

DEEP_BLOCKS = "int d = 0;\n" + "".join("while (d < 1) {\n" for _ in range(30)) + "d = 1;\n" + "}\n" * 30
LONG_EXPR = "int s = " + " + ".join(["1"] * 500) + ";\n"
LONG_LINE = "int a = 1;\n" + "a = a + 1; " * 400 + "\n"
NESTED_PARENS = "int p = " + "(" * 60 + "1" + ")" * 60 + ";\n"

COMPLEX = """// counting program with nested control flow
int n = 10;
int i = 0;
int total = 0;
while (i < n) {
    int sq = i * i;
    if (sq > 20 && !(i == 7)) {
        total = total + sq;
    } else {
        if (i < 3 || i == 9) {
            total = total - 1;
        } else {
            total = total + (i * 2 - 1) / 2;
        }
    }
    i = i + 1;
    print(total);
}
if (total > 50) {
    print(total);
}
"""

CASES = [
    # ---- VALID INPUTS
    ("V01", "Valid", "variable declaration with arithmetic", "int x = 1 + 2 * 3;\n", OK),
    ("V02", "Valid", "if / else", "int x = 1;\nif (x < 2) {\n  x = 2;\n} else {\n  x = 3;\n}\n", OK),
    ("V03", "Valid", "while loop", "int i = 0;\nwhile (i < 3) {\n  i = i + 1;\n}\n", OK),
    ("V04", "Valid", "nested blocks", "int a = 1;\n{\n  int b = a;\n  {\n    int c = b + a;\n  }\n}\n", OK),
    ("V05", "Valid", "built-in function call", "int x = 4;\nprint(x);\nprint(x + 1);\n", OK),
    ("V06", "Valid", "boolean operators && || !", "int a = 1;\nif (a < 2 && !(a == 0) || a > 5) {\n  a = 0;\n}\n", OK),
    ("V07", "Valid", "unary minus and parentheses", "int a = -(3 + 4) * 2;\n", OK),
    ("V08", "Valid", "shadowing in inner block", "int a = 1;\n{\n  int a = 2;\n  a = a + 1;\n}\n", OK),
    ("V09", "Valid", "comments and blank lines", "// a comment\n\nint a = 1; // trailing\n\n", OK),
    ("V10", "Valid", "boolean literals as condition", "int a = 1;\nif (true) {\n  a = 2;\n}\nwhile (false) {\n}\n", OK),
    ("V11", "Valid", "equality of two bools in a condition", "int a = 1;\nif ((a < 2) == (a > 0)) {\n  a = 0;\n}\n", OK),
    # ---- INVALID SYNTAX
    ("S01", "Invalid syntax", "missing semicolon", "int x = 5\nint y = 2;\n", syn("missing ';'")),
    ("S02", "Invalid syntax", "missing closing brace", "int a = 1;\nif (a < 2) {\n  a = 2;\n", syn("end of file")),
    ("S03", "Invalid syntax", "missing closing parenthesis", "int a = 1;\nif (a < 2 {\n}\n", syn("missing ')'")),
    ("S04", "Invalid syntax", "declaration without a name", "int = 5;\n", syn("variable name")),
    ("S05", "Invalid syntax", "'else' without 'if'", "int a = 1;\nelse {\n}\n", syn("unexpected")),
    ("S06", "Invalid syntax", "condition without parentheses", "int a = 1;\nif a < 2 {\n}\n", syn("expected '('")),
    ("S07", "Invalid syntax", "extra closing brace", "int a = 1;\n}\n", syn("unexpected")),
    ("S08", "Invalid syntax", "missing '=' in declaration", "int a 5;\n", syn("expected '='")),
    ("S09", "Invalid syntax", "empty condition", "while () {\n}\n", syn("unexpected")),
    ("S10", "Invalid syntax", "unsupported 'return'", "return 1;\n", syn("return")),
    ("S11", "Invalid syntax", "number glued to name", "int 5x = 1;\n", syn("variable name")),
    ("S12", "Invalid syntax", "dangling operator", "int a = 1 + ;\n", syn("unexpected")),
    ("S13", "Invalid syntax", "unclosed call", "int a = 1;\nprint(a;\n", syn("missing ')'")),
    # ---- LEXICAL ERRORS
    ("L01", "Lexical error", "illegal character @", "int a = 1 @ 2;\n", lex("'@'")),
    ("L02", "Lexical error", "illegal character #", "# define\n", lex("'#'")),
    ("L03", "Lexical error", "single & (not &&)", "int a = 1 & 2;\n", lex("'&'")),
    ("L04", "Lexical error", "single | (not ||)", "int a = 1 | 2;\n", lex("'|'")),
    ("L05", "Lexical error", "string literal (unsupported)", 'int a = "hi";\n', lex("'\"'")),
    ("L06", "Lexical error", "error reported on the right line", "int a = 1;\nint b = 2;\nint c = $;\n", lex("'$'")),
    # ---- SEMANTIC ERRORS
    ("M01", "Semantic error", "undeclared variable", "int a = b + 1;\n", sem("undeclared variable 'b'")),
    ("M02", "Semantic error", "assignment to undeclared variable", "a = 1;\n", sem("assignment to undeclared")),
    ("M03", "Semantic error", "redeclaration in global scope", "int a = 1;\nint a = 2;\n", sem("redeclaration")),
    ("M04", "Semantic error", "redeclaration in the same block", "{\n  int a = 1;\n  int a = 2;\n}\n", sem("redeclaration")),
    ("M05", "Semantic error", "int initialised with bool", "int a = 1 < 2;\n", sem("cannot initialize")),
    ("M06", "Semantic error", "if condition is int", "int a = 1;\nif (a) {\n}\n", sem("must be bool")),
    ("M07", "Semantic error", "arithmetic on bool", "int a = true + 1;\n", sem("needs int operands")),
    ("M08", "Semantic error", "&& on ints", "int a = 1;\nif (a && a) {\n}\n", sem("needs bool operands")),
    ("M09", "Semantic error", "! on int", "int a = 1;\nif (!a) {\n}\n", sem("'!' needs a bool")),
    ("M10", "Semantic error", "comparing int with bool", "int a = 1;\nif (a == (a < 2)) {\n}\n", sem("cannot compare")),
    ("M11", "Semantic error", "division by zero literal", "int a = 4 / 0;\n", sem("division by zero")),
    ("M12", "Semantic error", "call to unknown function", "foo(1);\n", sem("undeclared function")),
    ("M13", "Semantic error", "wrong number of arguments", "print(1, 2);\n", sem("expects 1")),
    ("M14", "Semantic error", "use before declaration", "a = 1;\nint a = 2;\n", sem("undeclared")),
    ("M15", "Semantic error", "variable used outside its block", "{\n  int a = 1;\n}\na = 2;\n", sem("undeclared")),
    ("M16", "Semantic error", "assigning bool to int variable", "int a = 1;\na = a < 2;\n", sem("cannot assign")),
    ("M17", "Semantic error", "several errors are all reported", "x = 1;\ny = 2;\nint z = true;\n", sem("undeclared")),
    # ---- BOUNDARY CASES
    ("B01", "Boundary", "empty file", "", OK),
    ("B02", "Boundary", "only whitespace", "   \n\t\n  ", OK),
    ("B03", "Boundary", "only comments", "// one\n// two\n", OK),
    ("B04", "Boundary", "no trailing newline", "int a = 1;", OK),
    ("B05", "Boundary", "Windows (CRLF) line endings", "int a = 1;\r\nint b = a;\r\n", OK),
    ("B06", "Boundary", "huge integer literal", "int a = 99999999999999999999999;\n", OK),
    ("B07", "Boundary", "30 nested blocks", DEEP_BLOCKS, OK),
    ("B08", "Boundary", "expression with 500 terms", LONG_EXPR, OK),
    ("B09", "Boundary", "very long line (4,000+ chars)", LONG_LINE, OK),
    ("B10", "Boundary", "identifier with underscore and digits", "int _a1_b2 = 1;\n", OK),
    ("B11", "Boundary", "identifier that starts with a keyword", "int integer = 1;\nint iffy = integer;\n", OK),
    ("B12", "Boundary", "60 nested parentheses", NESTED_PARENS, OK),
    ("B13", "Boundary", "a lone semicolon", ";\n", syn("unexpected")),
    ("B14", "Boundary", "error on the very last character", "int a = 1 +", syn("end of file")),
    ("B15", "Boundary", "tabs as indentation", "int a = 1;\nif (a < 2) {\n\ta = 2;\n}\n", OK),
    # ---- COMPLEX INPUT
    ("C01", "Complex", "nested loops, branches, calls, long expressions", COMPLEX, OK),
    ("C02", "Complex", "complex program with one hidden type error",
        COMPLEX.replace("total = total - 1;", "total = total < 1;"), sem("cannot assign")),
]


def run_case(case):
    cid, cat, desc, src, (want_status, want_text) = case
    t = time.perf_counter()
    res = compile_source(src)
    ms = (time.perf_counter() - t) * 1e3
    shown = res.status if not res.messages else f"{res.status}: {res.messages[0]}"
    ok = res.status == want_status and any(want_text in m for m in res.messages) if want_text else res.status == want_status
    expected = want_status if not want_text else f"{want_status} containing {want_text!r}"
    return cid, cat, desc, expected, shown, ok, ms


def run_incremental_cases():
    rows, n = [], 0
    for name, old, new in eq.edits_on_base():
        n += 1
        sess = IncrementalSession(old)
        t = time.perf_counter()
        got, want = eq.incr(sess, new), eq.full(new)
        ms = (time.perf_counter() - t) * 1e3
        rows.append((f"E{n:02d}", "Incremental edit", name, "incremental == full compile",
                     "identical" if got == want else "MISMATCH", got == want, ms))
    return rows


if __name__ == "__main__":
    rows = [run_case(c) for c in CASES] + run_incremental_cases()
    width = max(len(r[2]) for r in rows) + 2
    lines = [f"{'ID':<5}{'Category':<18}{'Test case':<{width}}{'Result':<7} Actual outcome"]
    lines.append("-" * 110)
    for cid, cat, desc, exp, shown, ok, ms in rows:
        lines.append(f"{cid:<5}{cat:<18}{desc:<{width}}{'PASS' if ok else 'FAIL':<7} {shown[:70]}")
    passed = sum(r[5] for r in rows)
    lines.append("-" * 110)
    by_cat = {}
    for r in rows:
        by_cat.setdefault(r[1], [0, 0])
        by_cat[r[1]][0] += r[5]; by_cat[r[1]][1] += 1
    for cat, (p, t) in by_cat.items():
        lines.append(f"  {cat:<18} {p}/{t} passed")
    lines.append(f"\nTOTAL: {passed}/{len(rows)} test cases passed")
    out = "\n".join(lines)
    print(out)
    open("test_results.txt", "w", encoding="utf-8").write(out + "\n")
    with open("test_results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "category", "test_case", "expected", "actual", "result", "time_ms"])
        for cid, cat, desc, exp, shown, ok, ms in rows:
            w.writerow([cid, cat, desc, exp, shown, "PASS" if ok else "FAIL", f"{ms:.3f}"])
    sys.exit(0 if passed == len(rows) else 1)
