#!/usr/bin/env python3

import hashlib
import functools
import json
import os
import platform
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/release'))
import package as pkg

REQUEST = pkg.ReleaseRequest('v' + (ROOT / 'VERSION').read_text().strip(), 'a' * 40)
CERTIFICATE = {'sourceRepositoryIdentifier': '1144643418', 'sourceRepositoryOwnerIdentifier': '240215896'}
VERIFIED = [{'verificationResult': {'signature': {'certificate': CERTIFICATE}}}]


@functools.lru_cache(maxsize=1)
def published_release():
    adapter = (ROOT / 'install.sh').read_text()
    tag = re.search(r'^tag=(v[0-9]+\.[0-9]+\.[0-9]+)$', adapter, re.MULTILINE).group(1)
    source = re.search(r'^source_sha=([0-9a-f]{40})$', adapter, re.MULTILINE).group(1)
    request = pkg.ReleaseRequest(tag, source)
    paths = (*pkg.PAYLOAD, 'scripts/release/package.py')
    blobs = {name: subprocess.check_output(['git', '-C', str(ROOT), 'show', source + ':' + name])
             for name in paths}
    return request, blobs


class DirectInstallTests(unittest.TestCase):
    def setUp(self, *, published=False):
        if published:
            self.request, blobs = published_release()
            self.payload = {name: blobs[name] for name in pkg.PAYLOAD}
            installer = blobs['scripts/release/package.py']
        else:
            self.request = REQUEST
            self.payload = {name: (ROOT / name).read_bytes() for name in pkg.PAYLOAD}
            installer = (ROOT / 'scripts/release/package.py').read_bytes()
        self.temporary = tempfile.TemporaryDirectory(prefix='tailmux-direct-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.home = self.root / 'home'
        self.home.mkdir(mode=0o700)
        self.stage = self.root / 'staging'
        self.stage.mkdir(mode=0o700)
        self.tools = self.root / 'tools'
        self.tools.mkdir(mode=0o700)
        self.assets = self.root / 'assets'
        self.assets.mkdir(mode=0o700)
        self.installer = self.assets / f'tailmux-{self.request.tag}-installer.py'
        self.installer.write_bytes(installer)
        self.archive = self.assets / f'tailmux-{self.request.tag}.tar.gz'
        self.archive.write_bytes(pkg.assemble(self.request, self.payload))
        self.bundle = self.assets / f'tailmux-{self.request.tag}.sigstore.json'
        self.bundle.write_text('{"inert":"bundle fixture"}')
        self.control = {'verification': {'installer': json.dumps(VERIFIED), 'package': json.dumps(VERIFIED)},
                        'tag': self.request.tag, 'source_sha': self.request.source_sha,
                        'gh_status': {}, 'curl_status': {}, 'oversized': {}, 'empty': {},
                        'hashes': {name: hashlib.sha256((self.assets / name).read_bytes()).hexdigest()
                                   for name in (self.installer.name, self.archive.name)}}
        self.save()
        common = (f'#!{sys.executable}\nimport hashlib, json, os, pathlib, shutil, subprocess, sys\n'
                  f'root = pathlib.Path({str(self.root)!r})\n'
                  'config = json.loads((root / "control.json").read_text())\n'
                  'def log(event):\n'
                  '    with (root / "events.jsonl").open("a") as stream: stream.write(json.dumps(event) + "\\n")\n')
        self.tool('curl', common + '''
args = sys.argv[1:]
if args == ['-q', '--version']:
    print('curl ' + config.get('curl_version', '8.4.0') + ' fixture')
    sys.exit(0)
assert args[0] == '-q'
for flag, expected in {'--proto': '=https', '--proto-redir': '=https', '--connect-timeout': '15',
                       '--max-time': '110', '--max-redirs': '5'}.items():
    assert args[args.index(flag) + 1] == expected, args
for flag in ('--fail', '--silent', '--show-error', '--location'):
    assert flag in args, args
url = next(value for value in args if value.startswith('https:'))
assert url.startswith('https://github.com/ddv1982/tailmux/releases/download/' + config['tag'] + '/'), url
name = url.rsplit('/', 1)[1]
log(['download', name])
sys.exit(config['curl_status'][name]) if name in config['curl_status'] else None
limit = int(args[args.index('--max-filesize') + 1])
assert limit == (8388608 if name.endswith('.tar.gz') else 2097152 if name.endswith('.json') else 1048576)
out = pathlib.Path(args[args.index('--output') + 1])
assert out.parent.stat().st_mode & 0o777 == 0o700
out.write_bytes(b'' if config['empty'].get(name) else b'x' * (limit + 1) if config['oversized'].get(name) else (root / 'assets' / name).read_bytes())
''')
        self.tool('gh', common + '''
args = sys.argv[1:]
if args == ['--version']:
    print('gh version ' + config.get('gh_version', '2.103.0') + ' fixture')
    sys.exit(0)
assert args[:2] == ['attestation', 'verify'], args
snapshot = pathlib.Path(args[2])
kind = 'installer' if snapshot.name.endswith('-installer.py') else 'package'
log(['verify', kind])
assert snapshot.parent.stat().st_mode & 0o777 == 0o700
for flag, value in {'--hostname': 'github.com', '--repo': 'ddv1982/tailmux',
                    '--signer-workflow': 'ddv1982/tailmux/.github/workflows/release.yml',
                    '--signer-digest': config['source_sha'], '--source-ref': 'refs/tags/' + config['tag'],
                    '--source-digest': config['source_sha'], '--format': 'json'}.items():
    assert args[args.index(flag) + 1] == value, args
assert '--deny-self-hosted-runners' in args
assert '--bundle' in args
assert pathlib.Path(args[args.index('--bundle') + 1]).read_bytes() == (root / 'assets' / ('tailmux-' + config['tag'] + '.sigstore.json')).read_bytes()
if kind in config['gh_status']:
    print(config['verification'][kind])
    sys.exit(config['gh_status'][kind])
expected = 'tailmux-' + config['tag'] + ('-installer.py' if kind == 'installer' else '.tar.gz')
if hashlib.sha256(snapshot.read_bytes()).hexdigest() != config['hashes'][expected]:
    sys.exit(19)
print(config['verification'][kind])
''')
        self.tool('python3', common + f'''
args = sys.argv[1:]
if len(args) > 1 and args[1].endswith('-installer.py'):
    log(['execute', 'installer'])
if config.get('root') and args == ['-I', '-']:
    code = sys.stdin.read()
    args = ['-I', '-c', 'import os; os.getuid = lambda: 0;\\n' + code]
if config.get('old_python') and args[:2] == ['-I', '-c']:
    sys.exit('Python 3.11 or later is required.')
os.execv({sys.executable!r}, [{sys.executable!r}, *args])
''')
        for name in ('tailscale', 'ssh', 'tmux', 'sudo'):
            self.tool(name, common + "log(['FORBIDDEN', pathlib.Path(sys.argv[0]).name]); sys.exit(99)\n")
        jq = shutil.which('jq')
        self.assertIsNotNone(jq, 'trusted jq is required for the real bootstrap test')
        (self.tools / 'jq').symlink_to(jq)
        self.environment = {'PATH': f'{self.tools}:{Path(sys.executable).parent}:/usr/bin:/bin',
                            'HOME': str(self.home), 'TMPDIR': str(self.stage), 'LC_ALL': 'C'}
        rendered = subprocess.run([sys.executable, '-I', str(self.installer),
                                   'bootstrap-command', '--tag', self.request.tag, '--source-sha', self.request.source_sha],
                                  check=True, capture_output=True, text=True)
        self.command = rendered.stdout

    def tool(self, name, code):
        path = self.tools / name
        path.write_text(code)
        path.chmod(0o700)

    def save(self):
        (self.root / 'control.json').write_text(json.dumps(self.control))

    def events(self):
        path = self.root / 'events.jsonl'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def bootstrap(self, extra=None):
        self.save()
        return subprocess.run(['/bin/bash', '--noprofile', '--norc'], input=self.command,
                              env={**self.environment, **(extra or {})}, capture_output=True, text=True, timeout=30)

    def assert_refused(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertFalse((self.home / '.local/bin/tailmux').exists())
        self.assertFalse(any(event[0] == 'FORBIDDEN' for event in self.events()))
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_real_rendered_bootstrap_installs_runs_and_retries_same_version(self):
        (self.home / '.bashrc').write_text('operator-owned\n')
        for _ in range(2):
            result = self.bootstrap()
            self.assertEqual(result.returncode, 0, result.stderr)
            installed = self.home / '.local/bin/tailmux'
            self.assertEqual(installed.read_bytes(), self.payload['bin/tailmux'])
            version = subprocess.run([str(installed), '--version'], env=self.environment, capture_output=True, text=True)
            self.assertEqual((version.returncode, version.stdout), (0, 'tailmux ' + self.request.tag[1:] + '\n'))
            self.assertEqual((self.home / '.bashrc').read_text(), 'operator-owned\n')
            self.assertEqual(list(self.stage.iterdir()), [])
        self.assertEqual(self.events()[:6], [
            ['download', self.installer.name], ['download', self.bundle.name],
            ['verify', 'installer'], ['execute', 'installer'], ['download', self.archive.name],
            ['verify', 'package']])
        self.assertFalse(any(event[0] == 'FORBIDDEN' for event in self.events()))

    @unittest.skipUnless(platform.system() == 'Linux', 'native Linux direct migration test')
    def test_linux_direct_install_migrates_legacy_bashrc(self):
        before = b'# operator prefix\n'
        after = b'# operator suffix without newline'
        legacy = (ROOT / 'scripts/tests/fixtures/legacy-core-pr01.rc').read_bytes()
        rc = self.home / '.bashrc'
        rc.write_bytes(before + legacy + after)
        rc.chmod(0o640)
        os.setxattr(rc, 'user.tailmux-test', b'preserved by direct install')
        result = self.bootstrap()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(rc.read_bytes(), before + after)
        self.assertEqual(rc.stat().st_mode & 0o777, 0o640)
        self.assertEqual(os.getxattr(rc, 'user.tailmux-test'), b'preserved by direct install')
        backups = list(self.home.glob('.tailmux-backup.*/original'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), before + legacy + after)
        self.assertEqual((self.home / '.local/bin/tailmux').read_bytes(), self.payload['bin/tailmux'])
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_verification_failure_precedes_execution_and_package_failure_precedes_parsing(self):
        self.control['gh_status']['installer'] = 17
        self.assert_refused(self.bootstrap())
        self.assertNotIn(['execute', 'installer'], self.events())
        self.control['gh_status'] = {'package': 18}
        self.archive.write_bytes(b'not even gzip')
        result = self.bootstrap()
        self.assert_refused(result)
        self.assertIn('exit status 18', result.stderr)
        self.assertNotIn('Not a gzipped file', result.stderr)

    def test_all_successful_certificate_results_must_have_exact_string_ids(self):
        certificates = [None, {}, {'sourceRepositoryIdentifier': '1144643418'},
                        {**CERTIFICATE, 'sourceRepositoryIdentifier': None},
                        {**CERTIFICATE, 'sourceRepositoryIdentifier': 1144643418},
                        {**CERTIFICATE, 'sourceRepositoryOwnerIdentifier': 240215896},
                        {**CERTIFICATE, 'sourceRepositoryIdentifier': 'other'},
                        {**CERTIFICATE, 'sourceRepositoryOwnerIdentifier': 'other'}]
        results = ['', 'null', '{}', '[]', '[{}]', '[null]', '[1]', '{', json.dumps(VERIFIED) + '\n' + json.dumps(VERIFIED)]
        for certificate in certificates:
            bad = {'verificationResult': {'signature': {'certificate': certificate}}}
            results.extend((json.dumps([bad]), json.dumps([VERIFIED[0], bad])))
        for kind in ('installer', 'package'):
            for raw in results:
                with self.subTest(kind=kind, raw=raw):
                    self.control['verification'] = {'installer': json.dumps(VERIFIED), 'package': json.dumps(VERIFIED)}
                    self.control['verification'][kind] = raw
                    (self.root / 'events.jsonl').unlink(missing_ok=True)
                    self.assert_refused(self.bootstrap())
                    if kind == 'installer':
                        self.assertNotIn(['execute', 'installer'], self.events())

    def test_tampered_installer_and_archive_never_install(self):
        original = self.installer.read_bytes()
        self.installer.write_bytes(original + b'\nraise SystemExit("tampered executable ran")\n')
        result = self.bootstrap()
        self.assert_refused(result)
        self.assertNotIn(['execute', 'installer'], self.events())
        self.installer.write_bytes(original)
        self.archive.write_bytes(self.archive.read_bytes() + b'tamper')
        self.assert_refused(self.bootstrap())

    def test_authenticated_malformed_archive_still_rejected_before_setup(self):
        self.archive.write_bytes(b'not gzip but fake-authenticated')
        self.control['hashes'][self.archive.name] = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        result = self.bootstrap()
        self.assert_refused(result)
        self.assertIn('Not a gzipped file', result.stderr)

    def test_unsafe_staging_and_root_refused_before_download(self):
        shared = self.root / 'shared'
        shared.mkdir(mode=0o777)
        shared.chmod(0o777)
        nested = shared / 'nested'
        nested.mkdir(mode=0o700)
        link = self.root / 'link'
        link.symlink_to(self.stage, target_is_directory=True)
        for value in (str(shared), str(nested), str(link), 'relative', str(self.stage) + '/../staging',
                      str(self.stage) + '\n', str(self.root / 'missing')):
            with self.subTest(tmpdir=value):
                self.assert_refused(self.bootstrap({'TMPDIR': value}))
                self.assertEqual(self.events(), [])
        self.control['root'] = True
        result = self.bootstrap()
        self.assert_refused(result)
        self.assertIn('non-root', result.stderr)
        self.assertEqual(self.events(), [])

    def test_prerequisite_floors_fail_before_download(self):
        for key, value in (('curl_version', '8.3.0'), ('gh_version', '2.102.0'), ('old_python', True)):
            with self.subTest(key=key):
                self.control[key] = value
                self.assert_refused(self.bootstrap())
                self.assertEqual(self.events(), [])
                del self.control[key]
        (self.tools / 'jq').unlink()
        for name in ('env', 'bash', 'uname'):
            (self.tools / name).symlink_to(shutil.which(name))
        self.assert_refused(self.bootstrap({'PATH': str(self.tools)}))
        self.assertEqual(self.events(), [])

    def test_unsupported_platform_refused_before_download(self):
        self.tool('uname', '#!/bin/sh\nprintf "%s\\n" FreeBSD\n')
        result = self.bootstrap()
        self.assert_refused(result)
        self.assertIn('Only macOS and Linux', result.stderr)
        self.assertEqual(self.events(), [])

    def test_network_size_and_bounded_verifier_failures(self):
        for name in (self.installer.name, self.bundle.name, self.archive.name):
            with self.subTest(name=name):
                self.control['curl_status'] = {name: 22}
                self.assert_refused(self.bootstrap())
                self.control['curl_status'] = {}
                self.control['oversized'] = {name: True}
                self.assert_refused(self.bootstrap())
                self.control['oversized'] = {}
                self.control['empty'] = {name: True}
                self.assert_refused(self.bootstrap())
                self.control['empty'] = {}
        for kind in ('installer', 'package'):
            with self.subTest(kind=kind):
                self.control['verification'][kind] = 'x' * (pkg.MAX_VERIFICATION + 1)
                self.assert_refused(self.bootstrap())
                self.control['verification'][kind] = json.dumps(VERIFIED)

    def installer_cli(self, *args, extra=None):
        self.save()
        return subprocess.run([sys.executable, '-I', str(self.installer), 'install', '--tag', self.request.tag,
                               '--source-sha', self.request.source_sha, '--bundle', str(self.bundle),
                               *args], env={**self.environment, **(extra or {})}, capture_output=True, text=True, timeout=30)

    def test_installer_cli_prefix_and_clean_setup_environment(self):
        prefix = self.home / 'custom/bin'
        marker = self.root / 'shell-injection'
        injection = self.root / 'injection.sh'
        injection.write_text(f'touch {marker}\n')
        result = self.installer_cli('--prefix', str(prefix), extra={'BASH_ENV': str(injection), 'ENV': str(injection),
                                                                  'PYTHONPATH': '/untrusted', 'BASH_FUNC_bad%%': '() { exit 99; }'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((prefix / 'tailmux').read_bytes(), self.payload['bin/tailmux'])
        self.assertFalse(marker.exists())
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_unsafe_home_prefix_and_existing_foreign_executable(self):
        shared = self.root / 'unsafe-home'
        shared.mkdir(mode=0o777)
        shared.chmod(0o777)
        self.assert_refused(self.bootstrap({'HOME': str(shared)}))
        linked_home = self.root / 'linked-home'
        linked_home.symlink_to(self.home, target_is_directory=True)
        self.assert_refused(self.bootstrap({'HOME': str(linked_home)}))
        for value in ('relative', str(self.home / '../outside'), str(self.home) + '\n'):
            self.assert_refused(self.installer_cli('--prefix', value))
        unsafe = self.root / 'unsafe-prefix'
        unsafe.mkdir(mode=0o777)
        unsafe.chmod(0o777)
        self.assert_refused(self.installer_cli('--prefix', str(unsafe)))
        prefix = self.home / '.local/bin'
        prefix.mkdir(parents=True, mode=0o700)
        foreign = prefix / 'tailmux'
        foreign.write_text('foreign executable\n')
        result = self.bootstrap()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(foreign.read_text(), 'foreign executable\n')
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_rendered_block_passes_shellcheck(self):
        path = self.root / 'command.sh'
        path.write_text('#!/usr/bin/env bash\n' + self.command)
        result = subprocess.run(['shellcheck', str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
