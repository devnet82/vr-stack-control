#!/usr/bin/env python3
import hashlib,json,stat,tempfile,unittest,zipfile
from pathlib import Path
import guest_app_qa as app

class VMGuestHarnessRegression(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.p=Path(self.t.name)/'app.zip'
        self.good={'test_scope':'pyside6 desktop acceptance','checks_passed':[f'check_{i:02}' for i in range(33)]}
    def output(self, obj=None):
        return 'Qt diagnostics\n'+json.dumps(self.good if obj is None else obj)+'\n'
    def test_desktop_success(self):
        self.assertEqual(app.classify_desktop(0,self.output()),app.PASS)
    def test_failed_exit(self):
        self.assertEqual(app.classify_desktop(2,self.output()),app.FAIL)
    def test_traceback(self):
        self.assertEqual(app.classify_desktop(0,'Traceback (most recent call last):\n'+self.output()),app.FAIL)
    def test_missing_json(self):
        self.assertEqual(app.classify_desktop(0,'OK\n'),app.NOT_TESTED)
    def test_skipped_count(self):
        d={**self.good,'checks_passed':['a']*32}
        self.assertEqual(app.classify_desktop(0,self.output(d)),app.FAIL)
    def test_duplicates(self):
        d={**self.good,'checks_passed':['one']*33}
        self.assertEqual(app.classify_desktop(0,self.output(d)),app.FAIL)
    def test_errors(self):
        d={**self.good,'checks_failed':['bad']}
        self.assertEqual(app.classify_desktop(0,self.output(d)),app.FAIL)
    def test_wrong_scope(self):
        d={**self.good,'test_scope':'generic'}
        self.assertEqual(app.classify_desktop(0,self.output(d)),app.NOT_TESTED)
    def mkzip(self,name='foo.py',data=b'foo'):
        with zipfile.ZipFile(self.p,'w') as z:z.writestr(name,data)
        return hashlib.sha256(self.p.read_bytes()).hexdigest()
    def test_dependency_clean_install(self):
        self.assertEqual(app.dependency_status(0,0),app.PASS)
    def test_dependency_interrupted_exit_minus9(self):
        self.assertEqual(app.dependency_status(-9,0),app.NOT_TESTED)
    def test_dependency_failed_import(self):
        self.assertEqual(app.dependency_status(0,1),app.NOT_TESTED)
    def test_good_zip(self):
        sha=self.mkzip()
        self.assertEqual(app.validate_zip(self.p,sha),1)
    def test_wrong_hash(self):
        self.mkzip()
        with self.assertRaises(ValueError):app.validate_zip(self.p,'0'*64)
    def test_zip_traversal(self):
        sha=self.mkzip('../evil')
        with self.assertRaises(ValueError):app.validate_zip(self.p,sha)
    def test_zip_symlink(self):
        with zipfile.ZipFile(self.p,'w') as z:
            info=zipfile.ZipInfo('symlink');info.create_system=3
            info.external_attr=(stat.S_IFLNK|0o777)<<16
            z.writestr(info,'target')
        with self.assertRaises(ValueError):app.validate_zip(self.p,hashlib.sha256(self.p.read_bytes()).hexdigest())
    def test_zip_duplicates(self):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',UserWarning)
            with zipfile.ZipFile(self.p,'w') as z:
                z.writestr('a','one');z.writestr('a','two')
        with self.assertRaises(ValueError):app.validate_zip(self.p,hashlib.sha256(self.p.read_bytes()).hexdigest())
    def test_missing_archive(self):
        with self.assertRaises(FileNotFoundError):app.validate_zip(self.p,app.APP_SHA256)
    def test_check_no_pass_on_debian(self):
        rc,out=app.run(['python3','-c','print("ok")'])
        self.assertEqual(rc,0)
        self.assertIn('ok',out)

if __name__=='__main__':unittest.main()