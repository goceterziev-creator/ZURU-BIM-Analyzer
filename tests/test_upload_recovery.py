import unittest

from zuru_upload_recovery import (
    UploadSessionRegistry,
    is_valid_owner_token,
    is_valid_session_id,
)


OWNER_A = "A" * 32
OWNER_B = "B" * 32
OWNER_C = "C" * 32
SESSION_A = "a" * 32
SESSION_B = "b" * 32


class UploadSessionRegistryTests(unittest.TestCase):
    def test_first_observation_is_not_replacement(self):
        registry = UploadSessionRegistry(ttl_seconds=60)

        result = registry.observe(OWNER_A, SESSION_A, now=10)

        self.assertFalse(result.session_replaced)
        self.assertIsNone(result.previous_session_id)

    def test_same_session_is_not_replacement(self):
        registry = UploadSessionRegistry(ttl_seconds=60)
        registry.observe(OWNER_A, SESSION_A, now=10)

        result = registry.observe(OWNER_A, SESSION_A, now=20)

        self.assertFalse(result.session_replaced)
        self.assertEqual(SESSION_A, result.previous_session_id)

    def test_new_session_for_same_owner_is_replacement(self):
        registry = UploadSessionRegistry(ttl_seconds=60)
        registry.observe(OWNER_A, SESSION_A, now=10)

        result = registry.observe(OWNER_A, SESSION_B, now=20)

        self.assertTrue(result.session_replaced)
        self.assertEqual(SESSION_A, result.previous_session_id)

    def test_different_owner_does_not_inherit_replacement(self):
        registry = UploadSessionRegistry(ttl_seconds=60)
        registry.observe(OWNER_A, SESSION_A, now=10)

        result = registry.observe(OWNER_B, SESSION_B, now=20)

        self.assertFalse(result.session_replaced)

    def test_expired_owner_does_not_report_replacement(self):
        registry = UploadSessionRegistry(ttl_seconds=10)
        registry.observe(OWNER_A, SESSION_A, now=10)

        result = registry.observe(OWNER_A, SESSION_B, now=20)

        self.assertFalse(result.session_replaced)
        self.assertIsNone(result.previous_session_id)

    def test_prune_has_deterministic_expiry_boundary(self):
        registry = UploadSessionRegistry(ttl_seconds=10)
        registry.observe(OWNER_A, SESSION_A, now=10)

        self.assertEqual(0, registry.prune(now=19.999))
        self.assertEqual(1, registry.prune(now=20))
        self.assertEqual(0, len(registry))

    def test_capacity_evicts_oldest_entry(self):
        registry = UploadSessionRegistry(ttl_seconds=60, max_entries=2)
        registry.observe(OWNER_A, SESSION_A, now=10)
        registry.observe(OWNER_B, SESSION_A, now=11)
        registry.observe(OWNER_C, SESSION_A, now=12)

        self.assertEqual(2, len(registry))
        result = registry.observe(OWNER_A, SESSION_B, now=13)
        self.assertFalse(result.session_replaced)

    def test_invalid_identifiers_are_rejected(self):
        registry = UploadSessionRegistry()

        for owner in ("", "short", "!" * 32, None):
            with self.subTest(owner=owner):
                with self.assertRaises(ValueError):
                    registry.observe(owner, SESSION_A, now=10)
        for session_id in ("", "g" * 32, "a" * 31, None):
            with self.subTest(session_id=session_id):
                with self.assertRaises(ValueError):
                    registry.observe(OWNER_A, session_id, now=10)

    def test_identifier_validators_accept_only_expected_shapes(self):
        self.assertTrue(is_valid_owner_token(OWNER_A))
        self.assertTrue(is_valid_owner_token("_-" * 16))
        self.assertTrue(is_valid_session_id(SESSION_A))
        self.assertFalse(is_valid_owner_token("A" * 31))
        self.assertFalse(is_valid_session_id("A" * 32))


if __name__ == "__main__":
    unittest.main()
