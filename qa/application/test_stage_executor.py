import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import stage_executor as stage
import release_coordinator as gate

class RestrictedStageExecution(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.job = root/"demo"
        self.job.mkdir()
        self.ev = root/"evidence"
        (self.ev/"github").mkdir(parents=True)
        self.trust = root/"trust"
        self.trust.mkdir()
        self.driver_path = root/"protected-driver.json"
        self.candidate = self.job/"candidate.zip"
        self.candidate.write_bytes(b"fixture-candidate")
        ids = ["install", "upgrade", "rollback", "gui", "tray", "recovery", "security"]
        self.vm_ids = ids
        checks = [{"id":"github_integrity","stage":"github",
                   "argv":["python3", "check.py"]}]
        checks += [{"id":cid,"stage":"vm","argv":[]} for cid in ids]
        checks += [{"id":"host_gpu","stage":"host","argv":[]}]
        self.manifest = {"job_id":"demo",
                         "candidate":"qa/application/jobs/demo/candidate.zip",
                         "sha256":gate.sha256(self.candidate), "checks":checks}
        (self.job/"manifest.json").write_text(json.dumps(self.manifest))
        (self.job/"manifest.sig").write_text("fixture-untrusted")
        self.sha = "a" * 40
        receipt = {"schema":1,"job_id":"demo",
                   "candidate_sha256":self.manifest["sha256"],
                   "manifest_sha256":gate.sha256(self.job/"manifest.json"),
                   "github_sha":self.sha, "release_approved":False,
                   "full_acceptance":False,"checks":[]}
        for check in checks:
            if check["stage"]=="github":
                receipt["checks"].append({"id":check["id"],
                                          "status":"PASS", "exit_code":0,
                                          "output_sha256":"0"*64})
            else:
                receipt["checks"].append({"id":check["id"],
                                          "stage":check["stage"],
                                          "status":"NOT_TESTED"})
        (self.ev/"github"/"receipt.json").write_text(json.dumps(receipt))
        self.driver = {"schema":"devnet-stage-driver-v1","stage":"vm",
                       "job_id":"demo", "checks":{
                           cid:{"argv":[sys.executable,"-c",
                                        "print('FIXTURE REAL SUBPROCESS EXECUTED')"],
                                "timeout":10} for cid in ids}}
        self.driver_path.write_text(json.dumps(self.driver))
        self.params = {"job_dir":self.job,"evidence_dir":self.ev,
                       "driver_path":self.driver_path,"trust_dir":self.trust,
                       "repo":"devnet82/vr-stack-control","stage":"vm",
                       "github_verifier":lambda *args: None,
                       "signature_verifier":lambda *args: None}

    def run_vm(self):
        with mock.patch.object(stage,"safe_driver",return_value=self.driver):
            return stage.run_stage(**self.params)

    def test_real_subprocesses_run_and_receipt_stays_unsigned(self):
        result = self.run_vm()
        self.assertEqual(result["checks_passed"],7)
        self.assertEqual(result["result"],"EXECUTED_UNSIGNED")
        self.assertFalse((self.ev/"vm"/"receipt.sig").exists())
        receipt = json.loads((self.ev/"vm"/"receipt.json").read_text())
        self.assertEqual(set(receipt["checks"]),set(self.vm_ids))
        self.assertTrue(all(v["status"]=="PASS" for v in receipt["checks"].values()))
        self.assertIn("FIXTURE REAL SUBPROCESS EXECUTED",
                      (self.ev/"vm"/"logs"/"gui.log").read_text())
        self.assertIs(receipt["release_approved"],False)

    def test_check_failure_never_creates_pass_receipt(self):
        self.driver["checks"]["install"]["argv"] = [
            sys.executable, "-c", "raise SystemExit(2)"]
        with self.assertRaises(gate.Blocked):
            self.run_vm()
        self.assertTrue((self.ev/"vm"/"blocked.json").exists())
        self.assertFalse((self.ev/"vm"/"receipt.json").exists())
        self.assertFalse((self.ev/"vm"/"logs"/"upgrade.log").exists())

    def test_changed_candidate_must_restart_github(self):
        self.candidate.write_bytes(b"changed")
        with self.assertRaises(gate.Blocked):
            self.run_vm()

    def test_existing_evidence_cannot_be_reused(self):
        self.run_vm()
        with self.assertRaises(gate.Blocked):
            self.run_vm()

    def test_no_missing_github_handoff_allowed(self):
        (self.ev/"github"/"receipt.json").unlink()
        with self.assertRaises(OSError):
            self.run_vm()

    def test_driver_must_be_root_controlled(self):
        with self.assertRaises(gate.Blocked):
            stage.safe_driver(self.driver_path, self.vm_ids)

    def test_different_driver_scope_is_blocked(self):
        self.driver["checks"].pop("gui")
        with self.assertRaises(gate.Blocked):
            stage.validate_driver(self.driver, self.vm_ids)

    def test_exact_driver_scope_validation(self):
        # GitHub setup-python can expose sys.executable as a symlink; driver
        # policy intentionally requires a direct root-managed executable.
        for test in self.driver["checks"].values():
            test["argv"] = ["/usr/bin/printf", "TEST_OK"]
        self.assertEqual(stage.validate_driver(self.driver,self.vm_ids),self.driver)

    def test_host_pauses_before_first_real_command(self):
        self.params["stage"]="host"
        driver={"schema":"devnet-stage-driver-v1","stage":"host",
                "job_id":"demo","checks":{"host_gpu":{
                    "argv":[sys.executable,"-c","print('must never run')"],
                    "timeout":10}}}
        def pause():
            raise gate.Blocked("gaming")
        with mock.patch.object(stage,"safe_driver",return_value=driver):
            with mock.patch.object(gate,"signed_stage",return_value="a"*64):
                with self.assertRaises(gate.Blocked):
                    stage.run_stage(**self.params,pause=pause)
        self.assertFalse((self.ev/"host"/"logs"/"host_gpu.log").exists())
        self.assertFalse((self.ev/"host"/"receipt.json").exists())

if __name__=="__main__":
    unittest.main()
