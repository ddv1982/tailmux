#!/usr/bin/env python3
import hashlib
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time
import unittest

import installer_cli
import runtime_cli
from fixture_env import cli_environment

ROOT = Path(__file__).resolve().parents[3]
SETUP = ROOT / 'setup.sh'
CANDIDATE = ROOT / 'bin/tailmux'
WRAPPER = b'''#!/bin/bash
printf 'FORBIDDEN installed wrapper execution\\n' >> "$FORBIDDEN_TRACE"
exit 97
tailscale() {
  /opt/homebrew/bin/tailscale --socket=/var/run/tailscaled.socket "$@"
}
exec /opt/homebrew/bin/tailscale --socket=/var/run/tailscaled.socket "$@"
'''


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Recovery(unittest.TestCase):
    def setUp(self):
        self.fx = installer_cli.Lifecycle()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.root, self.home, self.bin = self.fx.root, self.fx.home, self.fx.bin
        self.prefix = self.fx.prefix
        self.source = self.root / 'reviewed-source'
        library = self.source / 'scripts/lib'
        library.mkdir(parents=True, mode=0o700)
        for module in (ROOT / 'scripts/lib').glob('*.sh'):
            target = library / module.name
            target.write_bytes(module.read_bytes())
            target.chmod(0o644)
        self.setup = self.source / 'setup.sh'
        self.setup.write_bytes(SETUP.read_bytes())
        self.setup.chmod(0o644)
        (self.source / 'bin').mkdir(mode=0o700)
        candidate = self.source / 'bin/tailmux'
        candidate.write_bytes(CANDIDATE.read_bytes())
        candidate.chmod(0o755)
        (self.bin / 'head').symlink_to(shutil.which('head'))
        self.addCleanup(self.assert_no_forbidden)

    def assert_no_forbidden(self):
        self.assertFalse(self.fx.trace.exists(), self.fx.trace.read_text() if self.fx.trace.exists() else '')

    def run_setup(self, *args, **changes):
        return self.fx.run_setup(*args, setup=self.setup, **changes)

    def ok(self, *args, **changes):
        result = self.run_setup(*args, **changes)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def refuse(self, *args, contains=None, **changes):
        result = self.run_setup(*args, **changes)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        if contains:
            self.assertIn(contains, result.stdout + result.stderr)
        return result

    def modified(self, prefix=None):
        if prefix:
            self.prefix = prefix
        self.prefix.mkdir(parents=True, exist_ok=True, mode=0o700)
        binary = self.prefix / 'tailmux'
        older = b'#!/bin/bash\nprintf "FORBIDDEN installed execution\\n" >> "$FORBIDDEN_TRACE"\nexit 97\n'
        receipt = f'tailmux-receipt-v1\n{binary}\n{sha(older)}\n'.encode()
        binary.write_bytes(older)
        binary.chmod(0o755)
        (self.prefix / '.tailmux-receipt').write_bytes(receipt)
        (self.prefix / '.tailmux-receipt').chmod(0o600)
        binary.write_bytes(WRAPPER)
        return WRAPPER, receipt

    def recover(self, *args, **changes):
        return self.ok('recover', '--prefix', str(self.prefix), *args, **changes)

    def inventory(self):
        result = {}
        for p in self.home.rglob('*'):
            stat = p.lstat()
            content = p.read_bytes() if p.is_file() and not p.is_symlink() else None
            result[str(p.relative_to(self.home))] = (stat.st_mode, stat.st_ino, stat.st_mtime_ns, content)
        return result

    def test_readonly_preview(self):
        wrapper, receipt = self.modified()
        self.fx.rc.write_bytes(b'# unrelated shell content\nalias tailmux=opaque\n')
        self.ok('configure', '--socket', '/explicit.sock')
        (self.home / '.config/tailmux/hosts').write_bytes(b'work work.example.ts.net\n')
        before = self.inventory()
        result = self.recover('--dry-run')
        for literal in ('Classification: modified', str(self.prefix), sha(wrapper),
                        receipt.decode().splitlines()[2], '0.3.0', sha(CANDIDATE.read_bytes()),
                        str(self.source), '.tailmux-backup.XXXXXX', 'Effective socket:'):
            self.assertIn(literal, result.stdout)
        self.assertEqual(self.inventory(), before)

    def test_candidate_fixture_is_private_when_checkout_ancestor_has_acl(self):
        self.modified()
        self.fx.script('ls', '''#!/bin/bash
for arg; do
  if [[ "$arg" == "$CHECKOUT_ANCESTOR" ]]; then
    printf '%s\\n' 'drwxr-xr-x+ fixture checkout ancestor'
    exit 0
  fi
done
exec "''' + shutil.which('ls') + '''" "$@"
''')
        before = self.inventory()
        result = self.recover('--dry-run', CHECKOUT_ANCESTOR=str(ROOT / 'bin'))
        self.assertIn('Classification: modified', result.stdout)
        self.assertIn(str(self.source), result.stdout)
        self.assertEqual((self.source / 'bin/tailmux').read_bytes(), CANDIDATE.read_bytes())
        self.assertEqual(self.inventory(), before)
        self.ok('configure', '--socket', '/fixture.sock', CHECKOUT_ANCESTOR=str(ROOT / 'bin'))
        self.assertEqual((self.home / '.config/tailmux/config').read_bytes(),
                         b'tailmux-config-v1\nsocket=/fixture.sock\n')
        before = self.inventory()
        for args in [('recover', '--dry-run'), ('configure', '--socket', '/refused.sock')]:
            self.refuse(*args, CHECKOUT_ANCESTOR=str(self.source / 'bin'),
                        contains='Unknown or mutating RC ancestor ACLs')
            self.assertEqual(self.inventory(), before)

    def test_exact_apply_backup_and_idempotence(self):
        wrapper, receipt = self.modified()
        self.recover('--expect-current-sha256', sha(wrapper))
        self.assertEqual((self.prefix / 'tailmux').read_bytes(), CANDIDATE.read_bytes())
        self.assertEqual((self.prefix / '.tailmux-receipt').read_bytes(),
                         f'tailmux-receipt-v1\n{self.prefix}/tailmux\n{sha(CANDIDATE.read_bytes())}\n'.encode())
        backups = list(self.prefix.glob('.tailmux-backup.*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / 'tailmux').read_bytes(), wrapper)
        self.assertEqual((backups[0] / 'receipt').read_bytes(), receipt)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o700)
        self.assertEqual((backups[0] / 'tailmux').stat().st_mode & 0o777, 0o700)
        self.assertEqual((backups[0] / 'receipt').stat().st_mode & 0o777, 0o600)
        before = self.inventory()
        self.recover('--expect-current-sha256', sha(wrapper))
        self.assertEqual(self.inventory(), before)

    def test_stale_approval_and_under_lock_observation_changes(self):
        wrapper, receipt = self.modified()
        self.recover('--dry-run')
        binary = self.prefix / 'tailmux'
        binary.write_bytes(wrapper + b'# changed\n')
        before = self.inventory()
        self.refuse('recover', '--expect-current-sha256', sha(wrapper), contains='digest changed')
        self.assertEqual(self.inventory(), before)
        binary.write_bytes(wrapper)
        self.fx.script('cmp', '''#!/bin/bash
if [[ "$2" == */.tailmux-install-lock/owner ]]; then
  printf '# changed under lock\\n' >> "$MUTATE_PATH"
fi
exec "''' + shutil.which('cmp') + '''" "$@"
''')
        for target in (binary, self.prefix / '.tailmux-receipt'):
            with self.subTest(target=target.name):
                binary.write_bytes(wrapper)
                (self.prefix / '.tailmux-receipt').write_bytes(receipt)
                self.refuse('recover', '--expect-current-sha256', sha(wrapper), MUTATE_PATH=str(target))
                self.assertTrue(target.read_bytes().endswith(b'# changed under lock\n'))
                self.assertEqual(list(self.prefix.glob('.tailmux-backup.*')), [])
                self.assertFalse((self.prefix / '.tailmux-transaction').exists())
                self.assertFalse((self.prefix / '.tailmux-install-lock').exists())

    def test_missing_malformed_and_path_mismatched_receipts(self):
        wrapper, receipt = self.modified()
        path = self.prefix / '.tailmux-receipt'
        for data in (None, b'bad\n', receipt + b'extra\n', receipt[:-1], receipt + b'\0',
                     receipt.replace(str(self.prefix).encode(), b'/different-prefix')):
            with self.subTest(data=data):
                if data is None:
                    path.unlink()
                else:
                    path.write_bytes(data)
                before = self.inventory()
                self.refuse('recover', '--dry-run', contains='unsafe' if data and b'\0' in data else 'foreign')
                self.refuse('recover', '--expect-current-sha256', sha(wrapper))
                self.assertEqual(self.inventory(), before)

    def test_backup_create_copy_and_verification_failures(self):
        wrapper, receipt = self.modified()
        for tool, body in (
            ('mktemp', '[[ "$*" != *tailmux-backup* ]] || exit 73\n'),
            ('cp', '[[ "$2" != *tailmux-backup*/tailmux ]] || exit 73\n'),
            ('cp', 'if [[ "$2" == *tailmux-backup*/tailmux ]]; then printf "corrupt\\n" > "$2"; exit 0; fi\n'),
            ('cp', 'if [[ "$2" == *tailmux-backup*/receipt ]]; then printf "corrupt\\n" > "$2"; exit 0; fi\n'),
        ):
            with self.subTest(tool=tool, body=body):
                self.fx.script(tool, '#!/bin/bash\n' + body + 'exec "' + shutil.which(tool) + '" "$@"\n')
                self.refuse('recover', '--expect-current-sha256', sha(wrapper))
                self.fx.assert_old_pair(wrapper, receipt)
                self.assertEqual(list(self.prefix.glob('.tailmux-stage.*')), [])
                self.fx.script(tool, '#!/bin/bash\nexec "' + shutil.which(tool) + '" "$@"\n')

    def test_caught_publication_failure_restores_exact_modified_pair(self):
        wrapper, receipt = self.modified()
        self.fx.script('mv', '''#!/bin/bash
if [[ "$1" == */receipt && "$2" == */.tailmux-receipt ]]; then exit 73; fi
exec "''' + shutil.which('mv') + '''" "$@"
''')
        result = self.refuse('recover', '--expect-current-sha256', sha(wrapper), contains='restored previous client')
        self.assertNotIn('Client installed at', result.stdout)
        self.fx.assert_old_pair(wrapper, receipt)

    def test_receipt_change_during_backup_does_not_become_new_approval(self):
        wrapper, receipt = self.modified()
        self.fx.script('cp', '''#!/bin/bash
if [[ "$2" == *tailmux-backup*/tailmux ]]; then
  printf 'tailmux-receipt-v1\\n%s/tailmux\\n%s\\n' "$APPROVED_PREFIX" "$OTHER_DIGEST" > "$APPROVED_PREFIX/.tailmux-receipt"
fi
exec "''' + shutil.which('cp') + '''" "$@"
''')
        result = self.run_setup('recover', '--expect-current-sha256', sha(wrapper),
                                APPROVED_PREFIX=str(self.prefix), OTHER_DIGEST='0' * 64)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.prefix / 'tailmux').read_bytes(), wrapper)
        self.assertEqual((self.prefix / '.tailmux-receipt').read_bytes(),
                         f'tailmux-receipt-v1\n{self.prefix}/tailmux\n{"0" * 64}\n'.encode())
        self.assertFalse((self.prefix / '.tailmux-transaction').exists())
        self.assertFalse((self.prefix / '.tailmux-install-lock').exists())

    def test_owned_other_version_requires_ordinary_replace_and_modified_candidate_needs_approval(self):
        self.modified()
        binary = self.prefix / 'tailmux'
        receipt = self.prefix / '.tailmux-receipt'
        old = b'#!/bin/bash\nexit 97\n'
        binary.write_bytes(old)
        receipt.write_bytes(f'tailmux-receipt-v1\n{binary}\n{sha(old)}\n'.encode())
        before = self.inventory()
        self.refuse('recover', '--expect-current-sha256', sha(old), contains='install --replace-owned')
        self.assertEqual(self.inventory(), before)
        binary.write_bytes(CANDIDATE.read_bytes())
        before = self.inventory()
        self.refuse('recover', '--expect-current-sha256', sha(old))
        self.assertEqual(self.inventory(), before)
        self.recover('--expect-current-sha256', sha(CANDIDATE.read_bytes()))
        self.assertEqual(receipt.read_bytes(), f'tailmux-receipt-v1\n{binary}\n{sha(CANDIDATE.read_bytes())}\n'.encode())

    def pause_recovery(self, boundary):
        ready = self.root / 'recovery-ready'
        ready.unlink(missing_ok=True)
        self.fx.script('mv', '''#!/bin/bash
pause=false
case "$PAUSE_AT:$2" in
  prepared:*/.tailmux-transaction) grep -q phase=prepared "$1" && pause=true ;;
  binary-renamed:*/tailmux) [[ "$1" == */tailmux ]] && pause=true ;;
  receipt-renamed:*/.tailmux-receipt) [[ "$1" == */receipt ]] && pause=true ;;
  binary-published:*/.tailmux-transaction) grep -q phase=binary-published "$1" && pause=true ;;
  committed:*/.tailmux-transaction) grep -q phase=committed "$1" && pause=true ;;
esac
"''' + shutil.which('mv') + '''" "$@" || exit
if $pause; then : > "$PUBLISHER_READY"; exec /bin/sleep 30; fi
''')
        p = subprocess.Popen(['/bin/bash', str(self.setup), 'recover', '--prefix', str(self.prefix),
                              '--expect-current-sha256', sha(WRAPPER)],
                             env=cli_environment(self.bin, self.fx.env, PAUSE_AT=boundary, PUBLISHER_READY=str(ready)),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        self.addCleanup(self.fx.stop_process, p)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and not ready.exists() and p.poll() is None:
            time.sleep(.02)
        self.assertTrue(ready.exists(), 'recovery never reached ' + boundary)
        return p

    def pending(self, boundary='binary-renamed'):
        self.modified()
        p = self.pause_recovery(boundary)
        os.killpg(p.pid, signal.SIGKILL)
        stdout, stderr = p.communicate(timeout=10)
        self.assertEqual(p.returncode, -signal.SIGKILL, stdout + stderr)
        self.fx.script('mv', '#!/bin/bash\nexec "' + shutil.which('mv') + '" "$@"\n')
        record = self.prefix / '.tailmux-transaction'
        fields = dict(line.split('=', 1) for line in record.read_text().splitlines()[1:])
        return fields

    def maintenance(self, action, fields, *, digest=None):
        return self.recover('--' + action, '--transaction', fields['id'],
                            '--expect-current-sha256', digest or sha((self.prefix / 'tailmux').read_bytes()))

    def test_real_sigterm_restores_modified_pair_at_publication_boundaries(self):
        for boundary in ('prepared', 'binary-renamed', 'binary-published', 'receipt-renamed', 'committed'):
            with self.subTest(boundary=boundary):
                wrapper, receipt = self.modified()
                p = self.pause_recovery(boundary)
                os.killpg(p.pid, signal.SIGTERM)
                stdout, stderr = p.communicate(timeout=15)
                self.assertNotEqual(p.returncode, 0, stdout + stderr)
                self.fx.assert_old_pair(wrapper, receipt)
                print('P3 SIGTERM', boundary, p.returncode, stderr.decode().strip(), flush=True)

    def test_sigkill_exact_unlock_then_recognized_resume_and_rollback(self):
        for action in ('resume', 'rollback'):
            for boundary in ('prepared', 'binary-renamed', 'binary-published', 'receipt-renamed', 'committed'):
                with self.subTest(action=action, boundary=boundary):
                    fields = self.pending(boundary)
                    record = self.prefix / '.tailmux-transaction'
                    binary_before = (self.prefix / 'tailmux').read_bytes()
                    receipt_before = (self.prefix / '.tailmux-receipt').read_bytes()
                    digest = sha(binary_before)
                    before = self.inventory()
                    self.refuse('recover', '--' + action, '--transaction', fields['id'],
                                '--expect-current-sha256', digest, contains='locked')
                    self.assertEqual(self.inventory(), before)
                    self.maintenance('unlock-abandoned', fields)
                    self.assertTrue(record.exists())
                    self.assertEqual((self.prefix / 'tailmux').read_bytes(), binary_before)
                    self.assertEqual((self.prefix / '.tailmux-receipt').read_bytes(), receipt_before)
                    self.maintenance(action, fields)
                    expected = CANDIDATE.read_bytes() if action == 'resume' else WRAPPER
                    self.assertEqual((self.prefix / 'tailmux').read_bytes(), expected)
                    self.assertFalse(record.exists())
                    self.assertFalse((self.prefix / '.tailmux-install-lock').exists())
                    backup = self.prefix / fields['backup']
                    self.assertEqual((backup / 'tailmux').read_bytes(), WRAPPER)
                    if action == 'rollback':
                        self.assertEqual((self.prefix / '.tailmux-receipt').read_bytes(), (backup / 'receipt').read_bytes())
                    else:
                        self.assertIn(sha(expected).encode(), (self.prefix / '.tailmux-receipt').read_bytes())
                    print('P3 SIGKILL', boundary, action, fields['id'], 'verified', flush=True)

    def test_candidate_configure_never_executes_old_and_fresh_process_uses_literal(self):
        self.modified()
        before = self.inventory()
        socket = str(self.root / "daemon ' ü ;$(touch marker)`id` [x].sock")
        self.ok('configure', '--socket', socket, ZDOTDIR='relative')
        config = self.home / '.config/tailmux/config'
        self.assertEqual(config.read_bytes(), f'tailmux-config-v1\nsocket={socket}\n'.encode())
        self.assertEqual((self.prefix / 'tailmux').read_bytes(), WRAPPER)
        for path, entry in before.items():
            self.assertEqual(self.inventory()[path], entry)
        self.recover('--expect-current-sha256', sha(WRAPPER))
        runtime = runtime_cli.Runtime()
        runtime.setUp()
        self.addCleanup(runtime.doCleanups)
        env = cli_environment(runtime.bin, runtime.env, HOME=str(self.home))
        p = subprocess.run(['/bin/bash', str(self.prefix / 'tailmux'), 'Alice@work'], env=env,
                           capture_output=True, text=True, timeout=10, cwd=self.root)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(runtime.calls(), [[f'--socket={socket}'.encode(), b'status', b'--json'],
                                         [f'--socket={socket}'.encode(), b'ssh', b'Alice@100.64.0.20', b'-t', runtime_cli.REMOTE.encode()]])
        self.assertFalse(runtime.forbidden.exists())
        self.assertFalse((self.root / 'marker').exists())

    def test_configure_has_no_lifecycle_prefix_and_malformed_config_stays_separate(self):
        self.ok('configure', '--socket', '/explicit.sock')
        self.assertFalse(self.prefix.exists())
        config = self.home / '.config/tailmux/config'
        config.write_bytes(b'tailmux-config-v1\nsocket=relative\n')
        wrapper, _ = self.modified()
        before = self.inventory()
        self.refuse('recover', '--dry-run', contains='Configuration needs separate')
        self.assertEqual(self.inventory(), before)
        self.refuse('configure', '--socket', '/new.sock')
        self.assertEqual({path: (entry[0], entry[3]) for path, entry in self.inventory().items()},
                         {path: (entry[0], entry[3]) for path, entry in before.items()})
        self.recover('--expect-current-sha256', sha(wrapper))
        self.assertEqual(config.read_bytes(), b'tailmux-config-v1\nsocket=relative\n')

    def test_configure_refuses_symlinked_candidate_without_executing_installed_script(self):
        self.modified()
        source = self.root / 'candidate'
        source.mkdir()
        shutil.copyfile(SETUP, source / 'setup.sh')
        shutil.copytree(ROOT / 'scripts/lib', source / 'scripts/lib')
        (source / 'bin').mkdir()
        (source / 'bin/tailmux').symlink_to(self.prefix / 'tailmux')
        before = self.inventory()
        p = self.fx.run_setup('configure', '--socket', '/explicit.sock', setup=source / 'setup.sh')
        self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn('Unsafe local candidate', p.stderr)
        self.assertEqual(self.inventory(), before)

    def test_prefix_spaces_and_shell_punctuation(self):
        self.modified(self.home / "bin ' ;$(exit 91)`exit 92` [x]")
        self.recover('--dry-run', ZDOTDIR='relative')
        self.recover('--expect-current-sha256', sha(WRAPPER), ZDOTDIR='relative')
        self.assertEqual((self.prefix / 'tailmux').read_bytes(), CANDIDATE.read_bytes())
        self.assertFalse(self.fx.prefix.exists())
        self.assertEqual(list(self.home.iterdir()), [self.prefix])

    def test_parser_rejects_malformed_duplicate_and_incompatible_requests_before_effects(self):
        self.modified()
        valid = sha(WRAPPER)
        requests = [(), ('--dry-run', '--dry-run'), ('--dry-run', '--resume'),
                    ('--dry-run', '--expect-current-sha256', valid), ('--dry-run', '--transaction', 'abc'),
                    ('--resume', '--expect-current-sha256', valid), ('--transaction', 'abc', '--expect-current-sha256', valid),
                    ('--expect-current-sha256', valid, '--expect-current-sha256', valid),
                    ('--resume', '--transaction', 'abc', '--transaction', 'abc', '--expect-current-sha256', valid),
                    ('--prefix', str(self.prefix), '--prefix', str(self.prefix), '--dry-run'),
                    ('--dry-run', 'extra'), ('--replace-owned',), ('--socket', '/x'), ('--force',)]
        requests += [('--expect-current-sha256', digest) for digest in ('', 'A' * 64, 'a' * 63, 'a' * 65, 'g' * 64, 'x\n')]
        requests += [('--resume', '--transaction', tx, '--expect-current-sha256', valid)
                     for tx in ('', '.', '..', '../x', 'a/b', 'a' * 97, 'ü', 'a\n')]
        before = self.inventory()
        for args in requests:
            with self.subTest(args=args):
                self.assertEqual(self.refuse('recover', *args).returncode, 2)
                self.assertEqual(self.inventory(), before)
        for args in [(), ('--socket',), ('--socket', 'relative'), ('--socket', '/x\n'),
                     ('--socket', '/x', '--socket', '/y'), ('--prefix', str(self.prefix), '--socket', '/x'),
                     ('--socket', '/x', 'extra'), ('--dry-run',)]:
            with self.subTest(configure=args):
                self.assertEqual(self.refuse('configure', *args).returncode, 2)
                self.assertEqual(self.inventory(), before)

    def test_unsafe_paths_and_failed_hashes_preserve_objects(self):
        wrapper, _ = self.modified()
        binary = self.prefix / 'tailmux'
        for kind in ('fifo', 'symlink', 'hardlink', 'writable', 'nonexecutable'):
            with self.subTest(kind=kind):
                binary.unlink()
                if kind == 'fifo':
                    os.mkfifo(binary)
                elif kind == 'symlink':
                    binary.symlink_to(CANDIDATE)
                else:
                    binary.write_bytes(wrapper)
                    binary.chmod(0o777 if kind == 'writable' else 0o600 if kind == 'nonexecutable' else 0o755)
                    if kind == 'hardlink':
                        os.link(binary, self.root / 'hardlink')
                before = self.inventory()
                self.refuse('recover', '--dry-run')
                self.refuse('recover', '--expect-current-sha256', sha(wrapper))
                self.assertEqual(self.inventory(), before)
        binary.unlink()
        binary.write_bytes(wrapper)
        binary.chmod(0o755)
        for output, status in (('', 0), ('bad', 0), ('A' * 64, 0), (sha(wrapper), 73)):
            self.fx.script('shasum', f'#!/bin/bash\nprintf "%s" "{output}"\nexit {status}\n')
            before = self.inventory()
            self.refuse('recover', '--dry-run')
            self.refuse('recover', '--expect-current-sha256', sha(wrapper))
            self.assertEqual(self.inventory(), before)

    def test_pending_unknown_identity_digest_artifacts_and_candidate_mismatch(self):
        fields = self.pending('prepared')
        record = self.prefix / '.tailmux-transaction'
        saved = record.read_bytes()
        current = sha((self.prefix / 'tailmux').read_bytes())
        before = self.inventory()
        for action in ('unlock-abandoned', 'resume', 'rollback'):
            for tx, digest in (('unknown', current), (fields['id'], '0' * 64)):
                self.refuse('recover', '--' + action, '--transaction', tx, '--expect-current-sha256', digest)
                self.assertEqual(self.inventory(), before)
        for invalid in (saved + b'extra\n', saved + b'\0', saved[:-1],
                        saved.replace(fields['prefix-sha256'].encode(), b'0' * 64),
                        saved.replace(b'phase=prepared', b'phase=unknown'),
                        saved.replace(b'backup=.tailmux-backup.', b'backup=../')):
            record.write_bytes(invalid)
            before = self.inventory()
            for action in ('unlock-abandoned', 'resume', 'rollback'):
                self.refuse('recover', '--' + action, '--transaction', fields['id'], '--expect-current-sha256', current)
                self.assertEqual(self.inventory(), before)
        record.write_bytes(saved)
        for path in (self.prefix / fields['backup'] / 'tailmux', self.prefix / fields['stage'] / 'candidate'):
            original = path.read_bytes()
            path.write_bytes(b'forged artifact\n')
            before = self.inventory()
            self.refuse('recover', '--unlock-abandoned', '--transaction', fields['id'], '--expect-current-sha256', current)
            self.assertEqual(self.inventory(), before)
            path.write_bytes(original)
        self.maintenance('unlock-abandoned', fields)
        stage = self.prefix / fields['stage']
        forged = b'#!/bin/bash\nexit 97\n'
        (stage / 'candidate').write_bytes(forged)
        forged_receipt = f'tailmux-receipt-v1\n{self.prefix}/tailmux\n{sha(forged)}\n'.encode()
        (stage / 'candidate-receipt').write_bytes(forged_receipt)
        record.write_bytes(saved.replace(fields['after-binary-sha256'].encode(), sha(forged).encode())
                          .replace(fields['after-receipt-sha256'].encode(), sha(forged_receipt).encode()))
        before = self.inventory()
        self.refuse('recover', '--resume', '--transaction', fields['id'], '--expect-current-sha256', current,
                    contains='matching candidate or explicit --rollback')
        self.assertEqual(self.inventory(), before)
        self.maintenance('rollback', fields)
        self.assertEqual((self.prefix / 'tailmux').read_bytes(), WRAPPER)

    def test_resume_guard_failure_under_new_lock_does_not_roll_back(self):
        fields = self.pending()
        self.maintenance('unlock-abandoned', fields)
        stage = self.prefix / fields['stage'] / 'candidate'
        staged = stage.read_bytes()
        public = [(self.prefix / name).read_bytes() for name in ('tailmux', '.tailmux-receipt', '.tailmux-transaction')]
        self.fx.script('cmp', '''#!/bin/bash
if [[ "$2" == */.tailmux-install-lock/owner ]]; then
  printf '# changed staged bytes\\n' >> "$MUTATE_STAGE"
fi
exec "''' + shutil.which('cmp') + '''" "$@"
''')
        self.refuse('recover', '--resume', '--transaction', fields['id'],
                    '--expect-current-sha256', sha(public[0]), MUTATE_STAGE=str(stage))
        self.assertEqual([(self.prefix / name).read_bytes() for name in ('tailmux', '.tailmux-receipt', '.tailmux-transaction')], public)
        self.assertTrue(stage.read_bytes().endswith(b'# changed staged bytes\n'))
        self.assertFalse((self.prefix / '.tailmux-install-lock').exists())
        self.fx.script('cmp', '#!/bin/bash\nexec "' + shutil.which('cmp') + '" "$@"\n')
        stage.write_bytes(staged)
        self.maintenance('rollback', fields)

    def test_unknown_third_public_bytes_are_preserved(self):
        fields = self.pending()
        binary = self.prefix / 'tailmux'
        binary.write_bytes(b'#!/bin/bash\nexit 96\n')
        before = self.inventory()
        for action in ('unlock-abandoned', 'resume', 'rollback'):
            self.refuse('recover', '--' + action, '--transaction', fields['id'], '--expect-current-sha256', sha(binary.read_bytes()))
            self.assertEqual(self.inventory(), before)

    def test_completed_recordless_cleanup_lock_requires_inspection(self):
        fields = self.pending('committed')
        (self.prefix / '.tailmux-transaction').unlink()
        before = self.inventory()
        for args in (('--expect-current-sha256', sha(WRAPPER)),
                     ('--unlock-abandoned', '--transaction', fields['id'], '--expect-current-sha256', sha(CANDIDATE.read_bytes()))):
            self.refuse('recover', *args)
            self.assertEqual(self.inventory(), before)

    def test_concurrent_writer_unknown_and_recordless_locks(self):
        self.modified()
        p = self.pause_recovery('binary-renamed')
        record = self.prefix / '.tailmux-transaction'
        fields = dict(line.split('=', 1) for line in record.read_text().splitlines()[1:])
        before = self.inventory()
        for args in [('recover', '--expect-current-sha256', sha(WRAPPER)), ('install', '--replace-owned'), ('uninstall',)]:
            self.refuse(*args, contains='locked')
            self.assertEqual(self.inventory(), before)
        os.killpg(p.pid, signal.SIGKILL)
        p.communicate(timeout=10)
        self.fx.script('mv', '#!/bin/bash\nexec "' + shutil.which('mv') + '" "$@"\n')
        owner = self.prefix / '.tailmux-install-lock/owner'
        saved_owner = owner.read_bytes()
        owner.write_bytes(b'unknown\n')
        before = self.inventory()
        self.refuse('recover', '--unlock-abandoned', '--transaction', fields['id'],
                    '--expect-current-sha256', sha((self.prefix / 'tailmux').read_bytes()))
        self.assertEqual(self.inventory(), before)
        owner.write_bytes(saved_owner)
        saved = record.read_bytes()
        record.unlink()
        before = self.inventory()
        self.refuse('recover', '--unlock-abandoned', '--transaction', fields['id'],
                    '--expect-current-sha256', sha((self.prefix / 'tailmux').read_bytes()))
        self.assertEqual(self.inventory(), before)
        record.write_bytes(saved)
        record.chmod(0o600)
        self.maintenance('unlock-abandoned', fields)
        self.maintenance('rollback', fields)


if __name__ == '__main__':
    unittest.main()
