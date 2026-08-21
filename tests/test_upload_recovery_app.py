import io
import importlib
import os
import sys
import types
import unittest
from unittest import mock

import ezdxf
from streamlit.testing.v1 import AppTest

from zuru_upload_recovery import UPLOAD_SESSION_REGISTRY


class UploadRecoveryAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # AppTest executes the script repeatedly in one interpreter. Isolate the
        # optional Gemini import and restore the real analyzer after older tests
        # inject their lightweight ``zuru_core`` test double.
        cls._original_genai = sys.modules.get("google.generativeai")
        fake_genai = types.ModuleType("google.generativeai")
        fake_genai.configure = lambda **_: None
        fake_genai.GenerativeModel = lambda *_args, **_kwargs: None
        sys.modules["google.generativeai"] = fake_genai

        sys.modules.pop("zuru_core", None)
        importlib.import_module("zuru_core")

    @classmethod
    def tearDownClass(cls):
        if cls._original_genai is None:
            sys.modules.pop("google.generativeai", None)
        else:
            sys.modules["google.generativeai"] = cls._original_genai

    @staticmethod
    def _minimal_dxf_bytes():
        document = ezdxf.new("R2010")
        document.modelspace().add_line(
            (0, 0),
            (10, 10),
            dxfattribs={"layer": "WALLS"},
        )
        output = io.StringIO()
        document.write(output)
        return output.getvalue().encode("utf-8")

    def test_fresh_session_renders_one_uploader_without_recovery_warning(self):
        app = AppTest.from_file("../zuru_simple.py", default_timeout=20)

        app.run()

        self.assertEqual([], list(app.exception))
        self.assertEqual(1, len(app.get("file_uploader")))
        self.assertEqual([], list(app.warning))

    def test_replaced_session_renders_warning_and_clean_uploader(self):
        owner_token = "R" * 32
        UPLOAD_SESSION_REGISTRY.observe(owner_token, "a" * 32)
        app = AppTest.from_file("../zuru_simple.py", default_timeout=20)
        app.query_params["zuru_upload_owner"] = owner_token

        app.run()

        self.assertEqual([], list(app.exception))
        self.assertEqual(1, len(app.get("file_uploader")))
        self.assertEqual(1, len(app.warning))
        self.assertIn("Избери файла отново", app.warning[0].value)

    def test_desktop_dxf_upload_reaches_existing_analysis_path(self):
        app = AppTest.from_file("../zuru_simple.py", default_timeout=20).run()

        app.get("file_uploader")[0].upload(
            "control.dxf",
            self._minimal_dxf_bytes(),
            "application/dxf",
        ).run()

        self.assertEqual([], list(app.exception))
        self.assertEqual([], list(app.error))
        metrics = {metric.label: metric.value for metric in app.metric}
        self.assertEqual("1", metrics["📊 DXF entities"])
        self.assertEqual("1", metrics["🧾 Evidence records"])

    def test_desktop_dwg_upload_preserves_existing_converter_and_analysis_path(self):
        converter_module = types.ModuleType("zuru_test_dwg_converter")
        converter_module.convert_dwg_to_dxf = lambda _: self._minimal_dxf_bytes()

        with mock.patch.dict(
            os.environ,
            {"DWG_CONVERTER_IMPL": "zuru_test_dwg_converter"},
        ), mock.patch.dict(
            sys.modules,
            {"zuru_test_dwg_converter": converter_module},
        ):
            app = AppTest.from_file("../zuru_simple.py", default_timeout=20).run()
            app.get("file_uploader")[0].upload(
                "control.dwg",
                b"bounded-test-dwg",
                "application/acad",
            ).run()

        self.assertEqual([], list(app.exception))
        self.assertEqual([], list(app.error))
        metrics = {metric.label: metric.value for metric in app.metric}
        self.assertEqual("1", metrics["📊 DXF entities"])
        self.assertEqual("1", metrics["🧾 Evidence records"])


if __name__ == "__main__":
    unittest.main()
