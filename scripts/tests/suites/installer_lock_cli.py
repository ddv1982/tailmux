import hashlib
import json
import os
import shutil
import signal
import subprocess
import time
import unittest

from fixture_env import cli_environment
import installer_cli


class LockAcquisition(unittest.TestCase):
    def setUp(self):
        self.life = installer_cli.Lifecycle(methodName='runTest')
        self.addCleanup(self.life.doCleanups)
        self.life.setUp()

    def punctuation_prefix(self):
        f = self.life
        f.prefix = f.home / 'bin \' ; $(exit 91) `exit 92` " [x]'
        return ['--prefix', str(f.prefix)]

    def owner_write_failure(self, *args):
        f = self.life
        older, receipt = f.older_owned()
        before = f.tree()
        result = subprocess.run(
            ['/bin/bash', '-c', 'trap "" XFSZ; ulimit -f 0; exec /bin/bash "$@"',
             'fault', str(installer_cli.SETUP), *args],
            env=cli_environment(f.bin, f.env), capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('File too large', result.stderr)
        self.assertNotIn('Client installed at', result.stdout)
        self.assertNotIn('Client uninstall complete', result.stdout)
        self.assertFalse(f.trace.exists())
        owner = f.prefix / '.tailmux-install-lock/owner'
        print('P1 acquisition evidence ' + json.dumps({
            'operation': list(args), 'exit': result.returncode, 'stderr': result.stderr,
            'lock_present': owner.parent.exists(), 'owner_hex': owner.read_bytes().hex() if owner.exists() else None,
            'binary_unchanged': (f.prefix / 'tailmux').read_bytes() == older,
            'receipt_unchanged': (f.prefix / '.tailmux-receipt').read_bytes() == receipt,
            'forbidden_called': f.trace.exists()}), flush=True)
        f.assert_old_pair(older, receipt)
        self.assertEqual(f.tree(), before)

    def test_owner_write_failure_install(self):
        self.owner_write_failure('install')

    def test_owner_write_failure_replace(self):
        self.owner_write_failure('install', '--replace-owned')

    def test_owner_write_failure_uninstall(self):
        self.owner_write_failure('uninstall')

    def owner_cmp(self, pause=False):
        f = self.life
        ready = f.root / 'acquisition-ready'
        f.env['ACQUISITION_READY'] = str(ready)
        f.script('cmp', '''#!/bin/bash
if [[ "$2" == */.tailmux-install-lock/owner ]]; then
''' + ('''  if [[ ! -e "$ACQUISITION_READY" ]]; then
    : > "$ACQUISITION_READY"
    exec /bin/sleep 30
  fi
''' if pause else '  exit 73\n') + '''fi
exec "''' + shutil.which('cmp') + '''" "$@"
''')
        return ready

    def test_owner_verification_failure_preserves_inventory(self):
        f = self.life
        older, receipt = f.older_owned()
        before = f.tree()
        self.owner_cmp()
        for args in [('install',), ('install', '--replace-owned'), ('uninstall',)]:
            with self.subTest(args=args):
                result = f.refusal(*args)
                self.assertEqual(result.returncode, 1, result.stderr)
                f.assert_old_pair(older, receipt)
                self.assertEqual(f.tree(), before)

    def test_cleanup_failure_preserves_original_exit(self):
        f = self.life
        older, receipt = f.older_owned()
        self.owner_cmp()
        attempted = f.root / 'cleanup-attempted'
        f.env['CLEANUP_ATTEMPTED'] = str(attempted)
        f.script('rm', '''#!/bin/bash
: > "$CLEANUP_ATTEMPTED"
exit 74
''')
        result = f.refusal('install', '--replace-owned')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertTrue(attempted.exists())
        self.assertTrue((f.prefix / '.tailmux-install-lock/owner').is_file())
        self.assertEqual((f.prefix / 'tailmux').read_bytes(), older)
        self.assertEqual((f.prefix / '.tailmux-receipt').read_bytes(), receipt)

    def pause_acquisition(self, args):
        f = self.life
        ready = self.owner_cmp(pause=True)
        ready.unlink(missing_ok=True)
        p = subprocess.Popen(['/bin/bash', str(installer_cli.SETUP), *args],
                             env=cli_environment(f.bin, f.env), stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, start_new_session=True)
        self.addCleanup(self.stop_process, p)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not ready.exists() and p.poll() is None:
            time.sleep(.02)
        self.assertTrue(ready.exists(), 'CLI never reached owner verification')
        owner = f.prefix / '.tailmux-install-lock/owner'
        self.assertRegex(owner.read_bytes(), rb'\Atailmux-lock-v1\nuid=\d+\ntransaction=\.tailmux-tx\.\d+\.\d+\n\Z')
        return p

    def stop_process(self, p):
        self.life.stop_process(p)
        p.communicate(timeout=5)

    def terminate_acquisition(self, p):
        os.killpg(p.pid, signal.SIGTERM)
        stdout, stderr = p.communicate(timeout=10)
        self.assertEqual(p.returncode, -signal.SIGTERM, stderr.decode())
        self.assertNotIn(b'Client installed at', stdout)
        self.assertNotIn(b'Client uninstall complete', stdout)
        self.assertFalse(self.life.trace.exists())

    def test_sigterm_during_acquisition_and_competing_writers(self):
        f = self.life
        prefix_args = self.punctuation_prefix()
        f.success('install', *prefix_args)
        older = b'#!/bin/bash\nprintf "older usable client\\n"\n'
        receipt = ('tailmux-receipt-v1\n' + str(f.prefix / 'tailmux') + '\n' +
                   hashlib.sha256(older).hexdigest() + '\n').encode()
        (f.prefix / 'tailmux').write_bytes(older)
        (f.prefix / '.tailmux-receipt').write_bytes(receipt)
        before = f.tree()
        for args in [('install',), ('install', '--replace-owned'), ('uninstall',)]:
            with self.subTest(args=args):
                p = self.pause_acquisition([*args, *prefix_args])
                for other in [('install',), ('install', '--replace-owned'), ('uninstall',)]:
                    f.refusal(*other, *prefix_args, contains='locked')
                self.terminate_acquisition(p)
                f.assert_old_pair(older, receipt)
                self.assertEqual(f.tree(), before)

    def test_unknown_preexisting_lock_is_untouched(self):
        f = self.life
        older, receipt = f.older_owned()
        lock = f.prefix / '.tailmux-install-lock'
        lock.mkdir(mode=0o700)
        owner = lock / 'owner'
        for data in (None, b'', b'unknown owner\n'):
            with self.subTest(owner=data):
                if data is not None:
                    owner.write_bytes(data)
                    owner.chmod(0o600)
                before = f.tree()
                for args in [('install',), ('install', '--replace-owned'), ('uninstall',)]:
                    f.refusal(*args, contains='locked')
                    self.assertEqual(f.tree(), before)
                    self.assertEqual(owner.read_bytes() if owner.exists() else None, data)
                    self.assertEqual((f.prefix / 'tailmux').read_bytes(), older)
                    self.assertEqual((f.prefix / '.tailmux-receipt').read_bytes(), receipt)

    def test_acquisition_cleanup_preserves_unexpected_objects(self):
        f = self.life
        older, receipt = f.older_owned()
        for kind in ('symlink', 'hardlink', 'directory', 'extra-child'):
            with self.subTest(kind=kind):
                p = self.pause_acquisition(['install', '--replace-owned'])
                lock = f.prefix / '.tailmux-install-lock'
                owner = lock / 'owner'
                target = f.root / ('target-' + kind)
                target.write_bytes(b'keep these bytes\n')
                target.chmod(0o600)
                if kind != 'extra-child':
                    owner.unlink()
                if kind == 'symlink':
                    owner.symlink_to(target)
                elif kind == 'hardlink':
                    os.link(target, owner)
                elif kind == 'directory':
                    owner.mkdir()
                else:
                    (lock / 'unexpected').write_bytes(b'keep child\n')
                self.terminate_acquisition(p)
                self.assertTrue(lock.is_dir())
                self.assertEqual(target.read_bytes(), b'keep these bytes\n')
                if kind == 'symlink':
                    self.assertTrue(owner.is_symlink())
                elif kind == 'hardlink':
                    self.assertEqual(owner.read_bytes(), b'keep these bytes\n')
                    self.assertEqual(target.stat().st_nlink, 2)
                elif kind == 'directory':
                    self.assertTrue(owner.is_dir())
                else:
                    self.assertEqual((lock / 'unexpected').read_bytes(), b'keep child\n')
                self.assertEqual((f.prefix / 'tailmux').read_bytes(), older)
                self.assertEqual((f.prefix / '.tailmux-receipt').read_bytes(), receipt)
                shutil.rmtree(lock)


if __name__ == '__main__':
    unittest.main(verbosity=2)
