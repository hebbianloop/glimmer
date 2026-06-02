# Worked example: `experiment` + `contributed-by` (v0.3)

A minimal 2-node graph showing the two v0.3 additions:
- an **`experiment`** node (the EmoFilm paradigm) with `realized-by` → a `dataset`, and
- **`contributed-by`** attribution edges (out-of-graph ORCID/email targets, role in metadata) on both nodes.

Validate:
```
python ../../glimmer/tools/validate.py rokb
```
