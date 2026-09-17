"""
main.py -- Phase 1 prototype driver.

Runs the full (non-incremental) lexer and parser over samples/sample.src,
then runs the change detector over samples/sample_old.src vs
samples/sample_new.src to show that a localized edit only touches a tiny
fraction of the file. Incremental re-tokenization / subtree reuse are the
Phase 2/3 deliverables (see report Section 6, Scope).
"""

import os
from lexer import tokenize, print_tokens
from parser import parse, print_ast
import diff_tool

SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "samples")


def read_sample(name):
    with open(os.path.join(SAMPLES_DIR, name), "r") as f:
        return f.read()


def section(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def main():
    source_path = os.path.join(SAMPLES_DIR, "sample.src")

    # ---- 1. LEXER: full tokenization ----
    section("1. LEXER - full tokenization of samples/sample.src")
    src = read_sample("sample.src")
    tokens = tokenize(src)
    print_tokens(tokens)

    # ---- 2. PARSER: full AST ----
    section("2. PARSER - full AST for samples/sample.src")
    ast = parse(tokens)
    print_ast(ast)
    print(
        "\nEvery node above is tagged with its [start:end] character span - "
        "this is the position information the incremental re-parser (Phase 2/3) "
        "will use to locate 'the smallest subtree whose token span fully "
        "contains the affected tokens' (Report, Section 9, step 4)."
    )

    # ---- 3. CHANGE DETECTOR ----
    section("3. CHANGE DETECTOR - edit span between sample_old.src and sample_new.src")
    old_src = read_sample("sample_old.src")
    new_src = read_sample("sample_new.src")
    info = diff_tool.summarize(old_src, new_src)

    print("\nOLD source, changed region marked with >>> <<<:")
    print("-" * 70)
    print(diff_tool.mark_region(old_src, info["editStart"], info["old_editEnd"]))

    print("\nNEW source, changed region marked with >>> <<<:")
    print("-" * 70)
    print(diff_tool.mark_region(new_src, info["editStart"], info["new_editEnd"]))

    print("-" * 70)
    print(f"editStart      = {info['editStart']}")
    print(
        f"old editEnd    = {info['old_editEnd']}  "
        f"(old source length {info['old_len']}, {info['chars_removed']} char(s) replaced)"
    )
    print(
        f"new editEnd    = {info['new_editEnd']}  "
        f"(new source length {info['new_len']}, {info['chars_inserted']} char(s) inserted)"
    )

    print(
        f"\nOnly {info['chars_inserted']} character(s) out of {info['old_len']} changed "
        f"({info['pct_of_file_changed']:.2f}% of the file) - confirming the edit is "
        f"localized and does not require the full file to be re-tokenized/re-parsed "
        f"in the incremental design."
    )

    print(
        "\nDone. This is the Phase 1 prototype: full (non-incremental) lexer "
        "and parser, plus a working change-detection mock-up. Incremental "
        "re-tokenization and subtree reuse are Phase 2/3 deliverables."
    )


if __name__ == "__main__":
    main()
