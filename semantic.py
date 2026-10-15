"""
semantic.py  -  change-scoped semantic analysis (Phase 3)

Checks performed
  * declared-before-use            (variables)
  * redeclaration in the same scope
  * type checking: int / bool expressions, conditions must be bool,
    arithmetic needs int, && || ! need bool, == != need matching types
  * calls: only the built-in print(x) exists; wrong arity / unknown function
  * division by a literal zero

Scopes: Program = global scope; every { } block opens a nested scope.

INCREMENTAL DESIGN  (the "dependency-aware" part)
  The unit of work is a TOP-LEVEL statement.  For each one we cache
        diags      - the errors found inside it
        free       - names it uses from OUTSIDE itself (i.e. from the global scope)
        decl       - the global name it declares (only `int x = ...;` at top level)
  and an index  users[name] -> {top-level statements whose result depends on `name`}.

  After an edit the parser tells us which top-level statements were removed / added.
  We then re-check only
        1. the added / modified statements, and
        2. the statements in users[n] for every name n whose global declaration was
           added or removed by this edit  (their answer may have changed).
  Everything else keeps its cached result.
"""

from parser import (Program, Block, VarDecl, Assignment, IfStmt, WhileStmt, ExprStmt,
                    BinaryExpr, UnaryExpr, Identifier, Literal, Call)

INT, BOOL, ERR = "int", "bool", "?"
BUILTINS = {"print": 1}                    # name -> number of arguments


class Diagnostic:
    __slots__ = ("node", "message")

    def __init__(self, node, message):
        self.node = node
        self.message = message

    def key(self):
        return (self.node.start, self.node.end, self.message)


class StmtInfo:
    __slots__ = ("stmt", "diags", "free", "decl")

    def __init__(self, stmt, diags, free, decl):
        self.stmt, self.diags, self.free, self.decl = stmt, diags, free, decl


# ---------------------------------------------------------------- analysis of ONE top-level statement
class _Analyzer:
    def __init__(self, is_global_declared):
        self.is_global = is_global_declared      # name -> was it declared at global level BEFORE this stmt?
        self.scopes = []                         # local scopes opened by { } inside this statement
        self.diags = []
        self.free = set()
        self.decl = None

    def err(self, node, msg):
        self.diags.append(Diagnostic(node, msg))

    def resolve(self, name):
        for sc in reversed(self.scopes):
            if name in sc:
                return True
        self.free.add(name)                      # depends on the global scope
        return self.is_global(name)

    # ---- expressions: return INT, BOOL or ERR (ERR = already reported, stay quiet)
    def expr(self, n):
        if isinstance(n, Literal):
            return BOOL if isinstance(n.value, str) else INT
        if isinstance(n, Identifier):
            if self.resolve(n.name):
                return INT
            self.err(n, f"undeclared variable '{n.name}' (declare it first, e.g. 'int {n.name} = 0;')")
            return ERR
        if isinstance(n, Call):
            for a in n.args:
                self.expr(a)
            if n.callee not in BUILTINS:
                self.err(n, f"call to undeclared function '{n.callee}' (only print(...) is built in)")
            elif len(n.args) != BUILTINS[n.callee]:
                self.err(n, f"'{n.callee}' expects {BUILTINS[n.callee]} argument(s) but got {len(n.args)}")
            return INT
        if isinstance(n, UnaryExpr):
            t = self.expr(n.operand)
            if n.op == "-":
                if t == BOOL:
                    self.err(n, "operator '-' needs an int operand but got bool")
                return INT
            if t == INT:
                self.err(n, "operator '!' needs a bool operand but got int")
            return BOOL
        if isinstance(n, BinaryExpr):
            lt, rt = self.expr(n.left), self.expr(n.right)
            op = n.op
            if op in ("+", "-", "*", "/", "<", ">", "<=", ">="):
                if BOOL in (lt, rt):
                    self.err(n, f"operator '{op}' needs int operands but got {lt} and {rt}")
                if op == "/" and isinstance(n.right, Literal) and not isinstance(n.right.value, str) and n.right.value == 0:
                    self.err(n.right, "division by zero")
                return INT if op in ("+", "-", "*", "/") else BOOL
            if op in ("==", "!="):
                if ERR not in (lt, rt) and lt != rt:
                    self.err(n, f"cannot compare {lt} with {rt} using '{op}'")
                return BOOL
            # && ||
            if INT in (lt, rt):
                self.err(n, f"operator '{op}' needs bool operands but got {lt} and {rt}")
            return BOOL
        return ERR

    # ---- statements
    def stmt(self, n):
        if isinstance(n, VarDecl):
            t = self.expr(n.init)
            if t == BOOL:
                self.err(n.init, f"cannot initialize int variable '{n.name}' with a bool expression")
            if not self.scopes:                              # global declaration
                self.free.add(n.name)                        # redeclaration check depends on earlier decls
                self.decl = n.name
                if self.is_global(n.name):
                    self.err(n, f"redeclaration of '{n.name}' (already declared in this scope)")
            else:
                if n.name in self.scopes[-1]:
                    self.err(n, f"redeclaration of '{n.name}' (already declared in this block)")
                self.scopes[-1].add(n.name)
        elif isinstance(n, Assignment):
            if not self.resolve(n.name):
                self.err(n, f"assignment to undeclared variable '{n.name}'")
            t = self.expr(n.value)
            if t == BOOL:
                self.err(n.value, f"cannot assign a bool value to int variable '{n.name}'")
        elif isinstance(n, (IfStmt, WhileStmt)):
            kind = "if" if isinstance(n, IfStmt) else "while"
            t = self.expr(n.cond)
            if t == INT:
                self.err(n.cond, f"condition of '{kind}' must be bool but got int (try a comparison like x != 0)")
            if isinstance(n, IfStmt):
                self.stmt(n.then_block)
                if n.else_block is not None:
                    self.stmt(n.else_block)
            else:
                self.stmt(n.body)
        elif isinstance(n, Block):
            self.scopes.append(set())
            for s in n.stmts:
                self.stmt(s)
            self.scopes.pop()
        elif isinstance(n, ExprStmt):
            self.expr(n.expr)


