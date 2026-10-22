#!/usr/bin/env python3

import gzip
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/release/package.py"
spec = importlib.util.spec_from_file_location("release_package", SCRIPT)
pkg = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = pkg
spec.loader.exec_module(pkg)
REQUEST = pkg.ReleaseRequest("v0.2.0-dev", "a" * 40)
FILES = {name: (ROOT / name).read_bytes() if (ROOT / name).is_file() else b"release instructions\n"
         for name in pkg.PAYLOAD}


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fake = self.root / "gh"
        self.fake.write_text("#!/usr/bin/env python3\nimport json, os, sys\n"
                             "open(os.environ['GH_LOG'], 'w').write(json.dumps(sys.argv[1:]))\n"
                             "sys.exit(int(os.environ.get('GH_RESULT', '0')))\n")
        self.fake.chmod(0o700)
        self.archive = self.root / "input.tar.gz"
        self.output = self.root / "output"
        self.output.mkdir(mode=0o700)
        self.env = {**os.environ, "PATH": f"{self.root}:{os.environ['PATH']}",
                    "GH_LOG": str(self.root / "gh.json")}
        self.valid = pkg.assemble(REQUEST, FILES)

    def verify(self, data, result="0", request=REQUEST):
        self.archive.write_bytes(data)
        return subprocess.run([sys.executable, str(SCRIPT), "verify", str(self.archive),
                               "--tag", request.tag, "--source-sha", request.source_sha,
                               "--output-parent", str(self.output)],
                              env={**self.env, "GH_RESULT": result}, capture_output=True, text=True)

    def malformed(self, entries):
        out = io.BytesIO()
        with tarfile.open(fileobj=out, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            for info, data in entries:
                archive.addfile(info, io.BytesIO(data))
        return gzip.compress(out.getvalue(), mtime=0)

    def entries(self):
        entries = []
        with tarfile.open(fileobj=io.BytesIO(self.valid), mode="r:gz") as archive:
            for info in archive:
                entries.append((info, archive.extractfile(info).read()))
        return entries

    def test_deterministic_roundtrip_and_private_nonoverwriting_stages(self):
        self.assertEqual(self.valid, pkg.assemble(REQUEST, FILES))
        first = self.verify(self.valid)
        self.assertEqual(first.returncode, 0, first.stderr)
        stage = Path(first.stdout.strip())
        self.assertEqual(stage.stat().st_mode & 0o777, 0o700)
        self.assertEqual(sorted(str(p.relative_to(stage)) for p in stage.rglob('*') if p.is_file()),
                         sorted([pkg.MANIFEST, *pkg.PAYLOAD]))
        for name in pkg.PAYLOAD:
            self.assertEqual((stage / name).read_bytes(), FILES[name])
        second = self.verify(self.valid)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertNotEqual(first.stdout, second.stdout)
        args = json.loads((self.root / 'gh.json').read_text())
        self.assertEqual(args[:2], ['attestation', 'verify'])
        self.assertEqual(args[3:], ['--repo', 'ddv1982/tailmux', '--signer-workflow',
                                   'ddv1982/tailmux/.github/workflows/release.yml',
                                   '--signer-digest', 'a' * 40, '--source-ref', 'refs/tags/v0.2.0-dev',
                                   '--source-digest', 'a' * 40, '--deny-self-hosted-runners'])
        help_result = subprocess.run(['bash', str(stage / 'bin/tailmux'), '--help'], capture_output=True)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        version = subprocess.run(['bash', str(stage / 'bin/tailmux'), '--version'], capture_output=True)
        self.assertEqual(version.stdout, b'tailmux 0.2.0-dev\n')

    def test_verifier_failure_precedes_even_gzip_parsing(self):
        result = self.verify(b'not even gzip', result='17')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('exit status 17', result.stderr)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_wrong_expected_tag_and_source_rejected_even_by_fake_success(self):
        for request in (pkg.ReleaseRequest('v99.0.0', 'a' * 40),
                        pkg.ReleaseRequest(REQUEST.tag, 'b' * 40)):
            with self.subTest(request=request):
                self.assertNotEqual(self.verify(self.valid, request=request).returncode, 0)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_tampered_payload_no_payload_written(self):
        entries = self.entries()
        info, data = entries[-1]
        entries[-1] = (info, bytes([data[0] ^ 1]) + data[1:])
        result = self.verify(self.malformed(entries))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('digests do not match', result.stderr)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_hostile_members(self):
        cases = []
        for name in ('../escape', '/escape', 'bin/../tailmux', './bin/tailmux',
                     'bin//tailmux', 'BIN/tailmux', 'extra', 'bin/tailmux/'):
            cases.append((name, tarfile.REGTYPE))
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.DIRTYPE, tarfile.FIFOTYPE,
                     tarfile.CHRTYPE, tarfile.BLKTYPE, tarfile.XHDTYPE, tarfile.XGLTYPE,
                     tarfile.GNUTYPE_LONGNAME, tarfile.GNUTYPE_SPARSE):
            cases.append(('bin/tailmux', kind))
        for name, kind in cases:
            with self.subTest(name=name, kind=kind):
                entries = self.entries()
                info = tarfile.TarInfo(name)
                info.type = kind
                info.linkname = 'setup.sh' if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE) else ''
                entries[4] = (info, b'')
                self.assertNotEqual(self.verify(self.malformed(entries)).returncode, 0)
                self.assertEqual(list(self.output.iterdir()), [])

    def test_duplicate_missing_extra_and_trailing_members(self):
        entries = self.entries()
        for bad in ([entries[0], *entries], entries[:-1], entries + [entries[1]],
                    [entries[0], entries[1], entries[1], *entries[3:]]):
            with self.subTest(count=len(bad)):
                self.assertNotEqual(self.verify(self.malformed(bad)).returncode, 0)
        raw = gzip.decompress(self.valid)
        for bad in (raw[:-512], raw + b'attack' + b'\0' * 506, raw + b'\0' * 10240,
                    raw[:-10240] if len(raw) > 10240 else b''):
            self.assertNotEqual(self.verify(gzip.compress(bad)).returncode, 0)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_manifest_duplicate_keys_and_invalid_shapes(self):
        for content in (b'{"format":"x","format":"tailmux-portable-v1"}', b'[]', b'null',
                        b'{"members":{"x":1,"x":2}}', b'{"format": NaN}'):
            with self.subTest(content=content):
                entries = self.entries()
                info = tarfile.TarInfo(pkg.MANIFEST)
                info.size = len(content)
                info.mode = 0o644
                entries[0] = (info, content)
                self.assertNotEqual(self.verify(self.malformed(entries)).returncode, 0)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_limits_and_invalid_request(self):
        for data in (b'x' * (pkg.MAX_COMPRESSED + 1),
                     gzip.compress(b'\0' * (pkg.MAX_EXPANDED + 1)), b''):
            self.assertNotEqual(self.verify(data).returncode, 0)
        for tag, sha in (('../v1', 'a' * 40), ('v1.2.3', 'main'), ('v1.2.3\n', 'a' * 40)):
            with self.assertRaises(ValueError):
                pkg.ReleaseRequest(tag, sha)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_builder_uses_git_objects_and_refuses_overwrite(self):
        def committed(root, *args):
            if args[0] == 'rev-parse':
                return (REQUEST.source_sha + '\n').encode()
            if args[0] == 'ls-tree':
                name = args[-1]
                mode = '100755' if name == 'bin/tailmux' else '100644'
                return f'{mode} blob {name}\t{name}\n'.encode()
            if args[:2] == ('cat-file', '-s'):
                return str(len(FILES[args[-1]])).encode()
            return FILES[args[-1]]
        destination = self.root / 'built.tar.gz'
        with patch.object(pkg, 'git', side_effect=committed):
            pkg.build(ROOT, REQUEST, destination)
            self.assertEqual(destination.read_bytes(), self.valid)
            with self.assertRaises(FileExistsError):
                pkg.build(ROOT, REQUEST, destination)
        self.assertEqual(destination.read_bytes(), self.valid)
        for name, content, message in (
                ('bin/tailmux', b'readonly TAILMUX_VERSION=9.0.0\n', 'Embedded binary version'),
                ('setup.sh', b'TAILMUX_VERSION=9.0.0\n', 'Installer version')):
            with patch.dict(FILES, {name: content}), patch.object(pkg, 'git', side_effect=committed):
                with self.assertRaisesRegex(ValueError, message):
                    pkg.build(ROOT, REQUEST, self.root / 'bad-version.tar.gz')
            self.assertFalse((self.root / 'bad-version.tar.gz').exists())

    def test_shared_output_parent_rejected_and_existing_content_preserved(self):
        marker = self.output / 'existing'
        marker.write_text('preserve me')
        self.output.chmod(0o777)
        result = self.verify(self.valid)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(marker.read_text(), 'preserve me')
        self.assertEqual(list(self.output.iterdir()), [marker])
        self.output.chmod(0o700)

    def test_real_source_git_fixture_builds_and_ignores_working_tree(self):
        fixture = self.root / 'source'
        fixture.mkdir()
        for name in pkg.PAYLOAD:
            path = fixture / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / name).read_bytes())
            path.chmod(0o755 if name == 'bin/tailmux' else 0o644)
        def git(*args, **kwargs):
            return subprocess.run(['git', '-C', str(fixture), *args], check=True,
                                  capture_output=True, **kwargs).stdout.strip().decode()
        git('init', '--quiet')
        git('add', '.')
        tree = git('write-tree')
        source = git('-c', 'user.name=Release fixture', '-c', 'user.email=fixture@example.invalid',
                     'commit-tree', tree, input=b'Isolated release test fixture\n')
        git('update-ref', 'HEAD', source)
        git('update-ref', f'refs/tags/{REQUEST.tag}', source)
        (fixture / 'bin/tailmux').write_text('Uncommitted input must never ship\n')
        built = []
        for name in ('first.tar.gz', 'second.tar.gz'):
            destination = self.root / name
            result = subprocess.run([sys.executable, str(SCRIPT), 'build', '--root', str(fixture),
                                     '--tag', REQUEST.tag, '--source-sha', source,
                                     '--output', str(destination)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            built.append(destination.read_bytes())
        self.assertEqual(built[0], built[1])
        result = self.verify(built[0], request=pkg.ReleaseRequest(REQUEST.tag, source))
        self.assertEqual(result.returncode, 0, result.stderr)
        stage = Path(result.stdout.strip())
        self.assertEqual((stage / 'bin/tailmux').read_bytes(), (ROOT / 'bin/tailmux').read_bytes())
        self.assertEqual((stage / 'setup.sh').stat().st_mode & 0o777, 0o644)
        self.assertEqual((stage / 'bin/tailmux').stat().st_mode & 0o777, 0o755)
        (fixture / 'VERSION').write_text('9.0.0\n')
        git('add', 'VERSION')
        tree = git('write-tree')
        mismatch = git('-c', 'user.name=Release fixture', '-c', 'user.email=fixture@example.invalid',
                       'commit-tree', tree, input=b'Invalid version test fixture\n')
        git('update-ref', 'HEAD', mismatch)
        git('update-ref', f'refs/tags/{REQUEST.tag}', mismatch)
        result = subprocess.run([sys.executable, str(SCRIPT), 'build', '--root', str(fixture),
                                 '--tag', REQUEST.tag, '--source-sha', mismatch,
                                 '--output', str(self.root / 'rejected.tar.gz')], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('VERSION does not match', result.stderr)
        self.assertFalse((self.root / 'rejected.tar.gz').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
