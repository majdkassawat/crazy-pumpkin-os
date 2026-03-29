# Plugin Development Prompt Template

Use this structured prompt when building a plugin for Crazy Pumpkin OS.

## Prompt

```
You are building a plugin for Crazy Pumpkin OS.

Plugin: [name and purpose]

Steps:
1. Read CONTRIBUTING.md for contribution guidelines
2. Read examples/config.yaml for plugin configuration patterns
3. Read src/crazypumpkin/framework/agent.py for the BaseAgent interface
4. Create your plugin directory under a suitable location
5. Implement the plugin following the BaseAgent pattern if it's an agent plugin
6. Write comprehensive tests in tests/
7. Add configuration examples in examples/
8. Document usage in a README within your plugin directory
9. Run: python -m pytest tests/ -v --tb=short
10. Open a PR with clear description of the plugin's purpose

Rules:
- Use Edit/Write tools — do not output code as text
- Follow the existing package structure in src/crazypumpkin/
- Include type hints and docstrings
- Write at least 3 tests covering core functionality
- Keep dependencies minimal — declare any new deps in pyproject.toml [optional]
- Do not modify existing core code — plugins should extend, not change
```