def analyze_stmt(stmt, is_global_declared):
    a = _Analyzer(is_global_declared)
    a.stmt(stmt)
    return StmtInfo(stmt, a.diags, a.free, a.decl)


# ---------------------------------------------------------------- REFERENCE: simple full analysis
def analyze_full(ast):
    """Straightforward whole-program analysis (used as the baseline and as the test oracle)."""
    names, out = set(), []
    for s in ast.stmts:
        info = analyze_stmt(s, lambda n: n in names)
        out.extend(info.diags)
        if info.decl:
            names.add(info.decl)
    return sorted(out, key=Diagnostic.key)


# ---------------------------------------------------------------- INCREMENTAL: cache + dependency index
class SemanticCache:
    def __init__(self):
        self.reset()

    def reset(self):
        self.meta = {}          # id(stmt)  -> StmtInfo
        self.users = {}         # name      -> set(id(stmt))   statements whose result depends on name
        self.decls = {}         # name      -> [top-level VarDecl stmts], kept in program order
        self.with_diags = {}    # id(stmt)  -> StmtInfo  (only those that have errors)

    # -- global declaration index
    def _declared_before(self, name, stmt):
        lst = self.decls.get(name)
        return bool(lst) and lst[0].start < stmt.start

    def _add_decl(self, stmt):
        lst = self.decls.setdefault(stmt.name, [])
        lo, hi = 0, len(lst)
        while lo < hi:                                   # insert in position order
            mid = (lo + hi) // 2
            if lst[mid].start < stmt.start:
                lo = mid + 1
            else:
                hi = mid
        lst.insert(lo, stmt)

    def _remove_decl(self, stmt):
        lst = self.decls.get(stmt.name, [])
        for i, s in enumerate(lst):
            if s is stmt:
                del lst[i]
                break
        if not lst:
            self.decls.pop(stmt.name, None)

    # -- per-statement analysis + bookkeeping
    def _analyze(self, stmt):
        info = analyze_stmt(stmt, lambda n: self._declared_before(n, stmt))
        self.meta[id(stmt)] = info
        for n in info.free:
            self.users.setdefault(n, set()).add(id(stmt))
        if info.diags:
            self.with_diags[id(stmt)] = info
        else:
            self.with_diags.pop(id(stmt), None)

    def _forget(self, stmt):
        info = self.meta.pop(id(stmt), None)
        if info is None:
            return None
        for n in info.free:
            u = self.users.get(n)
            if u:
                u.discard(id(stmt))
                if not u:
                    self.users.pop(n, None)
        self.with_diags.pop(id(stmt), None)
        return info

    # -- public API
    def rebuild(self, ast):
        """Analyze everything (first run, or after a full re-parse)."""
        self.reset()
        for s in ast.stmts:
            if isinstance(s, VarDecl):
                self._add_decl(s)
        for s in ast.stmts:
            self._analyze(s)
        return len(ast.stmts)

    def update(self, removed, added):
        """Re-check only what the edit can have changed. Returns number of statements re-analyzed."""
        dirty = set()
        for s in removed:
            self._forget(s)
            if isinstance(s, VarDecl):
                self._remove_decl(s)
                dirty.add(s.name)
        for s in added:
            if isinstance(s, VarDecl):
                self._add_decl(s)
                dirty.add(s.name)
        done = set()
        for s in added:                                   # 1. new / modified statements
            if id(s) not in done:
                self._analyze(s)
                done.add(id(s))
        for n in dirty:                                   # 2. statements that depend on a changed declaration
            for sid in list(self.users.get(n, ())):
                if sid not in done and sid in self.meta:
                    self._analyze(self.meta[sid].stmt)
                    done.add(sid)
        return len(done)

    def diagnostics(self):
        out = []
        for info in self.with_diags.values():
            out.extend(info.diags)
        return sorted(out, key=Diagnostic.key)
