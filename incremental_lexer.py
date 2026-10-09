"""
incremental_lexer.py
"""

from lexer import tokenize


def _lower_bound(tokens, x):
    """Index of the first token whose .start >= x (binary search, O(log n))."""
    lo, hi = 0, len(tokens)
    while lo < hi:
        mid = (lo + hi) // 2
        if tokens[mid].start < x:
            lo = mid + 1
        else:
            hi = mid
    return lo


def relex(old_src, new_src, tokens, edit):
    """
    old_src, new_src : source before / after the edit
    tokens           : cached token list for old_src  (MODIFIED IN PLACE)
    edit             : (edit_start, old_end, new_end)  e.g. from diff_tool

    Returns a dict describing the "dirty region" (used by the parser too):
        ds        : dirty start offset (same in old and new source)
        de_old    : dirty end offset in the OLD source
        de_new    : dirty end offset in the NEW source
        delta     : de_new - de_old  (how much everything after the edit moved)
        relexed   : how many tokens were produced again
        reused    : how many tokens were kept
    """
    edit_start, old_end, new_end = edit
    delta = new_end - old_end

    # 1. Grow the edit to whole lines of the NEW source.
    ds = new_src.rfind("\n", 0, edit_start) + 1            # start of first dirty line
    nl = new_src.find("\n", new_end)
    de_new = len(new_src) if nl == -1 else nl                # end of last dirty line
    de_old = de_new - delta                                  # same place in OLD source

    # 2. Split the cached tokens into  prefix | middle (dirty) | suffix.
    lo = _lower_bound(tokens, ds)
    hi = _lower_bound(tokens, de_old)

    # 3. Re-lex only the dirty lines. (Done BEFORE touching the cache, so if the
    #    new text has a lex error nothing is corrupted.)
    first_line = 1 + new_src.count("\n", 0, ds)
    middle = tokenize(new_src[ds:de_new])[:-1]               # drop the EOF token
    for t in middle:
        t.start += ds
        t.end += ds
        t.line += first_line - 1

    # 4. Shift every token AFTER the dirty region (reuse, don't re-lex).
    line_delta = new_src.count("\n", edit_start, new_end) - old_src.count("\n", edit_start, old_end)
    if delta or line_delta:
        for i in range(hi, len(tokens)):
            t = tokens[i]
            t.start += delta
            t.end += delta
            t.line += line_delta

    # 5. Splice the fresh tokens in.
    tokens[lo:hi] = middle

    return {
        "ds": ds, "de_old": de_old, "de_new": de_new, "delta": delta,
        "relexed": len(middle), "reused": len(tokens) - len(middle),
    }
