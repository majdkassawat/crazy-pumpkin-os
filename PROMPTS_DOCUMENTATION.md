# Documentation Contribution Prompt Template

Use this structured prompt when contributing documentation to Crazy Pumpkin OS.

## Prompt

```
You are improving documentation for Crazy Pumpkin OS.

Target: [which doc file or section]

Steps:
1. Read the existing documentation to understand current coverage
2. Identify gaps, unclear sections, or missing examples
3. Read the source code in src/crazypumpkin/ to verify technical accuracy
4. Write clear, concise documentation with code examples where helpful
5. Link to related docs (CONTRIBUTING.md, ARCHITECTURE.md, etc.)
6. Verify all links work and code examples are syntactically correct
7. Run: python -m pytest tests/ -v --tb=short (ensure nothing is broken)
8. Commit with message: "Docs: [brief description]"

Rules:
- Use Edit/Write tools — do not output content as text
- Write for developers who are new to the project
- Include runnable code examples where applicable
- Use consistent markdown formatting
- Do not change source code — documentation only
- Verify technical claims by reading the actual source
```
