"""
tests.py  -  incremental-vs-full equivalence tests (hand-written + random fuzz).
Core rule:   incremental(old -> new)  ==  full(new)   for tokens, AST, offsets,
             line numbers, semantic errors AND error messages.
Run:  python tests.py
"""
import random, sys
sys.setrecursionlimit(20000)
from lexer import tokenize, LexError
from parser import parse, ParseError
from semantic import analyze_full
from incremental import IncrementalSession


def tok_key(tokens):
    return [(t.type, t.value, t.start, t.end, t.line) for t in tokens]


def dump(node):
    return (node.label(), node.start, node.end, tuple(dump(c) for _, c in node.children()))


def full(src):
    """Reference answer: lex + parse + analyze everything from scratch."""
    try:
        toks = tokenize(src)
    except LexError as e:
        return ("LexError", str(e))
    try:
        ast = parse(toks)
    except ParseError as e:
        return ("ParseError", str(e), tok_key(toks))
    return ("ok", tok_key(toks), dump(ast), [d.key() for d in analyze_full(ast)])


def incr(session, new_src):
    try:
        session.update(new_src)
    except LexError as e:
        return ("LexError", str(e))
    except ParseError as e:
        return ("ParseError", str(e), tok_key(session.tokens))
    return ("ok", tok_key(session.tokens), dump(session.ast), [d.key() for d in session.diagnostics()])


BASE = """int g = 1;
int x = 5;
int y = 10;

if (x < y && y > 0) {
    x = x + g;
} else {
    x = x - 1;
}

while (x < y) {
    x = x + 1;
    print(x);
}
"""


def edits_on_base():
    s = BASE
    yield "change a number",         s, s.replace("x = x + 1;\n    print", "x = x + 2;\n    print")
    yield "rename identifier",       s, s.replace("int y = 10;", "int z = 10;")          # y now undeclared everywhere
    yield "rename global used in blocks", s, s.replace("int g = 1;", "int h = 1;")        # dependency fan-out
    yield "change operator",         s, s.replace("x < y &&", "x > y &&")
    yield "insert statement at top", s, "int w = 1;\n" + s
    yield "insert stmt in while",    s, s.replace("    print(x);\n", "    print(x);\n    print(y);\n")
    yield "delete a line",           s, s.replace("    print(x);\n", "")
    yield "delete a declaration",    s, s.replace("int x = 5;\n", "")
    yield "delete whole while",      s, s[: s.index("while")]
    yield "add newline inside",      s, s.replace("x = x - 1;", "x =\n x - 1;")
    yield "remove newline (join)",   s, s.replace("int x = 5;\n", "int x = 5;")
    yield "edit first char",         s, "  " + s
    yield "edit last char",          s, s[:-1]
    yield "append at end",           s, s + "int q = 3;\n"
    yield "merge two tokens",        s, s.replace("print(x);", "pri nt(x);").replace("pri nt", "print")
    yield "turn code into comment",  s, s.replace("    print(x);", "    // print(x);")
    yield "uncomment code",          s.replace("    print(x);", "    // print(x);"), s
    yield "edit inside a comment",   s.replace("    print(x);", "    // print(x);"), s.replace("    print(x);", "    // print(xyz);")
    yield "syntax error: drop ;",    s, s.replace("int x = 5;", "int x = 5")
    yield "syntax error: drop }",    s, s.replace("    print(x);\n}", "    print(x);\n")
    yield "lex error: bad char",     s, s.replace("int y = 10;", "int y = 10 @;")
    yield "no change",               s, s
    yield "cond of while changed",   s, s.replace("while (x < y)", "while (x < y + 1)")
    yield "else removed",            s, s.replace("} else {\n    x = x - 1;\n}", "}")
    yield "type error introduced",   s, s.replace("x = x + 1;\n    print", "x = x < 1;\n    print")
    yield "redeclaration introduced", s, s.replace("int y = 10;", "int x = 10;")
    yield "redeclaration fixed",     s.replace("int y = 10;", "int x = 10;"), s


def run_hand_tests():
    ok = 0
    for name, old, new in edits_on_base():
        sess = IncrementalSession(old)
        got, want = incr(sess, new), full(new)
        assert got == want, f"FAILED: {name}\n got  {got[:2]}\n want {want[:2]}"
        ok += 1
        print(f"  pass  {name}")
    print(f"{ok} hand-written incremental cases passed")


def run_recovery_test():
    """After a syntax error the session must recover on the next valid edit."""
    s = IncrementalSession(BASE)
    bad = BASE.replace("int x = 5;", "int x = 5")
    assert incr(s, bad) == full(bad)
    still_bad = bad + "int zz = ;"
    assert incr(s, still_bad) == full(still_bad)
    assert incr(s, BASE) == full(BASE)
    assert incr(s, BASE.replace("5", "6")) == full(BASE.replace("5", "6"))
    print("  pass  recovery after syntax errors")


SNIPPETS = ["x", "y", "g", "1", "42", " ", "\n", "{", "}", "(", ")", ";", "if", "else", "while", "+", "=", "//",
            "int ", "&&", "<", "!", "5 ", "x = 1;", "if (x) {", "}\n", "print(x);\n", "true", "int k = x < 2;"]


def random_edit(src, rng):
    if rng.random() < 0.6:        # plausible edit: swap one token for a similar one
        toks = [t for t in tokenize(src) if t.type != "EOF"]
        t = rng.choice(toks)
        pool = {"NUMBER": ["0", "7", "123", "9"], "IDENT": ["x", "y", "g", "zz", "print"],
                "OP": ["+", "-", "*", "/", "<", ">", "==", "&&", "||", "!="],
                "KEYWORD": ["int", "true", "false"], "PUNCT": [";", ";"]}[t.type]
        new = rng.choice(pool)
        if t.type == "KEYWORD" and t.value in ("if", "else", "while", "int"):
            new = t.value + rng.choice(["", " ", "\n"])
        return src[:t.start] + new + src[t.end:]
    a = rng.randint(0, len(src))
    kind = rng.choice(["ins", "del", "rep"])
    snip = rng.choice(SNIPPETS)
    if kind == "ins":
        return src[:a] + snip + src[a:]
    b = min(len(src), a + rng.randint(1, 6))
    return src[:a] + (snip if kind == "rep" else "") + src[b:]


def run_fuzz(n=6000, seed=1):
    rng = random.Random(seed)
    cur = BASE
    sess = IncrementalSession(cur)
    stats = {"ok": 0, "ParseError": 0, "LexError": 0, "fallback": 0, "with_semantic_errors": 0}
    for i in range(n):
        new = random_edit(cur, rng)
        got, want = incr(sess, new), full(new)
        assert got == want, f"FUZZ MISMATCH at step {i}\n--- old ---\n{cur}\n--- new ---\n{new}\n got {got[:2]}\n want {want[:2]}"
        stats[want[0]] += 1
        if want[0] == "ok":
            if sess.last_info.get("fallback"):
                stats["fallback"] += 1
            if want[3]:
                stats["with_semantic_errors"] += 1
            if len(want[3]) < 6:           # keep the working program from drowning in errors
                cur = new
            else:
                sess = IncrementalSession(cur)
        else:
            if rng.random() < 0.5:         # recover through the incremental path
                got2, want2 = incr(sess, cur), full(cur)
                assert got2 == want2, f"RECOVERY MISMATCH at step {i}"
            else:
                sess = IncrementalSession(cur)
    print(f"fuzz: {n} random edits, incremental == full every time  {stats}")


if __name__ == "__main__":
    run_hand_tests()
    run_recovery_test()
    run_fuzz()
    print("\nALL TESTS PASSED")
