#!/usr/bin/env python3
"""Tests for the sharded chunk store and its caches (run: python3 -m unittest test_chunk_store)."""
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chunk_store as cs  # noqa: E402


def row(target, idx, text, vector=None, sha="abc"):
    r = {"id": f"{target}:{idx}:{sha}", "resource_id": f"res-{target}", "target_path": target, "chunk_index": idx,
         "start_char": 0, "end_char": len(text), "text": text, "metadata": {"kind": "text"}, "sha256": sha,
         "updated_at": "2026-01-01T00:00:00Z", "row_index": None}
    if vector is not None:
        r["vector"] = vector
        r["embedding_model"] = "test-model"
    return r


class ChunkStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state = self.root / "store/state"
        self.state.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def targets(self):
        return sorted(cs.shard_index(self.state))

    def test_vector_roundtrip_is_close(self):
        vector = [0.12345, -0.5, 0.0, 0.999]
        decoded = cs.decode_vector(cs.encode_vector(vector))
        self.assertTrue(all(abs(a - b) < 1e-3 for a, b in zip(vector, decoded)))

    def test_shard_roundtrip_keeps_fields_and_line_separators(self):
        text = "line one line two end"
        cs.write_shard(self.state, "src/a.md", [row("src/a.md", 1, "second", [0.1, 0.2]), row("src/a.md", 0, text, [0.3, 0.4])])
        self.assertEqual(len(cs.shard_path(self.state, "src/a.md").read_text().split("\n")), 4)
        rows = cs.read_chunks(self.state)
        self.assertEqual([r["chunk_index"] for r in rows], [0, 1])
        self.assertEqual(rows[0]["text"], text)
        self.assertEqual(rows[0]["metadata"], {"kind": "text"})
        self.assertEqual(rows[0]["embedding_model"], "test-model")

    def test_unchanged_shard_is_not_rewritten(self):
        cs.save_chunks(self.state, [row("a.md", 0, "a", [0.5])], None, set())
        path = cs.shard_path(self.state, "a.md")
        before = path.stat().st_mtime_ns
        cs.save_chunks(self.state, [row("a.md", 0, "a", [0.5])], {"a.md"}, set())
        self.assertEqual(path.stat().st_mtime_ns, before)

    def test_legacy_migration_keeps_embeddings_and_existing_shards_win(self):
        cs.write_shard(self.state, "a.md", [row("a.md", 0, "newer shard text", [0.1])])
        legacy = self.state / "chunks.jsonl"
        legacy.write_text("\n".join(json.dumps(row(t, 0, "legacy", [0.5, 0.25])) for t in ("a.md", "b/c.md")) + "\n")
        report = cs.migrate_legacy(self.state)
        self.assertTrue(report["migrated"])
        self.assertEqual(report["skipped_existing"], 1)
        self.assertFalse(legacy.exists())
        texts = {r["target_path"]: r["text"] for r in cs.read_chunks(self.state)}
        self.assertEqual(texts, {"a.md": "newer shard text", "b/c.md": "legacy"})
        self.assertIn("store/lancedb/", (self.root / ".gitignore").read_text())

    def test_save_chunks_rewrites_only_changed_and_drops_removed(self):
        cs.save_chunks(self.state, [row("a.md", 0, "a"), row("b.md", 0, "b")], None, set())
        b_before = cs.shard_path(self.state, "b.md").read_bytes()
        hash_before = cs.content_hash(self.state)
        cs.save_chunks(self.state, [row("a.md", 0, "a changed", sha="def")], {"a.md"}, set())
        self.assertEqual(cs.shard_path(self.state, "b.md").read_bytes(), b_before)
        self.assertNotEqual(cs.content_hash(self.state), hash_before)
        cs.save_chunks(self.state, [], set(), {"b.md"})
        self.assertEqual(self.targets(), ["a.md"])

    def test_case_only_rename_keeps_the_renamed_file(self):
        cs.save_chunks(self.state, [row("docs/Policy.md", 0, "p", [0.1])], None, set())
        cs.save_chunks(self.state, [row("docs/policy.md", 0, "p", [0.1])], {"docs/policy.md"}, {"docs/Policy.md"})
        self.assertEqual(self.targets(), ["docs/policy.md"])
        self.assertEqual(len(cs.read_chunks(self.state)), 1)

    def test_run_without_embedding_keeps_stored_vectors(self):
        cs.save_chunks(self.state, [row("a.md", 0, "a", [0.25, 0.5])], None, set())
        cs.save_chunks(self.state, [row("a.md", 0, "a")], None, set())
        self.assertEqual(cs.read_chunks(self.state)[0]["vector"], [0.25, 0.5])

    def test_changed_file_without_chunks_loses_its_shard(self):
        cs.save_chunks(self.state, [row("dir/a.md", 0, "a")], None, set())
        cs.save_chunks(self.state, [], {"dir/a.md"}, set())
        self.assertEqual(self.targets(), [])
        self.assertFalse((self.state / "chunks/dir").exists())

    def test_long_file_names_get_a_short_shard_name(self):
        target = "docs/" + "x" * 249 + ".md"
        cs.save_chunks(self.state, [row(target, 0, "long")], None, set())
        self.assertEqual(self.targets(), [target])
        self.assertLessEqual(len(cs.shard_path(self.state, target).name.encode()), 255)

    def test_cache_staleness_follows_shard_files_and_sqlite_state(self):
        cs.save_chunks(self.state, [row("a.md", 0, "alpha")], None, set())
        self.assertEqual(cs.stale_caches(self.root, ["sqlite"]), ["sqlite"])
        self.assertEqual(cs.rebuild_caches(self.root, ["sqlite"])["rebuilt"], ["sqlite"])
        self.assertEqual(cs.stale_caches(self.root, ["sqlite"]), [])
        with sqlite3.connect(self.root / "store/sqlite/resources.db") as conn:
            self.assertEqual(conn.execute("select count(*) from chunks").fetchone()[0], 1)
            columns = {r[1] for r in conn.execute("pragma table_info(chunks)")}
            self.assertNotIn("vector_json", columns)  # vectors stay in shards and LanceDB
        shard = cs.shard_path(self.state, "a.md")
        shard.write_text(shard.read_text().replace("alpha", "edited"))
        self.assertEqual(cs.stale_caches(self.root, ["sqlite"]), ["sqlite"])  # e.g. after a pull or merge
        cs.rebuild_caches(self.root, ["sqlite"])
        (self.state / "summaries.jsonl").write_text("{}\n")
        self.assertEqual(cs.stale_caches(self.root, ["sqlite"]), ["sqlite"])


if __name__ == "__main__":
    unittest.main()
