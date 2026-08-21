import asyncio
from pathlib import Path
import tempfile
import unittest

from zuru_upload_staging import (
    InvalidUpload,
    MAX_UPLOAD_BYTES,
    StagingCapacityExceeded,
    UploadNotFound,
    UploadStagingRegistry,
    new_token,
)


class TestUploadStagingRegistry(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "staging"
        self.registry = UploadStagingRegistry(
            root=self.root,
            ttl_seconds=10,
            max_entries=2,
            max_staged_bytes=1024,
        )
        self.owner = new_token()

    def tearDown(self):
        self.registry.close()
        self.temp_dir.cleanup()

    def _stage(self, content=b"DXF", filename="drawing.dxf"):
        intent = self.registry.create_intent(
            owner_token=self.owner,
            filename=filename,
            declared_size=len(content),
            now=100,
        )
        pending = self.registry.store_stream(
            owner_token=self.owner,
            upload_id=intent.upload_id,
            chunks=[content[:1], content[1:]],
            now=101,
        )
        return intent, pending

    def test_explicit_claim_is_single_use_and_deletes_temp_file(self):
        intent, pending = self._stage(b"SECTION")
        self.assertTrue(pending.ready)
        self.assertEqual(list(self.root.iterdir()), [next(self.root.iterdir())])

        claim = self.registry.create_claim(
            owner_token=self.owner, upload_id=intent.upload_id, now=102
        )
        uploaded = self.registry.consume_claim(claim, now=103)

        self.assertEqual(uploaded.name, "drawing.dxf")
        self.assertEqual(uploaded.getvalue(), b"SECTION")
        self.assertEqual(len(self.registry), 0)
        self.assertEqual(list(self.root.iterdir()), [])
        with self.assertRaises(UploadNotFound):
            self.registry.consume_claim(claim, now=104)

    def test_different_owner_cannot_list_store_or_claim(self):
        other_owner = new_token()
        intent = self.registry.create_intent(
            owner_token=self.owner,
            filename="private.dwg",
            declared_size=3,
            now=100,
        )
        self.assertEqual(self.registry.list_pending(owner_token=other_owner, now=101), [])
        with self.assertRaises(UploadNotFound):
            self.registry.store_stream(
                owner_token=other_owner,
                upload_id=intent.upload_id,
                chunks=[b"DWG"],
                now=101,
            )
        with self.assertRaises(UploadNotFound):
            self.registry.create_claim(
                owner_token=other_owner, upload_id=intent.upload_id, now=101
            )

    def test_expiry_prunes_entry_claim_and_file(self):
        intent, _ = self._stage(b"DXF")
        claim = self.registry.create_claim(
            owner_token=self.owner, upload_id=intent.upload_id, now=102
        )
        self.assertEqual(self.registry.prune(now=111), 1)
        self.assertEqual(list(self.root.iterdir()), [])
        with self.assertRaises(UploadNotFound):
            self.registry.consume_claim(claim, now=111)

    def test_rejects_extension_empty_file_size_mismatch_and_over_limit(self):
        for filename in ("drawing.pdf", "drawing", "../drawing.exe"):
            with self.subTest(filename=filename), self.assertRaises(InvalidUpload):
                self.registry.create_intent(
                    owner_token=self.owner,
                    filename=filename,
                    declared_size=1,
                    now=100,
                )
        for size in (0, MAX_UPLOAD_BYTES + 1, True):
            with self.subTest(size=size), self.assertRaises(InvalidUpload):
                self.registry.create_intent(
                    owner_token=self.owner,
                    filename="drawing.dxf",
                    declared_size=size,
                    now=100,
                )

        intent = self.registry.create_intent(
            owner_token=self.owner,
            filename="drawing.dxf",
            declared_size=4,
            now=100,
        )
        with self.assertRaises(InvalidUpload):
            self.registry.store_stream(
                owner_token=self.owner,
                upload_id=intent.upload_id,
                chunks=[b"too long"],
                now=101,
            )
        self.assertEqual(list(self.root.iterdir()), [])

    def test_capacity_is_bounded_by_reserved_bytes(self):
        self.registry.create_intent(
            owner_token=self.owner,
            filename="one.dxf",
            declared_size=700,
            now=100,
        )
        with self.assertRaises(StagingCapacityExceeded):
            self.registry.create_intent(
                owner_token=self.owner,
                filename="two.dxf",
                declared_size=400,
                now=101,
            )

    def test_async_stream_is_not_buffered_by_route_contract(self):
        intent = self.registry.create_intent(
            owner_token=self.owner,
            filename="drawing.dwg",
            declared_size=6,
            now=100,
        )

        async def chunks():
            yield b"DWG"
            yield b"123"

        pending = asyncio.run(
            self.registry.store_async_stream(
                owner_token=self.owner,
                upload_id=intent.upload_id,
                chunks=chunks(),
                now=101,
            )
        )
        self.assertTrue(pending.ready)
        self.assertEqual(pending.size, 6)


if __name__ == "__main__":
    unittest.main()
