import unittest

from dxf_evidence import normalize_entity
from evidence_classifier import classify_evidence


class FakeEntity:
    def __init__(self, entity_type, **dxf_values):
        self._entity_type = entity_type
        self.dxf = type("DXF", (), dxf_values)

    def dxftype(self):
        return self._entity_type


class EvidenceClassifierTests(unittest.TestCase):
    def test_insert_on_door_layer_is_door_with_provenance(self):
        e = FakeEntity("INSERT", layer="_door", handle="10", name="DOOR_TEST_01")
        record = normalize_entity(e)
        result = classify_evidence([record])[0]
        self.assertEqual(result["classification"], "door")
        self.assertTrue(any(p["fact"] == "layer" and p["value"] == "_door" for p in result["provenance"]))

    def test_insert_on_window_layer_is_window_with_provenance(self):
        e = FakeEntity("INSERT", layer="_window", handle="10W", name="WINDOW_TEST_01")
        record = normalize_entity(e)
        result = classify_evidence([record])[0]
        self.assertEqual(result["classification"], "window")
        self.assertTrue(any(p["fact"] == "layer" and p["value"] == "_window" for p in result["provenance"]))

    def test_generic_insert_with_chair_block_is_furnishing_not_door(self):
        e = FakeEntity("INSERT", layer="A-FURN", handle="11", name="CHAIR_01")
        record = normalize_entity(e)
        result = classify_evidence([record])[0]
        self.assertEqual(result["classification"], "furnishing")
        self.assertTrue(any(p["fact"] == "block_name" for p in result["provenance"]))

    def test_line_on_wall_layer_is_wall(self):
        e = FakeEntity("LINE", layer="_wall", handle="12")
        record = normalize_entity(e)
        result = classify_evidence([record])[0]
        self.assertEqual(result["classification"], "wall")
        self.assertTrue(any(p["fact"] == "layer" and p["value"] == "_wall" for p in result["provenance"]))

    def test_text_matching_room_pattern_is_room_label_with_only_triggering_provenance(self):
        e = FakeEntity("TEXT", layer="A-TEXT", handle="13", text="  БАНЯ-123  ")
        record = normalize_entity(e)
        result = classify_evidence([record])[0]
        self.assertEqual(result["classification"], "room_label")
        self.assertTrue(any(p["fact"] == "text" for p in result["provenance"]))
        self.assertFalse(any(p["fact"] == "layer" for p in result["provenance"]))

    def test_conflicting_evidence_downgrades_to_unknown(self):
        e = FakeEntity("INSERT", layer="_furnish", handle="14", name="DOOR_CHAIR_01")
        record = normalize_entity(e)
        result = classify_evidence([record])[0]
        self.assertEqual(result["classification"], "unknown")

    def test_non_bim_insert_not_classified_as_door(self):
        e = FakeEntity("INSERT", layer="A-FURN", handle="15", name="BLOCK_ABC")
        record = normalize_entity(e)
        result = classify_evidence([record])[0]
        self.assertEqual(result["classification"], "unknown")


if __name__ == "__main__":
    unittest.main()
