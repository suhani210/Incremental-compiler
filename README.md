# Incremental Lexical, Syntax and Semantic Analyzer

A compiler front end for a small C-like language that **re-does only the work an edit made necessary**.
After an edit it re-lexes only the touched lines, re-parses only the affected statements, and re-checks
only the statements whose meaning can have changed. Everything else is reused from a cache.

Course: Compiler Design Laboratory  |  Author: Suhani Chauhan (24BKT0153)

## 1. Requirements
* Python 3.8 or newer (no other packages needed to run the compiler or tests)
* Optional, for benchmark graphs only: `pip install matplotlib numpy`

## 2. Files

| File | Role |
|---|---|
| `lexer.py` | full lexer: source -> tokens |
| `parser.py` | recursive-descent parser: tokens -> AST (every node has `[start:end]`) |
| `diff_tool.py` | change detector: longest common prefix/suffix -> edit span |
| `incremental_lexer.py` | re-lexes only the dirty lines, shifts the rest |
| `incremental_parser.py` | re-parses only the affected statements, splices into the old AST |
| `semantic.py` | scoped symbol table, type checks, dependency-aware incremental re-checking |
| `incremental.py` | `IncrementalSession`: the cache store + driver for all stages |
| `errors.py` | readable error messages with line, column and a source caret |
| `pipeline.py` | the full (non-incremental) front end as one call |
| `compiler_cli.py` | **single entry point** for the whole system |
| `tests.py` | incremental == full equivalence tests (27 cases + 6,000 random edits) |
| `test_suite.py` | 91 documented test cases; writes `test_results.txt/.csv` |
| `benchmark.py` | time vs size, time vs edit type, memory; writes graphs + CSV |
| `demo_incremental.py` | short demo: reused vs rebuilt AST |
| `samples/` | example programs (valid and with errors) |

## 3. How to run

```
python compiler_cli.py check samples/valid_program.src            # compile a file (lex + parse + semantic)
python compiler_cli.py check samples/valid_program.src --tokens --ast
python compiler_cli.py check samples/error_syntax.src             # syntax error with caret
python compiler_cli.py check samples/error_lexical.src            # lexical error
python compiler_cli.py check samples/error_semantic.src           # several semantic errors

python compiler_cli.py diff samples/sample_old.src samples/sample_new.src --tree
                                                                  # incremental update OLD -> NEW + reuse statistics

python compiler_cli.py repl samples/sample_old.src                # interactive live editor (type 'help')

python compiler_cli.py tests                                      # all tests
python compiler_cli.py bench                                      # benchmarks (graphs + CSV)
```
`check` exits with code 0 when the program is correct and 1 when errors were found.

Interactive editor commands: `show`, `replace N text`, `insert N text`, `delete N`, `undo`, `diag`, `tokens`, `ast`, `help`, `quit`.
A syntax or lexical error rejects the edit and keeps the previous valid version.

## 4. The language
```
program   -> { statement }
statement -> 'int' IDENT '=' expr ';'  |  IDENT '=' expr ';'  |  expr ';'
           | 'if' '(' expr ')' block [ 'else' block ]  |  'while' '(' expr ')' block  |  block
block     -> '{' { statement } '}'
expr      -> or-expr  (|| , && , == != , < > <= >= , + - , * / , unary - ! , primary)
primary   -> NUMBER | 'true' | 'false' | IDENT | IDENT '(' [ args ] ')' | '(' expr ')'
```
Comments: `// to end of line`. Only integer variables exist; `true`/`false` and comparisons are bool *expressions*.

## 5. Semantic rules
* a variable must be declared before use; a name cannot be declared twice in one scope (inner blocks may shadow)
* arithmetic and comparisons need `int` operands; `&&`, `||`, `!` need `bool` operands; `==`/`!=` need matching types
* `if`/`while` conditions must be `bool`; `int` variables can only hold `int` values
* the only function is the built-in `print(x)` (exactly one argument); division by a literal 0 is an error

## 6. Error messages
```
syntax error: missing ';' to end the statement (found 'int')
  --> line 1, column 10
  |
1 | int x = 5
  |          ^
```
Lexical, syntax and semantic errors all show the line, column and the offending source line. Semantic analysis
reports every error it finds; the lexer and parser stop at the first one.

## 7. How the incremental design works
1. **Diff** the old and new text -> changed span.
2. **Re-lex** only the whole lines the span touches (the lexer has no multi-line tokens, so this is exact); shift later tokens by `delta`.
3. **Re-parse** only the statements that overlap the dirty region, inside the deepest block that contains it; reuse every other node object; escalate to the parent block or a full parse if the local parse fails.
4. **Re-check** only the new/changed top-level statements plus the statements that depend on a global name whose declaration was added or removed (dependency index `name -> users`).
5. The cache (tokens, AST, symbol/dependency index) is updated; a failed edit never corrupts it.

## 8. Known limitations
* Granularity is the statement (not the expression); the diff scan and offset shifting are still O(n)
* Only one built-in function; no user-defined functions, pointers, structs or strings
* The parser stops at the first syntax error (no error recovery)
* Very deeply nested input is limited by Python recursion (the CLI raises the limit to 20,000)
