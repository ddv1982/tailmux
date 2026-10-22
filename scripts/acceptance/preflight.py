#!/usr/bin/env python3
"""Read-only acceptance dispatch checks, separate from publisher tag policy."""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

from verify import require, sha

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = 'ddv1982/tailmux'


def release_helpers():
    directory = ROOT / 'scripts/release'
    sys.path.insert(0, str(directory))
    spec = importlib.util.spec_from_file_location('tailmux_release_preflight', directory / 'preflight.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_environment(environment, pages):
    require(type(environment) is dict and environment.get('name') == 'acceptance' and
            type(environment.get('id')) is int and environment['id'] > 0, 'acceptance environment missing')
    require(environment.get('deployment_branch_policy') == {
        'protected_branches': False, 'custom_branch_policies': True}, 'explicit main-only policy required')
    rules = environment.get('protection_rules')
    require(type(rules) is list and all(type(rule) is dict for rule in rules), 'protection rules missing')
    reviews = [rule for rule in rules if rule.get('type') == 'required_reviewers']
    require(len(reviews) == 1 and reviews[0].get('prevent_self_review') is True, 'independent approval required')
    reviewers = reviews[0].get('reviewers')
    require(type(reviewers) is list and len(reviewers) > 0, 'reviewers missing')
    for reviewer in reviewers:
        require(type(reviewer) is dict and reviewer.get('type') in ('User', 'Team') and
                type(reviewer.get('reviewer')) is dict and
                type(reviewer['reviewer'].get('id')) is int and reviewer['reviewer']['id'] > 0,
                'reviewer identity missing')
    require(type(pages) is list and len(pages) > 0, 'deployment policies missing')
    policies = []
    for page in pages:
        require(type(page) is dict and type(page.get('total_count')) is int and page['total_count'] == 1 and
                type(page.get('branch_policies')) is list, 'one deployment policy required')
        policies.extend(page['branch_policies'])
    require(len(policies) == 1 and type(policies[0]) is dict and
            policies[0].get('name') == 'main' and policies[0].get('type') == 'branch' and
            type(policies[0].get('id')) is int and policies[0]['id'] > 0, 'only main branch is accepted')


def preflight(expected_sha):
    sha(expected_sha)
    expected = {'GITHUB_REPOSITORY': REPOSITORY, 'GITHUB_EVENT_NAME': 'workflow_dispatch',
                'GITHUB_REF': 'refs/heads/main', 'GITHUB_REF_TYPE': 'branch', 'GITHUB_REF_NAME': 'main',
                'GITHUB_SHA': expected_sha, 'GITHUB_WORKFLOW_SHA': expected_sha,
                'GITHUB_WORKFLOW_REF': REPOSITORY + '/.github/workflows/acceptance.yml@refs/heads/main',
                'RUNNER_ENVIRONMENT': 'github-hosted'}
    for key, value in expected.items():
        require(os.environ.get(key) == value, 'acceptance dispatch identity mismatch')
    helpers = release_helpers()
    require(helpers.git(ROOT, 'rev-parse', 'HEAD').decode().strip() == expected_sha, 'checkout SHA mismatch')
    main_sha = helpers.validate_main(helpers.api('branches/main'), helpers.api('rules/branches/main?per_page=100', True))
    require(main_sha == expected_sha, 'dispatch must use the currently reviewed main head')
    validate_environment(helpers.api('environments/acceptance'),
                         helpers.api('environments/acceptance/deployment-branch-policies?per_page=100', True))
    return {'preflight': 'PASS', 'source_sha': main_sha, 'verdict': 'NOT_VERIFIED'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-sha', required=True)
    args = parser.parse_args()
    try:
        import json
        print(json.dumps(preflight(args.expected_sha), sort_keys=True))
        return 0
    except (ValueError, TypeError, OSError, ImportError, AttributeError, subprocess.SubprocessError):
        print('Acceptance preflight rejected. NOT VERIFIED.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
