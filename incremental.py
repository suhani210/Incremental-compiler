"""
incremental.py  -  CACHE STORE + driver that ties every stage together (Phase 3: integrated system)

    s = IncrementalSession(source)      # one full lex + parse + semantic pass, all cached
    stats = s.update(new_source)        # incremental lex -> parse -> semantic; cache updated
    s.diagnostics()                     # semantic errors of the current version
"""

import time
from lexer import tokenize
from parser import parse, ParseError
from diff_tool import compute_edit_span
from incremental_lexer import relex
from incremental_parser import reparse, _all_nodes
from semantic import SemanticCache


class IncrementalSession:
    def __init__(self, src):
        self.src = src
        self.tokens = tokenize(src)
        self.ast = parse(self.tokens)
        self.sem = SemanticCache()
        self.sem.rebuild(self.ast)
        self.last_rebuilt = set()
        self.last_info = {}

    def diagnostics(self):
        return self.sem.diagnostics()

    # edit given as an explicit (start, end, replacement) range, like an editor would send
    def apply_edit(self, start, end, replacement):
        new_src = self.src[:start] + replacement + self.src[end:]
        return self.update(new_src, edit=(start, end, start + len(replacement)))

    def update(self, new_src, edit=None):
        t0 = time.perf_counter()
        if new_src == self.src:
            return {"noop": True}
        if edit is None:
            edit = compute_edit_span(self.src, new_src)      # 1. change detection
        t1 = time.perf_counter()

        dirty = relex(self.src, new_src, self.tokens, edit)  # 2. incremental lexing (LexError -> nothing changed)
        self.src = new_src
        t2 = time.perf_counter()

        try:
            if self.ast is None:                             # previous version had a syntax error
                self.ast = parse(self.tokens)
                rebuilt = set()
                _all_nodes(self.ast, rebuilt)
                info = {"fallback": True}
            else:                                            # 3. incremental parsing
                self.ast, rebuilt, info = reparse(self.ast, self.tokens, dirty)
        except ParseError:
            self.ast = None                                  # tokens are fresh, tree is stale
            raise
        t3 = time.perf_counter()

        if info["fallback"]:                                 # 4. change-scoped semantic analysis
            rechecked = self.sem.rebuild(self.ast)
        else:
            rechecked = self.sem.update(info["top_removed"], info["top_added"])
        t4 = time.perf_counter()

        self.last_rebuilt = rebuilt
        self.last_info = info
        return {
            "noop": False,
            "tokens_total": len(self.tokens), "tokens_relexed": dirty["relexed"],
            "nodes_rebuilt": len(rebuilt), "fallback": info["fallback"],
            "stmts_total": len(self.ast.stmts), "stmts_rechecked": rechecked,
            "diff_ms": (t1 - t0) * 1e3, "lex_ms": (t2 - t1) * 1e3,
            "parse_ms": (t3 - t2) * 1e3, "sem_ms": (t4 - t3) * 1e3,
            "total_ms": (t4 - t0) * 1e3,
        }
