"""
diff_tool.py -- hand-rolled longest-common-prefix / longest-common-suffix
diff to locate the changed character span between an old and a new
version of the source (report Section 9, step 2; Section 11, "Change
detection"). No external diff library is used.

Given old_src and new_src, compute_edit_span returns:
    editStart   -- offset (shared by both strings) where they first differ
    old_editEnd -- offset in old_src where the common suffix begins
    new_editEnd -- offset in new_src where the common suffix begins

Everything before editStart and everything from *_editEnd onward is
identical between the two versions; the region in between is what was
actually edited.
"""


def compute_edit_span(old_src: str, new_src: str):
    old_len = len(old_src)
    new_len = len(new_src)
    max_common = min(old_len, new_len)

    # Longest common prefix
    lcp = 0
    while lcp < max_common and old_src[lcp] == new_src[lcp]:
        lcp += 1

    # Longest common suffix, but never allowed to overlap back past the LCP
    lcs = 0
    while (
        lcs < max_common - lcp
        and old_src[old_len - 1 - lcs] == new_src[new_len - 1 - lcs]
    ):
        lcs += 1

    edit_start = lcp
    old_edit_end = old_len - lcs
    new_edit_end = new_len - lcs
    return edit_start, old_edit_end, new_edit_end


def mark_region(src: str, start: int, end: int) -> str:
    """Return src with the [start:end) span wrapped in >>> <<< markers, for display."""
    return f"{src[:start]}>>>{src[start:end]}<<<{src[end:]}"


def summarize(old_src, new_src):
    edit_start, old_end, new_end = compute_edit_span(old_src, new_src)
    changed_old = old_end - edit_start
    changed_new = new_end - edit_start
    pct = (max(changed_old, changed_new) / max(len(old_src), 1)) * 100
    return {
        "editStart": edit_start,
        "old_editEnd": old_end,
        "new_editEnd": new_end,
        "old_len": len(old_src),
        "new_len": len(new_src),
        "chars_removed": changed_old,
        "chars_inserted": changed_new,
        "pct_of_file_changed": pct,
    }
