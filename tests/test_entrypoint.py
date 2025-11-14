import importlib
import unittest


class EntryPointTests(unittest.TestCase):
    def test_wrapper_reexports_public_api(self):
        wrapper = importlib.import_module("app_pdf_praa_portable_v7_6")
        implementation = importlib.import_module("pdf_praa_portable")

        self.assertTrue(hasattr(wrapper, "main"))
        self.assertIs(wrapper.main, implementation.main)
        self.assertEqual(set(wrapper.__all__), set(implementation.__all__))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
