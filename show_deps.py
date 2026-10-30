"""
show_deps.py - prints the dependency-aware symbol table kept by SemanticCache.

  python show_deps.py FILE                 show the tables for one file
  python show_deps.py OLD NEW              show the tables, apply the edit OLD -> NEW incrementally, show them again
"""
import sys
sys.setrecursionlimit(20000)
from incremental import IncrementalSession
from errors import line_col


def ln(sess, stmt):
    return line_col(sess.src, stmt.start)[0]


def show(sess, title):
    sem = sess.sem
    print("=" * 66)
    print(title)
    print("=" * 66)

    print("\n1. Global symbol table (name -> declared at)")
    if not sem.decls:
        print("   (no global declarations)")
    for name, lst in sorted(sem.decls.items()):
        print(f"   {name:<10} line {', '.join(str(ln(sess, s)) for s in lst)}")

    print("\n2. Dependency index (name -> statements whose result depends on it)")
    if not sem.users:
        print("   (empty)")
    for name, ids in sorted(sem.users.items()):
        stmts = sorted((sem.meta[i].stmt for i in ids if i in sem.meta), key=lambda s: s.start)
        print(f"   {name:<10} used by " + ", ".join(f"{s.label()} (line {ln(sess, s)})" for s in stmts))

    print("\n3. Per-statement analysis (cached)")
    print(f"   {'line':<6}{'statement':<26}{'depends on':<16}{'declares':<10}errors")
    for s in sess.ast.stmts:
        info = sem.meta.get(id(s))
        if info:
            print(f"   {ln(sess, s):<6}{s.label():<26}{', '.join(sorted(info.free)) or '-':<16}{info.decl or '-':<10}{len(info.diags)}")
    print()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    old = open(sys.argv[1], encoding="utf-8").read()
    sess = IncrementalSession(old)
    show(sess, f"BEFORE: {sys.argv[1]}")
    if len(sys.argv) > 2:
        new = open(sys.argv[2], encoding="utf-8").read()
        st = sess.update(new)
        print(f">>> incremental update: {st['stmts_rechecked']} of {st['stmts_total']} statements re-checked "
              f"(only the changed ones and those that depend on a changed declaration)\n")
        show(sess, f"AFTER: {sys.argv[2]}")
        for d in sess.diagnostics():
            print(f"semantic error: {d.message}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
