#!/usr/bin/env python3
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
import unittest

import direct_install as direct

ROOT = direct.ROOT
LEGACY_SOURCE = '6d3a47f95a89287f432fa3f13abd17c35f5cd4a0'


class SetupScriptTests(unittest.TestCase):
    def setUp(self):
        self.fixture = direct.DirectInstallTests()
        self.fixture.setUp(published=True)
        self.addCleanup(self.fixture.doCleanups)
        self.script = self.fixture.root / 'install.sh'
        self.script.write_bytes((ROOT / 'install.sh').read_bytes())
        self.binary = self.fixture.home / '.local/bin/tailmux'
        self.rc = self.fixture.home / '.bashrc'
        self.rc.write_bytes(b'# operator-owned\n')

    def run_script(self, *args, timeout=30, extra=None):
        self.fixture.save()
        command = ['/bin/bash', str(self.script), *args]
        with subprocess.Popen(command, env={**self.fixture.environment, **(extra or {})}, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True, start_new_session=True) as process:
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
                self.fail('Setup did not finish within ' + str(timeout) + ' seconds')
            result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        self.assertFalse(any(e[0] == 'FORBIDDEN' for e in self.fixture.events()))
        self.assertFalse((self.fixture.root / 'old-client-called').exists())
        self.assertEqual(list(self.fixture.stage.iterdir()), [])
        self.assertEqual(self.rc.read_bytes(), b'# operator-owned\n')
        return result

    def success(self, *args, **kwargs):
        result = self.run_script(*args, **kwargs)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def older_owned(self):
        older = subprocess.check_output(['git', '-C', str(ROOT), 'show', LEGACY_SOURCE + ':bin/tailmux'])
        self.binary.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.binary.write_bytes(older)
        self.binary.chmod(0o755)
        receipt = ('tailmux-receipt-v1\n' + str(self.binary) + '\n' +
                   hashlib.sha256(older).hexdigest() + '\n').encode()
        (self.binary.parent / '.tailmux-receipt').write_bytes(receipt)
        (self.binary.parent / '.tailmux-receipt').chmod(0o600)
        return older, receipt

    def modified_legacy(self):
        older, _ = self.older_owned()
        receipt = f'tailmux-receipt-v1\n{self.binary}\n{hashlib.sha256(older).hexdigest()}\n'.encode()
        (self.binary.parent / '.tailmux-receipt').write_bytes(receipt)
        wrapper = (f'#!/bin/bash\nprintf "old client executed\\n" >> {shlex.quote(str(self.fixture.root / "old-client-called"))}\n'
                   'exit 97\ntailscale() {\n'
                   '  /opt/homebrew/bin/tailscale --socket=/var/run/tailscaled.socket "$@"\n'
                   '}\nexec /opt/homebrew/bin/tailscale --socket=/var/run/tailscaled.socket "$@"\n').encode()
        self.binary.write_bytes(wrapper)
        return wrapper, receipt

    def inventory(self):
        result = {}
        for path in self.fixture.home.rglob('*'):
            metadata = path.lstat()
            content = path.read_bytes() if path.is_file() and not path.is_symlink() else None
            result[str(path.relative_to(self.fixture.home))] = (metadata.st_mode, metadata.st_ino,
                                                               metadata.st_mtime_ns, content)
        return result

    def test_configure_before_installation_uses_authenticated_candidate(self):
        socket = str(self.fixture.root / "daemon ' ü ;$(touch marker)`id` [x].sock")
        self.success('configure', '--socket', socket)
        self.assertEqual((self.fixture.home / '.config/tailmux/config').read_bytes(),
                         f'tailmux-config-v1\nsocket={socket}\n'.encode())
        self.assertFalse(self.binary.parent.exists())
        self.assertFalse((self.fixture.root / 'marker').exists())

    def test_recover_preview_then_explicit_apply(self):
        wrapper, receipt = self.modified_legacy()
        socket = str(self.fixture.root / "saved ' ü ;$(touch marker)`id` [x].sock")
        self.success('configure', '--socket', socket)
        before = self.inventory()
        preview = self.success('recover', '--dry-run')
        self.assertIn('Classification: modified', preview.stdout)
        self.assertIn(hashlib.sha256(wrapper).hexdigest(), preview.stdout)
        self.assertIn(receipt.decode().splitlines()[2], preview.stdout)
        self.assertIn('Candidate version: 0.3.0', preview.stdout)
        self.assertIn('Effective socket: ' + socket, preview.stdout)
        self.assertEqual(self.inventory(), before)
        self.assertEqual(self.binary.read_bytes(), wrapper)
        self.assertEqual((self.binary.parent / '.tailmux-receipt').read_bytes(), receipt)
        self.assertEqual(list(self.binary.parent.glob('.tailmux-backup.*')), [])
        result = self.run_script('recover', '--expect-current-sha256', '0' * 64)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.inventory(), before)
        self.success('recover', '--expect-current-sha256', hashlib.sha256(wrapper).hexdigest())
        self.assertEqual(self.binary.read_bytes(), self.fixture.payload['bin/tailmux'])
        backups = list(self.binary.parent.glob('.tailmux-backup.*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / 'tailmux').read_bytes(), wrapper)
        self.assertEqual((backups[0] / 'receipt').read_bytes(), receipt)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o700)
        self.assertEqual((backups[0] / 'receipt').stat().st_mode & 0o777, 0o600)
        completed = self.inventory()
        self.success('recover', '--expect-current-sha256', hashlib.sha256(wrapper).hexdigest())
        self.assertEqual(self.inventory(), completed)
        result = subprocess.run(['/bin/bash', str(self.binary), '--config', 'show'],
                                env=self.fixture.environment, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Saved socket: ' + socket, result.stdout)
        self.assertIn('Effective socket: ' + socket, result.stdout)
        self.assertFalse((self.fixture.root / 'old-client-called').exists())
        self.assertFalse((self.fixture.root / 'marker').exists())

    def test_update_receipt_publication_failure_preserves_old_pair_without_uninstall_gap(self):
        older, receipt = self.older_owned()
        trace = self.fixture.root / 'publication.jsonl'
        locks = self.fixture.root / 'locks.jsonl'
        self.fixture.tool('mkdir', f'''#!{sys.executable}
import json, pathlib, os, sys
if sys.argv[-1] == {str(self.binary.parent / '.tailmux-install-lock')!r}:
    with pathlib.Path({str(locks)!r}).open('a') as stream:
        stream.write(json.dumps(sys.argv[1:]) + '\\n')
os.execv({shutil.which('mkdir')!r}, [{shutil.which('mkdir')!r}, *sys.argv[1:]])
''')
        self.fixture.tool('mv', f'''#!{sys.executable}
import json, pathlib, os, sys
source, destination = sys.argv[-2:]
binary = pathlib.Path({str(self.binary)!r})
with pathlib.Path({str(trace)!r}).open('a') as stream:
    stream.write(json.dumps([source, destination, binary.exists()]) + '\\n')
if pathlib.Path(destination).name == '.tailmux-receipt' and pathlib.Path(source).name == 'receipt':
    sys.exit(73)
os.execv({shutil.which('mv')!r}, [{shutil.which('mv')!r}, *sys.argv[1:]])
''')
        result = self.run_script('update')
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.binary.read_bytes(), older)
        self.assertEqual((self.binary.parent / '.tailmux-receipt').read_bytes(), receipt)
        self.assertTrue(all(event[2] for event in map(json.loads, trace.read_text().splitlines())))
        self.assertEqual(len(locks.read_text().splitlines()), 1)
        backups = list(self.binary.parent.glob('.tailmux-backup.*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / 'tailmux').read_bytes(), older)
        self.assertEqual((backups[0] / 'receipt').read_bytes(), receipt)
        self.assertFalse((self.binary.parent / '.tailmux-install-lock').exists())
        self.assertFalse((self.binary.parent / '.tailmux-transaction').exists())

    def test_install_update_and_repeat_uninstall(self):
        self.success('configure', '--socket', '/saved.socket')
        config = self.fixture.home / '.config/tailmux/config'
        hosts = config.parent / 'hosts'
        hosts.write_bytes(b'desktop desktop.example.ts.net\n')
        preserved = (config.read_bytes(), hosts.read_bytes())
        self.success('install')
        expected = self.fixture.payload['bin/tailmux']
        self.assertEqual(self.binary.read_bytes(), expected)
        self.success('install')
        self.success('update')
        self.assertEqual(self.binary.read_bytes(), expected)
        self.assertEqual(list(self.binary.parent.glob('.tailmux-backup.*')), [])
        self.success('uninstall')
        self.success('uninstall')
        self.assertFalse(self.binary.exists())
        backups = list(self.binary.parent.glob('.tailmux-backup.*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / 'tailmux').read_bytes(), expected)
        self.assertEqual((config.read_bytes(), hosts.read_bytes()), preserved)

    def test_update_absent_and_same_source_receipt_only_use_ordinary_install(self):
        self.success('update')
        receipt = (self.binary.parent / '.tailmux-receipt').read_bytes()
        self.binary.unlink()
        self.success('update')
        self.assertEqual(self.binary.read_bytes(), self.fixture.payload['bin/tailmux'])
        self.assertEqual((self.binary.parent / '.tailmux-receipt').read_bytes(), receipt)
        self.assertEqual(list(self.binary.parent.glob('.tailmux-backup.*')), [])
        setup = [event for event in self.fixture.events() if event[0] == 'setup']
        self.assertEqual(setup, [['setup', 'install', '--prefix', str(self.binary.parent)]] * 2)

    def test_configure_and_preview_scrub_environment_and_preserve_old_wrapper(self):
        wrapper, receipt = self.modified_legacy()
        extra = {'TAILMUX_TAILSCALE_SOCKET': '/untrusted.socket', 'TAILMUX_PREFIX': '/untrusted',
                 'TAILMUX_SENTRY_DSN': 'untrusted', 'ENV': '/untrusted', 'PYTHONPATH': '/untrusted'}
        self.success('configure', '--socket', '/saved.socket', extra=extra)
        preview = self.success('recover', '--dry-run', extra=extra)
        self.assertIn('Effective socket: /saved.socket\nSource: saved\n', preview.stdout)
        self.assertNotIn('/untrusted.socket', preview.stdout)
        self.assertEqual(self.binary.read_bytes(), wrapper)
        self.assertEqual((self.binary.parent / '.tailmux-receipt').read_bytes(), receipt)

    def test_all_new_requests_authenticate_before_setup_or_archive_parse(self):
        wrapper, _ = self.modified_legacy()
        digest = hashlib.sha256(wrapper).hexdigest()
        requests = [('configure', '--socket', '/saved.socket'), ('recover', '--dry-run'),
                    ('recover', '--expect-current-sha256', digest)]
        requests += [('recover', '--' + operation, '--transaction', '.tailmux-tx.literal_1',
                      '--expect-current-sha256', digest)
                     for operation in ('resume', 'rollback', 'unlock-abandoned')]
        before = self.inventory()
        self.fixture.archive.write_bytes(b'not even gzip')
        for kind in ('installer', 'package'):
            self.fixture.control['gh_status'] = {kind: 18}
            for args in requests:
                with self.subTest(kind=kind, args=args):
                    start = len(self.fixture.events())
                    result = self.run_script(*args)
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(self.inventory(), before)
                    events = self.fixture.events()[start:]
                    self.assertNotIn('setup', [event[0] for event in events])
                    self.assertNotIn('Not a gzipped file', result.stderr)
                    if kind == 'installer':
                        self.assertNotIn(['execute', 'installer'], events)
        self.assertFalse((self.fixture.home / '.config').exists())

    def test_public_tampered_and_oversized_assets_never_configure(self):
        for asset in (self.fixture.installer, self.fixture.archive, self.fixture.bundle):
            original = asset.read_bytes()
            for mode in ('tampered', 'oversized'):
                with self.subTest(asset=asset.name, mode=mode):
                    if mode == 'tampered':
                        asset.write_bytes(original + b'tamper')
                    else:
                        self.fixture.control['oversized'] = {asset.name: True}
                    start = len(self.fixture.events())
                    result = self.run_script('configure', '--socket', '/saved.socket')
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertFalse((self.fixture.home / '.config').exists())
                    self.assertFalse(self.binary.parent.exists())
                    self.assertNotIn('setup', [event[0] for event in self.fixture.events()[start:]])
                    self.fixture.control['oversized'] = {}
                    asset.write_bytes(original)

    def pending_recovery(self):
        wrapper, receipt = self.modified_legacy()
        ready = self.fixture.root / 'publisher-ready'
        ready.unlink(missing_ok=True)
        self.fixture.tool('mv', f'''#!{sys.executable}
import pathlib, sys, time
source, destination = sys.argv[-2:]
result = __import__('subprocess').run([{shutil.which('mv')!r}, *sys.argv[1:]])
if result.returncode:
    sys.exit(result.returncode)
if pathlib.Path(destination).name == 'tailmux' and pathlib.Path(source).name == 'tailmux':
    pathlib.Path({str(ready)!r}).touch()
    time.sleep(30)
''')
        self.fixture.save()
        with subprocess.Popen(['/bin/bash', str(self.script), 'recover', '--expect-current-sha256',
                               hashlib.sha256(wrapper).hexdigest()], env=self.fixture.environment,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True) as process:
            deadline = time.monotonic() + 15
            while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(.02)
            reached = ready.exists()
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=10)
        self.assertTrue(reached, 'public recovery never reached executable rename')
        (self.fixture.tools / 'mv').unlink()
        # SIGKILL also leaves the adapter's private download directory.
        for stage in self.fixture.stage.iterdir():
            shutil.rmtree(stage)
        record = self.binary.parent / '.tailmux-transaction'
        fields = dict(line.split('=', 1) for line in record.read_text().splitlines()[1:])
        return wrapper, receipt, fields

    def test_public_pending_transaction_uses_literal_id_and_exact_current_digest(self):
        for operation in ('resume', 'rollback'):
            with self.subTest(operation=operation):
                wrapper, receipt, fields = self.pending_recovery()
                digest = hashlib.sha256(self.binary.read_bytes()).hexdigest()
                before = self.inventory()
                for tx, observed in (('unknown', digest), (fields['id'], '0' * 64)):
                    result = self.run_script('recover', '--unlock-abandoned', '--transaction', tx,
                                             '--expect-current-sha256', observed)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(self.inventory(), before)
                result = self.run_script('recover', '--' + operation, '--transaction', fields['id'],
                                         '--expect-current-sha256', digest)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('locked', result.stderr)
                self.assertEqual(self.inventory(), before)
                self.success('recover', '--unlock-abandoned', '--transaction', fields['id'],
                             '--expect-current-sha256', digest)
                self.assertEqual(self.binary.read_bytes(), self.fixture.payload['bin/tailmux'])
                self.assertEqual((self.binary.parent / '.tailmux-receipt').read_bytes(), receipt)
                self.success('recover', '--' + operation, '--transaction', fields['id'],
                             '--expect-current-sha256', digest)
                expected = self.fixture.payload['bin/tailmux'] if operation == 'resume' else wrapper
                self.assertEqual(self.binary.read_bytes(), expected)
                backup = self.binary.parent / fields['backup']
                self.assertEqual((backup / 'tailmux').read_bytes(), wrapper)
                self.assertEqual((backup / 'receipt').read_bytes(), receipt)
                self.assertFalse((self.binary.parent / '.tailmux-transaction').exists())
                self.assertFalse((self.binary.parent / '.tailmux-install-lock').exists())
                setup = [event for event in self.fixture.events() if event[0] == 'setup'][-1]
                self.assertEqual(setup, ['setup', 'recover', '--prefix', str(self.binary.parent),
                                        '--expect-current-sha256', digest, '--' + operation,
                                        '--transaction', fields['id']])
                shutil.rmtree(self.binary.parent)

    def test_foreign_receipts_and_unknown_locks_preserve_all_evidence(self):
        wrapper, receipt = self.modified_legacy()
        record = self.binary.parent / '.tailmux-receipt'
        for data in (None, b'foreign\n', receipt + b'extra\n', receipt.rstrip(b'\n'), receipt + b'\0'):
            with self.subTest(receipt=data):
                if data is None:
                    record.unlink()
                else:
                    record.write_bytes(data)
                before = self.inventory()
                for args in [('update',), ('uninstall',), ('recover', '--dry-run'),
                             ('recover', '--expect-current-sha256', hashlib.sha256(wrapper).hexdigest())]:
                    result = self.run_script(*args)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(self.inventory(), before)
        record.write_bytes(receipt)
        lock = self.binary.parent / '.tailmux-install-lock'
        lock.mkdir(mode=0o700)
        (lock / 'owner').write_bytes(b'unknown\n')
        before = self.inventory()
        for args in [('update',), ('uninstall',), ('recover', '--dry-run'),
                     ('recover', '--expect-current-sha256', hashlib.sha256(wrapper).hexdigest()),
                     ('recover', '--unlock-abandoned', '--transaction', 'unknown',
                      '--expect-current-sha256', hashlib.sha256(wrapper).hexdigest())]:
            result = self.run_script(*args)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(self.inventory(), before)

    def test_each_successful_action_downloads_only_three_exact_assets(self):
        socket = "/literal ' ü ;$(exit 91) [x].sock"
        for args in [('configure', '--socket', socket), ('install',), ('update',), ('recover', '--dry-run'),
                     ('recover', '--expect-current-sha256', '0' * 64), ('uninstall',)]:
            with self.subTest(args=args):
                start = len(self.fixture.events())
                self.success(*args)
                events = self.fixture.events()[start:]
                self.assertEqual([event for event in events if event[0] == 'download'],
                                 [['download', self.fixture.installer.name], ['download', self.fixture.bundle.name],
                                  ['download', self.fixture.archive.name]])
                self.assertLess(events.index(['verify', 'installer']), events.index(['execute', 'installer']))
                self.assertLess(events.index(['verify', 'package']),
                                next(index for index, event in enumerate(events) if event[0] == 'setup'))

    def test_published_adapter_installs_its_pinned_source_not_the_candidate(self):
        source = re.search(r'^source_sha=([0-9a-f]{40})$', (ROOT / 'install.sh').read_text(), re.MULTILINE).group(1)
        expected = subprocess.check_output(['git', '-C', str(ROOT), 'show', source + ':bin/tailmux'])
        self.success('install')
        self.assertEqual(self.binary.read_bytes(), expected)

    def test_update_replaces_owned_older_bytes_and_retains_backup(self):
        self.success('install')
        older = b'#!/bin/bash\nexit 98\n'
        self.binary.write_bytes(older)
        receipt = self.binary.parent / '.tailmux-receipt'
        receipt.write_text('tailmux-receipt-v1\n' + str(self.binary) + '\n' +
                           hashlib.sha256(older).hexdigest() + '\n')
        self.success('update')
        self.assertEqual(self.binary.read_bytes(), self.fixture.payload['bin/tailmux'])
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

    def test_update_refuses_fifos_and_symlinks_without_blocking_or_modifying_them(self):
        self.binary.parent.mkdir(parents=True)
        fifo = self.fixture.root / 'foreign-fifo'
        os.mkfifo(fifo)
        regular = self.fixture.root / 'foreign-file'
        regular.write_bytes(b'foreign target\n')
        for kind in ('fifo', 'fifo-symlink', 'file-symlink', 'broken-symlink', 'directory'):
            with self.subTest(kind=kind):
                if kind == 'fifo':
                    os.mkfifo(self.binary)
                elif kind.endswith('symlink'):
                    target = fifo if kind == 'fifo-symlink' else regular if kind == 'file-symlink' else self.fixture.root / 'missing'
                    self.binary.symlink_to(target)
                else:
                    self.binary.mkdir()
                before = self.binary.lstat()
                result = self.run_script('update', timeout=3)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('regular, non-symlinked', result.stderr)
                after = self.binary.lstat()
                self.assertEqual((after.st_ino, after.st_mode), (before.st_ino, before.st_mode))
                self.assertEqual(regular.read_bytes(), b'foreign target\n')
                self.assertFalse((self.binary.parent / '.tailmux-receipt').exists())
                self.assertEqual(list(self.binary.parent.glob('.tailmux-backup.*')), [])
                if kind == 'directory':
                    self.binary.rmdir()
                else:
                    self.binary.unlink()

    def test_custom_prefix_and_offline_help(self):
        prefix = self.fixture.home / "custom ' ü ;$(exit 91) [x] bin"
        self.success('install', '--prefix', str(prefix))
        self.assertEqual((prefix / 'tailmux').read_bytes(), self.fixture.payload['bin/tailmux'])
        self.success('update', '--prefix', str(prefix))
        self.success('uninstall', '--prefix', str(prefix))
        self.assertFalse((prefix / 'tailmux').exists())
        before = self.fixture.events()
        self.success('--help')
        self.assertEqual(before, self.fixture.events())

    def test_unknown_action_and_bad_arguments_refuse_before_download(self):
        valid = 'a' * 64
        requests = [('bogus',), ('update', '--wrong'), ('uninstall', '--prefix'),
                    ('--help', 'extra'), ('install', '--prefix', 'relative'),
                    ('update', '--prefix', '/x/../y'), ('uninstall', '--prefix', '/x\n'),
                    ('install', '--prefix', '/x', '--prefix', '/y'),
                    ('configure',), ('configure', '--socket'), ('configure', '--socket', 'relative'),
                    ('configure', '--socket', '/x\n'), ('configure', '--socket', '/' + 'x' * 8166),
                    ('configure', '--socket', '/x', '--socket', '/y'),
                    ('configure', '--prefix', '/x', '--socket', '/y'), ('configure', '--socket', '/x', 'extra'),
                    ('recover',), ('recover', '--dry-run', '--dry-run'), ('recover', '--dry-run', '--resume'),
                    ('recover', '--dry-run', '--expect-current-sha256', valid),
                    ('recover', '--dry-run', '--transaction', 'abc'),
                    ('recover', '--resume', '--expect-current-sha256', valid),
                    ('recover', '--transaction', 'abc', '--expect-current-sha256', valid),
                    ('recover', '--expect-current-sha256', valid, '--expect-current-sha256', valid),
                    ('recover', '--resume', '--transaction', 'abc', '--transaction', 'abc', '--expect-current-sha256', valid),
                    ('recover', '--prefix', '/x', '--prefix', '/x', '--dry-run'),
                    ('recover', '--replace-owned'), ('recover', '--socket', '/x'), ('recover', '--force')]
        requests += [('recover', '--expect-current-sha256', digest)
                     for digest in ('', 'A' * 64, 'a' * 63, 'a' * 65, 'g' * 64, 'x\n')]
        requests += [('recover', '--resume', '--transaction', tx, '--expect-current-sha256', valid)
                     for tx in ('', '.', '..', '../x', 'a/b', 'a' * 97, 'ü', 'a\n', '$(touch marker)')]
        for args in requests:
            with self.subTest(args=args):
                result = self.run_script(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.fixture.events(), [])
                self.assertFalse(self.binary.exists())

    def test_readme_last_line_forwards_literal_arguments(self):
        block = (ROOT / 'README.md').read_text().split('```bash\n', 1)[1].split('\n```', 1)[0]
        verifier = shlex.split(block.split('\npython3 ', 1)[1])
        self.assertEqual(verifier[-1], 'install')
        socket = str(self.fixture.root / "README literal ' ü ;$(exit 91) [x].sock")
        marker = self.fixture.root / 'shell-injection-ran'
        injection = self.fixture.root / 'injection.sh'
        injection.write_text('touch ' + shlex.quote(str(marker)) + '\n')
        self.fixture.save()
        result = subprocess.run([sys.executable, *verifier[:-1], 'configure', '--socket', socket],
                                input=self.script.read_bytes(), env={**self.fixture.environment,
                                'BASH_ENV': str(injection), 'ENV': str(injection), 'PYTHONPATH': '/untrusted',
                                'TAILMUX_TAILSCALE_SOCKET': '/untrusted.socket'},
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.fixture.home / '.config/tailmux/config').read_bytes(),
                         f'tailmux-config-v1\nsocket={socket}\n'.encode())
        self.assertFalse(self.binary.parent.exists())
        self.assertFalse(marker.exists())

    def test_readme_verifier_refuses_tampered_or_oversized_script_before_execution(self):
        block = (ROOT / 'README.md').read_text().split('```bash\n', 1)[1].split('\n```', 1)[0]
        verifier = shlex.split(block.split('\npython3 ', 1)[1])
        command = [sys.executable, *verifier[:-1], '--help']
        payload = (ROOT / 'install.sh').read_bytes()
        marker = self.fixture.root / 'injection-ran'
        tampered = ('touch "' + str(marker) + '"\n').encode()
        for data in (payload + b'\n', tampered, b'x' * 65537, b''):
            with self.subTest(size=len(data)):
                result = subprocess.run(command, input=data, env=self.fixture.environment,
                                        capture_output=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b'checksum mismatch', result.stderr)
                self.assertFalse(self.binary.exists())
                self.assertFalse(marker.exists())
        env = dict(self.fixture.environment, BASH_ENV=str(self.fixture.root / 'injected'))
        (self.fixture.root / 'injected').write_text('touch "' + str(marker) + '"\n')
        result = subprocess.run(command, input=payload, env=env, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b'Usage:', result.stdout)
        self.assertFalse(marker.exists())
        self.assertEqual(self.fixture.events(), [])
        failed = subprocess.run([*command[:-1], 'invalid-action'], input=payload, env=env,
                                capture_output=True, timeout=10)
        self.assertEqual(failed.returncode, 1)
        self.assertIn(b'Expected install, update, uninstall, recover, or configure', failed.stderr)
        self.assertNotIn(b'Traceback', failed.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
