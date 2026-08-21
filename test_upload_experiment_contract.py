from pathlib import Path
import io
import unittest
from unittest import mock

try:
    import ezdxf
    from streamlit.testing.v1 import AppTest

    APP_TEST_AVAILABLE = True
except ModuleNotFoundError:
    APP_TEST_AVAILABLE = False

from zuru_upload_staging import UPLOAD_STAGING_REGISTRY, new_token


ROOT = Path(__file__).resolve().parent


class TestUploadExperimentContract(unittest.TestCase):
    def test_app_uses_supported_asgi_entry_and_existing_streamlit_script(self):
        app_source = (ROOT / "zuru_app.py").read_text(encoding="utf-8")
        self.assertIn('st.App(\n    "zuru_simple.py"', app_source)
        self.assertIn("routes=create_upload_routes()", app_source)

    def test_confirmed_upload_uses_existing_ingestion_call_only(self):
        source = (ROOT / "zuru_simple.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("ingest_file_bytes(filename, file_bytes)"), 1)
        self.assertIn("UPLOAD_STAGING_REGISTRY.consume_claim", source)
        self.assertIn("st.session_state.pop(_STAGED_FILE_KEY, None)", source)

    def test_frontend_requires_explicit_confirmation(self):
        source = (
            ROOT / "zuru_staged_uploader_component" / "index.html"
        ).read_text(encoding="utf-8")
        self.assertIn("Потвърди и анализирай", source)
        self.assertIn('button.addEventListener("click", async () => {', source)
        self.assertIn('/claim`, {', source)
        self.assertIn('input.addEventListener("change", async () => {', source)
        self.assertIn('/bytes`, {', source)

    def test_claim_secret_never_uses_url_query_history_or_referrer(self):
        app_source = (ROOT / "zuru_simple.py").read_text(encoding="utf-8")
        component_source = (
            ROOT / "zuru_staged_uploader_component" / "index.html"
        ).read_text(encoding="utf-8")
        combined = app_source + component_source

        for forbidden in (
            "st.query_params",
            "zuru_staged_claim",
            "searchParams",
            "location.assign",
            "location.href",
            "document.referrer",
        ):
            self.assertNotIn(forbidden, combined)
        self.assertIn("window.sessionStorage.setItem", component_source)
        self.assertIn("streamlit:setComponentValue", component_source)
        self.assertIn("window.sessionStorage.removeItem", component_source)

    def test_diagnostics_do_not_log_bytes(self):
        for relative in (
            "zuru_upload_staging.py",
            "zuru_upload_routes.py",
            "zuru_staged_uploader_ui.py",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn("print(", source, relative)
            self.assertNotIn("logger.", source, relative)


@unittest.skipUnless(APP_TEST_AVAILABLE, "Streamlit/ezdxf test dependencies unavailable")
class TestConfirmedUploadIntegration(unittest.TestCase):
    def tearDown(self):
        UPLOAD_STAGING_REGISTRY.close()

    def test_confirmed_staged_dxf_enters_existing_app_once(self):
        UPLOAD_STAGING_REGISTRY.close()
        document = ezdxf.new()
        document.modelspace().add_line(
            (0, 0), (1, 1), dxfattribs={"layer": "WALL"}
        )
        output = io.StringIO()
        document.write(output)
        dxf_bytes = output.getvalue().encode("utf-8")

        owner = new_token()
        intent = UPLOAD_STAGING_REGISTRY.create_intent(
            owner_token=owner,
            filename="mobile.dxf",
            declared_size=len(dxf_bytes),
        )
        UPLOAD_STAGING_REGISTRY.store_stream(
            owner_token=owner,
            upload_id=intent.upload_id,
            chunks=[dxf_bytes],
        )
        claim = UPLOAD_STAGING_REGISTRY.create_claim(
            owner_token=owner, upload_id=intent.upload_id
        )

        app = AppTest.from_file("zuru_simple.py", default_timeout=10)
        with mock.patch(
            "zuru_staged_uploader_ui.staged_uploader",
            side_effect=[claim, None],
        ) as component:
            app.run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(len(UPLOAD_STAGING_REGISTRY), 0)
        self.assertEqual(component.call_count, 2)
        self.assertEqual(
            app.session_state["_zuru_staged_component_generation"], 1
        )


if __name__ == "__main__":
    unittest.main()
