import io
import os
import unittest

import ezdxf

from dxf_evidence import normalize_modelspace
from zuru_core import analyze_dxf_bytes


def to_dxf_bytes(doc):
    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue().encode("utf-8")


class ClassificationIntegrationTests(unittest.TestCase):
    def test_normalized_evidence_flows_through_classifier_into_result(self):
        doc = ezdxf.new()
        doc.layers.add("_door")
        doc.layers.add("_furnish")
        door_block = doc.blocks.new("DOOR_TEST_X")
        door_block.add_line((0, 0), (1, 0))
        chair_block = doc.blocks.new("CHAIR_TEST_X")
        chair_block.add_circle((0, 0), radius=0.5)

        msp = doc.modelspace()
        msp.add_blockref("DOOR_TEST_X", (1, 0), dxfattribs={"layer": "_door"})
        msp.add_blockref("CHAIR_TEST_X", (2, 0), dxfattribs={"layer": "_furnish"})

        result = analyze_dxf_bytes(to_dxf_bytes(doc))

        # classifications must be present and reference the normalized evidence
        self.assertIn("evidence_classifications", result)
        self.assertEqual(len(result["evidence_classifications"]), len(result["evidence_records"]))

        # ensure deterministic classifications include expected classes
        classes = {c["classification"] for c in result["evidence_classifications"]}
        self.assertIn("door", classes)
        self.assertIn("furnishing", classes)

    def test_normalized_evidence_is_unchanged_after_classification(self):
        doc = ezdxf.new()
        doc.layers.add("_door")
        door_block = doc.blocks.new("DOOR_TEST_Y")
        door_block.add_line((0, 0), (1, 0))

        msp = doc.modelspace()
        msp.add_blockref("DOOR_TEST_Y", (1, 0), dxfattribs={"layer": "_door"})

        # get normalized evidence directly
        original_evidence = normalize_modelspace(doc.modelspace())

        # run full analysis which performs classification internally
        result = analyze_dxf_bytes(to_dxf_bytes(doc))

        self.assertEqual(result["evidence_records"], original_evidence)

    def test_unknown_survives_into_product_output(self):
        doc = ezdxf.new()
        # create ambiguous INSERT that matches both door and furnishing rules
        doc.layers.add("_door")
        doc.layers.add("_furnish")
        mixed_block = doc.blocks.new("DOOR_CHAIR_MIX")
        mixed_block.add_circle((0, 0), radius=0.5)

        msp = doc.modelspace()
        # put the block on a layer that will trigger _door and name that triggers furnishing
        msp.add_blockref("DOOR_CHAIR_MIX", (1, 0), dxfattribs={"layer": "_door"})

        result = analyze_dxf_bytes(to_dxf_bytes(doc))

        # find classification for the ambiguous record
        classifications = result["evidence_classifications"]
        # there should be at least one unknown classification present
        self.assertTrue(any(c["classification"] == "unknown" for c in classifications))

    def test_deterministic_analysis_works_without_api_key(self):
        # ensure GEMINI_API_KEY or similar is not required for deterministic classification
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)

        doc = ezdxf.new()
        doc.layers.add("_wall")
        msp = doc.modelspace()
        msp.add_line((0, 0), (5, 0), dxfattribs={"layer": "_wall"})

        result = analyze_dxf_bytes(to_dxf_bytes(doc))
        self.assertIn("evidence_classifications", result)
        # wall geometry should be present and classified as wall
        classes = [c["classification"] for c in result["evidence_classifications"]]
        self.assertIn("wall", classes)


if __name__ == "__main__":
    unittest.main()
