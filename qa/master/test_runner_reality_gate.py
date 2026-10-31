"""Development regressions only; real target VM must execute runner_reality_gate separately."""
import unittest
from unittest import mock
import runner_reality_gate as g

class RunnerContractTests(unittest.TestCase):
    def test_exact_cachyos_v224_output(self):
        self.assertEqual(g.parse_opencode("opencode v2.2.4\n"),"2.2.4")
    def test_bare_version(self):
        self.assertEqual(g.parse_opencode("2.2.4"),"2.2.4")
    def test_v_version(self):
        self.assertEqual(g.parse_opencode("v2.2.4"),"2.2.4")
    def test_suffix(self):
        self.assertEqual(g.parse_opencode("opencode v2.2.4-rc.1"),"2.2.4")
    def test_whitespace(self):
        self.assertEqual(g.parse_opencode(" opencode v2.2.4 \n"),"2.2.4")
    def test_invalid_major_and_output_fail_closed(self):
        for s in ("opencode v1.2.4","v3.0.0","2.2","opencode error",
                  "opencode v2.2.4\nbad","ollama v2.2.4","v2.2.4; rm -rf /",""):
            with self.subTest(s=s),self.assertRaises(ValueError):
                g.parse_opencode(s)
    def test_missing_real_binary_blocks(self):
        with mock.patch.object(g.shutil,"which",return_value=None):
            with self.assertRaisesRegex(RuntimeError,"real OpenCode missing"):
                g.live_target()
    def test_nonzero_exit_blocks(self):
        class Result:
            returncode=2
            stdout="opencode v2.2.4"
            stderr="failed"
        with mock.patch.object(g.shutil,"which",return_value="/usr/bin/python3"):
            with mock.patch.object(g.subprocess,"run",return_value=Result()):
                with self.assertRaisesRegex(RuntimeError,"exit 2"):
                    g.live_target()
    def test_incomplete_receipt_blocks(self):
        with self.assertRaisesRegex(ValueError,"incomplete evidence"):
            g.verify({},__file__,__file__,"x","r1")
    def test_forged_approval_blocks(self):
        e={k:None for k in ("schema","kind","argv","binary_sha256","runner_sha256",
             "candidate_sha256","job_id","revision","stdout","stderr","exit_code",
             "parsed_version","timestamp","release_approved","scope")}
        e.update(schema=g.SCHEMA,kind="LIVE_EXECUTION",scope="CLI_ONLY",
                 release_approved=True,exit_code=0)
        with self.assertRaisesRegex(ValueError,"untrusted evidence"):
            g.verify(e,__file__,__file__,"x","r1")
if __name__=="__main__":
    unittest.main()
