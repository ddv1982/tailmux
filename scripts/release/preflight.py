#!/usr/bin/env python3
"""Read-only publisher checks. Missing repository protection evidence rejects release."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from package import REPOSITORY, SHA, ReleaseRequest, git, run, strict_object

GITHUB_ACTIONS_APP_ID = 15368
REQUIRED_CHECKS = {"full-linux", "full-macos", "workflow-policy"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def api(endpoint, pages=False):
    args = ["gh", "api", "--hostname", "github.com", "--method", "GET",
            "-H", "Accept: application/vnd.github+json",
            "-H", "X-GitHub-Api-Version: 2022-11-28", f"repos/{REPOSITORY}/{endpoint}"]
    if pages:
        args += ["--paginate", "--slurp"]
    data = run(args)
    require(len(data) <= 1024 * 1024, "Protection API response exceeds limit")
    return json.loads(data, object_pairs_hook=strict_object)


def validate_environment(environment, policy_pages, name):
    require(type(environment) is dict and environment.get("name") == name
            and type(environment.get("id")) is int and environment["id"] > 0,
            "Required release environment does not exist")
    require(environment.get("deployment_branch_policy") == {
        "protected_branches": False, "custom_branch_policies": True},
        "Environment must restrict deployments to explicit version tags")
    rules = environment.get("protection_rules")
    require(type(rules) is list and all(type(rule) is dict for rule in rules),
            "Environment protection rules missing")
    review = [rule for rule in rules if rule.get("type") == "required_reviewers"]
    require(len(review) == 1 and review[0].get("prevent_self_review") is True,
            "Environment requires reviewers and prevent-self-review")
    reviewers = review[0].get("reviewers")
    require(type(reviewers) is list and len(reviewers) > 0, "Approved reviewers missing")
    for reviewer in reviewers:
        require(type(reviewer) is dict and reviewer.get("type") in ("User", "Team")
                and type(reviewer.get("reviewer")) is dict
                and type(reviewer["reviewer"].get("id")) is int and reviewer["reviewer"]["id"] > 0,
                "Invalid reviewer identity")
    require(type(policy_pages) is list and len(policy_pages) > 0, "Deployment policy pages missing")
    policies = []
    for page in policy_pages:
        require(type(page) is dict and type(page.get("branch_policies")) is list
                and type(page.get("total_count")) is int and page["total_count"] == 1, "Exactly one deployment restriction required")
        policies.extend(page["branch_policies"])
    require(len(policies) == 1 and type(policies[0]) is dict
            and policies[0].get("name") == "v*" and policies[0].get("type") == "tag"
            and type(policies[0].get("id")) is int and policies[0]["id"] > 0,
            "Only the v* tag deployment restriction is accepted")


def validate_main(branch, rule_pages):
    require(type(branch) is dict and branch.get("name") == "main" and branch.get("protected") is True,
            "main must be protected")
    commit = branch.get("commit")
    require(type(commit) is dict and type(commit.get("sha")) is str and SHA.fullmatch(commit["sha"]),
            "main commit identity missing")
    require(type(rule_pages) is list and len(rule_pages) > 0
            and all(type(page) is list for page in rule_pages), "Active main rules missing")
    rules = [rule for page in rule_pages for rule in page]
    require(all(type(rule) is dict for rule in rules), "Invalid active main rule")
    reviews = [r.get("parameters") for r in rules if r.get("type") == "pull_request"]
    require(any(type(p) is dict and type(p.get("required_approving_review_count")) is int
                and p["required_approving_review_count"] >= 1
                and p.get("dismiss_stale_reviews_on_push") is True
                and p.get("require_last_push_approval") is True for p in reviews),
            "Active main rules must require fresh independent PR approval")
    checks = [r.get("parameters") for r in rules if r.get("type") == "required_status_checks"]
    accepted = False
    for parameters in checks:
        if type(parameters) is not dict or parameters.get("strict_required_status_checks_policy") is not True:
            continue
        statuses = parameters.get("required_status_checks")
        if type(statuses) is not list:
            continue
        contexts = {s.get("context") for s in statuses if type(s) is dict
                    and type(s.get("context")) is str and type(s.get("integration_id")) is int
                    and s["integration_id"] == GITHUB_ACTIONS_APP_ID}
        if REQUIRED_CHECKS <= contexts:
            accepted = True
    require(accepted, "Active main rules must require current Linux, macOS, and workflow policy checks")
    return commit["sha"]


def identity(request, root):
    expected = {
        "GITHUB_REPOSITORY": REPOSITORY, "GITHUB_EVENT_NAME": "push", "GITHUB_REF_TYPE": "tag",
        "GITHUB_REF": f"refs/tags/{request.tag}", "GITHUB_REF_NAME": request.tag,
        "GITHUB_SHA": request.source_sha, "GITHUB_WORKFLOW_SHA": request.source_sha,
        "GITHUB_WORKFLOW_REF": f"{REPOSITORY}/.github/workflows/release.yml@refs/tags/{request.tag}",
        "RUNNER_ENVIRONMENT": "github-hosted",
    }
    for key, value in expected.items():
        require(os.environ.get(key) == value, f"Unexpected publisher identity: {key}")
    require(git(root, "rev-parse", "HEAD").decode().strip() == request.source_sha,
            "Checkout does not match independently expected source")
    require(git(root, "rev-parse", f"refs/tags/{request.tag}^{{commit}}").decode().strip() == request.source_sha,
            "Peeled tag does not match independently expected source")


def preflight(request, root, environment, expected_main=None):
    identity(request, root)
    validate_environment(api(f"environments/{environment}"),
                         api(f"environments/{environment}/deployment-branch-policies?per_page=100", True),
                         environment)
    main_sha = validate_main(api("branches/main"), api("rules/branches/main?per_page=100", True))
    if expected_main is not None:
        require(main_sha == expected_main, "Reviewed main changed since preflight")
    git(root, "merge-base", "--is-ancestor", request.source_sha, main_sha)
    return main_sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--environment", default="release")
    parser.add_argument("--main-sha")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    try:
        require(re.fullmatch(r"[A-Za-z0-9_-]+", args.environment), "Invalid environment name")
        require(args.main_sha is None or SHA.fullmatch(args.main_sha), "Invalid captured main SHA")
        request = ReleaseRequest(args.tag, args.source_sha)
        main_sha = preflight(request, args.root, args.environment, args.main_sha)
        output = f"main_sha={main_sha}\nsource_sha={request.source_sha}\ntag={request.tag}\n"
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
                stream.write(output)
        print(output, end="")
    except (ValueError, TypeError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Release preflight rejected: {error}\n")


if __name__ == "__main__":
    main()
