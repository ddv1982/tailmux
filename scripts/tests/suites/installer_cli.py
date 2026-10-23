#!/usr/bin/env python3
import os
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import signal
import time
import unittest

from fixture_env import cli_environment

ROOT = Path(__file__).resolve().parents[3]
SETUP = ROOT / 'setup.sh'
FIXTURES = ROOT / 'scripts/tests/fixtures'
FORBIDDEN = ('curl wget sudo su doas brew apt apt-get dnf yum pacman zypper apk port systemctl '
             'service launchctl defaults osascript open tailscale tailscaled ssh mount mount_webdav '
             'umount fusermount git').split()
CENSUS = ['alias tailmux=other\n', 'alias -- tailmux=other\n', "alias 'tailmux=other'\n",
          "alias 'tailmux'=other\n", 'alias tailmux\\=other\n', 'alias \\\n  tailmux=other\n', 'alias other=x\n']


class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='tailmux-life-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.home = self.root / 'home'
        self.bin = self.root / 'tools'
        self.home.mkdir()
        self.bin.mkdir()
        self.prefix = self.home / '.local/bin'
        self.trace = self.root / 'forbidden'
        for name in ('bash dirname uname stat ls tr cmp shasum sha256sum dd cat mkdir rmdir mktemp cp mv rm cut xattr wc grep chmod lsattr python3').split():
            tool = shutil.which(name)
            if tool:
                (self.bin / name).symlink_to(tool)
        for name in FORBIDDEN:
            self.script(name, '#!/bin/bash\nprintf "%s\\n" "$0 $*" >> "$FORBIDDEN_TRACE"\nexit 97\n')
        self.env = {'HOME': str(self.home), 'ZDOTDIR': str(self.home), 'SHELL': '/bin/bash',
                    'PATH': str(self.bin), 'LC_ALL': 'C', 'TMPDIR': str(self.root),
                    'FORBIDDEN_TRACE': str(self.trace)}
        self.rc = self.home / '.profile'

    def script(self, name, body):
        p = self.bin / name
        p.unlink(missing_ok=True)
        p.write_text(body)
        p.chmod(0o755)

    def run_setup(self, *args, setup=SETUP, **changes):
        p = subprocess.run(['/bin/bash', str(setup), *args], env=cli_environment(self.bin, self.env, **changes),
                           capture_output=True, text=True, timeout=20)
        self.assertFalse(self.trace.exists(), self.trace.read_text() if self.trace.exists() else '')
        return p

    def success(self, *args, **changes):
        p = self.run_setup(*args, **changes)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return p

    def refusal(self, *args, contains=None, **changes):
        p = self.run_setup(*args, **changes)
        self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
        if contains:
            self.assertIn(contains, p.stdout + p.stderr)
        self.assertNotIn('Client installed at', p.stdout)
        self.assertNotIn('Client uninstall complete', p.stdout)
        return p

    def tree(self):
        return sorted(str(p.relative_to(self.home)) for p in self.home.rglob('*'))

    def older_owned(self):
        self.success('install')
        binary = self.prefix / 'tailmux'
        older = b'#!/bin/bash\nprintf "older usable client\\n"\n'
        binary.write_bytes(older)
        receipt = ('tailmux-receipt-v1\n' + str(binary) + '\n' + hashlib.sha256(older).hexdigest() + '\n').encode()
        (self.prefix / '.tailmux-receipt').write_bytes(receipt)
        return older, receipt

    def inspection(self):
        code = '''for module in platform rc_blocks managed_blocks install; do
source "$1/scripts/lib/$module.sh"
done
inspect_installation "$2" || exit
printf '%s\\n' "$INSTALL_STATE" "$INSTALL_PREFIX" "$INSTALL_CURRENT_DIGEST" "$INSTALL_RECEIPT_DIGEST" "$INSTALL_TRANSACTION"
'''
        result = subprocess.run(['/bin/bash', '-u', '-c', code, 'inspect', str(ROOT), str(self.prefix)],
                                env=cli_environment(self.bin, self.env), capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.splitlines()

    def assert_old_pair(self, older, receipt):
        self.assertEqual((self.prefix / 'tailmux').read_bytes(), older)
        self.assertEqual((self.prefix / '.tailmux-receipt').read_bytes(), receipt)
        self.assertFalse((self.prefix / '.tailmux-transaction').exists())
        self.assertFalse((self.prefix / '.tailmux-install-lock').exists())

    def test_p1_inspection_states_and_refusals(self):
        self.assertEqual(self.inspection(), ['absent', str(self.prefix), '', '', ''])
        older, receipt = self.older_owned()
        digest = hashlib.sha256(older).hexdigest()
        self.assertEqual(self.inspection(), ['owned', str(self.prefix), digest, digest, ''])
        binary = self.prefix / 'tailmux'
        binary.write_bytes(older + b': changed\n')
        self.assertEqual(self.inspection()[0], 'modified')
        for args in [('install',), ('install', '--replace-owned'), ('uninstall',)]:
            self.refusal(*args, contains='modified installation')
        binary.unlink()
        self.assertEqual(self.inspection()[0], 'receipt-only')
        self.refusal('install', '--replace-owned', contains='existing owned executable')
        (self.prefix / '.tailmux-receipt').unlink()
        binary.write_bytes(b'foreign\n')
        self.assertEqual(self.inspection()[0], 'foreign')
        binary.unlink()
        os.mkfifo(binary)
        self.assertEqual(self.inspection()[0], 'unsafe')
        self.refusal('install', '--replace-owned')
        binary.unlink()
        binary.symlink_to(self.root / 'missing')
        self.assertEqual(self.inspection()[0], 'unsafe')
        self.refusal('install', '--replace-owned')
        binary.unlink()
        binary.write_bytes(older)
        binary.chmod(0o755)
        r = self.prefix / '.tailmux-receipt'
        for data in (b'foreign\n', receipt + b'extra\n', receipt.rstrip(b'\n'), receipt + b'\0', b'x' * 16385):
            r.write_bytes(data)
            self.assertIn(self.inspection()[0], ('foreign', 'unsafe'))
            before = self.tree()
            self.refusal('install', '--replace-owned')
            self.assertEqual(self.tree(), before)
            self.assertEqual(r.read_bytes(), data)
        r.unlink()
        os.mkfifo(r)
        self.assertEqual(self.inspection()[0], 'unsafe')
        self.refusal('uninstall')

    def test_p1_invalid_digest_output_refuses_modified_installation(self):
        older, receipt = self.older_owned()
        modified = older + b': changed\n'
        binary = self.prefix / 'tailmux'
        binary.write_bytes(modified)
        before = self.tree()
        for output in ('not-a-digest', 'a' * 63, 'A' * 64, 'g' * 64, ''):
            self.script('shasum', '#!/bin/bash\nprintf "%s" "' + output + '"\nexit 0\n')
            for args in [('install',), ('install', '--replace-owned'), ('uninstall',)]:
                with self.subTest(output=output, args=args):
                    result = self.run_setup(*args)
                    self.assertEqual(binary.read_bytes() if binary.exists() else None, modified)
                    self.assertEqual((self.prefix / '.tailmux-receipt').read_bytes(), receipt)
                    self.assertEqual(self.tree(), before)
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertNotIn('Client installed at', result.stdout)
                    self.assertNotIn('Client uninstall complete', result.stdout)

    def test_p1_invalid_digest_output_refuses_fresh_publication(self):
        for index, output in enumerate(('', 'not-a-digest', 'a' * 63, 'A' * 64, 'g' * 64)):
            with self.subTest(output=output):
                prefix = self.home / ('prefix-' + str(index))
                prefix.mkdir()
                before = self.tree()
                self.script('shasum', '#!/bin/bash\nprintf "%s" "' + output + '"\nexit 0\n')
                self.refusal('install', '--prefix', str(prefix))
                self.assertEqual(self.tree(), before)

    def test_p1_invalid_prefix_digest_never_publishes_transaction(self):
        older, receipt = self.older_owned()
        attempted = self.root / 'attempted-transaction'
        real_hash = shutil.which('shasum')
        real_mv = shutil.which('mv')
        self.script('shasum', '#!/bin/bash\nIFS= read -r first\n'
                    'if [[ "$first" == "$HASH_PREFIX" ]]; then exit 0; fi\n'
                    '{ printf "%s\\n" "$first"; cat; } | "' + real_hash + '" "$@"\n')
        self.script('mv', '#!/bin/bash\nif [[ "$2" == */.tailmux-transaction ]]; then\n'
                    'cp "$1" "$ATTEMPTED_TRANSACTION"\nexit 73\nfi\nexec "' + real_mv + '" "$@"\n')
        self.refusal('install', '--replace-owned', HASH_PREFIX=str(self.prefix),
                     ATTEMPTED_TRANSACTION=str(attempted))
        self.assert_old_pair(older, receipt)
        self.assertFalse(attempted.exists(), attempted.read_text() if attempted.exists() else '')

    def test_p1_replace_owned_without_rc_prerequisites_and_repeat(self):
        older, receipt = self.older_owned()
        body = b'# >>> tailmux managed block (unknown) >>>\n'
        self.rc.write_bytes(body)
        self.refusal('install', contains='Unknown')
        self.success('install', '--prefix', str(self.prefix), '--replace-owned', ZDOTDIR='relative')
        self.assertEqual(self.rc.read_bytes(), body)
        self.assertEqual((self.prefix / 'tailmux').read_bytes(), (ROOT / 'bin/tailmux').read_bytes())
        self.assertEqual(self.inspection()[0], 'owned')
        backups = list(self.prefix.glob('.tailmux-backup.*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / 'tailmux').read_bytes(), older)
        self.assertEqual((backups[0] / 'receipt').read_bytes(), receipt)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o700)
        self.success('install', '--replace-owned')
        self.assertEqual(list(self.prefix.glob('.tailmux-backup.*')), backups)
        self.assertFalse((self.prefix / '.tailmux-transaction').exists())
        self.assertFalse((self.prefix / '.tailmux-install-lock').exists())
        self.refusal('uninstall', '--replace-owned')
        self.refusal('install', '--replace-owned', '--replace-owned')

    def test_p1_prefix_boundary_refusals_preserve_owned_pair(self):
        older, receipt = self.older_owned()
        operations = [('install',), ('install', '--replace-owned'), ('uninstall',)]
        for node in (self.prefix, self.prefix.parent, self.home, self.root):
            before_mode = node.stat().st_mode & 0o7777
            try:
                node.chmod(before_mode | 0o020)
                for args in operations:
                    with self.subTest(node=node, args=args):
                        before = self.tree()
                        self.refusal(*args)
                        self.assertEqual(self.tree(), before)
                        self.assert_old_pair(older, receipt)
            finally:
                node.chmod(before_mode)
        for node in (self.prefix, self.prefix.parent):
            saved = self.root / 'saved-prefix-ancestor'
            node.rename(saved)
            node.symlink_to(saved, target_is_directory=True)
            try:
                for args in operations:
                    with self.subTest(symlink=node, args=args):
                        before = self.tree()
                        self.refusal(*args)
                        self.assertEqual(self.tree(), before)
                        self.assert_old_pair(older, receipt)
            finally:
                node.unlink()
                saved.rename(node)
        self.assertEqual(self.inspection()[0], 'owned')

    def test_p1_validation_context_does_not_escape_inspection(self):
        self.older_owned()
        code = '''for module in platform rc_blocks managed_blocks install; do
source "$1/scripts/lib/$module.sh"
done
inspect_installation "$2"
printf '%s\\n' "$INSTALL_STATE"
chmod 0775 "$HOME"
inspect_installation "$2"
printf '%s\\n' "$INSTALL_STATE"
if lifecycle_file "$2/tailmux"; then exit 71; fi
printf '%s\\n' rejected
'''
        env = cli_environment(self.bin, self.env, LIFECYCLE_CONTEXT=str(self.prefix))
        result = subprocess.run(['/bin/bash', '-u', '-c', code, 'inspect', str(ROOT), str(self.prefix)],
                                env=env, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'owned\nunsafe\nrejected\n')

    def test_p1_metadata_rejects_failed_nul_scan(self):
        path = self.home / 'metadata-input'
        code = '''set -euo pipefail
source "$1/scripts/lib/rc_blocks.sh"
validate_rc_metadata "$2"
'''
        for body in (b'', b'complete input\n'):
            path.write_bytes(body)
            for command in ('exit 73', 'cat; exit 73'):
                with self.subTest(body=body, command=command):
                    self.script('tr', '#!/bin/bash\n' + command + '\n')
                    result = subprocess.run(['/bin/bash', '-c', code, 'metadata', str(ROOT), str(path)],
                                            env=cli_environment(self.bin, self.env), capture_output=True, text=True, timeout=5)
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(path.read_bytes(), body)
        self.script('tr', '#!/bin/bash\nexec "' + shutil.which('tr') + '" "$@"\n')
        path.write_bytes(b'complete input\n')
        result = subprocess.run(['/bin/bash', '-c', code, 'metadata', str(ROOT), str(path)],
                                env=cli_environment(self.bin, self.env), capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        path.write_bytes(b'complete\0input\n')
        result = subprocess.run(['/bin/bash', '-c', code, 'metadata', str(ROOT), str(path)],
                                env=cli_environment(self.bin, self.env), capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_p1_publication_rechecks_ancestor_after_prepared_record(self):
        older, receipt = self.older_owned()
        self.script('mv', '''#!/bin/bash
"''' + shutil.which('mv') + '''" "$@" || exit
if [[ "$2" == */.tailmux-transaction ]]; then
  "''' + shutil.which('chmod') + '''" 0775 "$HOME/.local"
fi
''')
        result = self.refusal('install', '--replace-owned', contains='Replacement incomplete')
        self.assertNotIn('restored previous client', result.stderr)
        self.assertEqual((self.prefix / 'tailmux').read_bytes(), older)
        self.assertEqual((self.prefix / '.tailmux-receipt').read_bytes(), receipt)
        self.assertTrue((self.prefix / '.tailmux-transaction').is_file())
        self.assertTrue((self.prefix / '.tailmux-install-lock/owner').is_file())
        self.assertEqual(self.inspection()[0], 'unsafe')
        self.prefix.parent.chmod(0o755)
        self.assertEqual(self.inspection()[0], 'pending')
        before = self.tree()
        self.refusal('install', '--replace-owned', contains='locked')
        self.assertEqual(self.tree(), before)

    @unittest.skipUnless(platform.system() == 'Darwin', 'macOS ACL evidence only')
    def test_p1_prefix_and_transaction_directory_acls_refuse(self):
        older, receipt = self.older_owned()
        for node in (self.prefix, self.prefix.parent, self.home, self.root):
            subprocess.run(['/bin/chmod', '+a', 'everyone allow delete_child,add_subdirectory', str(node)], check=True)
            try:
                for args in [('install',), ('install', '--replace-owned'), ('uninstall',)]:
                    with self.subTest(node=node, args=args):
                        self.refusal(*args, contains='Unknown or mutating RC ancestor ACLs')
                        self.assert_old_pair(older, receipt)
            finally:
                subprocess.run(['/bin/chmod', '-N', str(node)], check=True)
        self.script('mv', '''#!/bin/bash
[[ "$1" != */receipt && "$1" != */rollback-binary ]] || exit 73
exec "''' + shutil.which('mv') + '''" "$@"
''')
        self.refusal('install', '--replace-owned', contains='Replacement incomplete')
        record = self.prefix / '.tailmux-transaction'
        fields = dict(line.split('=', 1) for line in record.read_text().splitlines()[1:])
        for node in (self.prefix / '.tailmux-install-lock', self.prefix / fields['stage'], self.prefix / fields['backup']):
            subprocess.run(['/bin/chmod', '+a', 'everyone allow delete_child,add_subdirectory', str(node)], check=True)
            try:
                self.assertEqual(self.inspection()[0], 'unsafe')
                before = self.tree()
                self.refusal('install', '--replace-owned')
                self.assertEqual(self.tree(), before)
                self.assertEqual(record.read_text().splitlines()[1], 'id=' + fields['id'])
                self.assertEqual((self.prefix / fields['backup'] / 'tailmux').read_bytes(), older)
                self.assertEqual((self.prefix / '.tailmux-receipt').read_bytes(), receipt)
            finally:
                subprocess.run(['/bin/chmod', '-N', str(node)], check=True)
        self.assertEqual(self.inspection()[0], 'pending')

    def test_p1_caught_publication_failures_restore_pair(self):
        older, receipt = self.older_owned()
        real_mv = shutil.which('mv')
        for destination in ('prepared', 'tailmux', '.tailmux-receipt', 'binary-published', 'committed'):
            with self.subTest(destination=destination):
                self.script('mv', '''#!/bin/bash
if [[ "$1" == *tailmux-stage*/tailmux || "$1" == *tailmux-stage*/receipt || "$1" == *tailmux-stage*/transaction ]]; then
  if [[ "$2" == "$FAIL_DEST" ]] || { [[ "$2" == */.tailmux-transaction ]] && grep -q "phase=$FAIL_PHASE" "$1"; }; then exit 73; fi
fi
exec "''' + real_mv + '''" "$@"
''')
                result = self.refusal('install', '--replace-owned', FAIL_DEST=str(self.prefix / destination), FAIL_PHASE=destination)
                self.assertNotIn('Usage:', result.stderr)
                self.assert_old_pair(older, receipt)
        self.script('mv', '#!/bin/bash\nexit 0\n')
        result = self.refusal('install', '--replace-owned')
        self.assertNotIn('Usage:', result.stderr)
        self.assert_old_pair(older, receipt)

    def test_p1_staging_and_backup_failures_preserve_pair(self):
        older, receipt = self.older_owned()
        for command in ('mktemp', 'cp', 'chmod'):
            with self.subTest(command=command):
                tool = shutil.which(command)
                self.script(command, '#!/bin/bash\nexit 73\n')
                result = self.refusal('install', '--replace-owned')
                self.assertNotIn('Usage:', result.stderr)
                self.assert_old_pair(older, receipt)
                (self.bin / command).unlink()
                (self.bin / command).symlink_to(tool)

    def test_p1_failed_rollback_retains_verified_transaction(self):
        older, receipt = self.older_owned()
        self.script('mv', '''#!/bin/bash
[[ "$1" != */receipt && "$1" != */rollback-binary ]] || exit 73
exec "''' + shutil.which('mv') + '''" "$@"
''')
        self.refusal('install', '--replace-owned', contains='Replacement incomplete')
        self.assertEqual((self.prefix / 'tailmux').read_bytes(), (ROOT / 'bin/tailmux').read_bytes())
        self.assertEqual((self.prefix / '.tailmux-receipt').read_bytes(), receipt)
        self.assertEqual(self.inspection()[0], 'pending')
        record = self.prefix / '.tailmux-transaction'
        fields = dict(line.split('=', 1) for line in record.read_text().splitlines()[1:])
        self.assertEqual((self.prefix / fields['backup'] / 'tailmux').read_bytes(), older)
        self.assertTrue((self.prefix / fields['stage'] / 'candidate').is_file())
        self.assertTrue((self.prefix / '.tailmux-install-lock/owner').is_file())
        before = record.read_bytes()
        lines = before.splitlines(keepends=True)
        for data in (b''.join(lines[:-1]), b''.join([lines[0], lines[2], lines[1], *lines[3:]]),
                     before.replace(b'prefix-sha256=', b'unknown-sha256='),
                     before.replace(fields['prefix-sha256'].encode(), b'0' * 64),
                     before.replace(b'id=', b'id=../', 1), before.rstrip(b'\n')):
            record.write_bytes(data)
            self.assertEqual(self.inspection()[0], 'unsafe')
            self.refusal('install', '--replace-owned')
            self.assertEqual(record.read_bytes(), data)
        record.write_bytes(before)
        record.chmod(0o644)
        self.assertEqual(self.inspection()[0], 'unsafe')
        record.chmod(0o600)
        record.unlink()
        os.mkfifo(record)
        self.assertEqual(self.inspection()[0], 'unsafe')
        record.unlink()
        target = self.root / 'transaction-target'
        target.write_bytes(before)
        record.symlink_to(target)
        self.assertEqual(self.inspection()[0], 'unsafe')
        record.unlink()
        record.write_bytes(before)
        record.chmod(0o600)
        owner = self.prefix / '.tailmux-install-lock/owner'
        owner_bytes = owner.read_bytes()
        for data in (owner_bytes + b'extra\n', owner_bytes.replace(fields['id'].encode(), b'other'), b'x' * 257):
            owner.write_bytes(data)
            self.assertEqual(self.inspection()[0], 'unsafe')
            self.refusal('install', '--replace-owned')
            self.assertEqual(owner.read_bytes(), data)
        owner.write_bytes(owner_bytes)
        owner.unlink()
        os.mkfifo(owner)
        self.assertEqual(self.inspection()[0], 'unsafe')
        owner.unlink()
        target = self.root / 'owner-target'
        target.write_bytes(owner_bytes)
        owner.symlink_to(target)
        self.assertEqual(self.inspection()[0], 'unsafe')
        owner.unlink()
        owner.write_bytes(owner_bytes)
        owner.chmod(0o600)
        stage = self.prefix / fields['stage']
        saved_stage = self.root / 'saved-stage'
        stage.rename(saved_stage)
        stage.symlink_to(saved_stage, target_is_directory=True)
        self.assertEqual(self.inspection()[0], 'unsafe')
        stage.unlink()
        saved_stage.rename(stage)
        self.assertEqual(self.inspection()[0], 'pending')

    def pause_replacement(self, boundary):
        ready = self.root / 'replacement-ready'
        ready.unlink(missing_ok=True)
        self.script('mv', '''#!/bin/bash
if [[ "$PAUSE_AT" == rollback-* && "$1" == */transaction ]] && grep -q phase=committed "$1"; then exit 73; fi
pause=false
case "$PAUSE_AT:$2" in
  prepared:*/.tailmux-transaction) grep -q phase=prepared "$1" && pause=true ;;
  binary-renamed:*/tailmux) [[ "$1" == */tailmux ]] && pause=true ;;
  receipt-renamed:*/.tailmux-receipt) [[ "$1" == */receipt ]] && pause=true ;;
  binary-published:*/.tailmux-transaction) grep -q phase=binary-published "$1" && pause=true ;;
  committed:*/.tailmux-transaction) grep -q phase=committed "$1" && pause=true ;;
esac
case "$PAUSE_AT:$1" in
  rollback-receipt-*:*/rollback-receipt|rollback-binary-*:*/rollback-binary) pause=true ;;
esac
if $pause && [[ "$PAUSE_AT" == rollback-*-before ]]; then : > "$PUBLISHER_READY"; exec /bin/sleep 30; fi
"''' + shutil.which('mv') + '''" "$@" || exit
if $pause; then : > "$PUBLISHER_READY"; exec /bin/sleep 30; fi
''')
        p = subprocess.Popen(['/bin/bash', str(SETUP), 'install', '--replace-owned'],
                             env=cli_environment(self.bin, self.env, PAUSE_AT=boundary, PUBLISHER_READY=str(ready)),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        self.addCleanup(self.stop_process, p)
        for _ in range(1500):
            if ready.exists() or p.poll() is not None:
                break
            time.sleep(.02)
        self.assertTrue(ready.exists(), 'replacement never reached ' + boundary)
        return p

    def stop_process(self, p):
        if p.poll() is None:
            os.killpg(p.pid, signal.SIGKILL)
            p.communicate(timeout=5)

    def reconcile_transaction(self, action):
        self.script('mv', '#!/bin/bash\nexec "' + shutil.which('mv') + '" "$@"\n')
        code = '''set -euo pipefail
for module in platform rc_blocks managed_blocks install; do source "$1/scripts/lib/$module.sh"; done
transaction_read "$2"
case "$3" in
  restore) transaction_restore_receipt_then_binary "$2" ;;
  publish) transaction_publish "$2"; transaction_clear "$2" ;;
  *) exit 2 ;;
esac
transaction_remove_stage "$2/$TX_STAGE"
lifecycle_unlock "$2" "$TX_ID"
'''
        result = subprocess.run(['/bin/bash', '-c', code, 'reconcile', str(ROOT), str(self.prefix), action],
                                env=cli_environment(self.bin, self.env), capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_p1_sigkill_at_each_restore_rename_can_finish_restore(self):
        older, receipt = self.older_owned()
        for boundary in ('rollback-receipt-before', 'rollback-receipt-after', 'rollback-binary-before', 'rollback-binary-after'):
            with self.subTest(boundary=boundary):
                p = self.pause_replacement(boundary)
                os.killpg(p.pid, signal.SIGKILL)
                stdout, _ = p.communicate(timeout=5)
                self.assertEqual(p.returncode, -signal.SIGKILL)
                self.assertNotIn(b'Client installed at', stdout)
                record = self.prefix / '.tailmux-transaction'
                fields = dict(line.split('=', 1) for line in record.read_text().splitlines()[1:])
                state = self.inspection()
                self.assertEqual((state[0], state[4]), ('pending', fields['id']))
                expected_binary = older if boundary == 'rollback-binary-after' else (ROOT / 'bin/tailmux').read_bytes()
                expected_receipt = receipt if boundary != 'rollback-receipt-before' else (
                    'tailmux-receipt-v1\n' + str(self.prefix / 'tailmux') + '\n' + hashlib.sha256(expected_binary).hexdigest() + '\n').encode()
                self.assertEqual((self.prefix / 'tailmux').read_bytes(), expected_binary)
                self.assertEqual((self.prefix / '.tailmux-receipt').read_bytes(), expected_receipt)
                before = self.tree()
                for args in [('install',), ('install', '--replace-owned'), ('uninstall',)]:
                    self.refusal(*args, contains=fields['id'])
                    self.assertEqual(self.tree(), before)
                self.reconcile_transaction('restore')
                self.assert_old_pair(older, receipt)
                self.assertFalse((self.prefix / fields['stage']).exists())
                self.assertEqual((self.prefix / fields['backup'] / 'tailmux').read_bytes(), older)
                print('P1 restore interruption evidence ' + json.dumps({'boundary': boundary, 'exit': p.returncode,
                      'transaction': fields['id'], 'restored_binary_sha256': hashlib.sha256(older).hexdigest()}), flush=True)

    def test_p1_internal_publish_from_each_publication_boundary(self):
        expected = (ROOT / 'bin/tailmux').read_bytes()
        expected_receipt = ('tailmux-receipt-v1\n' + str(self.prefix / 'tailmux') + '\n' + hashlib.sha256(expected).hexdigest() + '\n').encode()
        for boundary in ('prepared', 'binary-renamed', 'binary-published', 'receipt-renamed', 'committed'):
            with self.subTest(boundary=boundary):
                older, receipt = self.older_owned()
                p = self.pause_replacement(boundary)
                os.killpg(p.pid, signal.SIGKILL)
                p.communicate(timeout=5)
                self.assertEqual(self.inspection()[0], 'pending')
                record = self.prefix / '.tailmux-transaction'
                fields = dict(line.split('=', 1) for line in record.read_text().splitlines()[1:])
                self.reconcile_transaction('publish')
                self.assertEqual((self.prefix / 'tailmux').read_bytes(), expected)
                self.assertEqual((self.prefix / '.tailmux-receipt').read_bytes(), expected_receipt)
                self.assertFalse(record.exists())
                self.assertFalse((self.prefix / fields['stage']).exists())
                self.assertFalse((self.prefix / '.tailmux-install-lock').exists())
                self.assertEqual((self.prefix / fields['backup'] / 'tailmux').read_bytes(), older)
                self.assertEqual((self.prefix / fields['backup'] / 'receipt').read_bytes(), receipt)
                self.success('install', '--replace-owned')

    def test_p1_sigkill_after_record_removal_retains_owner_inspection_lock(self):
        self.older_owned()
        self.script('rm', '''#!/bin/bash
"''' + shutil.which('rm') + '''" "$@" || exit
if [[ "$1" == */.tailmux-transaction ]]; then : > "$PUBLISHER_READY"; exec /bin/sleep 30; fi
''')
        p = self.pause_replacement('cleanup-cleared')
        os.killpg(p.pid, signal.SIGKILL)
        stdout, _ = p.communicate(timeout=5)
        self.assertEqual(p.returncode, -signal.SIGKILL)
        self.assertNotIn(b'Client installed at', stdout)
        state = self.inspection()
        self.assertEqual((state[0], state[4]), ('owned', ''))
        self.assertFalse((self.prefix / '.tailmux-transaction').exists())
        self.assertEqual((self.prefix / 'tailmux').read_bytes(), (ROOT / 'bin/tailmux').read_bytes())
        owner = self.prefix / '.tailmux-install-lock/owner'
        owner_bytes = owner.read_bytes()
        self.assertTrue(owner_bytes.startswith(('tailmux-lock-v1\nuid=' + str(os.getuid()) + '\ntransaction=.tailmux-tx.').encode()))
        before = self.tree()
        for args in [('install',), ('install', '--replace-owned'), ('uninstall',)]:
            self.refusal(*args, contains='locked; inspect before retrying')
            self.assertEqual(self.tree(), before)
            self.assertEqual(owner.read_bytes(), owner_bytes)

    def test_p1_sigterm_rolls_back_and_competing_writer_refuses(self):
        older, receipt = self.older_owned()
        p = self.pause_replacement('binary-renamed')
        self.assertEqual((self.prefix / 'tailmux').read_bytes(), (ROOT / 'bin/tailmux').read_bytes())
        self.assertEqual((self.prefix / '.tailmux-receipt').read_bytes(), receipt)
        for args in [('install',), ('install', '--replace-owned'), ('uninstall',)]:
            self.refusal(*args, contains='locked')
        os.killpg(p.pid, signal.SIGTERM)
        stdout, stderr = p.communicate(timeout=10)
        self.assertNotEqual(p.returncode, 0, stderr)
        self.assertNotIn(b'Client installed at', stdout)
        self.assert_old_pair(older, receipt)
        print('P1 SIGTERM evidence ' + json.dumps({'exit': p.returncode, 'stderr': stderr.decode(),
              'binary_sha256': hashlib.sha256((self.prefix / 'tailmux').read_bytes()).hexdigest(),
              'receipt_sha256': hashlib.sha256((self.prefix / '.tailmux-receipt').read_bytes()).hexdigest(),
              'lock_present': (self.prefix / '.tailmux-install-lock').exists()}), flush=True)

    def test_p1_sigkill_pending_at_every_publication_boundary(self):
        older, receipt = self.older_owned()
        for boundary in ('prepared', 'binary-renamed', 'binary-published', 'receipt-renamed', 'committed'):
            with self.subTest(boundary=boundary):
                p = self.pause_replacement(boundary)
                os.killpg(p.pid, signal.SIGKILL)
                stdout, _ = p.communicate(timeout=5)
                self.assertNotEqual(p.returncode, 0)
                self.assertNotIn(b'Client installed at', stdout)
                record = self.prefix / '.tailmux-transaction'
                fields = dict(line.split('=', 1) for line in record.read_text().splitlines()[1:])
                print('P1 SIGKILL evidence ' + json.dumps({'boundary': boundary, 'exit': p.returncode,
                      'record': record.read_text(), 'binary_sha256': hashlib.sha256((self.prefix / 'tailmux').read_bytes()).hexdigest(),
                      'receipt_sha256': hashlib.sha256((self.prefix / '.tailmux-receipt').read_bytes()).hexdigest()}), flush=True)
                state = self.inspection()
                self.assertEqual(state[0], 'pending')
                self.assertEqual(state[4], fields['id'])
                owner = self.prefix / '.tailmux-install-lock/owner'
                self.assertEqual(owner.read_text(), 'tailmux-lock-v1\nuid=' + str(os.getuid()) + '\ntransaction=' + fields['id'] + '\n')
                self.assertEqual(owner.stat().st_mode & 0o777, 0o600)
                self.assertEqual(record.stat().st_mode & 0o777, 0o600)
                for args in [('install',), ('install', '--replace-owned'), ('uninstall',)]:
                    self.refusal(*args, contains=fields['id'])
                saved = record.read_bytes()
                for damaged in (saved + b'extra=1\n', saved.replace(b'phase=', b'phase=unknown-', 1),
                                saved.replace(b'backup=.tailmux-backup.', b'backup=../', 1), saved + b'\0', b'x' * 16385):
                    record.write_bytes(damaged)
                    self.assertEqual(self.inspection()[0], 'unsafe')
                    self.refusal('install', '--replace-owned')
                    self.assertEqual(record.read_bytes(), damaged)
                record.write_bytes(saved)
                (self.prefix / 'tailmux').write_bytes(b'third digest\n')
                self.assertEqual(self.inspection()[0], 'unsafe')
                (self.prefix / 'tailmux').write_bytes(older if boundary == 'prepared' else (ROOT / 'bin/tailmux').read_bytes())
                backup = self.prefix / fields['backup']
                backup_bytes = (backup / 'tailmux').read_bytes()
                (backup / 'tailmux').write_bytes(b'damaged backup\n')
                self.assertEqual(self.inspection()[0], 'unsafe')
                (backup / 'tailmux').write_bytes(backup_bytes)
                self.assertEqual(self.inspection()[0], 'pending')
                self.reconcile_transaction('restore')
                self.assert_old_pair(older, receipt)
                self.assertFalse((self.prefix / fields['stage']).exists())

    def test_offline_dispatch_without_modules(self):
        setup = self.root / 'setup.sh'
        setup.write_bytes(SETUP.read_bytes())
        for option in ('--help', '-h', '--version', '-V'):
            p = self.success(option, setup=setup)
            self.assertIn('0.2.3', p.stdout)
        self.refusal('update', setup=setup, contains='deprecated')
        self.refusal('install', setup=setup, contains='Required module missing')
        self.refusal('--help', 'extra', setup=setup)
        self.refusal('install', '--prefix', 'relative')
        self.assertEqual(self.tree(), [])
        p = subprocess.run(['/bin/bash', '-c', 'bash <(cat "$1") install', 'bash', str(SETUP)],
                           env=cli_environment(self.bin, self.env), capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('remote/process-substitution setup is disabled', p.stderr)
        self.assertEqual(self.tree(), [])

    def test_fresh_repeat_uninstall_and_unrelated_bytes(self):
        body = b'# caf\xc3\xa9\nsource ~/.other\nalias tailmux=other\n# no newline \xce\xa9'
        self.rc.write_bytes(body)
        self.rc.chmod(0o640)
        (self.home / 'aliases').write_text('unchanged')
        p = self.success('install')
        self.assertIn(str(self.prefix / 'tailmux'), p.stdout)
        self.assertIn('may shadow bare tailmux', p.stdout)
        self.assertEqual((self.prefix / 'tailmux').read_bytes(), (ROOT / 'bin/tailmux').read_bytes())
        self.assertEqual(self.rc.read_bytes(), body)
        self.assertEqual(self.rc.stat().st_mode & 0o777, 0o640)
        self.assertEqual(sorted(p.name for p in self.prefix.iterdir()), ['.tailmux-receipt', 'tailmux'])
        self.success('install')
        p = subprocess.run([str(self.prefix / 'tailmux'), '--version'], env=cli_environment(self.bin, self.env), capture_output=True, text=True)
        self.assertEqual((p.returncode, p.stdout), (0, 'tailmux 0.2.3\n'))
        self.success('uninstall')
        self.assertFalse((self.prefix / 'tailmux').exists())
        self.assertEqual(self.rc.read_bytes(), body)
        self.assertEqual((self.home / 'aliases').read_text(), 'unchanged')
        backups = list(self.prefix.glob('.tailmux-backup.*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o700)
        self.assertEqual((backups[0] / 'tailmux').read_bytes(), (ROOT / 'bin/tailmux').read_bytes())
        self.success('uninstall')
        self.assertEqual(len(list(self.prefix.glob('.tailmux-backup.*'))), 1)

    def test_installed_absolute_client_resolves_and_connects(self):
        self.success('install')
        trace = self.root / 'client-argv'
        self.script('tailscale', '''#!/bin/bash
if [[ "${1:-}" == --socket=* ]]; then
  [[ "$1" == "--socket=$EXPECTED_SOCKET" ]] || exit 98
  printf '%s\\0' "$1" > "$SOCKET_TRACE"
  shift
else
  exit 98
fi
case "$1" in
  status) cat "$STATUS_FIXTURE" ;;
  ssh) printf '%s\\0' "$@" > "$CLIENT_TRACE"; exit 37 ;;
  *) exit 97 ;;
esac
''')
        jq = self.bin / 'jq'
        jq.symlink_to(shutil.which('jq'))
        (self.bin / 'head').symlink_to(shutil.which('head'))
        socket = str(self.root / 'installed daemon.sock')
        socket_trace = self.root / 'socket-argv'
        env = dict(self.env, STATUS_FIXTURE=str(FIXTURES / 'status-v1.104.2/running.json'), CLIENT_TRACE=str(trace),
                   TAILMUX_TAILSCALE_SOCKET=socket, EXPECTED_SOCKET=socket, SOCKET_TRACE=str(socket_trace))
        p = subprocess.run([str(self.prefix / 'tailmux'), 'alice@work'], env=cli_environment(self.bin, env), capture_output=True, text=True)
        self.assertEqual(p.returncode, 37, p.stdout + p.stderr)
        self.assertEqual(socket_trace.read_bytes(), f'--socket={socket}\0'.encode())
        argv = trace.read_bytes().split(b'\0')[:-1]
        self.assertEqual(argv[:3], [b'ssh', b'alice@100.64.0.20', b'-t'])
        self.assertEqual(len(argv), 4)
        self.assertIn(b'tmux attach || tmux new', argv[3])
        self.assertFalse(self.trace.exists())
        self.success('uninstall')

    def test_census_and_functions_preserved_without_evaluation(self):
        for form in CENSUS + ['# opaque \x00 bytes\n', 'tailmux() { echo user; }\n', 'function tailmux { :; }\n']:
            body = (form + 'touch "$HOME/RC_WAS_EXECUTED"\nsource "$HOME/unknown-code"\n').encode()
            self.rc.write_bytes(body)
            self.success('install')
            self.assertEqual(self.rc.read_bytes(), body)
            self.assertFalse((self.home / 'RC_WAS_EXECUTED').exists())
            p = subprocess.run([str(self.prefix / 'tailmux'), '--version'], env=cli_environment(self.bin, self.env), capture_output=True, text=True)
            self.assertEqual((p.returncode, p.stdout), (0, 'tailmux 0.2.3\n'))
            self.success('uninstall')
            self.assertEqual(self.rc.read_bytes(), body)

    def test_all_known_blocks_and_missing_final_newline(self):
        for fixture in sorted(FIXTURES.glob('legacy-*.rc')):
            with self.subTest(fixture=fixture.name):
                before = b'# prefix caf\xc3\xa9\n'
                after = b'# suffix \xce\xa9 without newline'
                original = before + fixture.read_bytes() + after
                self.rc.write_bytes(original)
                self.rc.chmod(0o640)
                p = self.success('install')
                self.assertIn('Recognized managed blocks removed', p.stdout)
                self.assertEqual(self.rc.read_bytes(), before + after)
                self.assertEqual(self.rc.stat().st_mode & 0o777, 0o640)
                backups = list(self.home.glob('.tailmux-backup.*/original'))
                self.assertTrue(any(b.read_bytes() == original for b in backups))
                self.success('uninstall')
                self.assertEqual(self.rc.read_bytes(), before + after)
        core = (FIXTURES / 'legacy-core-pr01.rc').read_bytes()
        drive = (FIXTURES / 'legacy-taildrive-mount-pr01.rc').read_bytes()
        self.rc.write_bytes(b'# one\n' + core + b'# two\n' + drive + b'# end')
        self.success('install')
        self.assertEqual(self.rc.read_bytes(), b'# one\n# two\n# end')
        self.success('uninstall')
        self.rc.write_bytes(core.rstrip(b'\n'))
        self.success('uninstall')
        self.assertEqual(self.rc.read_bytes(), b'')

    def test_unknown_changed_and_multifile_refuse_before_writes(self):
        core = (FIXTURES / 'legacy-core-pr01.rc').read_bytes()
        for body in [core.replace(b'tmux attach', b'tmux attach-CHANGED'), core.replace(b'(tailmux)', b'(unknown)'),
                     core + core, core.split(b'# <<<')[0], b'# <<< tailmux managed block (tailmux) <<<\n',
                     core.replace(b'(tailmux) <<<', b'(taildrive) <<<')]:
            self.rc.write_bytes(core)
            (self.home / '.bashrc').write_bytes(body)
            before = self.tree()
            for operation in ('install', 'uninstall'):
                self.refusal(operation)
                self.assertEqual(self.rc.read_bytes(), core)
                self.assertEqual((self.home / '.bashrc').read_bytes(), body)
                self.assertEqual(self.tree(), before)

    def test_symlink_and_foreign_installation_refusals(self):
        self.prefix.mkdir(parents=True)
        binary = self.prefix / 'tailmux'
        binary.write_text('foreign')
        for operation in ('install', 'uninstall'):
            self.refusal(operation, contains='receipt is missing')
            self.assertEqual(binary.read_text(), 'foreign')
        binary.unlink()
        target = self.root / 'target'
        target.write_text('# unrelated')
        self.rc.symlink_to(target)
        self.success('install')
        self.success('uninstall')
        self.assertTrue(self.rc.is_symlink())
        target.write_bytes((FIXTURES / 'legacy-core-pr01.rc').read_bytes())
        for operation in ('install', 'uninstall'):
            self.refusal(operation, contains='Symlinked RC paths')
            self.assertTrue(self.rc.is_symlink())
        self.rc.unlink()
        binary.symlink_to(target)
        self.refusal('install')
        self.assertTrue(binary.is_symlink())

    def test_modified_executable_and_receipt_refuse(self):
        self.success('install')
        binary = self.prefix / 'tailmux'
        original = binary.read_bytes()
        binary.write_bytes(original + b'\n: modified\n')
        for operation in ('install', 'uninstall'):
            self.refusal(operation, contains='modified installation')
        binary.write_bytes(original)
        receipt = self.prefix / '.tailmux-receipt'
        receipt.write_text('foreign\n')
        self.refusal('uninstall')
        receipt.unlink()
        receipt.symlink_to(self.root / 'absent')
        self.refusal('install')

    def test_interrupted_publication_and_false_success(self):
        real_mv = shutil.which('mv')
        self.script('mv', '#!/bin/bash\n[[ "$1" != *tailmux-stage*/tailmux ]] || exit 73\nexec "' + real_mv + '" "$@"\n')
        self.refusal('install')
        self.assertTrue((self.prefix / '.tailmux-receipt').exists())
        self.assertFalse((self.prefix / 'tailmux').exists())
        self.script('mv', '#!/bin/bash\nexec "' + real_mv + '" "$@"\n')
        self.success('install')
        self.success('uninstall')
        self.script('mv', '#!/bin/bash\nexit 0\n')
        self.refusal('install', contains='Published receipt verification failed')
        self.assertFalse((self.prefix / 'tailmux').exists())
        self.assertFalse((self.prefix / '.tailmux-receipt').exists())

    def test_actual_interruption_retains_receipt_and_recovers(self):
        ready = self.root / 'publisher-ready'
        real_mv = shutil.which('mv')
        self.script('mv', '''#!/bin/bash
if [[ "$1" == *tailmux-stage*/tailmux ]]; then
  : > "$PUBLISHER_READY"
  exec /bin/sleep 30
fi
exec "''' + real_mv + '''" "$@"
''')
        env = dict(self.env, PUBLISHER_READY=str(ready))
        p = subprocess.Popen(['/bin/bash', str(SETUP), 'install'], env=cli_environment(self.bin, env),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        try:
            for _ in range(300):
                if ready.exists():
                    break
                time.sleep(0.02)
            self.assertTrue(ready.exists())
            os.killpg(p.pid, signal.SIGTERM)
            stdout, _ = p.communicate(timeout=5)
            self.assertNotEqual(p.returncode, 0)
            self.assertNotIn(b'Client installed at', stdout)
            self.assertTrue((self.prefix / '.tailmux-receipt').exists())
            self.assertFalse((self.prefix / 'tailmux').exists())
            self.assertFalse((self.prefix / '.tailmux-install-lock').exists())
        finally:
            if p.poll() is None:
                os.killpg(p.pid, signal.SIGKILL)
                p.communicate()
        (self.bin / 'mv').unlink()
        (self.bin / 'mv').symlink_to(real_mv)
        self.success('install')
        self.success('uninstall')

    def test_write_failures_and_rc_backup_truth(self):
        core = (FIXTURES / 'legacy-core-pr01.rc').read_bytes()
        self.rc.write_bytes(core)
        for name in ('mktemp', 'cp', 'mv', 'dd'):
            original = shutil.which(name)
            self.script(name, '#!/bin/bash\nexit 73\n')
            self.refusal('install')
            self.assertEqual(self.rc.read_bytes(), core)
            (self.bin / name).unlink()
            (self.bin / name).symlink_to(original)
        self.success('install')
        self.rc.write_bytes(core)
        self.script('mv', '#!/bin/bash\nexit 0\n')
        self.refusal('install', contains='Published RC content or metadata verification failed')
        self.assertEqual(self.rc.read_bytes(), core)
        self.assertTrue(any(p.read_bytes() == core for p in self.home.glob('.tailmux-backup.*/original')))

    def test_false_success_removal_and_missing_binary_receipt(self):
        self.success('install')
        real_rm = shutil.which('rm')
        self.script('rm', '#!/bin/bash\n[[ "$1" != */tailmux && "$1" != */.tailmux-receipt ]] || exit 0\nexec "' + real_rm + '" "$@"\n')
        self.refusal('uninstall', contains='Executable removal verification failed')
        self.assertTrue((self.prefix / 'tailmux').exists())
        self.assertTrue((self.prefix / '.tailmux-receipt').exists())
        (self.bin / 'rm').unlink()
        (self.bin / 'rm').symlink_to(real_rm)
        (self.prefix / 'tailmux').unlink()
        self.success('uninstall')
        self.assertFalse((self.prefix / '.tailmux-receipt').exists())

    def test_environment_prefix_spaces_and_all_rc_locations(self):
        core = (FIXTURES / 'legacy-core-pr01.rc').read_bytes()
        self.rc.write_bytes(core)
        for variable in ('HOME', 'ZDOTDIR'):
            for value in ('relative path', str(self.home) + '\n' + str(self.root)):
                for operation in ('install', 'uninstall'):
                    before = self.tree()
                    self.refusal(operation, contains='HOME and ZDOTDIR', **{variable: value})
                    self.assertEqual(self.tree(), before)
                    self.assertEqual(self.rc.read_bytes(), core)
        zsh = self.home / 'zsh space'
        zsh.mkdir()
        for name in ('.bashrc', '.bash_profile'):
            (self.home / name).write_bytes(core)
        (zsh / '.zshrc').write_bytes(core)
        prefix = self.home / 'bin space'
        self.success('install', '--prefix', str(prefix), ZDOTDIR=str(zsh))
        for path in [self.rc, self.home / '.bashrc', self.home / '.bash_profile', zsh / '.zshrc']:
            self.assertEqual(path.read_bytes(), b'')
        self.success('uninstall', '--prefix', str(prefix), ZDOTDIR=str(zsh))
        for invalid in ('', 'relative', '/', str(prefix) + '/../bin', str(prefix) + '\nother'):
            self.refusal('install', '--prefix', invalid)
        home_space = self.root / 'home space'
        home_space.mkdir()
        self.success('install', HOME=str(home_space), ZDOTDIR=str(home_space))
        self.success('uninstall', HOME=str(home_space), ZDOTDIR=str(home_space))

    def test_permissions_hardlinks_and_ancestor_modes(self):
        core = (FIXTURES / 'legacy-core-pr01.rc').read_bytes()
        self.rc.write_bytes(core)
        for mode in (0o664, 0o646):
            self.rc.chmod(mode)
            self.refusal('install', contains='writable RC files')
            self.assertEqual(self.rc.read_bytes(), core)
        self.rc.chmod(0o644)
        os.link(self.rc, self.root / 'hardlink')
        self.refusal('install', contains='one hard link')
        (self.root / 'hardlink').unlink()
        self.home.chmod(0o775)
        self.refusal('install', contains='writable non-sticky RC ancestor')
        self.home.chmod(0o755)
        self.rc.chmod(0o444)
        self.refusal('install', contains='RC or parent is not writable')
        self.rc.chmod(0o644)
        self.assertEqual(self.rc.read_bytes(), core)

    @unittest.skipUnless(platform.system() == 'Linux', 'native Linux metadata test')
    def test_linux_legacy_migration_preserves_xattrs_and_backup(self):
        core = (FIXTURES / 'legacy-core-pr01.rc').read_bytes()
        original = b'# before\n' + core + b'# after without newline'
        self.rc.write_bytes(original)
        self.rc.chmod(0o640)
        os.setxattr(self.rc, 'user.tailmux-test', b'opaque\x00metadata')
        before = self.rc.stat()
        self.success('install')
        self.assertEqual(self.rc.read_bytes(), b'# before\n# after without newline')
        self.assertEqual(os.getxattr(self.rc, 'user.tailmux-test'), b'opaque\x00metadata')
        after = self.rc.stat()
        self.assertEqual((after.st_uid, after.st_gid, after.st_mode),
                         (before.st_uid, before.st_gid, before.st_mode))
        backups = list(self.home.glob('.tailmux-backup.*/original'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        self.assertEqual(os.getxattr(backups[0], 'user.tailmux-test'), b'opaque\x00metadata')
        self.success('uninstall')
        self.assertEqual(self.rc.read_bytes(), b'# before\n# after without newline')

    @unittest.skipUnless(platform.system() == 'Linux', 'native Linux metadata test')
    def test_linux_security_context_mode_indicator_is_accepted_but_acls_are_refused(self):
        core = (FIXTURES / 'legacy-core-pr01.rc').read_bytes()
        self.rc.write_bytes(core)
        os.setxattr(self.rc, 'user.context-sentinel', b'preserved context data')
        real_ls = shutil.which('ls')
        def indicator(suffix):
            self.script('ls', '#!/bin/bash\nlisting="$("' + real_ls + '" "$@")" || exit $?\n'
                        'permissions=${listing%% *}\nif [[ $permissions == -* ]]; then\n'
                        'printf \'%s' + suffix + '%s\\n\' "$permissions" "${listing#"$permissions"}"\n'
                        'else printf \'%s\\n\' "$listing"; fi\n')
        indicator('.')
        self.success('install')
        self.assertEqual(self.rc.read_bytes(), b'')
        self.assertEqual(os.getxattr(self.rc, 'user.context-sentinel'), b'preserved context data')
        backups = list(self.home.glob('.tailmux-backup.*/original'))
        self.assertEqual(backups[0].read_bytes(), core)
        self.assertEqual(os.getxattr(backups[0], 'user.context-sentinel'), b'preserved context data')
        self.success('uninstall')
        self.rc.write_bytes(core)
        indicator('+')
        before = self.tree()
        self.refusal('install', contains='RC has ACLs or extended metadata')
        self.assertEqual(self.rc.read_bytes(), core)
        self.assertEqual(self.tree(), before)

    @unittest.skipUnless(platform.system() == 'Linux', 'native Linux metadata test')
    def test_linux_unverified_inode_flags_refuse_before_lifecycle_writes(self):
        core = (FIXTURES / 'legacy-core-pr01.rc').read_bytes()
        self.rc.write_bytes(core)
        for code, message in [("printf '%s\\n' '----i------------- file'", 'Unsupported Linux inode flags'),
                              ('exit 73', 'Cannot verify Linux inode flags')]:
            self.script('lsattr', '#!/bin/bash\n' + code + '\n')
            before = self.tree()
            for action in ('install', 'uninstall'):
                self.refusal(action, contains=message)
                self.assertEqual(self.rc.read_bytes(), core)
                self.assertEqual(self.tree(), before)

    @unittest.skipUnless(platform.system() == 'Linux', 'native Linux metadata test')
    def test_linux_dropped_xattrs_refuse_rc_replacement(self):
        core = (FIXTURES / 'legacy-core-pr01.rc').read_bytes()
        self.rc.write_bytes(core)
        os.setxattr(self.rc, 'user.tailmux-test', b'preserve me')
        real_cp = shutil.which('cp')
        self.script('cp', '#!/bin/bash\nexec "' + real_cp + '" -p -- "${@: -2}"\n')
        self.refusal('install', contains='RC metadata could not be preserved')
        self.assertEqual(self.rc.read_bytes(), core)
        self.assertEqual(os.getxattr(self.rc, 'user.tailmux-test'), b'preserve me')
        self.assertEqual(list(self.home.glob('.tailmux-backup.*/original')), [])

    @unittest.skipUnless(platform.system() == 'Darwin', 'macOS metadata evidence only')
    def test_macos_xattrs_flags_and_ancestor_acls(self):
        core = (FIXTURES / 'legacy-core-pr01.rc').read_bytes()
        self.rc.write_bytes(core)
        subprocess.run(['/usr/bin/xattr', '-w', 'user.tailmux-test', 'sentinel', str(self.rc)], check=True, env=cli_environment(self.bin, self.env))
        subprocess.run(['/usr/bin/chflags', 'nodump', str(self.rc)], check=True, env=cli_environment(self.bin, self.env))
        self.addCleanup(subprocess.run, ['/usr/bin/chflags', '0', str(self.rc)], check=False, env=cli_environment(self.bin, self.env))
        flags = self.rc.stat().st_flags
        before = subprocess.check_output(['/usr/bin/xattr', '-lx', str(self.rc)], env=cli_environment(self.bin, self.env))
        self.success('install')
        self.assertEqual(subprocess.check_output(['/usr/bin/xattr', '-lx', str(self.rc)], env=cli_environment(self.bin, self.env)), before)
        self.assertEqual(self.rc.stat().st_flags, flags)
        self.success('uninstall')
        for node in (self.home, self.root):
            subprocess.run(['/usr/bin/xattr', '-w', 'user.tailmux-test', 'acl-marker', str(node)], check=True, env=cli_environment(self.bin, self.env))
            subprocess.run(['/bin/chmod', '+a', 'everyone allow delete_child,add_subdirectory', str(node)], check=True, env=cli_environment(self.bin, self.env))
            self.addCleanup(subprocess.run, ['/bin/chmod', '-N', str(node)], check=False, env=cli_environment(self.bin, self.env))
            for operation in ('install', 'uninstall'):
                self.refusal(operation, contains='Unknown or mutating RC ancestor ACLs')
            subprocess.run(['/bin/chmod', '-N', str(node)], check=True, env=cli_environment(self.bin, self.env))
        for node in (self.home, self.root):
            subprocess.run(['/bin/chmod', '+a', 'everyone deny delete', str(node)], check=True, env=cli_environment(self.bin, self.env))
        before = [subprocess.check_output(['/bin/ls', '-lde', str(n)], env=cli_environment(self.bin, self.env)).split(b'\n')[1:] for n in (self.home, self.root)]
        self.success('install')
        self.success('uninstall')
        after = [subprocess.check_output(['/bin/ls', '-lde', str(n)], env=cli_environment(self.bin, self.env)).split(b'\n')[1:] for n in (self.home, self.root)]
        self.assertEqual(after, before)
        for node in (self.home, self.root):
            subprocess.run(['/bin/chmod', '-N', str(node)], check=True, env=cli_environment(self.bin, self.env))
        self.rc.write_bytes(core)
        subprocess.run(['/bin/chmod', '+a', 'everyone allow read', str(self.rc)], check=True, env=cli_environment(self.bin, self.env))
        self.addCleanup(subprocess.run, ['/bin/chmod', '-N', str(self.rc)], check=False, env=cli_environment(self.bin, self.env))
        self.refusal('install', contains='RC ACLs are refused')
        self.assertEqual(self.rc.read_bytes(), core)


if __name__ == '__main__':
    unittest.main(verbosity=2)
