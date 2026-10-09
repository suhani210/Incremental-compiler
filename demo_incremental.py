import os
from incremental import IncrementalSession
from incremental_parser import count_nodes
from diff_tool import summarize, mark_region

USE_COLOR = True        # set False if your terminal shows weird characters like  ←[92m
GREEN, RED, RESET = ("\033[92m", "\033[91m", "\033[0m") if USE_COLOR else ("", "", "")
HERE = os.path.dirname(os.path.abspath(__file__))


def read(name):
    with open(os.path.join(HERE, "samples", name)) as f:
        return f.read()


def has_rebuilt(node, rebuilt):
    return id(node) in rebuilt or any(has_rebuilt(c, rebuilt) for _, c in node.children())


def print_diff_ast(node, rebuilt, indent=0, prefix=""):
    new = id(node) in rebuilt
    tag = f"{RED}[REBUILT]{RESET}" if new else f"{GREEN}[reused] {RESET}"
    tag_prefix = f"{prefix}: " if prefix else ""
    print(f"{tag} {'  ' * indent}{tag_prefix}{node.label()} [{node.start}:{node.end}]")
    # don't print the inside of big reused subtrees fully - just collapse them
    if not has_rebuilt(node, rebuilt) and indent >= 1 and node.children():
        print(f"{'':11} {'  ' * (indent + 1)}... ({count_nodes(node) - 1} descendant nodes, all reused)")
        return
    for p, c in node.children():
        print_diff_ast(c, rebuilt, indent + 1, p)


def banner(t):
    print("\n" + "=" * 70 + f"\n{t}\n" + "=" * 70)


old_src, new_src = read("sample_old.src"), read("sample_new.src")

banner("1. Cache holds the OLD file (full lex + parse done once)")
sess = IncrementalSession(old_src)
total_before = count_nodes(sess.ast)
print(f"{len(sess.tokens)} tokens, {total_before} AST nodes cached")

banner("2. Change detector")
info = summarize(old_src, new_src)
print(mark_region(old_src, info["editStart"], info["old_editEnd"]))
print("->")
print(mark_region(new_src, info["editStart"], info["new_editEnd"]))

banner("3. Incremental update")
stats = sess.update(new_src)
print(f"tokens re-lexed : {stats['tokens_relexed']} of {stats['tokens_total']}")
print(f"nodes rebuilt   : {stats['nodes_rebuilt']} of {count_nodes(sess.ast)}")
print(f"full re-parse fallback used: {stats['fallback']}")
print(f"time: diff {stats['diff_ms']:.3f} ms | lex {stats['lex_ms']:.3f} ms | parse {stats['parse_ms']:.3f} ms")

banner("4. AST after the edit  (green = reused from cache, red = rebuilt)")
print_diff_ast(sess.ast, sess.last_rebuilt)

# proof of correctness
from lexer import tokenize
from parser import parse
from tests import dump, tok_key
ref = parse(tokenize(new_src))
assert dump(ref) == dump(sess.ast) and tok_key(tokenize(new_src)) == tok_key(sess.tokens)
print("\nVERIFIED: incremental result is identical to a full re-lex + re-parse.")
