#!/usr/bin/env python3
import hashlib
import subprocess
import unittest

import direct_install as direct

REQUEST = direct.REQUEST
ROOT = direct.ROOT


class SetupScriptTests(unittest.TestCase):
    def setUp(self):
        self.fixture = direct.DirectInstallTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.script = self.fixture.root / 'install.sh'
        self.script.write_text((ROOT / 'install.sh').read_text().replace(
            'd3dbae670a1a9f2429a3db825e91628a7dbb74bc', REQUEST.source_sha))
        self.binary = self.fixture.home / '.local/bin/tailmux'
        self.rc = self.fixture.home / '.bashrc'
        self.rc.write_bytes(b'# operator-owned\n')

    def run_script(self, *args):
        self.fixture.save()
        result = subprocess.run(['/bin/bash', str(self.script), *args],
                                env=self.fixture.environment, capture_output=True,
                                text=True, timeout=30)
        self.assertFalse(any(e[0] == 'FORBIDDEN' for e in self.fixture.events()))
        self.assertEqual(list(self.fixture.stage.iterdir()), [])
        self.assertEqual(self.rc.read_bytes(), b'# operator-owned\n')
        return result

    def success(self, *args):
        result = self.run_script(*args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_install_update_and_repeat_uninstall(self):
        self.success('install')
        expected = (ROOT / 'bin/tailmux').read_bytes()
        self.assertEqual(self.binary.read_bytes(), expected)
        self.success('update')
        self.assertEqual(self.binary.read_bytes(), expected)
        self.assertEqual(list(self.binary.parent.glob('.tailmux-backup.*')), [])
        self.success('uninstall')
        self.success('uninstall')
        self.assertFalse(self.binary.exists())
        backups = list(self.binary.parent.glob('.tailmux-backup.*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / 'tailmux').read_bytes(), expected)

    def test_update_replaces_owned_older_bytes_and_retains_backup(self):
        self.success('install')
        older = b'#!/bin/bash\nexit 98\n'
        self.binary.write_bytes(older)
        receipt = self.binary.parent / '.tailmux-receipt'
        receipt.write_text('tailmux-receipt-v1\n' + str(self.binary) + '\n' +
                           hashlib.sha256(older).hexdigest() + '\n')
        self.success('update')
        self.assertEqual(self.binary.read_bytes(), (ROOT / 'bin/tailmux').read_bytes())
        backups = list(self.binary.parent.glob('.tailmux-backup.*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / 'tailmux').read_bytes(), older)

    def test_failed_authentication_keeps_installed_client_for_update_and_uninstall(self):
        self.success('install')
        original = self.binary.read_bytes()
        receipt = (self.binary.parent / '.tailmux-receipt').read_bytes()
        self.fixture.control['gh_status']['package'] = 18
        self.fixture.archive.write_bytes(b'not even gzip')
        for action in ('update', 'uninstall'):
            with self.subTest(action=action):
                result = self.run_script(action)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.binary.read_bytes(), original)
                self.assertEqual((self.binary.parent / '.tailmux-receipt').read_bytes(), receipt)
                self.assertEqual(list(self.binary.parent.glob('.tailmux-backup.*')), [])

    def test_update_and_uninstall_refuse_foreign_or_modified_client(self):
        self.success('install')
        self.binary.write_bytes(b'foreign replacement\n')
        for action in ('update', 'uninstall'):
            with self.subTest(action=action):
                result = self.run_script(action)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.binary.read_bytes(), b'foreign replacement\n')
                self.assertEqual(list(self.binary.parent.glob('.tailmux-backup.*')), [])

    def test_custom_prefix_and_offline_help(self):
        prefix = self.fixture.home / 'custom bin'
        self.success('install', '--prefix', str(prefix))
        self.assertEqual((prefix / 'tailmux').read_bytes(), (ROOT / 'bin/tailmux').read_bytes())
        self.success('uninstall', '--prefix', str(prefix))
        self.assertFalse((prefix / 'tailmux').exists())
        before = self.fixture.events()
        self.success('--help')
        self.assertEqual(before, self.fixture.events())

    def test_unknown_action_and_bad_arguments_refuse_before_download(self):
        for args in [('bogus',), ('update', '--wrong'), ('uninstall', '--prefix')]:
            with self.subTest(args=args):
                result = self.run_script(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.fixture.events(), [])
                self.assertFalse(self.binary.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
