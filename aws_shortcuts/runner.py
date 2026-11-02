"""Safe subprocess boundary for the installed AWS CLI."""

import os
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Mapping

from aws_shortcuts.actions import Action


class AwsCliError(RuntimeError):
    """An AWS CLI process could not be started or completed successfully."""


class AwsCliRunner:
    def __init__(self, executable: str = "aws", timeout_seconds: int = 120):
        self.executable = executable
        self.timeout_seconds = timeout_seconds

    def check_login(self) -> None:
        try:
            result = subprocess.run(
                [self.executable, "sts", "get-caller-identity", "--output", "json"],
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout_seconds,
                shell=False,
            )
        except FileNotFoundError as error:
            raise AwsCliError(
                "AWS CLI was not found. Install AWS CLI v2 and make sure `aws` is on PATH."
            ) from error
        except subprocess.TimeoutExpired as error:
            raise AwsCliError(
                f"AWS authentication check timed out after {self.timeout_seconds} seconds."
            ) from error

        if result.returncode:
            message = result.stderr.strip() or result.stdout.strip()
            raise AwsCliError(
                message or f"AWS authentication check exited with status {result.returncode}."
            )

    def run(self, action: Action, values: Mapping[str, str]) -> str:
        try:
            for argument in action.arguments:
                if argument.name not in values:
                    raise AwsCliError(f"Missing required value for {argument.name}.")

            with tempfile.TemporaryDirectory(prefix="aws-shortcuts-") as directory:
                temporary_files: dict[str, Path] = {}
                for name in action.sensitive_arguments:
                    path = Path(directory) / f"{name}.txt"
                    path.write_text(values[name], encoding="utf-8")
                    os.chmod(path, 0o600)
                    temporary_files[name] = path

                if action.response_file:
                    response_path = Path(directory) / "lambda-response.json"
                    temporary_files["response_file"] = response_path

                command = [self.executable]
                for token in action.command:
                    if token.startswith("{") and token.endswith("}"):
                        name = token[1:-1]
                        if name == "response_file":
                            command.append(str(temporary_files[name]))
                        elif name in temporary_files:
                            command.append(f"file://{temporary_files[name]}")
                        elif name in {"bucket", "prefix"} and "uri" in values:
                            bucket, separator, prefix = values["uri"][len("s3://") :].partition("/")
                            command.append(bucket if name == "bucket" else prefix if separator else "")
                        elif name in values:
                            command.append(values[name])
                        else:
                            raise AwsCliError(f"Internal error: missing value for {name}.")
                    else:
                        command.append(token)

                try:
                    result = subprocess.run(
                        command,
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=self.timeout_seconds,
                        shell=False,
                    )
                except FileNotFoundError as error:
                    raise AwsCliError(
                        "AWS CLI was not found. Install AWS CLI v2 and make sure `aws` is on PATH."
                    ) from error
                except subprocess.TimeoutExpired as error:
                    raise AwsCliError(
                        f"AWS CLI timed out after {self.timeout_seconds} seconds."
                    ) from error

                if result.returncode:
                    message = result.stderr.strip() or result.stdout.strip()
                    raise AwsCliError(message or f"AWS CLI exited with status {result.returncode}.")

                output = result.stdout.strip()
                if action.sort_objects:
                    output = self._format_sorted_objects(output, values)
                if action.response_file and temporary_files["response_file"].exists():
                    response = temporary_files["response_file"].read_bytes().decode(
                        "utf-8", errors="replace"
                    ).strip()
                    if response:
                        output = "\n".join(part for part in (output, "Function response:", response) if part)
                return output or "Command completed successfully (no output)."
        except OSError as error:
            raise AwsCliError(f"Local AWS CLI file/process error: {error}") from error

    @staticmethod
    def _format_sorted_objects(output: str, values: Mapping[str, str]) -> str:
        try:
            response = json.loads(output or "{}")
        except json.JSONDecodeError as error:
            raise AwsCliError(f"AWS CLI returned invalid JSON: {error.msg}.") from error

        objects = response.get("Contents", [])
        if not objects:
            return "No objects found."

        if values["sort_by"] == "date":
            newest_first = values["date_order"] == "newest"
            objects.sort(
                key=lambda item: item.get("LastModified", ""),
                reverse=newest_first,
            )
        else:
            objects.sort(key=lambda item: item.get("Key", "").casefold())

        rows = ["Name\tLast modified\tSize"]
        rows.extend(
            f"{item.get('Key', '')}\t{item.get('LastModified', '')}\t{item.get('Size', '')}"
            for item in objects
        )
        return "\n".join(rows)
