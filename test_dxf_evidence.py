import unittest

from dxf_evidence import normalize_entity, normalize_modelspace


class FakeDXF:
    def __init__(self, **values):
        self.__dict__.update(values)


class FakeEntity:
    def __init__(self, entity_type, **dxf_values):
        self._entity_type = entity_type
        self.dxf = FakeDXF(**dxf_values)

    def dxftype(self):
        return self._entity_type


class NormalizeEntityTests(unittest.TestCase):
    def test_insert_preserves_block_identity_without_architectural_inference(self):
        entity = FakeEntity("INSERT", layer="A-FURN", handle="2A", name="CHAIR_01")
        self.assertEqual(
            normalize_entity(entity),
            {
                "entity_type": "INSERT",
                "layer": "A-FURN",
                "handle": "2A",
                "block_name": "CHAIR_01",
                "text": None,
                "source": "DXF",
            },
        )

    def test_text_is_trimmed_and_preserved_as_source_evidence(self):
        entity = FakeEntity("TEXT", layer="A-ROOM", handle="31", text="  БАНЯ-123  ")
        record = normalize_entity(entity)
        self.assertEqual(record["text"], "БАНЯ-123")
        self.assertEqual(record["entity_type"], "TEXT")
        self.assertEqual(record["source"], "DXF")
        self.assertNotIn("room_type", record)

    def test_missing_optional_attributes_are_none(self):
        entity = FakeEntity("LINE", layer="A-WALL")
        record = normalize_entity(entity)
        self.assertIsNone(record["handle"])
        self.assertIsNone(record["block_name"])
        self.assertIsNone(record["text"])

    def test_modelspace_order_is_deterministic(self):
        entities = [
            FakeEntity("LINE", layer="0", handle="1"),
            FakeEntity("INSERT", layer="A-FURN", handle="2", name="TABLE"),
        ]
        first = normalize_modelspace(entities)
        second = normalize_modelspace(entities)
        self.assertEqual(first, second)
        self.assertEqual([r["handle"] for r in first], ["1", "2"])


if __name__ == "__main__":
    unittest.main()
