import io
import unittest

import ezdxf

from zuru_core import analyze_dxf_bytes, classify_room_labels


def to_dxf_bytes(doc):
    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue().encode("utf-8")


class ZuruCoreTests(unittest.TestCase):
    def test_room_label_heuristics_are_per_label_and_deterministic(self):
        texts = ["БАНЯ-123", "КУХНЯ-123", "СПАЛНЯ 2", "не е стая"]
        first = classify_room_labels(texts)
        second = classify_room_labels(texts)
        self.assertEqual(first, second)
        self.assertEqual(first["🛁 Бани/ВЦ"], 1)
        self.assertEqual(first["🍳 Кухни"], 1)
        self.assertEqual(first["🛏️ Спални"], 1)

    def test_synthetic_architectural_dxf_has_known_ground_truth(self):
        doc = ezdxf.new()
        for layer in ["_wall", "_door", "_furnish", "_room"]:
            doc.layers.add(layer)

        door_block = doc.blocks.new("DOOR_TEST_01")
        door_block.add_line((0, 0), (1, 0))
        chair_block = doc.blocks.new("CHAIR_TEST_01")
        chair_block.add_circle((0, 0), radius=0.5)

        msp = doc.modelspace()
        msp.add_line((0, 0), (5, 0), dxfattribs={"layer": "_wall"})
        msp.add_blockref("DOOR_TEST_01", (1, 0), dxfattribs={"layer": "_door"})
        msp.add_blockref("CHAIR_TEST_01", (2, 0), dxfattribs={"layer": "_furnish"})
        msp.add_text("БАНЯ-123", dxfattribs={"layer": "_room"})
        msp.add_mtext("КУХНЯ-123", dxfattribs={"layer": "_room"})
        msp.add_lwpolyline([(0, 0), (4, 0), (4, 4), (0, 4)], close=True, dxfattribs={"layer": "_room"})
        hatch = msp.add_hatch(dxfattribs={"layer": "_room"})
        hatch.paths.add_polyline_path([(0, 0), (4, 0), (4, 4), (0, 4)], is_closed=True)

        result = analyze_dxf_bytes(to_dxf_bytes(doc))

        self.assertEqual(sum(result["entity_stats"].values()), 7)
        self.assertEqual(result["entity_stats"]["INSERT"], 2)
        self.assertEqual(result["source_signals"]["_door layer entities"], 1)
        self.assertEqual(result["source_signals"]["INSERT entities"], 2)
        self.assertEqual(result["room_label_stats"]["🛁 Бани/ВЦ"], 1)
        self.assertEqual(result["room_label_stats"]["🍳 Кухни"], 1)
        self.assertEqual(result["geometry_candidates"], 2)
        self.assertEqual(len(result["evidence_records"]), 7)
        self.assertTrue(all("is_door" not in record for record in result["evidence_records"]))
        self.assertTrue(all("room_type" not in record for record in result["evidence_records"]))

    def test_non_bim_spline_dxf_stays_unclassified(self):
        doc = ezdxf.new()
        msp = doc.modelspace()
        msp.add_spline(fit_points=[(0, 0), (1, 2), (2, 0)], dxfattribs={"layer": "Plan 1"})

        result = analyze_dxf_bytes(to_dxf_bytes(doc))

        self.assertEqual(result["entity_stats"], {"SPLINE": 1})
        self.assertEqual(result["room_texts"], [])
        self.assertEqual(result["geometry_candidates"], 0)
        self.assertTrue(all(value == 0 for value in result["room_label_stats"].values()))


if __name__ == "__main__":
    unittest.main()
