import random
from lexer import tokenize, LexError
from parser import parse, ParseError
from incremental import IncrementalSession


def tok_key(tokens):
    return [(t.type, t.value, t.start, t.end, t.line) for t in tokens]


def dump(node):
    return (node.label(), node.start, node.end, tuple(dump(c) for _, c in node.children()))


def full(src):
    """Reference answer: lex + parse everything from scratch."""
    try:
        toks = tokenize(src)
    except LexError:
        return ("LexError",)
    try:
        return ("ok", tok_key(toks), dump(parse(toks)))
    except ParseError:
        return ("ParseError", tok_key(toks))


def incr(session, new_src):
    try:
        session.update(new_src)
    except LexError:
        return ("LexError",)
    except ParseError:
        return ("ParseError", tok_key(session.tokens))
    return ("ok", tok_key(session.tokens), dump(session.ast))


BASE = """int x = 5;
int y = 10;

if (x < y && y > 0) {
    x = x + 1;
} else {
    x = x - 1;
}

while (x < y) {
    x = x + 1;
    print(x);
}
"""

# (name, old, new)
def edits_on_base():
    s = BASE
    yield "change a number",        s, s.replace("x + 1;\n    print", "x + 2;\n    print")
    yield "rename identifier",      s, s.replace("int y = 10;", "int z = 10;")
    yield "change operator",        s, s.replace("x < y &&", "x > y &&")
    yield "insert statement at top", s, "int w = 1;\n" + s
    yield "insert stmt in while",   s, s.replace("    print(x);\n", "    print(x);\n    print(y);\n")
    yield "delete a line",          s, s.replace("    print(x);\n", "")
    yield "delete whole while",     s, s[: s.index("while")]
    yield "add newline inside",     s, s.replace("x = x - 1;", "x =\n x - 1;")
    yield "remove newline (join)",  s, s.replace("int x = 5;\n", "int x = 5;")
    yield "edit first char",        s, "  " + s
    yield "edit last char",         s, s[:-1]
    yield "append at end",          s, s + "int q = 3;\n"
    yield "merge two tokens",       s, s.replace("x = x + 1;\n    print", "x = x + 1;\n    pri nt").replace("pri nt", "print")
    yield "turn code into comment", s, s.replace("    print(x);", "    // print(x);")
    yield "uncomment code",         s.replace("    print(x);", "    // print(x);"), s
    yield "edit inside a comment",  s.replace("    print(x);", "    // print(x);"), s.replace("    print(x);", "    // print(xyz);")
    yield "syntax error: drop ;",   s, s.replace("int x = 5;", "int x = 5")
    yield "syntax error: drop }",   s, s.replace("    print(x);\n}", "    print(x);\n")
    yield "lex error: bad char",    s, s.replace("int y = 10;", "int y = 10 @;")
    yield "no change",              s, s
    yield "cond of while changed",  s, s.replace("while (x < y)", "while (x < y + 1)")
    yield "else removed",           s, s.replace("} else {\n    x = x - 1;\n}", "}")


def run_hand_tests():
    ok = 0
    for name, old, new in edits_on_base():
        sess = IncrementalSession(old)
        got, want = incr(sess, new), full(new)
        assert got == want, f"FAILED: {name}\n got  {got[0]}\n want {want[0]}"
        ok += 1
        print(f"  pass  {name}")
    print(f"{ok} hand-written cases passed")


SNIPPETS = ["x", "y", "1", "42", " ", "\n", "{", "}", "(", ")", ";", "if", "else", "while",
            "+", "=", "//", "int ", "&&", "<", "!", "5 ", "x = 1;", "if (x) {", "}\n", "print(x);\n"]


def random_edit(src, rng):
    # 60%: "plausible" edit = swap one token for a similar one (keeps programs valid more often)
    if rng.random() < 0.6:
        toks = [t for t in tokenize(src) if t.type != "EOF"]
        t = rng.choice(toks)
        pool = {"NUMBER": ["0", "7", "123", "9"], "IDENT": ["x", "y", "zz", "print"],
                "OP": ["+", "-", "*", "<", ">", "==", "&&", "||"],
                "KEYWORD": ["int", "true", "false"], "PUNCT": [";", ";"]}[t.type]
        new = rng.choice(pool)
        if t.type == "KEYWORD" and t.value in ("if", "else", "while", "int"):
            new = t.value  # keep structure keywords; (edit whitespace around instead)
            new = new + rng.choice(["", " ", "\n"])
        return src[:t.start] + new + src[t.end:]
    a = rng.randint(0, len(src))
    kind = rng.choice(["ins", "del", "rep"])
    snip = rng.choice(SNIPPETS)
    if kind == "ins":
        return src[:a] + snip + src[a:]
    b = min(len(src), a + rng.randint(1, 6))
    return src[:a] + (snip if kind == "rep" else "") + src[b:]


def run_fuzz(n=5000, seed=1):
    rng = random.Random(seed)
    cur = BASE
    sess = IncrementalSession(cur)
    stats = {"ok": 0, "ParseError": 0, "LexError": 0, "fallback": 0}
    for i in range(n):
        new = random_edit(cur, rng)
        got, want = incr(sess, new), full(new)
        assert got == want, f"FUZZ MISMATCH at step {i}\n--- old ---\n{cur}\n--- new ---\n{new}\n got {got[0]} want {want[0]}"
        stats[want[0]] += 1
        if want[0] == "ok" and sess.last_info.get("fallback"):
            stats["fallback"] += 1
        if want[0] == "ok":
            cur = new
        else:                                   # go back to the last valid program
            if want[0] == "ParseError":
                sess.src, sess.tokens = cur, tokenize(cur)   # resync cache after error
                sess.ast = parse(sess.tokens)
    print(f"fuzz: {n} random edits, incremental == full every time  {stats}")


if __name__ == "__main__":
    run_hand_tests()
    run_fuzz()
    print("\nALL TESTS PASSED")
