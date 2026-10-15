"""
pipeline.py  -  the full (non-incremental) front end as ONE call. Used by the CLI 'check' command and the test suite.
"""
from lexer import tokenize, LexError
from parser import parse, ParseError
from semantic import analyze_full
from errors import describe_exception, describe_diagnostic


class Result:
    def __init__(self, status, messages, blocks, tokens=None, ast=None):
        self.status = status          # "ok" | "lexical" | "syntax" | "semantic"
        self.messages = messages      # short messages
        self.blocks = blocks          # formatted, with source caret
        self.tokens, self.ast = tokens, ast


def compile_source(src, filename=None):
    try:
        tokens = tokenize(src)
    except LexError as e:
        m, b = describe_exception(e, src, filename)
        return Result("lexical", [m], [b])
    try:
        ast = parse(tokens)
    except ParseError as e:
        m, b = describe_exception(e, src, filename)
        return Result("syntax", [m], [b], tokens)
    diags = analyze_full(ast)
    if diags:
        return Result("semantic", [d.message for d in diags], [describe_diagnostic(d, src, filename) for d in diags], tokens, ast)
    return Result("ok", [], [], tokens, ast)
