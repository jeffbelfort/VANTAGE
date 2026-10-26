"""Windowed executable failures must retain their real exception and fail CI."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('verify_windows',Path(__file__).resolve().parents[1]/'packaging/verify_windows.py')
verify=importlib.util.module_from_spec(spec);spec.loader.exec_module(verify)

class PackagedDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.report=Path(self.temp.name)/'engine.json'
    def result(self, code=0, **report):
        if report:self.report.write_text(json.dumps(report),encoding='utf-8')
        return subprocess.CompletedProcess(['VANTAGE.exe','--release-self-test'],code,'','native startup failure')
    def test_traceback_is_in_ci_error(self):
        result=self.result(1,passed=False,traceback='ValueError: actual startup exception')
        with self.assertRaisesRegex(RuntimeError,'actual startup exception'):verify.validate_process_result(result,self.report,'engine')
    def test_success_report_cannot_mask_nonzero_exit(self):
        with self.assertRaisesRegex(RuntimeError,'exited 1'):verify.validate_process_result(self.result(1,passed=True),self.report,'engine')
    def test_zero_exit_requires_report(self):
        with self.assertRaisesRegex(RuntimeError,'no completion'):verify.validate_process_result(self.result(),self.report,'engine')
    def test_failure_report_cannot_pass_with_zero_exit(self):
        with self.assertRaisesRegex(RuntimeError,'failed'):verify.validate_process_result(self.result(passed=False),self.report,'engine')
    def test_malformed_report_is_failure(self):
        self.report.write_text('{',encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError,'Cannot read'):verify.validate_process_result(self.result(),self.report,'engine')
    def test_native_failure_is_reported_without_python_json(self):
        with self.assertRaisesRegex(RuntimeError,'native startup failure'):verify.validate_process_result(self.result(1),self.report,'engine')
    def test_success_requires_explicit_passed_boolean(self):
        result=self.result(passed=True)
        self.assertTrue(verify.validate_process_result(result,self.report,'engine')['passed'])
