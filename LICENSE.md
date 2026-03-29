# Licensing

Crazy Pumpkin OS uses a split licensing model.

## Open Source (MIT License)

The following directories and files are licensed under the [MIT License](LICENSE):

- `src/crazypumpkin/` — Core framework, agents, LLM providers, scheduler, CLI
- `tests/` — Test suite
- `docs/` — Documentation
- `examples/` — Example configurations and usage
- `scripts/` — Utility scripts
- All root-level `.md` files — Documentation
- `.github/` — CI/CD workflows, templates

You are free to use, modify, and distribute this code under the MIT License terms.

## Proprietary (All Rights Reserved)

The following are NOT open source and remain proprietary to Crazy Pumpkin / Majd Kassawat:

- Business logic specific to the Kassawat company
- Internal deployment and infrastructure code
- Financial systems and billing logic
- Internal agent credentials and secrets

These components are not included in this repository.

## Contributor License Agreement

By submitting a pull request, you agree that your contribution is licensed under the MIT License. This is confirmed via the PR template checklist.

## Third-Party Dependencies

This project uses third-party packages listed in `pyproject.toml`. Each has its own license (primarily MIT, Apache 2.0, and BSD). See individual package licenses for details.
