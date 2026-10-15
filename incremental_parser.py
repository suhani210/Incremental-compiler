"""
incremental_parser.py

Re-parses only the smallest region of the AST that the edit touched, keeps every
other node object (just shifting its offsets), and splices the new nodes in.

Granularity = STATEMENTS.  The "containers" are Program and Block (they hold
lists of statements).  We walk down from Program into nested Blocks as long as
the dirty region lies strictly inside ONE block, then re-parse just the
statements of that block that overlap the dirty region.

If the re-parse fails (e.g. the edit unbalanced a brace) we escalate to the
parent container, and finally to a full re-parse. Escalation never mutates the
old tree, so a failed attempt is harmless.
"""

from lexer import Token
from parser import Parser, parse, ParseError, Program, Block, IfStmt, WhileStmt


# ------------------------------------------------------------------ helpers
def _is_container(n):
    return isinstance(n, (Program, Block))


def _first_stmt_ending_at_or_after(stmts, x):
    lo, hi = 0, len(stmts)
    while lo < hi:
        mid = (lo + hi) // 2
        if stmts[mid].end < x:
            lo = mid + 1
        else:
            hi = mid
    return lo


def _first_stmt_starting_after(stmts, x):
    lo, hi = 0, len(stmts)
    while lo < hi:
        mid = (lo + hi) // 2
        if stmts[mid].start <= x:
            lo = mid + 1
        else:
            hi = mid
    return lo


def _first_stmt_starting_at_or_after(stmts, x):
    lo, hi = 0, len(stmts)
    while lo < hi:
        mid = (lo + hi) // 2
        if stmts[mid].start < x:
            lo = mid + 1
        else:
            hi = mid
    return lo


def _shift_subtree(node, delta):
    node.start += delta
    node.end += delta
    for _, c in node.children():
        _shift_subtree(c, delta)


def _all_nodes(node, out):
    out.add(id(node))
    for _, c in node.children():
        _all_nodes(c, out)


def count_nodes(node):
    return 1 + sum(count_nodes(c) for _, c in node.children())


def _blocks_of(stmt):
    """Child Blocks we are allowed to descend into."""
    if isinstance(stmt, Block):
        return [stmt]
    if isinstance(stmt, IfStmt):
        return [b for b in (stmt.then_block, stmt.else_block) if b is not None]
    if isinstance(stmt, WhileStmt):
        return [stmt.body]
    return []


def _overlap_range(container, ds, de_old):
    """
    Indices [lo, hi] of statements that overlap/touch the dirty region [ds, de_old].
    If none overlap, hi == lo-1 and lo is the insertion index.
    """
    stmts = container.stmts
    lo = _first_stmt_ending_at_or_after(stmts, ds)
    hi = _first_stmt_starting_after(stmts, de_old) - 1
    return lo, hi


def _find_path(root, ds, de_old):
    """Walk down while the dirty region is strictly inside exactly one nested Block."""
    path = [root]
    node = root
    while True:
        lo, hi = _overlap_range(node, ds, de_old)
        if lo != hi:                      # none or several statements overlap -> stop
            break
        stmt = node.stmts[lo]
        descended = False
        for b in _blocks_of(stmt):
            # strictly inside the braces
            if ds > b.start and de_old < b.end - 1:
                if b is not stmt:
                    path.append(stmt)     # the If/While node itself
                path.append(b)
                node = b
                descended = True
                break
        if not descended:
            break
    return path


def _parse_range(tokens, range_start, range_end_new):
    """Parse the tokens that lie inside [range_start, range_end_new) as a statement list."""
    from incremental_lexer import _lower_bound
    i0 = _lower_bound(tokens, range_start)
    i1 = _lower_bound(tokens, range_end_new)
    sl = tokens[i0:i1]
    line = sl[-1].line if sl else 1
    p = Parser(sl + [Token("EOF", "", range_end_new, range_end_new, line)])
    stmts = []
    while not p.check("EOF"):
        stmts.append(p.parse_stmt())
    return stmts


# ------------------------------------------------------------------ main API
def reparse(ast, tokens, dirty):
    """
    ast    : cached AST for the OLD source                   (MODIFIED IN PLACE on success)
    tokens : token list for the NEW source (already updated by incremental_lexer.relex)
    dirty  : dict returned by relex()

    Returns (ast, rebuilt_ids, info).  rebuilt_ids = ids of the brand-new nodes.
    Raises ParseError if the new source is not valid (ast is left untouched).
    """
    ds, de_old, delta = dirty["ds"], dirty["de_old"], dirty["delta"]
    path = _find_path(ast, ds, de_old)

    # try the deepest container first, then escalate upwards
    for k in range(len(path) - 1, -1, -1):
        container = path[k]
        if not _is_container(container):
            continue
        lo, hi = _overlap_range(container, ds, de_old)

        # old range covered by the statements being replaced (+ the dirty region)
        if hi >= lo:
            range_start = min(container.stmts[lo].start, ds)
            range_end_old = max(container.stmts[hi].end, de_old)
        else:
            range_start, range_end_old = ds, de_old
        range_end_new = range_end_old + delta

        try:
            new_stmts = _parse_range(tokens, range_start, range_end_new)
        except ParseError:
            continue                      # escalate one level up

        # ---- success: now (and only now) mutate the old tree ----
        # (a) ancestors on the path: their end moves, and any child AFTER the edit shifts
        for j in range(k + 1):
            node = path[j]
            node.end += delta
            if j < k:
                nxt = path[j + 1]
                if _is_container(node):
                    idx = _first_stmt_starting_at_or_after(node.stmts, de_old)
                    for s in node.stmts[idx:]:
                        if s is not nxt:
                            _shift_subtree(s, delta)
                else:  # IfStmt / WhileStmt
                    for _, c in node.children():
                        if c is not nxt and c.start >= de_old:
                            _shift_subtree(c, delta)
        # (b) siblings after the replaced range inside the target container
        for s in container.stmts[hi + 1:]:
            _shift_subtree(s, delta)
        # (c) splice the freshly parsed statements in
        old_stmts = container.stmts[lo:hi + 1]
        container.stmts[lo:hi + 1] = new_stmts
        if k == 0:                                   # top-level statements replaced
            top_removed, top_added = old_stmts, list(new_stmts)
        else:                                        # a top-level compound statement changed in place
            top_removed, top_added = [path[1]], [path[1]]

        # Program's own span always follows the token stream
        ast.start = tokens[0].start
        ast.end = tokens[-1].end

        rebuilt = set()
        for n in new_stmts:
            _all_nodes(n, rebuilt)
        return ast, rebuilt, {"fallback": False, "level": k, "stmts_reparsed": len(new_stmts),
                              "stmts_replaced": max(hi - lo + 1, 0),
                              "top_removed": top_removed, "top_added": top_added}

    # nothing worked -> full re-parse (raises ParseError if the source is invalid)
    old_top = list(ast.stmts)
    new_ast = parse(tokens)
    rebuilt = set()
    _all_nodes(new_ast, rebuilt)
    return new_ast, rebuilt, {"fallback": True, "level": -1,
                              "stmts_reparsed": len(new_ast.stmts), "stmts_replaced": len(old_top),
                              "top_removed": old_top, "top_added": list(new_ast.stmts)}
