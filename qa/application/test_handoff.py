import json
from pathlib import Path
import shutil
import tempfile
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import handoff
import release_coordinator as gate


class HandoffTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base=Path(tmp.name)
        self.job=base/"example_job"
        self.job.mkdir()
        self.evidence=base/"original_evidence"
        (self.evidence/"github").mkdir(parents=True)
        self.target=base/"transport"
        self.trust=base/"trust"
        self.trust.mkdir()
        (self.job/"candidate.zip").write_bytes(b"candidate original bytes")
        checks=[{"id":"github_archive","stage":"github","argv":["python3","-V"]}]
        checks.extend({"id":i,"stage":"vm","argv":[]} for i in
                      ("install","upgrade","rollback","gui","tray","recovery","security"))
        checks.append({"id":"host_hw","stage":"host","argv":[]})
        manifest={"job_id":"example_job",
                  "candidate":"qa/application/jobs/example_job/candidate.zip",
                  "sha256":gate.sha256(self.job/"candidate.zip"),
                  "checks":checks}
        (self.job/"manifest.json").write_text(json.dumps(manifest))
        (self.job/"policy.json").write_text(json.dumps({
            "schema":"devnet-qa-checklist-v1","job_id":"example_job","checks":checks}))
        self.private=Ed25519PrivateKey.generate()
        (self.job/"policy.sig").write_bytes(
            self.private.sign((self.job/"policy.json").read_bytes()))
        (self.trust/"operator.pub").write_bytes(
            self.private.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo))
        self.source="a"*40
        results=[{"id":c["id"],"status":"PASS","exit_code":0,
                  "output_sha256":"e"*64} if c["stage"]=="github" else
                 {"id":c["id"],"stage":c["stage"],"status":"NOT_TESTED"}
                 for c in checks]
        receipt={"schema":1,"job_id":"example_job",
                 "candidate_sha256":manifest["sha256"],
                 "manifest_sha256":gate.sha256(self.job/"manifest.json"),
                 "github_sha":self.source,"checks":results,
                 "full_acceptance":False,"release_approved":False}
        (self.evidence/"github"/"receipt.json").write_text(json.dumps(receipt))
        self.calls=[]

    def signatures(self,path,signature,key_path):
        public=serialization.load_pem_public_key(key_path.read_bytes())
        public.verify(signature.read_bytes(),path.read_bytes())

    def github_attest(self,path,repo,sha):
        self.calls.append(path.name)
        self.assertEqual(sha,self.source)
        self.assertEqual(repo,"devnet82/vr-stack-control")

    def make(self):
        return handoff.assemble(self.job,self.evidence,self.target)

    def check(self):
        return handoff.verify(self.target,self.trust,
                              "devnet82/vr-stack-control",
                              signature_verifier=self.signatures,
                              github_verifier=self.github_attest)

    def test_valid_handoff_verifies_both_attestations_scope_limited(self):
        self.make()
        result=self.check()
        self.assertEqual(result["github"],"PASS_SIGNED")
        self.assertEqual(result["vm"],"NOT_TESTED")
        self.assertEqual(result["host"],"NOT_TESTED")
        self.assertIs(result["release_approved"],False)
        self.assertEqual(set(self.calls),{"candidate.zip","receipt.json"})

    def test_handoff_never_overwrites(self):
        self.make()
        with self.assertRaises(gate.Blocked):
            self.make()

    def test_changed_candidate_is_blocked(self):
        self.make()
        (self.target/"example_job"/"candidate.zip").write_bytes(b"tampered")
        with self.assertRaises(gate.Blocked):
            self.check()

    def test_changed_manifest_is_blocked(self):
        self.make()
        (self.target/"example_job"/"manifest.json").write_text("{}")
        with self.assertRaises((gate.Blocked,KeyError)):
            self.check()

    def test_changed_policy_signature_is_blocked(self):
        self.make()
        (self.target/"example_job"/"policy.sig").write_bytes(b"fake")
        with self.assertRaises(Exception):
            self.check()

    def test_missing_attestation_is_blocked(self):
        self.make()
        def deny(*_):
            raise gate.Blocked("no valid GitHub attestation")
        with self.assertRaises(gate.Blocked):
            handoff.verify(self.target,self.trust,"devnet82/vr-stack-control",
                           signature_verifier=self.signatures,
                           github_verifier=deny)

    def test_missing_receipt_is_blocked(self):
        self.make()
        (self.target/"evidence"/"github"/"receipt.json").unlink()
        with self.assertRaises(gate.Blocked):
            self.check()

    def test_handoff_fake_release_approval_is_blocked(self):
        self.make()
        p=self.target/"HANDOFF.json"
        data=json.loads(p.read_text())
        data["release_approved"]=True
        p.write_text(json.dumps(data))
        with self.assertRaises(gate.Blocked):
            self.check()

    def test_symlink_candidate_is_blocked(self):
        self.make()
        p=self.target/"example_job"/"candidate.zip"
        p.unlink()
        p.symlink_to(self.job/"candidate.zip")
        with self.assertRaises(gate.Blocked):
            self.check()

    def test_mismatched_source_commit_is_blocked(self):
        self.make()
        p=self.target/"HANDOFF.json"
        data=json.loads(p.read_text())
        data["github_sha"]="b"*40
        p.write_text(json.dumps(data))
        with self.assertRaises(gate.Blocked):
            self.check()

if __name__=="__main__":
    unittest.main()
