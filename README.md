# Incremental Lexical & Syntax Analyzer

**Design and Implementation of an Incremental Lexical and Syntax Analyzer for
Reduced Recompilation Overhead**

Compiler Design Laboratory Project — Phase 1
Suhani Chauhan (24BKT0153)

## What this is

Conventional compilers re-run lexing, parsing, and semantic analysis on an
*entire* source file for every compilation request, even when only one line
changed. This project designs an incremental compiler front end that:

- Detects the minimal changed region of the source text after an edit
- Re-tokenizes only that span instead of the whole file
- Identifies the smallest AST subtree that must be rebuilt and reuses the rest
- Targets a 60–80% reduction in re-analysis time on 1,000+ line files for
  localized edits, benchmarked against full recompilation

This repository currently contains the **Phase 1 prototype**: a full
(non-incremental) lexer and recursive-descent parser for a small C-like
language, plus a working change-detector that proves edits are localized.
Incremental re-tokenization and AST subtree reuse are the Phase 2/3
deliverables.

## Project structure

```
.
├── lexer.py          # DFA-style tokenizer -> list of Token(type, value, start, end, line)
├── parser.py         # Recursive-descent parser -> position-tagged AST
├── diff_tool.py       # Hand-rolled LCP/LCS diff to locate an edit's character span
├── main.py           # Driver: runs lexer + parser + change-detector demo
└── samples/
    ├── sample.src      # Example program used for the lexer/parser demo
    ├── sample_old.src  # "Before" version for the change-detector demo
    └── sample_new.src  # "After" version (one localized edit)
```

## Language subset

Variable declarations, assignments, arithmetic and Boolean expressions,
`if`/`else`, `while`, and function calls — deliberately excludes pointers,
structs, and preprocessor directives (see report for full scope).

## Running it

Requires Python 3, no external dependencies.

```bash
python3 main.py
```

This prints three sections:
1. **Lexer** — full tokenization of `samples/sample.src`
2. **Parser** — the full AST, with every node tagged `[start:end]`
3. **Change Detector** — the character span that changed between
   `samples/sample_old.src` and `samples/sample_new.src`, proving that a
   localized edit only touches a tiny fraction of the file

## Roadmap

- [x] Phase 1 — full lexer, full parser, change-detection prototype
- [ ] Phase 2 — incremental re-tokenization, AST subtree reuse, dependency-aware
      symbol table
- [ ] Phase 3 — full incremental pipeline, benchmark suite (100–10,000 lines,
      3 edit types), final report

## License

Academic project for the Compiler Design Laboratory course. Individual work.
