#!/usr/bin/env python3

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/release'))
import preflight as gate

SOURCE = 'a' * 40
MAIN = 'b' * 40
ENVIRONMENT = {
    'id': 1, 'name': 'release',
    'deployment_branch_policy': {'protected_branches': False, 'custom_branch_policies': True},
    'protection_rules': [{'type': 'required_reviewers', 'prevent_self_review': False,
                          'reviewers': [{'type': 'User', 'reviewer': {'id': 82675328}}]}],
}
POLICIES = [{'total_count': 1, 'branch_policies': [{'id': 3, 'name': 'v0.2.0', 'type': 'tag'}]}]
BRANCH = {'name': 'main', 'protected': True, 'commit': {'sha': MAIN}}
RULES = [[{'type': 'pull_request', 'parameters': {'required_approving_review_count': 0,
           'dismiss_stale_reviews_on_push': True, 'require_last_push_approval': False, 'required_review_thread_resolution': True}},
          {'type': 'required_status_checks', 'parameters': {'strict_required_status_checks_policy': True,
           'required_status_checks': [{'context': name, 'integration_id': 15368}
                                      for name in ('full-linux', 'full-macos', 'workflow-policy')]}}]]
IDENTITY = {
    'GITHUB_REPOSITORY': 'ddv1982/tailmux', 'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF_TYPE': 'tag',
    'GITHUB_REF': 'refs/tags/v1.2.3', 'GITHUB_REF_NAME': 'v1.2.3', 'GITHUB_SHA': SOURCE,
    'GITHUB_WORKFLOW_SHA': SOURCE,
    'GITHUB_WORKFLOW_REF': 'ddv1982/tailmux/.github/workflows/release.yml@refs/tags/v1.2.3',
    'RUNNER_ENVIRONMENT': 'github-hosted',
}


TAG_RULES = {'id': 10, 'target': 'tag', 'source': 'ddv1982/tailmux', 'source_type': 'Repository',
             'enforcement': 'active', 'bypass_actors': [],
             'conditions': {'ref_name': {'include': ['refs/tags/v*'], 'exclude': []}},
             'rules': [{'type': 'update'}, {'type': 'deletion'}]}
WORKFLOW = {'id': 20, 'path': '.github/workflows/ci.yml', 'state': 'active'}
CI_RUN = {'id': 30, 'workflow_id': 20, 'path': '.github/workflows/ci.yml', 'head_sha': SOURCE,
          'event': 'push', 'status': 'completed', 'conclusion': 'success', 'run_attempt': 1,
          'check_suite_id': 40, 'repository': {'id': 1144643418, 'full_name': 'ddv1982/tailmux'},
          'head_repository': {'id': 1144643418, 'full_name': 'ddv1982/tailmux'}}
JOBS = [{'name': name, 'status': 'completed', 'conclusion': 'success', 'head_sha': SOURCE,
         'run_id': 30, 'run_attempt': 1, 'check_run_url': f'https://api.github.com/repos/ddv1982/tailmux/check-runs/{n}'}
        for n, name in enumerate(sorted(gate.REQUIRED_CHECKS), 50)]
CHECKS = {f'check-runs/{n}': {'id': n, 'name': name, 'head_sha': SOURCE, 'status': 'completed',
                            'conclusion': 'success', 'app': {'id': 15368}, 'check_suite': {'id': 40}}
          for n, name in enumerate(sorted(gate.REQUIRED_CHECKS), 50)}


def policy_fixtures():
    return {'rulesets?per_page=100': [[TAG_RULES]], 'rulesets/10': TAG_RULES,
            'actions/workflows/ci.yml': WORKFLOW,
            f'actions/workflows/ci.yml/runs?head_sha={SOURCE}&event=push&per_page=100': [{'workflow_runs': [CI_RUN]}],
            'actions/runs/30/attempts/1/jobs?per_page=100': [{'jobs': JOBS}], **CHECKS}


