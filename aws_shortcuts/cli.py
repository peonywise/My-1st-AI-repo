"""Interactive, numbered console interface."""

from __future__ import annotations

import getpass
from collections.abc import Callable

from aws_shortcuts.actions import SERVICES, Action, Service
from aws_shortcuts.runner import AwsCliError, AwsCliRunner


Input = Callable[[str], str]
PasswordInput = Callable[[str], str]


def choose(items: tuple, prompt: str, input_fn: Input) -> int | None:
    """Return a zero-based choice index, or None to go back/quit."""
    while True:
        selection = input_fn(prompt).strip().lower()
        if selection in {"q", "quit", "0"}:
            return None
        for index, item in enumerate(items):
            if selection == item.alias.lower() or selection == str(index + 1):
                return index
        print("Choose a listed number or alias, or enter 0 to go back.")


def _read_arguments(
    action: Action,
    input_fn: Input,
    password_fn: PasswordInput,
) -> dict[str, str]:
    values: dict[str, str] = {}
    for argument in action.arguments:
        prompt = argument.prompt
        while True:
            raw_value = (
                password_fn(prompt)
                if argument.sensitive
                else input_fn(prompt)
            )
            try:
                values[argument.name] = argument.validator(raw_value)
                break
            except ValueError as error:
                print(error)
    return values


def _show_actions(service: Service) -> None:
    print(f"\n{service.title} actions")
    for index, action in enumerate(service.actions, start=1):
        print(f"  {index}. {action.title}  [{action.alias}]")
    print("  0. Back")


def run_console(
    input_fn: Input = input,
    password_fn: PasswordInput = getpass.getpass,
    runner: AwsCliRunner | None = None,
) -> None:
    runner = runner or AwsCliRunner()
    print("AWS Shortcut Console")
    print("AWS CLI authentication is required. The app uses your existing AWS CLI configuration.")
    try:
        runner.check_login()
    except AwsCliError as error:
        print(
            "AWS login could not be verified. Run `aws login` or configure AWS CLI credentials before using AWS actions."
        )
        print(f"Authentication check: {error}")
    else:
        print("AWS login verified.")

    try:
        while True:
            print("\nServices")
            for index, service in enumerate(SERVICES, start=1):
                print(f"  {index}. {service.title}  [{service.alias}]")
            print("  0. Exit")
            service_index = choose(SERVICES, "Select a service: ", input_fn)
            if service_index is None:
                print("Goodbye.")
                return

            service = SERVICES[service_index]
            while True:
                _show_actions(service)
                action_index = choose(service.actions, "Select an action: ", input_fn)
                if action_index is None:
                    break

                action = service.actions[action_index]
                values = _read_arguments(action, input_fn, password_fn)
                if action.sort_objects and values["sort_by"] == "date":
                    while True:
                        try:
                            values["date_order"] = input_fn(
                                "Date order (newest/oldest): "
                            ).strip().lower()
                            if values["date_order"] not in {"newest", "oldest"}:
                                raise ValueError("Choose newest or oldest.")
                            break
                        except ValueError as error:
                            print(error)
                if action.confirmation:
                    print(action.confirmation)
                    confirmation = input_fn("Continue? Type 'yes' to confirm: ").strip().lower()
                    if confirmation != "yes":
                        print("Cancelled; no AWS command was run.")
                        continue

                try:
                    output = runner.run(action, values)
                except AwsCliError as error:
                    print(f"AWS CLI error: {error}")
                else:
                    print(output)
    except (EOFError, KeyboardInterrupt):
        print("\nGoodbye.")


def main() -> None:
    run_console()
