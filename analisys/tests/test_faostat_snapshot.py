"""Fixtures sintéticas: instalação, reuso e atualização sem CSV na VM."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from src.faostat_store import FaostatStore, CSV, COUNTRIES, sha256
from src.faostat_snapshot import BUNDLE, MANIFEST, package
from test_faostat import ROOT, sample, write_fixture


class FaostatSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / ".runtime")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copyfile(ROOT / COUNTRIES, self.root / COUNTRIES)
        write_fixture(self.root, [sample()])
        self.producer = FaostatStore(self.root)
        package(self.producer)
        (self.root / CSV).unlink()  # Apenas fixture criada pelo teste.
        self.consumer = FaostatStore(self.root, self.root / ".runtime/consumer.sqlite3")

    def test_restore_without_csv_reuses_database_and_keeps_contract(self):
        self.consumer.prepare()
        self.assertTrue(self.consumer.configured)
        self.assertFalse(self.consumer.originals_available)
        page = self.consumer.prices("21", "56", 2024, 2024, element_code="5532")
        self.assertEqual(page["items"][0]["value"], 142.2)
        self.assertEqual(page["items"][0]["raw"]["Area Code (M49)"], "'076")
        before = self.consumer.database.stat().st_mtime_ns
        self.consumer.prepare()
        self.assertEqual(before, self.consumer.database.stat().st_mtime_ns)
        self.assertEqual(page["source"]["sha256"], self.producer.metadata()["sha256"])

    def test_changed_snapshot_updates_existing_volume(self):
        self.consumer.prepare()
        write_fixture(self.root, [sample(value="155.000000")])
        package(self.producer)
        (self.root / CSV).unlink()
        updated = FaostatStore(self.root, self.consumer.database)
        updated.prepare()
        self.assertEqual(updated.prices("21", "56", 2024, 2024, element_code="5532")["items"][0]["value"], 155)

    def test_corrupt_package_does_not_replace_previous_database(self):
        self.consumer.prepare()
        before = sha256(self.consumer.database)
        write_fixture(self.root, [sample(value="155")])
        package(self.producer)
        (self.root / CSV).unlink()
        with (self.root / BUNDLE).open("ab") as stream:
            stream.write(b"corrupted")
        with self.assertRaises(ValueError): self.consumer.prepare()
        self.assertEqual(sha256(self.consumer.database), before)
        self.assertFalse(list(self.consumer.database.parent.glob("*.building.sqlite3")))

    def test_manifest_size_hash_and_schema_are_checked(self):
        path = self.root / MANIFEST
        original = json.loads(path.read_text(encoding="utf-8"))
        for key, value in [("database_bytes", original["database_bytes"] - 1), ("database_sha256", "0" * 64)]:
            manifest = dict(original)
            manifest[key] = value
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.subTest(key=key), self.assertRaises(ValueError): self.consumer.prepare()
            self.assertFalse(self.consumer.database.exists())
        original["fingerprint"]["schema"] = -1
        path.write_text(json.dumps(original), encoding="utf-8")
        with self.assertRaises(ValueError): self.consumer.prepare()

    def test_country_mismatch_is_not_silently_accepted(self):
        with (self.root / COUNTRIES).open("ab") as stream:
            stream.write(b"different source")
        with self.assertRaises(ValueError): self.consumer.prepare()
        self.assertFalse(self.consumer.database.exists())

    def test_damaged_runtime_is_replaced_from_valid_snapshot(self):
        self.consumer.prepare()
        self.consumer.database.write_bytes(b"broken derived database")
        self.consumer.prepare()
        self.assertEqual(self.consumer.metadata()["records"], 1)


if __name__ == "__main__":
    unittest.main()
