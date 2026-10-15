"""
errors.py  -  turn lexer / parser / semantic problems into readable messages with a source caret.

    error: missing ';' to end the statement
      --> line 3, column 10
       |
     3 | int x = 5
       |          ^
"""
import re


def line_col(src, offset):
    offset = max(0, min(offset, len(src)))
    line = src.count("\n", 0, offset) + 1
    col = offset - (src.rfind("\n", 0, offset) + 1) + 1
    return line, col


def _line_text(src, line):
    lines = src.split("\n")
    return lines[line - 1].rstrip("\r") if 0 < line <= len(lines) else ""


def format_diag(src, start, end, message, kind="error", filename=None):
    line, col = line_col(src, start)
    text = _line_text(src, line).replace("\t", " ")
    width = max(1, min(end - start, len(text) - col + 1)) if end > start else 1
    gutter = len(str(line))
    where = f"line {line}, column {col}"
    if filename:
        where = f"{filename}: {where}"
    return (f"{kind}: {message}\n"
            f"  --> {where}\n"
            f"{' ' * (gutter + 1)}|\n"
            f"{line:>{gutter}} | {text}\n"
            f"{' ' * (gutter + 1)}| {' ' * (col - 1)}{'^' * width}")


def _end_of_previous_token(src, offset):
    i = offset
    while i > 0 and src[i - 1] in " \t\r\n":
        i -= 1
    return i


_HINT = {
    "';'": "missing ';' to end the statement",
    "'}'": "missing '}' to close the block",
    "')'": "missing ')'",
    "'('": "expected '('",
    "'='": "expected '='",
    "'IDENT'": "expected a variable name",
}


def describe_exception(exc, src, filename=None):
    """Return (short_message, formatted_block) for a LexError or ParseError."""
    text = str(exc)
    m = re.match(r"Unexpected character (.+?) at offset (\d+), line (\d+)$", text)
    if m:
        off = int(m.group(2))
        msg = f"unexpected character {m.group(1)} (not part of the language)"
        return msg, format_diag(src, off, off + 1, msg, "lexical error", filename)
    m = re.match(r"Expected (.+?) but got (\w+) (.+?) at offset (\d+), line (\d+)$", text)
    if m:
        exp, gtype, gval, off = m.group(1), m.group(2), m.group(3), int(m.group(4))
        if gtype == "EOF":
            msg = f"unexpected end of file, " + _HINT.get(exp, f"expected {exp}")
            pos = _end_of_previous_token(src, off)
            return msg, format_diag(src, pos, pos + 1, msg, "syntax error", filename)
        msg = _HINT.get(exp, f"expected {exp}") + f" (found {gval})"
        pos = off
        if exp in ("';'", "'}'", "')'") and src.count("\n", _end_of_previous_token(src, off), off) > 0:
            pos = _end_of_previous_token(src, off)           # point at end of the previous line
            return msg, format_diag(src, pos, pos + 1, msg, "syntax error", filename)
        return msg, format_diag(src, pos, pos + len(gval) - 2, msg, "syntax error", filename)
    m = re.match(r"Unexpected token (\w+) (.+?) at offset (\d+), line (\d+)$", text)
    if m:
        off = int(m.group(3))
        gval = m.group(2)
        msg = f"unexpected {gval} here" if m.group(1) != "EOF" else "unexpected end of file (a '}', ')' or ';' is probably missing)"
        if m.group(1) == "KEYWORD" and gval == "'return'":
            msg += " ('return' is not supported by this language)"
        return msg, format_diag(src, off, off + max(1, len(gval) - 2), msg, "syntax error", filename)
    return text, f"error: {text}"


def describe_diagnostic(diag, src, filename=None):
    return format_diag(src, diag.node.start, diag.node.end, diag.message, "semantic error", filename)
