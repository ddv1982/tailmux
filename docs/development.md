# Development

Install jq and ShellCheck through their package owners. Prepare a development environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-dev.txt
. .venv/bin/activate
bash scripts/tests/run.sh lint
bash scripts/tests/run.sh quick
bash scripts/tests/run.sh full
```

Tests require Python 3.11 through 3.14 and the hashed development requirements.
Runtime requires no Python. The full command runs every offline suite, including workflow and acceptance policy checks.
Tests use disposable homes and controlled transport fixtures. Their success does not establish live SSH compatibility.
Use `actionlint -oneline .github/workflows/*.yml` for workflow syntax.
See [acceptance](acceptance.md) for isolated live testing and [release preparation](releases.md) for publication.
