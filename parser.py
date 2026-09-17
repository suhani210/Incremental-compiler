"""
parser.py -- recursive-descent parser that builds an AST from the token
stream produced by lexer.py.

Every AST node is tagged with a (start, end) character span covering all
the tokens it was built from. That tagging is the hook the incremental
parser (Phase 2/3) will use to find "the smallest subtree whose token
span fully contains the affected tokens" (see report, Section 9, step 4).

Grammar (informal, EBNF-ish):

    program    := stmt* EOF
    stmt       := vardecl | ifstmt | whilestmt | block | exprstmt
    vardecl    := 'int' IDENT '=' expr ';'
    ifstmt     := 'if' '(' expr ')' block ('else' block)?
    whilestmt  := 'while' '(' expr ')' block
    block      := '{' stmt* '}'
    exprstmt   := (IDENT '=' expr | expr) ';'
    expr       := or_expr
    or_expr    := and_expr ('||' and_expr)*
    and_expr   := cmp_expr ('&&' cmp_expr)*
    cmp_expr   := add_expr (('<'|'>'|'<='|'>='|'=='|'!=') add_expr)*
    add_expr   := mul_expr (('+'|'-') mul_expr)*
    mul_expr   := unary (('*'|'/') unary)*
    unary      := ('-'|'!') unary | primary
    primary    := NUMBER | IDENT | IDENT '(' args ')' | '(' expr ')'
"""


class Node:
    """Base AST node. `start`/`end` are character offsets into the source."""
    def __init__(self, start, end):
        self.start = start
        self.end = end

    def label(self):
        raise NotImplementedError

    def children(self):
        return []


class Program(Node):
    def __init__(self, stmts, start, end):
        super().__init__(start, end)
        self.stmts = stmts

    def label(self):
        return "Program"

    def children(self):
        return [(f"stmt{i}", s) for i, s in enumerate(self.stmts)]


class VarDecl(Node):
    def __init__(self, name, init, start, end):
        super().__init__(start, end)
        self.name = name
        self.init = init

    def label(self):
        return f"VarDecl(name={self.name!r})"

    def children(self):
        return [("init", self.init)]


class Assignment(Node):
    def __init__(self, name, op, value, start, end):
        super().__init__(start, end)
        self.name = name
        self.op = op
        self.value = value

    def label(self):
        return f"Assignment(name={self.name!r})"

    def children(self):
        return [("value", self.value)]


class IfStmt(Node):
    def __init__(self, cond, then_block, else_block, start, end):
        super().__init__(start, end)
        self.cond = cond
        self.then_block = then_block
        self.else_block = else_block

    def label(self):
        return "IfStmt"

    def children(self):
        out = [("cond", self.cond), ("then", self.then_block)]
        if self.else_block is not None:
            out.append(("else", self.else_block))
        return out


class WhileStmt(Node):
    def __init__(self, cond, body, start, end):
        super().__init__(start, end)
        self.cond = cond
        self.body = body

    def label(self):
        return "WhileStmt"

    def children(self):
        return [("cond", self.cond), ("body", self.body)]


class Block(Node):
    def __init__(self, stmts, start, end):
        super().__init__(start, end)
        self.stmts = stmts

    def label(self):
        return "Block"

    def children(self):
        return [(f"stmt{i}", s) for i, s in enumerate(self.stmts)]


class ExprStmt(Node):
    def __init__(self, expr, start, end):
        super().__init__(start, end)
        self.expr = expr

    def label(self):
        return "ExprStmt"

    def children(self):
        return [("expr", self.expr)]


class BinaryExpr(Node):
    def __init__(self, op, left, right, start, end):
        super().__init__(start, end)
        self.op = op
        self.left = left
        self.right = right

    def label(self):
        return f"BinaryExpr(op={self.op!r})"

    def children(self):
        return [("left", self.left), ("right", self.right)]


class UnaryExpr(Node):
    def __init__(self, op, operand, start, end):
        super().__init__(start, end)
        self.op = op
        self.operand = operand

    def label(self):
        return f"UnaryExpr(op={self.op!r})"

    def children(self):
        return [("operand", self.operand)]


class Identifier(Node):
    def __init__(self, name, start, end):
        super().__init__(start, end)
        self.name = name

    def label(self):
        return f"Identifier(name={self.name!r})"


class Literal(Node):
    def __init__(self, value, start, end):
        super().__init__(start, end)
        self.value = value

    def label(self):
        return f"Literal(value={self.value})"


class Call(Node):
    def __init__(self, callee, args, start, end):
        super().__init__(start, end)
        self.callee = callee
        self.args = args

    def label(self):
        return f"Call(callee={self.callee!r})"

    def children(self):
        return [(f"arg{i}", a) for i, a in enumerate(self.args)]


