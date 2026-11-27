"""Comprehensive unit & CLI integration tests for Glimmer v0.7.0 features."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

import yaml

from glimmer.tools import query as gquery
from glimmer.tools import retrieval as gretrieval
from glimmer.tools import skill_installer
from glimmer.tools import sync as gsync
from glimmer.tools import validate as gvalidate


NOW = "2026-11-26T00:00:00Z"


def _write_node(path: Path, fm: dict, body: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = dict(fm)
    fm.setdefault("created", NOW)
    fm.setdefault("modified", NOW)
    fm["provenance-hash"] = gsync.compute_body_hash(body)
    path.write_text("---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True) + "---\n" + body, encoding="utf-8")


class GlimmerV07Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="glimmer-v07-")
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        self.rokb = self.project / "research-program"
        self.rokb.mkdir()
        self._seed_graph()

    def _seed_graph(self):
        _write_node(
            self.rokb / "index.md",
            {
                "id": "program-demo",
                "type": "program",
                "name": "Demo Research Program",
                "program-kind": "initiative",
                "status": "active",
                "edges": [{"type": "addresses-concept", "target": "concept-adaptive-gate"}],
            },
            "\n# Demo Research Program\n\nRoot program container.\n",
        )
        _write_node(
            self.rokb / "concepts/adaptive-gate.md",
            {
                "id": "concept-adaptive-gate",
                "type": "concept",
                "name": "Adaptive threshold improves joint outcomes",
                "statement": "Goal-conditioned threshold adaptation outperforms a fixed filter.",
                "concept-kind": "hypothesis",
                "claim-kind": "design-assumption",
                "status": "open",
                "falsifiable": True,
                "edges": [
                    {"type": "in-program", "target": "program-demo"},
                    {"type": "tested-by-experiment", "target": "exp-field"},
                ],
            },
            "\n## Mechanism\n\nAdaptive thresholds weigh marginal decision value against feedback delay.\n",
        )
        _write_node(
            self.rokb / "experiments/field.md",
            {
                "id": "exp-field",
                "type": "experiment",
                "name": "Field comparison study",
                "design-status": "proposed",
                "edges": [
                    {"type": "tests-hypothesis", "target": "concept-adaptive-gate"},
                    {"type": "in-program", "target": "program-demo"},
                ],
            },
            "\nSynthetic comparison of fixed and adaptive filters.\n",
        )
        _write_node(
            self.rokb / "methods/minimal-model.md",
            {
                "id": "method-minimal-model",
                "type": "method",
                "name": "Minimal adaptive threshold model",
                "tool": "python-sim",
                "version": "0.1.0",
                "edges": [{"type": "in-program", "target": "program-demo"}],
            },
            "\nFormulation of internal boundary and filter cutoff.\n",
        )
        _write_node(
            self.rokb / "references/simon-1964.md",
            {
                "id": "ref-simon-1964",
                "type": "reference",
                "ref-kind": "paper",
                "name": "Simon (1964): On the Concept of Organizational Goal",
                "authors": ["Herbert A. Simon"],
                "year": 1964,
                "venue": "Administrative Science Quarterly",
                "doi": "10.2307/2391519",
                "edges": [
                    {"type": "addresses-concept", "target": "concept-adaptive-gate"},
                    {"type": "supports", "target": "concept-adaptive-gate"},
                    {"type": "in-program", "target": "program-demo"},
                ],
            },
            "\nGoals operate as sets of value-premise constraints.\n",
        )
        _write_node(
            self.rokb / "publications/legacy-external.md",
            {
                "id": "pub-lakkaraju-2017",
                "type": "publication",
                "role": "external-reference",
                "pub-status": "published",
                "name": "Lakkaraju et al. (2017): Selective Labels Problem",
                "authors": ["Himabindu Lakkaraju"],
                "year": 2017,
                "edges": [
                    {"type": "challenges", "target": "concept-adaptive-gate"},
                    {"type": "in-program", "target": "program-demo"},
                ],
            },
            "\nAdmitted-only observations create selective-labels bias in outcome evaluation.\n",
        )
        _write_node(
            self.rokb / "publications/project-essay.md",
            {
                "id": "pub-project-essay",
                "type": "publication",
                "role": "project-output",
                "pub-status": "draft",
                "name": "Example filter comparison",
                "authors": ["Example Researcher"],
                "year": 2026,
                "edges": [
                    {"type": "cites", "target": "ref-simon-1964"},
                    {"type": "cites-method", "target": "method-minimal-model"},
                    {"type": "cites-concept", "target": "concept-adaptive-gate"},
                    {"type": "in-program", "target": "program-demo"},
                ],
            },
            "\nDraft essay synthesizing goal constraints and adaptive thresholds.\n",
        )
        res = gsync.sync_rokb(self.rokb)
        self.assertEqual(res["errors"], [])

    def test_validate_v07_reference_and_publication_roles(self):
        schema = gvalidate.load_schema()
        errors, warnings = gvalidate.validate(self.rokb, schema)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

        # Disconnected reference emits an advisory warning (not an error)
        _write_node(
            self.rokb / "references/orphan.md",
            {
                "id": "ref-orphan",
                "type": "reference",
                "name": "Orphan paper",
                "edges": [{"type": "in-program", "target": "program-demo"}],
            },
            "\nNot linked to any claim.\n",
        )
        gsync.sync_rokb(self.rokb)
        errors, warnings = gvalidate.validate(self.rokb, schema)
        self.assertEqual(errors, [])
        self.assertTrue(any("ref-orphan" in w or "orphan.md" in w for w in warnings), warnings)

        # Invalid publication role is a hard error
        _write_node(
            self.rokb / "publications/bad-role.md",
            {
                "id": "pub-bad-role",
                "type": "publication",
                "role": "bogus-role",
                "pub-status": "draft",
                "name": "Bad role",
                "edges": [{"type": "cites", "target": "ref-simon-1964"}],
            },
            "\nBody.\n",
        )
        gsync.sync_rokb(self.rokb)
        errors, _ = gvalidate.validate(self.rokb, schema)
        self.assertTrue(any("bogus-role" in e for e in errors), errors)

    def test_enriched_index_structure_and_backwards_compatibility(self):
        idx = json.loads((self.rokb / "_glimmer-index.json").read_text(encoding="utf-8"))
        self.assertEqual(idx["schema"], "glimmer/v0.7.0")
        self.assertEqual(idx["root-node"], "program-demo")
        self.assertEqual(idx["node-count"], 7)
        by_id = {n["id"]: n for n in idx["nodes"]}
        c = by_id["concept-adaptive-gate"]
        self.assertEqual(c["type"], "concept")
        self.assertEqual(c["subtype"], "hypothesis")
        self.assertEqual(c["claim-kind"], "design-assumption")
        self.assertEqual(c["status"], "open")
        self.assertIn("Goal-conditioned threshold adaptation", c["summary"])
        self.assertTrue(any(e["type"] == "tested-by-experiment" for e in c["edges"]))

        # Minimal v0.6 index still loads and queries cleanly
        minimal = {
            "schema": "glimmer/v0.6.0",
            "dataset-name": "minimal",
            "node-count": len(idx["nodes"]),
            "nodes": [{"id": n["id"], "type": n["type"], "path": n["path"]} for n in idx["nodes"]],
        }
        (self.rokb / "_glimmer-index.json").write_text(json.dumps(minimal, indent=2), encoding="utf-8")
        summary = gquery.summarize_rokb(self.rokb)
        self.assertFalse(summary["enriched-index"])
        self.assertEqual(summary["node-count"], 7)

    def test_query_metadata_only_default_and_filters(self):
        res = gquery.query_nodes(self.rokb, node_types=["concept"], field_exprs=["claim-kind=design-assumption", "status=open"])
        self.assertEqual(res["total"], 1)
        self.assertNotIn("body", res["nodes"][0])
        self.assertEqual(res["nodes"][0]["id"], "concept-adaptive-gate")

        res_body = gquery.query_nodes(self.rokb, node_types=["concept"], include_body=True)
        self.assertIn("marginal decision value", res_body["nodes"][0]["body"])

        res_rel = gquery.query_nodes(self.rokb, rel="challenges", direction="out")
        self.assertEqual([n["id"] for n in res_rel["nodes"]], ["pub-lakkaraju-2017"])

        res_substr = gquery.query_nodes(self.rokb, field_exprs=["authors~=Simon"])
        self.assertEqual([n["id"] for n in res_substr["nodes"]], ["ref-simon-1964"])

    def test_neighbors_multihop_and_compiled_graph_json(self):
        hop1 = gquery.traverse_neighbors(self.rokb, "concept-adaptive-gate", hops=1)
        self.assertFalse(hop1["include-body"])
        ids1 = {n["id"] for n in hop1["neighbors"]}
        self.assertIn("ref-simon-1964", ids1)
        self.assertIn("pub-lakkaraju-2017", ids1)
        self.assertIn("exp-field", ids1)
        self.assertNotIn("method-minimal-model", ids1)

        hop2 = gquery.traverse_neighbors(self.rokb, "concept-adaptive-gate", hops=2)
        ids2 = {n["id"] for n in hop2["neighbors"]}
        self.assertIn("method-minimal-model", ids2)

        # Compiled graph.json mode
        gjson = self.project / "graph.json"
        gjson.write_text(json.dumps({
            "schema_version": 1,
            "project": {"id": "demo", "root_node": "program-demo"},
            "nodes": [
                {"id": "program-demo", "type": "program", "name": "Demo", "body": "Root", "fields": {"status": "active"}},
                {"id": "ref-simon-1964", "type": "reference", "name": "Simon 1964", "body": "Goal constraints", "fields": {"year": 1964}},
            ],
            "edges": [{"source": "ref-simon-1964", "rel": "in-program", "target": "program-demo"}],
        }), encoding="utf-8")
        s = gquery.summarize_rokb(gjson, from_graph_json=True)
        self.assertEqual(s["node-count"], 2)
        sr = gquery.search_rokb(gjson, "goal constraints", from_graph_json=True)
        self.assertEqual(sr["hits"][0]["id"], "ref-simon-1964")

    def test_bm25_retriever_idempotency_and_search(self):
        docs = gretrieval.load_rokb_documents(self.rokb)
        ret = gretrieval.Bm25Retriever()
        self.assertIsInstance(ret, gretrieval.LiteratureRetriever)
        ret.index(docs)
        m1 = ret.manifest()
        ret.index(docs)  # idempotent
        m2 = ret.manifest()
        self.assertEqual(m1["index-sha"], m2["index-sha"])

        result = ret.retrieve("selective labels bias", k=5)
        self.assertGreaterEqual(len(result.passages), 1)
        self.assertEqual(result.passages[0].source_node_id, "pub-lakkaraju-2017")
        self.assertTrue(result.passages[0].locator)

        finding = gretrieval.finding_from_retrieval(
            finding_id="finding-selective-labels",
            interpretation="Prior work warns of selective-labels bias.",
            result=result,
            model_identifier="test-agent",
            timestamp=NOW,
            concept_id="concept-adaptive-gate",
        )
        self.assertEqual(finding["provenance-mode"], "stochastic")
        self.assertIn("pub-lakkaraju-2017", finding["based-on"])

    def test_status_detects_hash_and_draft_drift_and_sync_fixes_hashes(self):
        # Create a sibling draft file newer than the graph
        writing = self.project / "writing"
        writing.mkdir()
        draft = writing / "new-discussion-paper.md"
        draft.write_text("# Draft\n\nNew material not yet indexed.\n", encoding="utf-8")
        future = time.time() + 5 * 86400
        os.utime(draft, (future, future))

        # Mutate a sidecar body without updating provenance-hash
        concept_path = self.rokb / "concepts/adaptive-gate.md"
        concept_path.write_text(concept_path.read_text(encoding="utf-8") + "\nAdded sentence.\n", encoding="utf-8")

        st = gsync.status_rokb(self.rokb)
        self.assertEqual(len(st["hash-drift"]), 1)
        self.assertEqual(st["hash-drift"][0]["id"], "concept-adaptive-gate")
        self.assertTrue(any(f["path"] == "writing/new-discussion-paper.md" for f in st["workspace-drift"]["newer-files"]))
        self.assertIn("writing/new-discussion-paper.md", st["workspace-drift"]["unregistered-artifacts"])

        # --check must not modify files
        chk = gsync.sync_rokb(self.rokb, check=True)
        self.assertEqual(len(chk["updated-hashes"]), 1)
        st_after_check = gsync.status_rokb(self.rokb)
        self.assertEqual(len(st_after_check["hash-drift"]), 1)

        # real sync fixes hashes and index cleanly
        syn = gsync.sync_rokb(self.rokb, check=False)
        self.assertEqual(syn["errors"], [])
        self.assertEqual(syn["warnings"], [])
        st_after_sync = gsync.status_rokb(self.rokb)
        self.assertEqual(st_after_sync["hash-drift"], [])
        self.assertFalse(st_after_sync["index"]["stale"])

    def test_init_hash_amend_and_migrate_references(self):
        fresh = self.project / "fresh-kb"
        init_res = gsync.init_rokb(fresh, dataset_name="Fresh Study", domain="fresh-domain", with_profile=True, with_agents_snippet=True)
        self.assertEqual(init_res["errors"], [])
        self.assertEqual(init_res["warnings"], [])
        self.assertTrue((fresh / "_glimmer-index.json").is_file())
        self.assertTrue((fresh / "_glimmer-profiles/fresh-domain.yaml").is_file())
        self.assertTrue((fresh / "AGENTS.glimmer.md").is_file())

        # hash utility
        h = gsync.hash_file(fresh / "index.md")
        self.assertTrue(h.startswith("sha256:") and len(h) == 71)

        # amend utility (must not break validation)
        am = gsync.scaffold_amendment(self.rokb, "method-minimal-model", "Refine threshold update rule")
        self.assertTrue(Path(am["path"]).is_file())
        errors, warnings = gvalidate.validate(self.rokb, gvalidate.load_schema())
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

        # migrate-references (dry-run vs apply)
        _write_node(
            self.rokb / "publications/unannotated-ext.md",
            {
                "id": "pub-unannotated-ext",
                "type": "publication",
                "pub-status": "published",
                "name": "Unannotated External Paper",
                "edges": [{"type": "addresses-concept", "target": "concept-adaptive-gate"}],
            },
            "\nExternal cited paper from a v0.6 graph.\n",
        )
        gsync.sync_rokb(self.rokb)
        dry = gsync.migrate_references(self.rokb, mode="type", apply=False)
        self.assertEqual([c["id"] for c in dry["candidates"]], ["pub-lakkaraju-2017", "pub-unannotated-ext"])
        applied = gsync.migrate_references(self.rokb, mode="type", apply=True)
        self.assertTrue(applied["applied"])
        errors, warnings = gvalidate.validate(self.rokb, gvalidate.load_schema())
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_install_skill_copy_and_symlink(self):
        dest_copy = skill_installer.install_skill(project=self.project, force=True)
        self.assertEqual(dest_copy, self.project.resolve() / ".agents/skills/glimmer")
        self.assertTrue((dest_copy / "SKILL.md").is_file())
        self.assertTrue((dest_copy / "references/cli-and-query.md").is_file())
        self.assertTrue((dest_copy / "agents/openai.yaml").is_file())

        dest_claude = skill_installer.install_skill(project=self.project, claude=True, symlink=True, force=True)
        self.assertTrue(dest_claude.is_symlink())
        self.assertTrue((dest_claude / "SKILL.md").is_file())

    def test_cli_end_to_end_subcommands(self):
        repo_root = Path(__file__).resolve().parents[1]
        env = dict(os.environ, PYTHONPATH=str(repo_root))
        for argv, ok_codes in [
            (["version"], (0,)),
            (["summary", str(self.rokb), "--format", "json"], (0,)),
            (["query", str(self.rokb), "--type", "reference", "--format", "ids"], (0,)),
            (["neighbors", str(self.rokb), "concept-adaptive-gate", "--hops", "1", "--format", "json"], (0,)),
            (["search", str(self.rokb), "goal constraints", "--format", "json"], (0,)),
            (["validate", str(self.rokb), "--json"], (0,)),
        ]:
            proc = subprocess.run(
                [sys.executable, "-m", "glimmer.tools.cli", *argv],
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertIn(proc.returncode, ok_codes, f"argv={argv} rc={proc.returncode} stderr={proc.stderr}")


if __name__ == "__main__":
    unittest.main()
