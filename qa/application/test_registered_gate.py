import importlib.util, pathlib, tempfile, unittest
p=pathlib.Path(__file__).with_name("registered_gate.py")
s=importlib.util.spec_from_file_location("registered_gate",p)
g=importlib.util.module_from_spec(s)
s.loader.exec_module(g)

class FailClosedTests(unittest.TestCase):
    def test_missing_candidate(self):
        with self.assertRaises(ValueError):
            g.register({"job_id":"absent","candidate":"qa/application/jobs/absent/candidate.zip",
                        "sha256":"0"*64,"checks":[]})
    def test_invalid_job(self):
        with self.assertRaises(ValueError):
            g.register({"job_id":"../escape","candidate":"qa/application/jobs/../escape/candidate.zip",
                        "sha256":"0"*64,"checks":[]})
    def test_no_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises((ValueError,KeyError)):
                g.register({})
    def test_required_lifecycle(self):
        self.assertEqual(len(g.REQUIRED),7)
    def test_valid_stages(self):
        self.assertEqual(g.VALID,{"github","vm","host"})

if __name__=="__main__":
    unittest.main()
