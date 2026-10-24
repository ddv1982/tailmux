#!/usr/bin/env python3
import copy
import errno
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pty
import select
import signal
import shutil
import struct
import termios
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[3]
VERIFY = ROOT / 'scripts/acceptance/verify.py'
SMOKE = ROOT / 'scripts/acceptance/smoke.py'
SHA = 'a' * 40
BASE = 'b' * 40
PAIRS = ('linux-linux', 'macos-linux', 'linux-macos')
CASES = ('attach-create', 'missing-tmux', 'backend-state', 'invalid-snapshot',
         'duplicate-identity', 'shared-ipv6-dns', 'denied-policy', 'host-keys',
         'terminal-lifecycle', 'install-recovery')
ENV = {k: os.environ[k] for k in ('PATH', 'HOME', 'TMPDIR') if k in os.environ}
ENV['PYTHONDONTWRITEBYTECODE'] = '1'


class Acceptance(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.bundle = self.root / 'bundle'
        self.bundle.mkdir()
        self.request_path = self.root / 'request.json'
        self.request = {'schema': 1, 'source_sha': SHA, 'merge_base_sha': BASE,
                        'approved_by': 'fixture-operator', 'approved_at': '2026-01-01T00:00:00Z',
                        'platforms': {pair: {'target': 'work', 'user': 'TEST_USER', 'isolated': True,
                                             'scope': 'disposable-acceptance'} for pair in PAIRS}}
        payloads = {'terminal.txt': ('text', b'SYNTHETIC FIXTURE. No real test ran.\n'),
                    'screen.png': ('native-screenshot', b'\x89PNG\r\n\x1a\nSTRUCTURE ONLY'),
                    'video.mp4': ('native-video', b'\x00\x00\x00\x18ftypSTRUCTURE ONLY')}
        files = []
        for name, (kind, data) in payloads.items():
            (self.bundle / name).write_bytes(data)
            files.append({'path': name, 'kind': kind, 'sha256': hashlib.sha256(data).hexdigest()})
        self.manifest = {'schema': 1, 'source_sha': SHA, 'merge_base_sha': BASE,
                         'origin': {'kind': 'protected-operator', 'operator': 'fixture-operator',
                                    'custody_ref': 'synthetic-offline-test'},
                         'redaction': {'reviewer': 'fixture-reviewer', 'reviewed_at': '2026-01-02T00:00:00Z', 'status': 'PASS'},
                         'files': files, 'scenarios': [], 'gates': {}}
        for pair in PAIRS:
            client, destination = pair.split('-')
            inventory = {key: 'fixture build and patch record' for key in
                         ('bash', 'jq', 'openssh', 'tailscale_cli', 'tailscale_daemon', 'tmux', 'vendor_patch', 'policy_fixture')}
            inventory.update(client_os=client + ' fixture', destination_os=destination + ' fixture')
            for scenario in CASES:
                code = 127 if scenario == 'missing-tmux' else 0
                self.manifest['scenarios'].append({
                    'platform': pair, 'scenario': scenario, 'target': 'work', 'user': 'TEST_USER',
                    'source_sha': SHA, 'merge_base_sha': BASE, 'status': 'PASS',
                    'started_at': '2026-01-01T01:00:00Z', 'finished_at': '2026-01-01T01:01:00Z',
                    'inventory': inventory, 'commands': [{'argv': ['tailmux', 'TEST_USER@work'],
                    'expected_exit': code, 'exit_code': code, 'outcome': 'exited', 'transcript': 'terminal.txt'}],
                    'expected': 'fixture expected', 'observed': 'fixture observed',
                    'evidence': list(payloads), 'operator_review': {'reviewer': 'fixture-reviewer',
                    'source_sha': SHA, 'reviewed_at': '2026-01-02T00:00:00Z', 'status': 'PASS', 'receipt': 'terminal.txt'}})
        for gate in ('unit-static', 'performance', 'audit-security', 'audit-release', 'operator-review'):
            self.manifest['gates'][gate] = {'status': 'PASS', 'source_sha': SHA, 'reviewer': 'fixture-reviewer',
                                          'reviewed_at': '2026-01-02T00:00:00Z', 'evidence': ['terminal.txt']}

    def run_verify(self, expected=0, *, save=True, extra=()):
        if save:
            self.request_path.write_text(json.dumps(self.request))
            (self.bundle / 'evidence.json').write_text(json.dumps(self.manifest))
        result = subprocess.run([sys.executable, str(VERIFY), '--bundle', str(self.bundle),
                                 '--request', str(self.request_path), '--expected-sha', SHA,
                                 '--expected-merge-base', BASE, *extra], capture_output=True,
                                text=True, timeout=10, env=ENV)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data['verdict'], 'NOT_VERIFIED')
        self.assertEqual(data['structure'], 'COMPLETE' if expected == 0 else 'REJECTED')
        return data

    def test_complete_protected_origin_fixture_is_structural_only(self):
        data = self.run_verify()
        self.assertEqual(data['scenario_count'], 30)
        self.assertEqual(data['platform_pairs'], list(PAIRS))
        self.assertEqual(data['request_sha256'], hashlib.sha256(self.request_path.read_bytes()).hexdigest())

    def test_missing_scenario_platform_gate_or_native_proof(self):
        original = copy.deepcopy(self.manifest)
        for mutation in ('scenario', 'platform', 'gate', 'native', 'commands', 'inventory', 'review'):
            with self.subTest(mutation=mutation):
                self.manifest = copy.deepcopy(original)
                if mutation == 'scenario':
                    self.manifest['scenarios'].pop()
                elif mutation == 'platform':
                    self.manifest['scenarios'] = [v for v in self.manifest['scenarios'] if v['platform'] != 'macos-linux']
                elif mutation == 'gate':
                    del self.manifest['gates']['performance']
                elif mutation == 'native':
                    self.manifest['scenarios'][0]['evidence'] = ['terminal.txt']
                elif mutation == 'commands':
                    self.manifest['scenarios'][0]['commands'] = []
                elif mutation == 'inventory':
                    self.manifest['scenarios'][0]['inventory']['vendor_patch'] = ''
                else:
                    self.manifest['scenarios'][0]['operator_review']['status'] = 'INCONCLUSIVE'
                self.run_verify(2)

    def test_stale_sha_merge_base_and_external_expectation(self):
        self.run_verify(2, extra=('--expected-sha', 'c' * 40))
        self.run_verify(2, extra=('--expected-merge-base', 'c' * 40))
        original = copy.deepcopy(self.manifest)
        for field in ('source_sha', 'merge_base_sha'):
            self.manifest = copy.deepcopy(original)
            self.manifest[field] = 'c' * 40
            self.run_verify(2)
            self.manifest = copy.deepcopy(original)
            self.manifest['scenarios'][0][field] = 'c' * 40
            self.run_verify(2)

    def test_failure_inconclusive_cancel_and_untrusted_origin(self):
        original = copy.deepcopy(self.manifest)
        for status in ('ERROR', 'INCONCLUSIVE', 'SKIP', 'NOT_VERIFIED'):
            self.manifest = copy.deepcopy(original)
            self.manifest['scenarios'][0]['status'] = status
            self.run_verify(2)
        self.manifest = copy.deepcopy(original)
        self.manifest['scenarios'][0]['commands'][0]['outcome'] = 'cancelled'
        self.run_verify(2)
        self.manifest = copy.deepcopy(original)
        self.manifest['origin']['kind'] = 'self-declared-json'
        self.run_verify(2)

    def test_target_user_platform_exit_and_time_binding(self):
        original = copy.deepcopy(self.manifest)
        for field, value in (('target', 'other'), ('user', 'root'), ('platform', 'windows-linux'),
                             ('finished_at', '2025-01-01T00:00:00Z')):
            self.manifest = copy.deepcopy(original)
            self.manifest['scenarios'][0][field] = value
            self.run_verify(2)
        self.manifest = copy.deepcopy(original)
        self.manifest['scenarios'][0]['inventory']['client_os'] = 'macos unexpected'
        self.run_verify(2)
        self.manifest = copy.deepcopy(original)
        self.manifest['scenarios'][0]['commands'][0]['exit_code'] = 37
        self.run_verify(2)

    def test_tamper_missing_and_unlisted_file(self):
        file = self.bundle / 'terminal.txt'
        original = file.read_bytes()
        file.write_bytes(b'tampered')
        self.run_verify(2)
        file.unlink()
        self.run_verify(2)
        file.write_bytes(original)
        (self.bundle / 'unlisted').write_text('extra')
        self.run_verify(2)

    def test_symlink_hardlink_traversal_and_absolute_paths(self):
        file = self.bundle / 'terminal.txt'
        destination = self.root / 'outside'
        file.rename(destination)
        file.symlink_to(destination)
        self.run_verify(2)
        file.unlink()
        os.link(destination, file)
        self.run_verify(2)
        file.unlink()
        destination.rename(file)
        for path in ('../outside', '/outside', './terminal.txt', 'sub/../terminal.txt', 'sub\\file'):
            self.manifest['files'][0]['path'] = path
            self.run_verify(2)

    def test_secrets_are_rejected_even_with_updated_digest(self):
        for data in (b'tskey-auth-TESTONLY12345', b'-----BEGIN OPENSSH PRIVATE KEY-----',
                     b'Authorization=BearerTESTONLY', b'access_token=TESTONLY12345'):
            (self.bundle / 'terminal.txt').write_bytes(data)
            self.manifest['files'][0]['sha256'] = hashlib.sha256(data).hexdigest()
            self.run_verify(2)

    def test_json_only_duplicate_keys_and_size_limits(self):
        self.run_verify()
        (self.bundle / 'evidence.json').write_text('{"schema":1,"schema":1}')
        self.run_verify(2, save=False)
        self.manifest['files'] = []
        self.run_verify(2)
        self.request['platforms']['linux-linux']['isolated'] = False
        self.run_verify(2)
        self.request_path.write_bytes(b' ' * (1024 * 1024 + 1))
        self.run_verify(2, save=False)

    def test_evidence_commands_are_never_executed(self):
        marker = self.root / 'MUST_NOT_EXIST'
        self.manifest['scenarios'][0]['commands'][0]['argv'] = ['/bin/sh', '-c', 'touch ' + str(marker)]
        self.run_verify()
        self.assertFalse(marker.exists())

    def test_live_driver_rejects_before_any_host_call(self):
        common = [sys.executable, str(SMOKE), '--expected-commit', SHA, '--target', 'work',
                  '--user', 'TEST_USER', '--platform', 'macos' if sys.platform == 'darwin' else 'linux',
                  '--consent', 'disposable-pty-smoke', '--output', str(self.root / 'private')]
        for extra in ([], ['--target', '-oProxyCommand=evil'], ['--user', 'root'],
                      ['--timeout', '181'], ['--expected-commit', 'short'], ['--consent', 'normal-workstation']):
            result = subprocess.run(common + extra, capture_output=True, timeout=5, env=ENV)
            self.assertEqual(result.returncode, 2)
            self.assertFalse((self.root / 'private').exists())

    def test_zip_intake_success_digest_and_unsafe_members(self):
        self.run_verify()
        archive = self.root / 'evidence.zip'
        def archive_with(extra=None):
            with zipfile.ZipFile(archive, 'w') as stream:
                stream.write(self.request_path, 'request.json')
                for file in self.bundle.iterdir():
                    stream.write(file, 'bundle/' + file.name)
                if extra is not None:
                    stream.writestr(extra, b'unsafe')
        def run_unpack(expected, output, digest=None):
            result = subprocess.run([sys.executable, str(VERIFY.with_name('unpack.py')),
                                     '--archive', str(archive), '--expected-sha256',
                                     digest or hashlib.sha256(archive.read_bytes()).hexdigest(),
                                     '--output', str(output)], env=ENV, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        archive_with()
        run_unpack(0, self.root / 'intake')
        self.assertEqual((self.root / 'intake/request.json').read_bytes(), self.request_path.read_bytes())
        run_unpack(2, self.root / 'intake')
        run_unpack(2, self.root / 'bad-digest', 'f' * 64)
        for number, name in enumerate(('../outside', '/absolute', 'bundle/../escape',
                                       'bundle/terminal.txt', 'bundle\\escape')):
            if name == 'bundle/terminal.txt':
                with self.assertWarns(UserWarning):
                    archive_with(name)
            else:
                archive_with(name)
            run_unpack(2, self.root / ('bad-' + str(number)))
        link = zipfile.ZipInfo('bundle/link')
        link.create_system = 3
        link.external_attr = 0o120777 << 16
        archive_with(link)
        run_unpack(2, self.root / 'bad-link')
        self.assertFalse((self.root / 'outside').exists())

    def test_unlisted_directory_and_metadata_secret(self):
        (self.bundle / 'unlisted-directory').mkdir()
        self.run_verify(2)
        (self.bundle / 'unlisted-directory').rmdir()
        self.manifest['origin']['custody_ref'] = 'tskey-auth-TESTONLY12345'
        self.run_verify(2)

    def test_acceptance_environment_main_only_policy(self):
        sys.path.insert(0, str(VERIFY.parent))
        self.addCleanup(lambda: sys.path.remove(str(VERIFY.parent)))
        spec = importlib.util.spec_from_file_location('acceptance_preflight_test', VERIFY.with_name('preflight.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        environment = {'name': 'acceptance', 'id': 1, 'deployment_branch_policy': {
            'protected_branches': False, 'custom_branch_policies': True},
            'protection_rules': [{'type': 'required_reviewers', 'prevent_self_review': True,
                                  'reviewers': [{'type': 'Team', 'reviewer': {'id': 1}}]}]}
        pages = [{'total_count': 1, 'branch_policies': [{'name': 'main', 'type': 'branch', 'id': 1}]}]
        module.validate_environment(environment, pages)
        for field, value in (('name', 'release'), ('id', None), ('protection_rules', []),
                             ('deployment_branch_policy', {'protected_branches': True, 'custom_branch_policies': False})):
            bad = copy.deepcopy(environment)
            bad[field] = value
            with self.assertRaises(ValueError):
                module.validate_environment(bad, pages)
        for change in ('self-review', 'reviewers', 'tag', 'wildcard', 'missing-pages', 'malformed-page'):
            bad, policies = copy.deepcopy(environment), copy.deepcopy(pages)
            if change == 'self-review':
                bad['protection_rules'][0]['prevent_self_review'] = False
            elif change == 'reviewers':
                bad['protection_rules'][0]['reviewers'] = []
            elif change == 'tag':
                policies[0]['branch_policies'][0].update(name='v*', type='tag')
            elif change == 'wildcard':
                policies[0]['branch_policies'][0]['name'] = '*'
            elif change == 'missing-pages':
                policies = []
            else:
                policies = [None]
            with self.assertRaises(ValueError):
                module.validate_environment(bad, policies)
        env = dict(ENV, GITHUB_REPOSITORY='ddv1982/tailmux', GITHUB_EVENT_NAME='pull_request')
        result = subprocess.run([sys.executable, str(VERIFY.with_name('preflight.py')), '--expected-sha', SHA],
                                env=env, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b'')

    def test_release_gate_private_fake_artifact_and_protected_expectations(self):
        self.run_verify()
        archive = self.root / 'gate.zip'
        with zipfile.ZipFile(archive, 'w') as stream:
            stream.write(self.request_path, 'request.json')
            for file in self.bundle.iterdir():
                stream.write(file, 'bundle/' + file.name)
        private = self.root / 'fake-bin'
        private.mkdir()
        trace = self.root / 'fake-gh-trace'
        fake_gh = private / 'gh'
        fake_gh.write_text('#!' + sys.executable + '\nimport os,sys,pathlib,json\n'
                           'expected=["api","--hostname","github.com","--method","GET",'
                           '"repos/ddv1982/tailmux/actions/artifacts/123/zip"]\n'
                           'assert sys.argv[1:] == expected\n'
                           'pathlib.Path(os.environ["FAKE_TRACE"]).write_text(json.dumps(sys.argv[1:]))\n'
                           'sys.exit(71) if os.environ.get("FAKE_GH_FAIL") else None\n'
                           'sys.stdout.buffer.write(pathlib.Path(os.environ["FAKE_ARCHIVE"]).read_bytes())\n')
        fake_gh.chmod(0o755)
        fake_git = private / 'git'
        fake_git.write_text('#!' + sys.executable + '\nimport os,sys\nargs=sys.argv[3:]\n'
                            'assert sys.argv[1] == "-C"\n'
                            'if args == ["rev-parse","HEAD"]: print(os.environ["FAKE_HEAD"])\n'
                            'elif args == ["merge-base","HEAD","origin/main"]: print(os.environ["FAKE_BASE"])\n'
                            'elif args != ["diff","--quiet","HEAD","--"]: sys.exit(72)\n')
        fake_git.chmod(0o755)
        env = dict(ENV, PATH=str(private) + ':' + ENV['PATH'], FAKE_ARCHIVE=str(archive),
                   FAKE_TRACE=str(trace), FAKE_HEAD=SHA, FAKE_BASE=BASE,
                   ACCEPTANCE_SOURCE_SHA=SHA, ACCEPTANCE_ARTIFACT_ID='123',
                   ACCEPTANCE_ARCHIVE_SHA256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                   ACCEPTANCE_REQUEST_SHA256=hashlib.sha256(self.request_path.read_bytes()).hexdigest(),
                   GITHUB_REPOSITORY='ddv1982/tailmux', RUNNER_ENVIRONMENT='github-hosted',
                   GITHUB_SHA=SHA, GITHUB_WORKFLOW_SHA=SHA)
        self.assertEqual(shutil.which('gh', path=env['PATH']), str(fake_gh))
        def run_gate(changes=None, remove=None, expected=2):
            current = dict(env, **(changes or {}))
            if remove:
                current.pop(remove)
            trace.unlink(missing_ok=True)
            result = subprocess.run([sys.executable, str(VERIFY.with_name('release_gate.py')),
                                     '--expected-sha', SHA, '--expected-merge-base', BASE],
                                    env=current, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
            if expected:
                self.assertEqual(result.stdout, '')
            return result
        result = json.loads(run_gate(expected=0).stdout)
        self.assertEqual(result['structure'], 'COMPLETE')
        self.assertEqual(result['verdict'], 'NOT_VERIFIED')
        self.assertEqual(result['source_sha'], SHA)
        self.assertEqual(result['merge_base_sha'], BASE)
        self.assertEqual(result['request_sha256'], env['ACCEPTANCE_REQUEST_SHA256'])
        for name in ('ACCEPTANCE_SOURCE_SHA', 'ACCEPTANCE_ARTIFACT_ID',
                     'ACCEPTANCE_ARCHIVE_SHA256', 'ACCEPTANCE_REQUEST_SHA256'):
            run_gate(remove=name)
            self.assertFalse(trace.exists())
        for changes in ({'ACCEPTANCE_SOURCE_SHA': 'c' * 40}, {'ACCEPTANCE_ARTIFACT_ID': '1;id'},
                        {'ACCEPTANCE_ARCHIVE_SHA256': 'bad'}, {'FAKE_HEAD': 'c' * 40},
                        {'FAKE_BASE': 'c' * 40}, {'GITHUB_WORKFLOW_SHA': 'c' * 40},
                        {'GITHUB_REPOSITORY': 'other/repository'}):
            run_gate(changes)
            self.assertFalse(trace.exists())
        for changes in ({'ACCEPTANCE_ARCHIVE_SHA256': 'f' * 64},
                        {'ACCEPTANCE_REQUEST_SHA256': 'f' * 64}, {'FAKE_GH_FAIL': '1'}):
            run_gate(changes)
            self.assertTrue(trace.exists())

    def test_cleanup_survives_late_alarm_and_terminal_restore_failures(self):
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                                 'Acceptance._check_cleanup_survives_late_alarm_and_terminal_restore_failures'],
                                capture_output=True, text=True, timeout=15, env=ENV)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def _check_cleanup_survives_late_alarm_and_terminal_restore_failures(self):
        spec = importlib.util.spec_from_file_location('cleanup_smoke', SMOKE)
        smoke = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(smoke)
        signals = (signal.SIGWINCH, signal.SIGTERM, signal.SIGHUP, signal.SIGALRM)
        cases = [(failure, late) for failure in (None, termios.error, OSError)
                 for late in (None, 'disarm', 'ignore', 'ignore-twice')]
        cases.append(('initial-io', None))
        for index, (failure, late) in enumerate(cases):
            with self.subTest(failure=failure, late_alarm=late):
                output = self.root / ('cleanup-' + str(index))
                output.mkdir()
                master, slave = pty.openpty()
                saved_input = os.dup(0)
                os.dup2(slave, 0)
                terminal_before = termios.tcgetattr(0)
                handlers = {signum: signal.getsignal(signum) for signum in signals}
                original_fork = pty.fork
                original_setattr = termios.tcsetattr
                original_ioctl = fcntl.ioctl
                original_timer = signal.setitimer
                original_signal = signal.signal
                owned = {}
                injected = 0

                def capture_fork():
                    pid, descriptor = original_fork()
                    if pid:
                        owned.update(pid=pid, descriptor=descriptor)
                    return pid, descriptor

                def restore(fd, when, attributes):
                    if failure in (termios.error, OSError) and when == termios.TCSANOW:
                        raise failure(errno.EIO, 'fixture terminal restoration failure')
                    return original_setattr(fd, when, attributes)

                def ioctl(fd, operation, argument):
                    if failure == 'initial-io' and fd == owned.get('descriptor'):
                        raise OSError(errno.EIO, 'fixture initial terminal sizing failure')
                    return original_ioctl(fd, operation, argument)

                def late_alarm(limit=1):
                    nonlocal injected
                    if injected < limit:
                        injected += 1
                        original_timer(signal.ITIMER_REAL, 0)
                        os.kill(os.getpid(), signal.SIGALRM)

                def timer(which, seconds, interval=0):
                    if late == 'ignore-twice' and which == signal.ITIMER_REAL and seconds > 0:
                        return original_timer(which, 0)
                    if late == 'disarm' and which == signal.ITIMER_REAL and seconds == 0:
                        late_alarm()
                    return original_timer(which, seconds, interval)

                def handler(signum, value):
                    if late in ('ignore', 'ignore-twice') and signum == signal.SIGALRM and value == signal.SIG_IGN:
                        late_alarm(2 if late == 'ignore-twice' else 1)
                    return original_signal(signum, value)

                try:
                    with patch.object(smoke.pty, 'fork', side_effect=capture_fork), \
                            patch.object(smoke.termios, 'tcsetattr', side_effect=restore), \
                            patch.object(smoke.fcntl, 'ioctl', side_effect=ioctl), \
                            patch.object(smoke.signal, 'setitimer', side_effect=timer), \
                            patch.object(smoke.signal, 'signal', side_effect=handler):
                        result = smoke.drive(['/bin/sleep', '5'], output, 0.05,
                                             {'PATH': '/usr/bin:/bin', 'TERM': 'xterm'})
                    self.assertEqual(result['outcome'], 'io-error' if failure else 'timeout')
                    self.assertEqual(injected, 2 if late == 'ignore-twice' else int(late is not None))
                    with self.assertRaises(ChildProcessError):
                        os.waitpid(owned['pid'], os.WNOHANG)
                    with self.assertRaises(OSError):
                        os.fstat(owned['descriptor'])
                    self.assertEqual({signum: signal.getsignal(signum) for signum in signals}, handlers)
                    self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))
                    if failure is None or failure == 'initial-io':
                        terminal_after = termios.tcgetattr(0)
                        for attributes in (terminal_before, terminal_after):
                            attributes[3] &= ~getattr(termios, 'PENDIN', 0)
                        self.assertEqual(terminal_after, terminal_before)
                finally:
                    original_timer(signal.ITIMER_REAL, 0)
                    for signum, value in handlers.items():
                        original_signal(signum, value)
                    if owned:
                        try:
                            os.close(owned['descriptor'])
                        except OSError:
                            pass
                        try:
                            waited, _ = os.waitpid(owned['pid'], os.WNOHANG)
                            if not waited:
                                os.kill(owned['pid'], signal.SIGKILL)
                                os.waitpid(owned['pid'], 0)
                        except ChildProcessError:
                            pass
                    os.dup2(saved_input, 0)
                    for descriptor in (saved_input, master, slave):
                        os.close(descriptor)

    def test_native_pty_resize_and_cancel_controls(self):
        output = self.root / 'pty-resize'
        output.mkdir()
        probe = ('import json,sys; sys.path.insert(0,sys.argv[1]); from pathlib import Path; '
                 'from smoke import drive; '
                 'r=drive(["/bin/bash","-c","printf control-ready; sleep 5"],Path(sys.argv[2]),6,'
                 '{"PATH":"/usr/bin:/bin","TERM":"xterm"}); '
                 '(Path(sys.argv[2])/"result.json").write_text(json.dumps(r))')
        master, slave = pty.openpty()
        child = subprocess.Popen([sys.executable, '-c', probe, str(SMOKE.parent), str(output)],
                                 stdin=slave, stdout=slave, stderr=slave, env=ENV, start_new_session=True)
        os.close(slave)
        try:
            transcript = b''
            deadline = time.monotonic() + 4
            while b'control-ready' not in transcript and time.monotonic() < deadline:
                ready, _, _ = select.select([master], [], [], 0.1)
                if ready:
                    transcript += os.read(master, 8192)
            self.assertIn(b'control-ready', transcript)
            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack('HHHH', 41, 101, 0, 0))
            child.send_signal(signal.SIGWINCH)
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline:
                select.select([], [], [], 0.02)
            child.send_signal(signal.SIGTERM)
            child.wait(timeout=3)
            self.assertEqual(child.returncode, 0)
            result = json.loads((output / 'result.json').read_text())
            self.assertEqual(result['outcome'], 'cancelled')
            self.assertEqual(result['exit_code'], -1)
            self.assertEqual([(event['rows'], event['columns']) for event in result['events']], [(41, 101)])
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=2)
            os.close(master)

    def test_native_pty_local_exit_and_timeout_controls(self):
        cases = [('exit', "printf 'local-native-pty-control\\n'; exit 37", 2, 'exited', 37),
                 ('timeout', 'sleep 5', 1, 'timeout', -1),
                 ('output', 'yes local-output-bound', 2, 'output-limit', -1),
                 ('missing', 'nonexistent-fixture-command', 2, 'exited', 127)]
        for name, program, timeout, expected_outcome, expected_exit in cases:
            with self.subTest(name=name):
                output = self.root / ('pty-' + name)
                output.mkdir()
                probe = ('import json,sys; sys.path.insert(0,sys.argv[1]); from pathlib import Path; '
                         'from smoke import drive; r=drive(["/bin/bash","-c",sys.argv[3]],Path(sys.argv[2]),int(sys.argv[4]),'
                         '{"PATH":"/usr/bin:/bin","TERM":"xterm"}); '
                         '(Path(sys.argv[2])/"result.json").write_text(json.dumps(r))')
                master, slave = pty.openpty()
                child = subprocess.Popen([sys.executable, '-c', probe, str(SMOKE.parent), str(output), program, str(timeout)],
                                         stdin=slave, stdout=slave, stderr=slave, env=ENV, start_new_session=True)
                os.close(slave)
                captured = b''
                deadline = time.monotonic() + 8
                while child.poll() is None and time.monotonic() < deadline:
                    ready, _, _ = select.select([master], [], [], 0.1)
                    if ready:
                        try:
                            captured += os.read(master, 8192)
                        except OSError:
                            break
                if child.poll() is None:
                    child.kill()
                child.wait(timeout=2)
                os.close(master)
                self.assertEqual(child.returncode, 0, captured[-4096:].decode(errors='replace'))
                result = json.loads((output / 'result.json').read_text())
                self.assertEqual(result['outcome'], expected_outcome)
                self.assertEqual(result['exit_code'], expected_exit)
                self.assertLessEqual((output / 'terminal.log').stat().st_size, 1024 * 1024)
                if name == 'exit':
                    self.assertIn(b'local-native-pty-control', (output / 'terminal.log').read_bytes())


if __name__ == '__main__':
    unittest.main(verbosity=2)