class ProtectionTests(unittest.TestCase):
    def test_protected_environment_and_main_accepted(self):
        gate.validate_environment(ENVIRONMENT, POLICIES, 'release')
        self.assertEqual(gate.validate_main(BRANCH, RULES), MAIN)
        other = {**ENVIRONMENT, 'name': 'release-acceptance'}
        gate.validate_environment(other, POLICIES, 'release-acceptance')

    def test_environment_missing_fields_and_unsafe_rules_rejected(self):
        cases = [None, {}, {**ENVIRONMENT, 'name': 'wrong'}, {**ENVIRONMENT, 'id': None}]
        for key in ENVIRONMENT:
            bad = copy.deepcopy(ENVIRONMENT)
            del bad[key]
            cases.append(bad)
        for field, value in (('prevent_self_review', True), ('reviewers', []),
                             ('reviewers', [{'type': 'User', 'reviewer': {}}])):
            bad = copy.deepcopy(ENVIRONMENT)
            bad['protection_rules'][0][field] = value
            cases.append(bad)
        for value in (None, {'protected_branches': True, 'custom_branch_policies': False},
                      {'protected_branches': False, 'custom_branch_policies': False}):
            cases.append({**ENVIRONMENT, 'deployment_branch_policy': value})
        for bad in cases:
            with self.subTest(environment=bad), self.assertRaises(ValueError):
                gate.validate_environment(bad, POLICIES, 'release')
        for policies in ([], [{}], [{'total_count': 0, 'branch_policies': []}],
                         [{'total_count': 1, 'branch_policies': [{'id': 3, 'name': '*', 'type': 'tag'}]}],
                         [{'total_count': 1, 'branch_policies': [{'id': 3, 'name': 'v0.2.0', 'type': 'branch'}]}],
                         POLICIES + POLICIES):
            with self.subTest(policies=policies), self.assertRaises(ValueError):
                gate.validate_environment(ENVIRONMENT, policies, 'release')

    def test_main_missing_active_review_or_required_checks_rejected(self):
        for branch in ({}, {**BRANCH, 'protected': False}, {**BRANCH, 'commit': {}}):
            with self.assertRaises(ValueError):
                gate.validate_main(branch, RULES)
        cases = [[], [[]], [[RULES[0][0]]], [[RULES[0][1]]]]
        wrong_app = copy.deepcopy(RULES)
        for status in wrong_app[0][1]['parameters']['required_status_checks']:
            status['integration_id'] = 1
        cases.append(wrong_app)
        for kind, key, value in ((0, 'required_approving_review_count', 1),
                                  (0, 'required_approving_review_count', True),
                                  (0, 'dismiss_stale_reviews_on_push', False),
                                  (0, 'require_last_push_approval', True),
                                  (0, 'required_review_thread_resolution', False),
                                  (1, 'strict_required_status_checks_policy', False),
                                  (1, 'required_status_checks', []),
                                  (1, 'required_status_checks', [{'context': 'full-linux', 'integration_id': None}])):
            bad = copy.deepcopy(RULES)
            bad[0][kind]['parameters'][key] = value
            cases.append(bad)
        for bad in cases:
            with self.subTest(rules=bad), self.assertRaises(ValueError):
                gate.validate_main(BRANCH, bad)

    def test_tag_preservation_rules_fail_closed(self):
        request = gate.ReleaseRequest('v0.2.0', SOURCE)
        gate.validate_tag_rules(TAG_RULES, request)
        for field, value in (('target', 'branch'), ('enforcement', 'evaluate'),
                             ('source', 'other/repo'), ('source_type', 'Organization'),
                             ('bypass_actors', [{'actor_type': 'User', 'actor_id': 82675328}]),
                             ('rules', [{'type': 'update'}]), ('rules', [{'type': 'deletion'}]),
                             ('conditions', {'ref_name': {'include': ['refs/tags/other'], 'exclude': []}}),
                             ('conditions', {'ref_name': {'include': ['refs/tags/v*'], 'exclude': ['refs/tags/v0.2.0']}})):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                gate.validate_tag_rules({**TAG_RULES, field: value}, request)

    def test_exact_source_ci_requires_actual_successful_workflow_jobs_and_checks(self):
        request = gate.ReleaseRequest('v0.2.0', SOURCE)
        fixture = policy_fixtures()
        with patch.object(gate, 'api', side_effect=lambda endpoint, *args: fixture[endpoint]):
            self.assertEqual(gate.check_source_ci(request), 30)
        changes = []
        for field, value in (('path', '.github/workflows/other.yml'), ('workflow_id', 99),
                             ('head_sha', 'c' * 40), ('event', 'pull_request'),
                             ('status', 'in_progress'), ('conclusion', 'failure'),
                             ('run_attempt', True), ('check_suite_id', None),
                             ('head_repository', {'id': 99, 'full_name': 'ddv1982/tailmux'})):
            changes.append(('run', field, value))
        for field, value in (('name', 'missing-linux'), ('status', 'queued'), ('conclusion', 'skipped'),
                             ('head_sha', 'c' * 40), ('run_id', 31), ('run_attempt', 2),
                             ('check_run_url', 'https://evil.invalid/check-runs/50')):
            changes.append(('job', field, value))
        for field, value in (('head_sha', 'c' * 40), ('status', 'queued'), ('conclusion', 'neutral'),
                             ('app', {'id': 1}), ('check_suite', {'id': 99}), ('name', 'wrong')):
            changes.append(('check', field, value))
        for kind, field, value in changes:
            fixture = copy.deepcopy(policy_fixtures())
            target = (fixture[f'actions/workflows/ci.yml/runs?head_sha={SOURCE}&event=push&per_page=100'][0]['workflow_runs'][0]
                      if kind == 'run' else fixture['actions/runs/30/attempts/1/jobs?per_page=100'][0]['jobs'][0]
                      if kind == 'job' else fixture['check-runs/50'])
            target[field] = value
            with self.subTest(kind=kind, field=field), patch.object(gate, 'api', side_effect=lambda endpoint, *args: fixture[endpoint]), self.assertRaises(ValueError):
                gate.check_source_ci(request)
        for jobs in ([], JOBS[:-1], JOBS + [JOBS[0]]):
            fixture = {**policy_fixtures(), 'actions/runs/30/attempts/1/jobs?per_page=100': [{'jobs': jobs}]}
            with patch.object(gate, 'api', side_effect=lambda endpoint, *args: fixture[endpoint]), self.assertRaises(ValueError):
                gate.check_source_ci(request)
        fixture = policy_fixtures()
        fixture[f'actions/workflows/ci.yml/runs?head_sha={SOURCE}&event=push&per_page=100'] = [
            {'workflow_runs': [CI_RUN, {**CI_RUN, 'id': 31, 'conclusion': 'failure'}]}]
        with patch.object(gate, 'api', side_effect=lambda endpoint, *args: fixture[endpoint]), self.assertRaises(ValueError):
            gate.check_source_ci(request)

    def test_live_only_waiver_is_exact_and_selector_does_not_weaken_evidence_validator(self):
        request = gate.ReleaseRequest('v0.2.0', SOURCE)
        waiver = {'schema': 'tailmux-live-only-waiver-v1', 'repository': 'ddv1982/tailmux',
                  'tag': 'v0.2.0', 'source_sha': SOURCE, 'scope': 'live-acceptance-only',
                  'live_acceptance': 'NOT_VERIFIED', 'operator_id': 82675328,
                  'reason': 'User explicitly requested stable 0.2.0 without waiting for the live test.'}
        raw = json.dumps(waiver)
        digest = hashlib.sha256(raw.encode()).hexdigest()
        self.assertEqual(gate.live_waiver(raw, request), digest)
        invalid = ['{', 'null', '[]', raw[:-1] + ',"tag":"v0.2.0"}', raw + ' ' * 4096]
        for key in waiver:
            bad = {**waiver}
            del bad[key]
            invalid.append(json.dumps(bad))
            invalid.append(json.dumps({**waiver, key: None}))
            invalid.append(json.dumps({**waiver, key: 'wrong'}))
        invalid += [json.dumps({**waiver, 'extra': True}), json.dumps({**waiver, 'operator_id': 82675328.0})]
        for candidate in invalid:
            with self.subTest(raw=candidate[:100]), self.assertRaises(ValueError):
                gate.live_waiver(candidate, request)
        for other in (gate.ReleaseRequest('v1.2.3', SOURCE), gate.ReleaseRequest('v0.2.0', 'c' * 40)):
            with self.assertRaises(ValueError):
                gate.live_waiver(raw, other)
        command = [sys.executable, str(ROOT / 'scripts/release/acceptance.py'), '--tag', request.tag,
                   '--source-sha', SOURCE, '--waiver-sha256', digest]
        result = subprocess.run(command, env={'RELEASE_LIVE_ONLY_WAIVER': raw}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('NOT_VERIFIED', result.stdout)
        result = subprocess.run(command, env={'RELEASE_LIVE_ONLY_WAIVER': raw + ' '}, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        no_waiver = command[:-1] + [hashlib.sha256(b'').hexdigest()]
        result = subprocess.run(no_waiver, env={}, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Acceptance release gate rejected. NOT VERIFIED.', result.stderr)
        result = subprocess.run(command, env={'RELEASE_LIVE_ONLY_WAIVER': raw.replace(SOURCE, 'c' * 40)}, capture_output=True)
        self.assertNotEqual(result.returncode, 0)

    def test_each_execution_identity_is_mandatory(self):
        request = gate.ReleaseRequest('v1.2.3', SOURCE)
        with patch.dict(os.environ, IDENTITY, clear=True), patch.object(gate, 'git', return_value=(SOURCE + '\n').encode()):
            gate.identity(request, ROOT)
            for key in IDENTITY:
                with self.subTest(key=key), patch.dict(os.environ, {key: 'wrong'}), self.assertRaises(ValueError):
                    gate.identity(request, ROOT)
        for values in ((b'b' * 40, b'a' * 40), (b'a' * 40, b'b' * 40)):
            with patch.dict(os.environ, IDENTITY, clear=True), patch.object(gate, 'git', side_effect=values), self.assertRaises(ValueError):
                gate.identity(request, ROOT)

    def test_api_failures_are_not_treated_as_empty_success(self):
        with patch.object(gate, 'run', side_effect=subprocess.CalledProcessError(1, ['gh', 'api'])):
            with self.assertRaises(subprocess.CalledProcessError):
                gate.api('environments/release')
        for raw in (b'{', b'{"id":1,"id":2}'):
            with patch.object(gate, 'run', return_value=raw), self.assertRaises(ValueError):
                gate.api('environments/release')

    def test_cli_fake_api_receipt_and_failure_do_not_write_success(self):
        with tempfile.TemporaryDirectory() as private:
            directory = Path(private)
            fixture = {
                'environments/release': ENVIRONMENT,
                'environments/release/deployment-branch-policies?per_page=100': POLICIES,
                'branches/main': BRANCH, 'rules/branches/main?per_page=100': RULES,
                **policy_fixtures(),
            }
            (directory / 'responses.json').write_text(json.dumps(fixture))
            (directory / 'gh').write_text('#!/usr/bin/env python3\nimport json, os, sys\n'
                "sys.exit(9) if os.environ.get('FAIL_API') else None\n"
                "endpoint=next(x for x in sys.argv if x.startswith('repos/')).split('/',3)[3]\n"
                "print(json.dumps(json.load(open(os.environ['FIXTURES']))[endpoint]))\n")
            (directory / 'git').write_text('#!/usr/bin/env python3\nimport os, sys\n'
                "sys.exit(int(os.environ.get('NOT_ANCESTOR', '0'))) if 'merge-base' in sys.argv else print('a'*40)\n")
            for name in ('gh', 'git'):
                (directory / name).chmod(0o700)
            env = {**os.environ, **IDENTITY, 'PATH': f'{directory}:{os.environ["PATH"]}',
                   'FIXTURES': str(directory / 'responses.json'), 'GITHUB_OUTPUT': str(directory / 'output')}
            command = [sys.executable, str(ROOT / 'scripts/release/preflight.py'), '--tag', 'v1.2.3',
                       '--source-sha', SOURCE, '--main-sha', MAIN]
            result = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((directory / 'output').read_text(), f'main_sha={MAIN}\nsource_sha={SOURCE}\ntag=v1.2.3\nwaiver_sha256={hashlib.sha256(b"").hexdigest()}\n')
            for extra in ({'FAIL_API': '1'}, {'NOT_ANCESTOR': '1'}, {'GITHUB_WORKFLOW_SHA': 'c' * 40}, {'RELEASE_LIVE_ONLY_WAIVER': '{}'}):
                (directory / 'output').unlink(missing_ok=True)
                result = subprocess.run(command, env={**env, **extra}, capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((directory / 'output').exists())
            (directory / 'output').unlink(missing_ok=True)
            result = subprocess.run(command[:-1] + ['c' * 40], env=env, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((directory / 'output').exists())
            result = subprocess.run(command + ['--waiver-sha256', 'f' * 64], env=env, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((directory / 'output').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
