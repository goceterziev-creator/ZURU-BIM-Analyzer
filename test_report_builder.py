import io
import json
import os
import unittest

import ezdxf

from zuru_core import analyze_dxf_bytes
from report_builder import build_reports


def to_dxf_bytes(doc):
    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue().encode("utf-8")


class ReportBuilderTests(unittest.TestCase):
    def test_reports_include_unknown_and_provenance_and_preserve_raw(self):
        # create doc that will produce an ambiguous/unknown classification
        doc = ezdxf.new()
        doc.layers.add("_door")
        doc.layers.add("_furnish")
        mixed_block = doc.blocks.new("DOOR_CHAIR_MIX")
        mixed_block.add_circle((0, 0), radius=0.5)

        msp = doc.modelspace()
        msp.add_blockref("DOOR_CHAIR_MIX", (1, 0), dxfattribs={"layer": "_door"})

        analysis = analyze_dxf_bytes(to_dxf_bytes(doc))

        reports = build_reports(analysis, "testfile.dxf")

        # deterministic classifications JSON must parse
        classifications = json.loads(reports["deterministic_classifications_json"])

        # at least one unknown must exist (preserve unknown)
        self.assertTrue(any(c.get("classification") == "unknown" for c in classifications))

        # provenance should be present for classifications (may be empty list/string but key should exist)
        self.assertTrue(any("provenance" in c for c in classifications))

        # normalized evidence JSON must round-trip to the original evidence records
        raw_from_reports = json.loads(reports["normalized_evidence_json"])
        self.assertEqual(raw_from_reports, analysis["evidence_records"])

        # report text must clearly separate deterministic classifications from source evidence
        self.assertIn("DETERMINISTIC EVIDENCE-BOUND CLASSIFICATIONS", reports["evidence_report_txt"]) 

    def test_report_builder_does_not_require_gemini_env(self):
        # ensure environment variables for AI keys do not affect report building
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)

        doc = ezdxf.new()
        doc.layers.add("_wall")
        msp = doc.modelspace()
        msp.add_line((0, 0), (5, 0), dxfattribs={"layer": "_wall"})

        analysis = analyze_dxf_bytes(to_dxf_bytes(doc))
        # Building reports should not raise and should include classification counts
        reports = build_reports(analysis, "nofkey.dxf")
        self.assertIn("classification_counts", reports)


if __name__ == "__main__":
    unittest.main()
