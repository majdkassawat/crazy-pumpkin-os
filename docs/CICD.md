# CI/CD Pipeline

## 1. Overview

Crazy Pumpkin OS uses two GitHub Actions workflows:

### CI (`ci.yml`)

- **Triggers:** Every push to `main` and every pull request.
- **What it does:** Installs the package with dev dependencies, runs the full test suite with `pytest`, and lints with `ruff`.
- **Matrix:** Tests against Python 3.11 and 3.12 in parallel (`fail-fast: false`).

### Publish (`publish.yml`)

- **Triggers:** Pushing a tag that matches `v*` (e.g. `v0.2.0`).
- **What it does:**
  1. **Build** — checks out the code, installs `build`, runs `python -m build`, and uploads the dist artifacts.
  2. **Verify** — downloads the built wheel, installs it, and runs a smoke-test import (`import crazypumpkin`).
  3. **Publish** — downloads the artifacts and publishes to PyPI using OIDC trusted publishing (`pypa/gh-action-pypi-publish`).
- **Permissions:** The `publish` job runs in the `pypi` environment and requires `id-token: write` for OIDC.

## 2. Running Checks Locally

Run the same checks that CI runs:

```bash
bash scripts/ci_check.sh
```

This executes `pytest tests/ -v --tb=short`. Make sure you have dev dependencies installed first:

```bash
pip install -e '.[dev]'
```

To lint locally (matching CI):

```bash
ruff check src/ tests/
```

## 3. Building Locally

Build the sdist and wheel without publishing:

```bash
bash scripts/build_dist.sh
```

This removes any previous `dist/` directory, runs `python -m build`, and lists the resulting artifacts. You need the `build` package installed:

```bash
pip install build
```

After building, you can install the wheel locally to verify:

```bash
pip install dist/*.whl
python -c "import crazypumpkin; print(crazypumpkin.__name__)"
```

## 4. Cutting a Release

Follow these steps to tag and publish a new version:

### Step 1 — Choose a version

Pick the next semver version (e.g. `0.2.0`). The release script enforces the `X.Y.Z` format.

### Step 2 — Run the release script

```bash
bash scripts/release.sh 0.2.0
```

This will:
1. Update `__version__` in `src/crazypumpkin/__init__.py` to `0.2.0`.
2. Stage all changes and create a commit: `Release v0.2.0`.
3. Create a git tag `v0.2.0`.

### Step 3 — Push the commit and tag

```bash
git push origin main --tags
```

Pushing the `v0.2.0` tag triggers the `publish.yml` workflow, which builds, verifies, and publishes to PyPI automatically.

### Full one-liner

```bash
bash scripts/release.sh 0.2.0 && git push origin main --tags
```

## 5. PyPI Trusted Publishing Setup

The publish workflow uses OIDC trusted publishing — no PyPI API tokens are stored in GitHub secrets. To configure it:

1. Go to your project on [pypi.org](https://pypi.org) (or create it on first publish).
2. Navigate to **Manage** → **Publishing** → **Add a new publisher**.
3. Select **GitHub Actions** and fill in:
   - **Owner:** `majdkassawat`
   - **Repository:** `crazy-pumpkin-os`
   - **Workflow name:** `publish.yml`
   - **Environment name:** `pypi`
4. Click **Add**.
5. In your GitHub repository, go to **Settings** → **Environments** and create an environment called `pypi`. Optionally add protection rules (e.g. required reviewers) to gate deployments.

Once configured, any run of `publish.yml` in the `pypi` environment can mint a short-lived OIDC token and upload to PyPI without stored credentials.

## 6. Troubleshooting

### Tests fail in CI but pass locally

- Check the Python version. CI tests on 3.11 and 3.12 — make sure you are running the same version locally.
- CI installs with `pip install -e '.[dev]'`. If you installed extra optional groups locally (e.g. `[all]`), tests may pass locally due to optional dependencies being present.

### `ruff check` fails

- Run `ruff check src/ tests/` locally to see the exact violations.
- Auto-fix what you can with `ruff check --fix src/ tests/`.

### Publish job fails with "trusted publisher not configured"

- Verify the OIDC publisher is set up on PyPI (see Section 5 above).
- The workflow file must be named exactly `publish.yml` and the environment must be `pypi` — these must match what you registered on PyPI.

### Publish job fails with "artifact not found"

- The `build` job must complete successfully before `verify` and `publish` run. Check the `build` job logs for errors.
- Ensure `python -m build` produces files in `dist/`.

### Release script rejects the version

- The version must be valid semver: three dot-separated integers (e.g. `1.2.3`). Pre-release suffixes like `1.2.3-rc1` are not supported by the script.

### Tag already exists

- If `git tag "vX.Y.Z"` fails because the tag exists, you already released that version. Bump to the next version instead.
