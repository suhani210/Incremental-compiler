"""
incremental.py  -  the CACHE STORE + driver that ties everything together.

    s = IncrementalSession(source)      # one full lex + parse, cached
    stats = s.update(new_source)        # incremental lex + parse, cache updated
"""

import time
from lexer import tokenize
from parser import parse, ParseError
from diff_tool import compute_edit_span
from incremental_lexer import relex
from incremental_parser import reparse, count_nodes


class IncrementalSession:
    def __init__(self, src):
        self.src = src
        self.tokens = tokenize(src)
        self.ast = parse(self.tokens)
        self.last_rebuilt = set()
        self.last_info = {}

    # edit given as an explicit (start, end, replacement) range, like an editor would send
    def apply_edit(self, start, end, replacement):
        new_src = self.src[:start] + replacement + self.src[end:]
        return self.update(new_src, edit=(start, end, start + len(replacement)))

    def update(self, new_src, edit=None):
        t0 = time.perf_counter()
        if new_src == self.src:
            return {"noop": True}
        if edit is None:
            edit = compute_edit_span(self.src, new_src)      # step 2: diff
        t1 = time.perf_counter()

        old_src = self.src
        dirty = relex(old_src, new_src, self.tokens, edit)   # step 3: re-lex  (LexError -> nothing changed)
        self.src = new_src
        t2 = time.perf_counter()

        try:
            if self.ast is None:                             # previous version was invalid
                self.ast = parse(self.tokens)
                from incremental_parser import _all_nodes
                rebuilt, info = set(), {"fallback": True, "level": -1}
                _all_nodes(self.ast, rebuilt)
            else:
                self.ast, rebuilt, info = reparse(self.ast, self.tokens, dirty)   # step 4: re-parse
        except ParseError:
            self.ast = None                                  # tokens are fresh, tree is stale
            raise
        t3 = time.perf_counter()

        self.last_rebuilt = rebuilt
        self.last_info = info
        return {
            "noop": False,
            "tokens_total": len(self.tokens), "tokens_relexed": dirty["relexed"],
            "nodes_rebuilt": len(rebuilt), "fallback": info["fallback"],
            "diff_ms": (t1 - t0) * 1e3, "lex_ms": (t2 - t1) * 1e3, "parse_ms": (t3 - t2) * 1e3,
            "total_ms": (t3 - t0) * 1e3,
        }