class ParseError(Exception):
    pass


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    # ---- token stream helpers ----
    def peek(self, offset=0):
        return self.tokens[min(self.pos + offset, len(self.tokens) - 1)]

    def advance(self):
        tok = self.tokens[self.pos]
        if tok.type != "EOF":
            self.pos += 1
        return tok

    def check(self, type_, value=None):
        tok = self.peek()
        if tok.type != type_:
            return False
        if value is not None and tok.value != value:
            return False
        return True

    def expect(self, type_, value=None):
        if not self.check(type_, value):
            tok = self.peek()
            expected = value if value is not None else type_
            raise ParseError(
                f"Expected {expected!r} but got {tok.type} {tok.value!r} "
                f"at offset {tok.start}, line {tok.line}"
            )
        return self.advance()

    # ---- grammar rules ----
    def parse_program(self):
        start = self.peek().start
        stmts = []
        while not self.check("EOF"):
            stmts.append(self.parse_stmt())
        end = self.tokens[-1].end if self.tokens else start
        return Program(stmts, start, end)

    def parse_stmt(self):
        if self.check("KEYWORD", "int"):
            return self.parse_vardecl()
        if self.check("KEYWORD", "if"):
            return self.parse_if()
        if self.check("KEYWORD", "while"):
            return self.parse_while()
        if self.check("PUNCT", "{"):
            return self.parse_block()
        return self.parse_exprstmt()

    def parse_vardecl(self):
        start_tok = self.expect("KEYWORD", "int")
        name_tok = self.expect("IDENT")
        self.expect("OP", "=")
        init = self.parse_expr()
        end_tok = self.expect("PUNCT", ";")
        return VarDecl(name_tok.value, init, start_tok.start, end_tok.end)

    def parse_if(self):
        start_tok = self.expect("KEYWORD", "if")
        self.expect("PUNCT", "(")
        cond = self.parse_expr()
        self.expect("PUNCT", ")")
        then_block = self.parse_block()
        else_block = None
        end = then_block.end
        if self.check("KEYWORD", "else"):
            self.advance()
            else_block = self.parse_block()
            end = else_block.end
        return IfStmt(cond, then_block, else_block, start_tok.start, end)

    def parse_while(self):
        start_tok = self.expect("KEYWORD", "while")
        self.expect("PUNCT", "(")
        cond = self.parse_expr()
        self.expect("PUNCT", ")")
        body = self.parse_block()
        return WhileStmt(cond, body, start_tok.start, body.end)

    def parse_block(self):
        start_tok = self.expect("PUNCT", "{")
        stmts = []
        while not self.check("PUNCT", "}"):
            stmts.append(self.parse_stmt())
        end_tok = self.expect("PUNCT", "}")
        return Block(stmts, start_tok.start, end_tok.end)

    def parse_exprstmt(self):
        # Disambiguate `IDENT = expr ;` (assignment) from a bare expression stmt.
        if self.check("IDENT") and self.peek(1).type == "OP" and self.peek(1).value == "=":
            name_tok = self.advance()
            op_tok = self.advance()
            value = self.parse_expr()
            end_tok = self.expect("PUNCT", ";")
            return Assignment(name_tok.value, op_tok.value, value, name_tok.start, end_tok.end)

        start = self.peek().start
        expr = self.parse_expr()
        end_tok = self.expect("PUNCT", ";")
        return ExprStmt(expr, start, end_tok.end)

    def parse_expr(self):
        return self.parse_or()

    def parse_or(self):
        node = self.parse_and()
        while self.check("OP", "||"):
            op = self.advance().value
            right = self.parse_and()
            node = BinaryExpr(op, node, right, node.start, right.end)
        return node

    def parse_and(self):
        node = self.parse_cmp()
        while self.check("OP", "&&"):
            op = self.advance().value
            right = self.parse_cmp()
            node = BinaryExpr(op, node, right, node.start, right.end)
        return node

    def parse_cmp(self):
        node = self.parse_add()
        while self.peek().type == "OP" and self.peek().value in ("<", ">", "<=", ">=", "==", "!="):
            op = self.advance().value
            right = self.parse_add()
            node = BinaryExpr(op, node, right, node.start, right.end)
        return node

    def parse_add(self):
        node = self.parse_mul()
        while self.peek().type == "OP" and self.peek().value in ("+", "-"):
            op = self.advance().value
            right = self.parse_mul()
            node = BinaryExpr(op, node, right, node.start, right.end)
        return node

    def parse_mul(self):
        node = self.parse_unary()
        while self.peek().type == "OP" and self.peek().value in ("*", "/"):
            op = self.advance().value
            right = self.parse_unary()
            node = BinaryExpr(op, node, right, node.start, right.end)
        return node

    def parse_unary(self):
        if self.peek().type == "OP" and self.peek().value in ("-", "!"):
            op_tok = self.advance()
            operand = self.parse_unary()
            return UnaryExpr(op_tok.value, operand, op_tok.start, operand.end)
        return self.parse_primary()

    def parse_primary(self):
        tok = self.peek()

        if tok.type == "NUMBER":
            self.advance()
            return Literal(int(tok.value), tok.start, tok.end)

        if tok.type == "KEYWORD" and tok.value in ("true", "false"):
            self.advance()
            return Literal(tok.value, tok.start, tok.end)

        if tok.type == "IDENT":
            # function call: IDENT '(' args ')'
            if self.peek(1).type == "PUNCT" and self.peek(1).value == "(":
                name_tok = self.advance()
                self.expect("PUNCT", "(")
                args = []
                if not self.check("PUNCT", ")"):
                    args.append(self.parse_expr())
                    while self.check("PUNCT", ","):
                        self.advance()
                        args.append(self.parse_expr())
                end_tok = self.expect("PUNCT", ")")
                return Call(name_tok.value, args, name_tok.start, end_tok.end)
            self.advance()
            return Identifier(tok.value, tok.start, tok.end)

        if tok.type == "PUNCT" and tok.value == "(":
            self.advance()
            expr = self.parse_expr()
            self.expect("PUNCT", ")")
            return expr
        raise ParseError(f"Unexpected token {tok.type} {tok.value!r} at offset {tok.start}, line {tok.line}")


def parse(tokens):
    return Parser(tokens).parse_program()


def print_ast(node, indent=0, prefix=""):
    pad = "  " * indent
    tag = f"{prefix}: " if prefix else ""
    print(f"{pad}{tag}{node.label()} [{node.start}:{node.end}]")
    for child_prefix, child in node.children():
        print_ast(child, indent + 1, child_prefix)
