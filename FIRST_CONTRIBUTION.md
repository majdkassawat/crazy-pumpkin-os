# Your First Contribution

Welcome! This guide walks you through making your first pull request to Crazy Pumpkin OS. No prior open-source experience required.

---

## Find Something to Work On

Browse issues labeled **good-first-issue** — these are small, well-scoped tasks chosen specifically for new contributors:

> [**good-first-issue** issues](https://github.com/majdkassawat/crazy-pumpkin-os/issues?q=is%3Aissue+is%3Aopen+label%3Agood-first-issue)

Pick one that interests you and leave a comment saying you'd like to work on it.

---

## Step-by-Step PR Walkthrough

### 1. Fork the Repository

Go to [github.com/majdkassawat/crazy-pumpkin-os](https://github.com/majdkassawat/crazy-pumpkin-os) and click the **Fork** button in the top-right corner. This creates your own copy of the repository under your GitHub account.

### 2. Clone Your Fork

```bash
git clone https://github.com/<your-username>/crazy-pumpkin-os.git
cd crazy-pumpkin-os
```

Replace `<your-username>` with your GitHub username.

### 3. Create a Branch

Create a descriptive branch for your change:

```bash
git checkout -b fix-typo-in-readme
```

Use a short name that describes what you're doing (e.g., `add-config-tests`, `fix-cli-help-text`).

### 4. Make Your Changes

Edit the relevant files. Keep your changes focused on the issue you picked — small, targeted changes are easier to review and merge.

If you need to set up the development environment first:

```bash
pip install -e ".[dev]"
```

### 5. Run the Tests

Make sure all tests pass before pushing:

```bash
pytest tests/ -v
```

If you added new functionality, add tests for it too. If you're fixing a bug, add a test that reproduces the bug and verifies your fix.

### 6. Commit and Push

Stage your changes, write a clear commit message, and push to your fork:

```bash
git add <files-you-changed>
git commit -m "Fix typo in README quick start section"
git push origin fix-typo-in-readme
```

Write commit messages that explain **what** changed and **why**. Keep the first line under 72 characters.

### 7. Open a Pull Request

Go to your fork on GitHub. You should see a banner offering to create a pull request. Click **Compare & pull request**, then:

- Write a clear title describing your change
- In the description, reference the issue you're fixing (e.g., `Fixes #12`)
- Describe what you changed and why
- Mention any testing you did

Submit the PR and wait for a maintainer review.

---

## What Happens Next

- A maintainer will review your PR, usually within a few days
- You may receive feedback or change requests — this is normal and part of the process
- Once approved, your PR will be merged into `main`

---

## Tips for a Smooth First PR

- **Start small.** Documentation fixes, typo corrections, and test additions are great first contributions.
- **Ask questions.** If the issue description is unclear, ask in the issue comments before starting.
- **One change per PR.** Don't bundle unrelated changes together.
- **Keep commits clean.** Each commit should represent a single logical change.

---

## Need Help?

- Check the [Contributing Guide](CONTRIBUTING.md) for project conventions and review tiers
- Check the [Getting Started Guide](GETTING_STARTED.md) for setup instructions
- Open an issue if you run into problems

Thank you for contributing!
