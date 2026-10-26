"""Compile-time Qt constants must not masquerade as loaded runtime validation."""
import unittest
from vantage.qt_runtime import EXPECTED, validate_versions

class QtRuntimeTests(unittest.TestCase):
    def check(self, **changes):
        values=dict(packages=dict(EXPECTED),compiled='6.9.0',before='6.9.1',after='6.9.1',library='6.9.1',webengine='6.9.0')
        values.update(changes)
        return validate_versions(**values)
    def test_expected_binding_build_and_runtime_are_compatible(self):self.check()
    def test_old_runtime_is_rejected_even_when_package_metadata_is_pinned(self):
        with self.assertRaisesRegex(RuntimeError,'runtime'):self.check(before='6.9.0',after='6.9.0',library='6.9.0')
    def test_webengine_cannot_replace_loaded_core(self):
        with self.assertRaisesRegex(RuntimeError,'runtime'):self.check(after='6.9.0')
    def test_library_runtime_must_agree(self):
        with self.assertRaisesRegex(RuntimeError,'runtime'):self.check(library='6.9.0')
    def test_webengine_version_must_match_pin(self):
        with self.assertRaisesRegex(RuntimeError,'WebEngine'):self.check(webengine='6.10.0')
    def test_package_version_drift_is_rejected(self):
        packages=dict(EXPECTED);packages['PyQt6-Qt6']='6.10.0'
        with self.assertRaisesRegex(RuntimeError,'PyQt6-Qt6'):self.check(packages=packages)
    def test_unexpected_binding_build_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'build'):self.check(compiled='6.10.0')
