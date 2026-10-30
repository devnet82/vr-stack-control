import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

source = Path(__file__).with_name("release_coordinator.py")
spec = importlib.util.spec_from_file_location("release_coordinator", source)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class StageChain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.job = root / "demo"
        self.job.mkdir()
        self.evidence = root / "evidence"
        self.trust = root / "trust"
        self.trust.mkdir()
        (self.job / "candidate.zip").write_bytes(b"fixed-registered-app-candidate")
        checks = [{"id": "package_integrity", "stage": "github", "argv": ["python3", "-V"]}]
        checks += [{"id": x, "stage": "vm", "argv": []} for x in
                   ("install", "upgrade", "rollback", "gui", "tray", "recovery", "security")]
        checks += [{"id": "vr_host", "stage": "host", "argv": []}]
        self.manifest = {"job_id": "demo",
                         "candidate": "qa/application/jobs/demo/candidate.zip",
                         "sha256": gate.sha256(self.job / "candidate.zip"),
                         "checks": checks}
        self.save_manifest()
        self.source = "a" * 40
        self.privates = {s: Ed25519PrivateKey.generate() for s in ("operator", "vm", "host")}
        for stage, key in self.privates.items():
            (self.trust / (stage + ".pub")).write_bytes(
                key.public_key().public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo))
        (self.job / "manifest.sig").write_bytes(
            self.privates["operator"].sign((self.job / "manifest.json").read_bytes()))
        self.make_github()
        self.make_signed_stages()

    def save_manifest(self):
        (self.job / "manifest.json").write_text(json.dumps(self.manifest, sort_keys=True))

    def write_receipt(self, stage, body):
        p = self.evidence / stage
        p.mkdir(exist_ok=True, parents=True)
        raw = json.dumps(body, sort_keys=True).encode()
        (p / "receipt.json").write_bytes(raw)
        if stage in self.privates:
            (p / "receipt.sig").write_bytes(self.privates[stage].sign(raw))

    def make_github(self):
        results = []
        for check in self.manifest["checks"]:
            if check["stage"] == "github":
                results.append({"id": check["id"], "status": "PASS",
                                "exit_code": 0, "output_sha256": "e" * 64})
            else:
                results.append({"id": check["id"], "stage": check["stage"],
                                "status": "NOT_TESTED"})
        body = {"schema": 1, "job_id": "demo",
                "candidate_sha256": self.manifest["sha256"],
                "manifest_sha256": gate.sha256(self.job / "manifest.json"),
                "github_sha": self.source, "checks": results,
                "full_acceptance": False, "release_approved": False}
        self.write_receipt("github", body)

    def make_signed_stages(self):
        prev = gate.sha256(self.evidence / "github" / "receipt.json")
        for stage in ("vm", "host"):
            checks = {}
            logdir = self.evidence / stage / "logs"
            logdir.mkdir(parents=True, exist_ok=True)
            for check in self.manifest["checks"]:
                if check["stage"] != stage:
                    continue
                cid = check["id"]
                log = logdir / (cid + ".log")
                log.write_text("actual executor placeholder evidence " + cid)
                checks[cid] = {"status": "PASS", "log": "logs/" + cid + ".log",
                               "log_sha256": gate.sha256(log)}
            body = {"schema": gate.SCHEMA, "stage": stage, "job_id": "demo",
                    "candidate_sha256": self.manifest["sha256"],
                    "manifest_sha256": gate.sha256(self.job / "manifest.json"),
                    "github_sha": self.source,
                    "previous_receipt_sha256": prev, "checks": checks,
                    "release_approved": False}
            self.write_receipt(stage, body)
            prev = gate.sha256(self.evidence / stage / "receipt.json")

    def signature_verifier(self, receipt, signature, pubkey):
        public = serialization.load_pem_public_key(pubkey.read_bytes())
        public.verify(signature.read_bytes(), receipt.read_bytes())

    def assess(self):
        return gate.assess(self.job, self.evidence, self.trust,
                           "devnet82/vr-stack-control",
                           github_verifier=lambda path, repo, sha: (
                               self.assertEqual(sha, self.source),
                               self.assertEqual(repo, "devnet82/vr-stack-control")),
                           stage_verifier=self.signature_verifier)

    def blocked(self):
        with self.assertRaises((gate.Blocked, ValueError, InvalidSignature)):
            self.assess()

    def test_exact_signed_chain_reaches_operator_only(self):
        r = self.assess()
        self.assertEqual(r["decision"], "READY_FOR_OPERATOR_ACCEPTANCE")
        self.assertIs(r["release_approved"], False)
        self.assertEqual(r["host"], "PASS_SIGNED")

    def test_changed_candidate_cannot_inherit_evidence(self):
        (self.job / "candidate.zip").write_bytes(b"changed")
        self.blocked()

    def test_changed_checklist_invalidates_every_stage(self):
        self.manifest["checks"].append({"id": "new_regression", "stage": "vm", "argv": []})
        self.save_manifest()
        self.blocked()

    def test_missing_github_is_blocked(self):
        (self.evidence / "github" / "receipt.json").unlink()
        with self.assertRaises((OSError, gate.Blocked)):
            self.assess()

    def test_missing_vm_is_blocked(self):
        (self.evidence / "vm" / "receipt.sig").unlink()
        self.blocked()

    def test_tampered_vm_evidence_is_blocked(self):
        p = self.evidence / "vm" / "receipt.json"
        p.write_bytes(p.read_bytes() + b" ")
        with self.assertRaises(Exception):
            self.assess()

    def test_wrong_vm_revision_is_blocked_even_with_valid_signature(self):
        p = self.evidence / "vm" / "receipt.json"
        d = json.loads(p.read_text())
        d["github_sha"] = "b" * 40
        self.write_receipt("vm", d)
        self.blocked()

    def test_vm_fail_does_not_advance(self):
        p = self.evidence / "vm" / "receipt.json"
        d = json.loads(p.read_text())
        d["checks"]["gui"]["status"] = "FAIL"
        self.write_receipt("vm", d)
        self.blocked()

    def test_host_cannot_inherit_different_vm_receipt(self):
        p = self.evidence / "host" / "receipt.json"
        d = json.loads(p.read_text())
        d["previous_receipt_sha256"] = "0" * 64
        self.write_receipt("host", d)
        self.blocked()

    def test_no_host_receipt_does_not_grant_acceptance(self):
        (self.evidence / "host" / "receipt.json").unlink()
        self.blocked()

    def test_wrong_github_execution_exit_is_blocked(self):
        p = self.evidence / "github" / "receipt.json"
        d = json.loads(p.read_text())
        d["checks"][0]["exit_code"] = 1
        self.write_receipt("github", d)
        self.blocked()

    def test_13_smokes_cannot_replace_full_checklist(self):
        self.manifest["checks"] = self.manifest["checks"][:1]
        self.save_manifest()
        self.blocked()

    def test_unsigned_host_pass_cannot_advance(self):
        (self.evidence / "host" / "receipt.sig").write_bytes(b"fake-signature")
        with self.assertRaises(Exception):
            self.assess()

    def test_unsigned_scope_change_is_blocked(self):
        self.manifest["checks"] = self.manifest["checks"][:-1]
        self.save_manifest()
        with self.assertRaises(Exception):
            self.assess()

    def test_tampered_vm_check_log_is_blocked(self):
        (self.evidence / "vm" / "logs" / "gui.log").write_text("tampered")
        self.blocked()

    def test_missing_installed_candidate(self):
        (self.job / "candidate.zip").unlink()
        self.blocked()


if __name__ == "__main__":
    unittest.main()
