#!/usr/bin/env python3
"""Backwards-compatible re-export of core stdlib-only retrievers.

As of Glimmer v0.7.0, `NullRetriever` and `Bm25Retriever` ship directly in
`glimmer.tools.retrieval` so retrieval works out of the box with zero heavy
dependencies. This module re-exports them so existing example imports keep working.
"""

from glimmer.tools.retrieval import Bm25Retriever, NullRetriever  # noqa: F401
