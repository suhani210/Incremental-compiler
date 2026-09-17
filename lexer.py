"""
lexer.py -- DFA-style hand-written lexer for the toy C-like language.

Converts a raw source string into a flat list of Token objects, each
carrying its (start, end) character offsets and its source line number.
This offset/line tagging is what the incremental lexer (Phase 2) will
later use to figure out which tokens overlap an edited character span.
"""

KEYWORDS = {"int", "if", "else", "while", "true", "false", "return"}

# Multi-char operators must be listed before their single-char prefixes.
OPERATORS = [
    "&&", "||", "==", "!=", "<=", ">=",
    "+", "-", "*", "/", "=", "<", ">", "!",
]

PUNCTUATION = set("(){};,")


class Token:
    __slots__ = ("type", "value", "start", "end", "line")

    def __init__(self, type_, value, start, end, line):
        self.type = type_
        self.value = value
        self.start = start
        self.end = end
        self.line = line

    def __repr__(self):
        return f"{self.type:<8} {self.value!r:<8} [{self.start}:{self.end}] line {self.line}"


class LexError(Exception):
    pass


def tokenize(source: str):
    """Full (non-incremental) tokenization of `source`. Returns a list of Token."""
    tokens = []
    i = 0
    n = len(source)
    line = 1

    while i < n:
        ch = source[i]

        # Track newlines for line numbers, then skip.
        if ch == "\n":
            line += 1
            i += 1
            continue

        # Skip other whitespace.
        if ch in " \t\r":
            i += 1
            continue

        # Line comments: // ...
        if ch == "/" and i + 1 < n and source[i + 1] == "/":
            while i < n and source[i] != "\n":
                i += 1
            continue

        start = i

        # Identifiers / keywords
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (source[j].isalnum() or source[j] == "_"):
                j += 1
            word = source[i:j]
            ttype = "KEYWORD" if word in KEYWORDS else "IDENT"
            tokens.append(Token(ttype, word, start, j, line))
            i = j
            continue

        # Numbers (integers only, at this project's scope)
        if ch.isdigit():
            j = i
            while j < n and source[j].isdigit():
                j += 1
            tokens.append(Token("NUMBER", source[i:j], start, j, line))
            i = j
            continue

        # Operators (check multi-char first)
        matched_op = None
        for op in OPERATORS:
            if source.startswith(op, i):
                matched_op = op
                break
        if matched_op:
            tokens.append(Token("OP", matched_op, start, start + len(matched_op), line))
            i += len(matched_op)
            continue

        # Punctuation
        if ch in PUNCTUATION:
            tokens.append(Token("PUNCT", ch, start, start + 1, line))
            i += 1
            continue

        raise LexError(f"Unexpected character {ch!r} at offset {i}, line {line}")

    tokens.append(Token("EOF", "", n, n, line))
    return tokens


def print_tokens(tokens):
    for t in tokens:
        print(f"{t.type:<8} {t.value!r:<8} [{t.start}:{t.end}] line {t.line}")
    print(f"\n{len(tokens)} tokens produced.")
