# Glimmer CLI & Query Reference (v0.7.0)

All commands run with Python 3.10+ and PyYAML only (zero vector-DB or ML dependencies).

## Orientation

```sh
glimmer summary <rokb>                  # human/agent-readable overview
glimmer summary <rokb> --format json    # machine-readable counts, hubs, dates
glimmer summary exports/workspace/graph.json --graph
```

Watch the `star-hubs` list (degree ≥ 10, typically `program-*`). Always keep default `--no-body` and set `--limit` when traversing hubs.

## Structured Querying (`glimmer query`)

```sh
# Filter by type (repeatable or comma-separated)
glimmer query <rokb> --type concept,reference

# Filter by frontmatter fields:
#   key=value   exact match (case-insensitive; matches elements of list fields)
#   key~=substr substring match
#   key?        field is present and non-empty
glimmer query <rokb> --type concept --field status=open --field claim-kind=design-assumption
glimmer query <rokb> --type reference --field authors~=Simon
glimmer query <rokb> --field doi?

# Filter by graph edges
glimmer query <rokb> --rel challenges --direction out
glimmer query <rokb> --rel tested-by-experiment --target experiment-field-comparison

# Output shapes & body control (metadata-only by default)
glimmer query <rokb> --type method --format ids
glimmer query <rokb> --type method --format paths
glimmer query <rokb> --type method --format json
glimmer query <rokb> --type method --include-body --limit 5
glimmer query <rokb> --type method --body-chars 400
```

## Multi-Hop Traversal (`glimmer neighbors`)

```sh
glimmer neighbors <rokb> hypothesis-adaptive-threshold --hops 1
glimmer neighbors <rokb> hypothesis-adaptive-threshold --hops 2 --rel supports,challenges,addresses-concept
glimmer neighbors <rokb> program-example --hops 1 --direction in --limit 20 --format json
glimmer neighbors <rokb> hypothesis-adaptive-threshold --hops 1 --include-body
```

Returns center metadata, reachable neighbors annotated with `hop` distance, and exact `{source, type, target, hop}` triples.

## Full-Text Ranked Search (`glimmer search`)

Powered by the built-in stdlib Okapi BM25 retriever (`glimmer.tools.retrieval.Bm25Retriever`) over weighted fields (`title/id` 3x, `statement/interpretation/description/authors/venue` 2x, Markdown `body` 1x) with section/line snippet locators:

```sh
glimmer search <rokb> "leaky integrate and fire threshold" -k 8
glimmer search <rokb> "goal constraints" --type reference,publication --format json
glimmer search <rokb> "selection bias" --emit-finding finding-lit-selection --concept-id concept-sampling-bias
```

## Querying Built Workspace Editions

Pass `--graph` to any query command to read `exports/workspace/graph.json` directly:

```sh
glimmer summary exports/workspace/graph.json --graph
glimmer neighbors exports/workspace/graph.json hypothesis-adaptive-threshold --hops 2 --graph
glimmer search exports/workspace/graph.json "feedback" --graph
```
