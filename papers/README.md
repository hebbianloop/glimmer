# Glimmer papers

Submittable Glimmer manuscripts live here as **LaTeX projects** — this is the standard
moving forward. Markdown drafts (e.g. `docs/paper-draft.md`) are for fast iteration; once a
paper is heading toward a preprint or submission it is authored here in LaTeX so it is
venue-portable and citation-managed.

## Layout

```
papers/
├── glimmer-paper.cls                 # the house document class (the standard)
├── 01-knowledge-graph-navigation/    # Paper 1 — the graph layer (through v0.5)
│   ├── main.tex   refs.bib   Makefile
└── 02-proactive-provenance/          # Paper 2 — the executable runner (v0.6)
    ├── main.tex   refs.bib   Makefile
```

Each paper is a self-contained directory with its own `main.tex`, `refs.bib`, and
`Makefile`. They share `papers/glimmer-paper.cls` (found via `TEXINPUTS=..:`, which the
Makefiles set).

## The house class

`\documentclass[preprint]{glimmer-paper}` — a thin, **venue-neutral** layer over `article`:
clean typography, a preprint/draft banner, and a small title block. It deliberately holds
nothing venue-specific, so retargeting to a journal or conference template is a one-line
`\documentclass` swap, not a rewrite. It preloads `amsmath`, `hyperref`, `natbib`,
`booktabs`, `xcolor`, `enumitem`, `microtype`, and `titlesec` — do not re-`\usepackage`
those. Options: `preprint` (banner + repo line), `draft` (do-not-circulate header).
Title-block macros: `\affil{}`, `\version{}`, `\repo{}`.

## Building

```bash
cd papers/02-proactive-provenance && make        # → main.pdf
make clean                                        # remove build artifacts
```

The `Makefile` runs `latexmk` with `TEXINPUTS` pointed at the shared class. A full TeX Live
install (with `latexmk` + `bibtex`) is assumed. Build artifacts (`*.pdf`, `*.aux`, …) are
git-ignored.

## The two papers

- **01 — Reproducibility as Knowledge Graph Navigation** (through v0.5): the typed
  research-object graph as the contribution; verification framed as a *navigable* property
  (re-run from cited SHAs). Preprint candidate.
- **02 — Proactive Provenance** (v0.6): makes the graph *executable* — the `run-record` and
  the node runner that gates inputs, replays the command, and verifies at three tiers. The
  successor that turns navigation into execution.
