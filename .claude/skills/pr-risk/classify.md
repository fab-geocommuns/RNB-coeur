# PR risk classification rules

You classify one pull request of fab-geocommuns/RNB-coeur by risk. You are read-only: use `gh pr view`, `gh pr diff`, `git fetch`, `git show` and searches; never edit a PR, a label or a file.

## Levels

Prototype: one risk level exists so far.

- **`risque bas`**: every file the PR changes is documentation (see below).

A PR that matches no level gets the verdict `none`.

## Documentation

A changed file is documentation when it is one of:

- **A Markdown file** (`*.md`), except agent instructions: `CLAUDE.md` and `AGENTS.md` at any depth, and every file under `.claude/`. Agent instructions are code.
- **The OpenAPI schema builder** `app/api_alpha/utils/rnb_doc.py`: the whole module only serves the public API doc.
- **A schema test**: `app/api_alpha/tests/**/test_*_doc.py` and `app/api_alpha/tests/test_schema*.py`.
- **A Python file whose every changed line only edits the OpenAPI schema**: a line inside an `@rnb_doc(...)` call, or an import or module constant read only by those calls, directly or through other such constants. What the calls themselves read (a serializer's `Meta.fields`, `BuildingStatus`) does not matter. Check each constant with a search in the file at the PR's head commit: a constant the request handling also reads (validation, a query, a response) makes its line code. Example: PR #1190 added `MAX_DIFF_DAYS` to the `@rnb_doc` text of `get_diff.py`, but the view's `since` validation reads it too, so the file is code.

Any other file is code.

## Steps

1. List every file the PR changes, deletions and renames included:

   ```bash
   gh pr view <number> --json files,changedFiles,headRefOid --jq '"changedFiles=\(.changedFiles) head=\(.headRefOid)", (.files[].path)'
   ```

   Done when the list length equals `changedFiles`.

2. Classify each file against "Documentation". For a Python file outside the schema builder and schema tests, read its hunks in `gh pr diff <number>`, and its full content at the head commit (`git show <head>:<path>`, after `git fetch origin` if the commit is missing) to see which `@rnb_doc(...)` call encloses a line and where a constant is read. Done when every file carries a verdict and each code verdict names the line or rule that decided it.

3. Match the verdicts against each level. A level applies only when every file satisfies it; a single code file rules it out.

## Report

Your first line is exactly `LEVEL: risque bas` or `LEVEL: none`. Then one line per code file with the line or rule that decided it, e.g. "`CLAUDE.md`: agent instructions" or "`list_create_buildings.py`: `post()` drops `with_plots=True`". For `risque bas`, one line listing the documentation files instead.
