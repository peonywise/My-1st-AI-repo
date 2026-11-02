---
name: python-cli-app
description: 'Build interactive or command-driven Python CLI/console apps (menus, aliases, validated prompts, subprocess wrappers, pyproject entry points, mocked unittest tests) - use whenever the user wants to create, extend, or test a Python command-line tool, especially one that wraps another CLI such as aws, git, kubectl, or docker.'
---

# Building Python CLI apps

This skill describes a layout that keeps a console app small, safe, and fully testable without real side effects. The reference implementation is the `aws_shortcuts` package in this repo.

## 1. Clarify scope first

Before writing code, pin down:

- **Interaction style:** an interactive numbered menu (`input()` loop), a command-style interface (`argparse` subcommands), or both.
- **Python floor:** for example `>=3.9`. If you support 3.9, add `from __future__ import annotations` so `str | None` hints work.
- **Dependencies:** prefer the standard library only (`argparse`, `subprocess`, `getpass`, `json`, `tempfile`, `unittest`). Add a third-party library such as `click`, `typer`, or `rich` only when the user asks for it.
- **Actions:** which operations are destructive or sensitive, and so need confirmation or hidden input.

## 2. Project layout

```
pyproject.toml          # setuptools, [project.scripts] entry point
README.md               # install, usage, prerequisites, tests
<package>/
  __init__.py
  __main__.py           # from <package>.cli import main; main()
  actions.py            # declarative catalog + validators (pure data/logic)
  runner.py             # the only module that touches subprocess/files
  cli.py                # prompts, menus, printing; no subprocess calls
tests/
  test_actions.py       # validators + catalog consistency
  test_cli.py           # console flows with fake input and fake runner
```

Minimal `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "my-tool"
version = "0.1.0"
requires-python = ">=3.9"
dependencies = []

[project.scripts]
my-tool = "my_tool.cli:main"

[tool.setuptools.packages.find]
include = ["my_tool*"]
```

Users can then run the app as `python3 -m my_tool`, or as `my-tool` after `pip install -e .`.

## 3. Use a declarative action catalog

Describe the operations as frozen dataclasses, not as `if`/`elif` branches. This lets you add a feature by adding a catalog entry plus a test.

```python
@dataclass(frozen=True)
class Argument:
    name: str
    prompt: str
    validator: Callable[[str], str] = non_empty
    sensitive: bool = False          # read with getpass, never put in argv

@dataclass(frozen=True)
class Action:
    alias: str                       # short keyboard shortcut, e.g. "ls"
    title: str
    command: tuple[str, ...]         # ("aws", "s3", "ls", "{uri}")
    arguments: tuple[Argument, ...] = ()
    confirmation: str | None = None  # set => require typing "yes"
```

Validators are plain functions that take a string and either return the normalized value or raise `ValueError` with a user-friendly message. Examples: `non_empty`, `resource_name`, `json_payload`, and `one_of(*choices)` (a factory). Normalize forgiving input, such as adding a missing `s3://` prefix, instead of rejecting it.

## 4. Runner: the single side-effect boundary

- Build commands as a list by substituting the `{placeholder}` tokens. Always call `subprocess.run(cmd, shell=False, capture_output=True, text=True, timeout=...)`.
- Raise one custom exception type, such as `ToolError`, with a clear message for each failure:
  - `FileNotFoundError`: the tool is not installed.
  - `TimeoutExpired`: the command timed out.
  - Nonzero exit: use stderr, then stdout, then "exited with status N".
- Check for missing required values before starting any process.
- Write sensitive values to temporary files with `0600` permissions and pass them as `file://path`. Delete the files in `finally`.
- Do output post-processing, such as JSON parsing, sorting, and table formatting, in pure helper functions so they are easy to unit-test.
- If the wrapped tool needs auth, add a `check_login()` method. Call it at startup and warn the user on failure, but don't block the menu.

## 5. Console layer

- Inject dependencies so tests can drive the app: `run_console(input_fn=input, password_fn=getpass.getpass, runner=None)`.
- Menus accept a number, an alias (case-insensitive), or `0`/`q` to go back or quit. Re-prompt on invalid input.
- Re-prompt for each argument until its validator passes. Use `password_fn` for sensitive arguments.
- For destructive actions, print a warning and require the user to type `yes`. Anything else cancels the action and runs nothing.
- Catch `EOFError` and `KeyboardInterrupt` at the top level, print "Goodbye." and exit cleanly.
- Print errors from the runner and return to the menu. Never print a traceback for expected failures.

## 6. Testing (unittest, no real side effects)

Run the tests with `python3 -m unittest discover -s tests -v`.

- **Validators:** cover the accepted, normalized, and rejected cases.
- **Catalog consistency:** check that aliases are unique, that every `{placeholder}` in a command has a matching argument (or a derived value), and that destructive commands have a `confirmation`.
- **CLI flows:**
  - Feed scripted answers with `iter([...]).__next__` as `input_fn`, and use a `FakeRunner` that records calls.
  - Assert on the captured stdout with `contextlib.redirect_stdout`.
  - Cover the happy path, invalid input then retry, cancelled confirmation, runner errors, EOF, and the startup login warning.
- **Runner:**
  - Patch `subprocess.run` with `unittest.mock.patch` and assert on the exact argv, `shell=False`, and the timeout.
  - Simulate `FileNotFoundError`, a nonzero exit, and empty or invalid JSON.
  - Check that secrets never appear in argv.
- After each change, also run `python3 -m compileall -q <package> tests` as a quick syntax check.

## 7. Workflow for adding a feature

1. Add or adjust the validator and catalog entry in `actions.py`.
2. Extend `runner.py` only if the feature needs new placeholder resolution or output formatting.
3. Wire in any extra prompts in `cli.py`.
4. Add tests at all three layers, then run the full suite.
5. Update the README's usage, the action list, and any prerequisites.
