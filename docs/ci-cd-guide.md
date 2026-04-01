# CI/CD Pipeline Guide

## Overview

Crazy Pumpkin OS uses GitHub Actions for continuous integration and delivery:

- **CI (Continuous Integration):** On every push to `main` and on every pull request targeting `main`, the test suite runs against Python 3.11 and 3.12. The workflow installs the package in editable mode with dev dependencies, runs `pytest`, and verifies the package compiles cleanly.
- **Publish (Continuous Delivery):** When a GitHub Release is published, the pipeline builds the `crazypumpkin` package and publishes it to PyPI using trusted publisher (OIDC) authentication — no API tokens required.

### Workflow files

| File | Trigger | Purpose |
|------|---------|---------|
| `.github/workflows/ci.yml` | Push to `main`, PRs to `main` | Lint-free compile check and full test suite |
| `.github/workflows/publish.yml` | GitHub Release published | Build sdist/wheel and publish to PyPI |

## Setup

### Prerequisites

- A GitHub repository (e.g., `majdkassawat/crazy-pumpkin-os`)
- A PyPI account at [pypi.org](https://pypi.org)
- The `crazypumpkin` project registered on PyPI (created on first publish or manually)

### Configure PyPI Trusted Publisher (OIDC)

PyPI trusted publishing lets GitHub Actions publish packages without storing API tokens as secrets. It uses OpenID Connect (OIDC) to verify that the publish request comes from your specific GitHub repository and workflow.

**Step-by-step:**

1. **Log in to PyPI** at [https://pypi.org/manage/account/](https://pypi.org/manage/account/).

2. **Navigate to your project's settings.** Go to [https://pypi.org/manage/project/crazypumpkin/settings/](https://pypi.org/manage/project/crazypumpkin/settings/).

3. **Open the "Publishing" tab.** Click on "Publishing" in the left sidebar.

4. **Add a new trusted publisher.** Fill in the form:
   - **Owner:** `majdkassawat`
   - **Repository name:** `crazy-pumpkin-os`
   - **Workflow name:** `publish.yml`
   - **Environment:** *(leave blank unless you use GitHub Environments)*

5. **Click "Add."** PyPI will now trust OIDC tokens from this specific workflow.

6. **Verify the GitHub workflow.** Ensure `.github/workflows/publish.yml` includes the `id-token: write` permission:

   ```yaml
   permissions:
     id-token: write
   ```

   This permission allows the workflow to request an OIDC token from GitHub, which PyPI validates.

### For a brand-new package

If the package does not exist on PyPI yet, you can configure a "pending" trusted publisher:

1. Go to [https://pypi.org/manage/account/publishing/](https://pypi.org/manage/account/publishing/).
2. Under "Add a new pending publisher", fill in:
   - **PyPI project name:** `crazypumpkin`
   - **Owner:** `majdkassawat`
   - **Repository name:** `crazy-pumpkin-os`
   - **Workflow name:** `publish.yml`
   - **Environment:** *(leave blank)*
3. Click "Add." The first publish from the workflow will create the project automatically.

## Usage

### Triggering CI

CI runs automatically on:

- Every push to the `main` branch
- Every pull request targeting `main`

No manual steps required. Check the **Actions** tab in GitHub to see results.

### Triggering a Release

To publish a new version to PyPI:

1. **Update the version** in `pyproject.toml`:

   ```toml
   version = "0.2.0"
   ```

2. **Commit and push** the version bump:

   ```bash
   git add pyproject.toml
   git commit -m "Bump version to 0.2.0"
   git push origin main
   ```

3. **Create and push a git tag:**

   ```bash
   git tag v0.2.0
   git push --tags
   ```

4. **Create a GitHub Release:**
   - Go to [https://github.com/majdkassawat/crazy-pumpkin-os/releases/new](https://github.com/majdkassawat/crazy-pumpkin-os/releases/new)
   - Select the tag `v0.2.0`
   - Set the release title (e.g., `v0.2.0`)
   - Add release notes describing the changes
   - Click **"Publish release"**

5. The `publish.yml` workflow triggers automatically, builds the package, and uploads it to PyPI.

6. **Verify** the package at [https://pypi.org/project/crazypumpkin/](https://pypi.org/project/crazypumpkin/).

## Tutorial

This tutorial walks through a complete cycle: making a code change, seeing CI pass, and publishing a release.

### Step 1: Create a feature branch

```bash
git checkout -b feature/my-improvement
```

### Step 2: Make your code change

Edit the relevant source files under `src/crazypumpkin/`. For example, add a utility function:

```python
# src/crazypumpkin/utils.py
def greet(name: str) -> str:
    return f"Hello, {name}!"
```

### Step 3: Add or update tests

Create or update a test file in `tests/`:

```python
# tests/test_utils.py
from crazypumpkin.utils import greet

def test_greet():
    assert greet("World") == "Hello, World!"
```

### Step 4: Run tests locally

```bash
pip install -e '.[dev]'
python -m pytest tests/ -v --tb=short
```

Ensure all tests pass before pushing.

### Step 5: Push and open a pull request

```bash
git add .
git commit -m "Add greet utility function"
git push origin feature/my-improvement
```

Open a pull request on GitHub targeting `main`. CI will run automatically.

### Step 6: Monitor CI

Go to the **Actions** tab on GitHub or check the PR status checks. The CI workflow will:

1. Check out the code
2. Set up Python 3.11 and 3.12
3. Install dependencies with `pip install -e '.[dev]'`
4. Run `python -m pytest tests/ -v --tb=short`
5. Verify the package compiles with `python -m py_compile src/crazypumpkin/__init__.py`

Wait for all checks to pass (green checkmark).

### Step 7: Merge the pull request

Once CI passes and the PR is approved, merge it into `main`.

### Step 8: Prepare the release

Update the version in `pyproject.toml`:

```toml
version = "0.2.0"
```

Commit and push:

```bash
git checkout main
git pull origin main
git add pyproject.toml
git commit -m "Bump version to 0.2.0"
git push origin main
```

### Step 9: Tag and release

```bash
git tag v0.2.0
git push --tags
```

Then create a GitHub Release:

1. Go to **Releases** → **Draft a new release**
2. Choose tag `v0.2.0`
3. Title: `v0.2.0`
4. Describe the changes (you can use "Generate release notes" for auto-generated notes)
5. Click **"Publish release"**

### Step 10: Verify the publish

1. Check the **Actions** tab — the `Publish to PyPI` workflow should complete successfully.
2. Visit [https://pypi.org/project/crazypumpkin/0.2.0/](https://pypi.org/project/crazypumpkin/0.2.0/) to confirm the release is live.
3. Test the install:

   ```bash
   pip install crazypumpkin==0.2.0
   ```

## Troubleshooting

### OIDC Authentication Failure

**Symptom:** The publish workflow fails with `Error: OpenID Connect token retrieval failed` or `403 Forbidden` from PyPI.

**Causes and fixes:**

- **Missing `id-token: write` permission.** Ensure the publish job has:
  ```yaml
  permissions:
    id-token: write
  ```
- **Trusted publisher not configured on PyPI.** Follow the [Setup](#configure-pypi-trusted-publisher-oidc) section to add the trusted publisher.
- **Workflow name mismatch.** The workflow filename in the trusted publisher config on PyPI must match exactly (e.g., `publish.yml`, not `publish.yaml` or `Publish.yml`).
- **Repository owner/name mismatch.** Double-check the owner and repository name in the trusted publisher config.
- **Environment mismatch.** If you specified a GitHub Environment in the trusted publisher config, the workflow job must also reference that environment.

### Build Errors

**Symptom:** `python -m build` fails during the publish workflow.

**Causes and fixes:**

- **Missing `build` dependency.** The workflow installs it with `pip install build`. If this step fails, check network connectivity or pip version.
- **Invalid `pyproject.toml`.** Validate your `pyproject.toml` locally:
  ```bash
  pip install build
  python -m build
  ```
  Common issues: missing required fields, syntax errors, invalid version strings.
- **Version already exists on PyPI.** PyPI rejects uploads with a version that already exists. Bump the version in `pyproject.toml` before releasing.

### Test Failures in CI

**Symptom:** Tests pass locally but fail in CI.

**Causes and fixes:**

- **Python version differences.** CI tests against Python 3.11 and 3.12. Ensure your code is compatible with both. Check for version-specific syntax or stdlib changes.
- **Missing dependencies.** If you added a new dependency, add it to the `dependencies` list in `pyproject.toml`.
- **Environment differences.** CI runs on `ubuntu-latest`. Path separators, temp directories, and locale may differ from your local OS. Use `pathlib.Path` instead of hardcoded paths.
- **Flaky tests.** If tests depend on timing, network, or ordering, they may fail intermittently. Use mocks and deterministic test data.
- **Import errors.** Ensure all modules are properly exported in `__init__.py` files. The CI installs the package in editable mode (`pip install -e '.[dev]'`), which relies on correct package structure.

### Common Quick Fixes

| Issue | Fix |
|-------|-----|
| `ModuleNotFoundError` in CI | Add missing package to `dependencies` in `pyproject.toml` |
| Version conflict on PyPI | Bump version number — PyPI does not allow re-uploads |
| CI times out | Check for infinite loops or long-running tests; add `timeout` to pytest |
| Publish skipped | Ensure you created a GitHub **Release** (not just a tag) |
