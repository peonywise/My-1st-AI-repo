import io
import json
import os
import subprocess
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from aws_shortcuts.actions import SERVICES
from aws_shortcuts.cli import run_console
from aws_shortcuts.runner import AwsCliError, AwsCliRunner


class FakeRunner:
    def __init__(self, output="fake AWS result", login_error=None):
        self.output = output
        self.login_error = login_error
        self.login_checks = 0
        self.calls = []

    def check_login(self):
        self.login_checks += 1
        if self.login_error:
            raise self.login_error

    def run(self, action, values):
        self.calls.append((action, values))
        return self.output


def action(service_alias, action_alias):
    service = next(item for item in SERVICES if item.alias == service_alias)
    return next(item for item in service.actions if item.alias == action_alias)


class ConsoleTests(unittest.TestCase):
    def run_inputs(self, inputs, password_inputs=()):
        runner = FakeRunner()
        output = io.StringIO()
        with redirect_stdout(output):
            run_console(
                input_fn=lambda _prompt: next(inputs),
                password_fn=lambda _prompt: next(password_inputs),
                runner=runner,
            )
        return runner, output.getvalue()

    def test_select_by_number_and_alias_runs_s3_bucket_listing(self):
        runner, output = self.run_inputs(iter(["1", "buckets", "0", "0"]))
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(runner.login_checks, 1)
        self.assertEqual(runner.calls[0][0].alias, "buckets")
        self.assertIn("fake AWS result", output)
        self.assertIn("AWS login verified.", output)

    def test_startup_warns_when_aws_login_check_fails(self):
        runner = FakeRunner(login_error=AwsCliError("Unable to locate credentials"))
        output = io.StringIO()
        inputs = iter(["0"])
        with redirect_stdout(output):
            run_console(input_fn=lambda _prompt: next(inputs), runner=runner)

        self.assertEqual(runner.login_checks, 1)
        self.assertIn("AWS login could not be verified", output.getvalue())
        self.assertIn("aws login", output.getvalue())
        self.assertIn("Unable to locate credentials", output.getvalue())

    def test_startup_warning_does_not_prevent_menu_use(self):
        runner = FakeRunner(login_error=AwsCliError("Unable to locate credentials"))
        output = io.StringIO()
        inputs = iter(["s3", "buckets", "0", "0"])
        with redirect_stdout(output):
            run_console(
                input_fn=lambda _prompt: next(inputs),
                runner=runner,
            )

        self.assertEqual(len(runner.calls), 1)
        self.assertIn("AWS login could not be verified", output.getvalue())
        self.assertIn("fake AWS result", output.getvalue())

    def test_eof_at_startup_exits_gracefully(self):
        runner = FakeRunner()
        output = io.StringIO()
        with redirect_stdout(output):
            run_console(input_fn=lambda _prompt: (_ for _ in ()).throw(EOFError()), runner=runner)

        self.assertEqual(runner.calls, [])
        self.assertIn("Goodbye.", output.getvalue())

    def test_bucket_name_without_scheme_is_normalized_for_listing(self):
        runner, _ = self.run_inputs(iter(["s3", "objects", "my-bucket", "name", "0", "0"]))
        self.assertEqual(runner.calls[0][1], {"uri": "s3://my-bucket", "sort_by": "name"})

    def test_s3_uri_with_prefix_is_preserved(self):
        runner, _ = self.run_inputs(iter(["s3", "objects", "s3://my-bucket/folder", "name", "0", "0"]))
        self.assertEqual(
            runner.calls[0][1],
            {"uri": "s3://my-bucket/folder", "sort_by": "name"},
        )

    def test_s3_object_listing_prompts_for_date_order_each_time(self):
        runner, _ = self.run_inputs(
            iter(["s3", "objects", "my-bucket", "date", "oldest", "0", "0"])
        )
        self.assertEqual(runner.calls[0][1]["sort_by"], "date")
        self.assertEqual(runner.calls[0][1]["date_order"], "oldest")

    def test_invalid_s3_sort_field_is_reprompted(self):
        runner, output = self.run_inputs(
            iter(["s3", "objects", "my-bucket", "size", "name", "0", "0"])
        )
        self.assertEqual(runner.calls[0][1]["sort_by"], "name")
        self.assertIn("Choose one of: name, date", output)

    def test_invalid_s3_date_order_is_reprompted(self):
        runner, output = self.run_inputs(
            iter(["s3", "objects", "my-bucket", "date", "recent", "newest", "0", "0"])
        )
        self.assertEqual(runner.calls[0][1]["date_order"], "newest")
        self.assertIn("Choose newest or oldest", output)

    def test_destructive_action_requires_exact_confirmation(self):
        runner, output = self.run_inputs(
            iter(["s3", "delete", "s3://bucket/object", "y", "0", "0"])
        )
        self.assertEqual(runner.calls, [])
        self.assertIn("Cancelled", output)

    def test_yes_confirms_destructive_action(self):
        runner, _ = self.run_inputs(
            iter(["s3", "delete", "s3://bucket/object", "YES", "0", "0"])
        )
        self.assertEqual(len(runner.calls), 1)

    def test_sensitive_input_is_prompted_separately_and_passed_to_runner(self):
        runner, output = self.run_inputs(
            iter(["secrets", "create", "exam-secret", "yes", "0", "0"]),
            iter(["not-printed"]),
        )
        self.assertEqual(runner.calls[0][1]["secret_value"], "not-printed")
        self.assertEqual(runner.calls[0][1]["name"], "exam-secret")
        self.assertNotIn("not-printed", output)

    def test_lambda_payload_must_be_valid_json(self):
        runner, output = self.run_inputs(
            iter(["lambda", "invoke", "my-function", "yes", "0", "0"]),
            iter(["{bad", '{"ok": true}']),
        )
        self.assertEqual(runner.calls[0][1]["payload"], '{"ok": true}')
        self.assertIn("Enter valid JSON", output)

    def test_invalid_menu_choice_is_reprompted(self):
        runner, output = self.run_inputs(iter(["invalid", "s3", "buckets", "0", "0"]))
        self.assertEqual(len(runner.calls), 1)
        self.assertIn("Choose a listed number or alias", output)

    def test_aws_cli_error_is_reported_and_console_remains_usable(self):
        class ErrorRunner:
            def __init__(self):
                self.calls = 0

            def check_login(self):
                return None

            def run(self, _action, _values):
                self.calls += 1
                raise AwsCliError("AccessDenied")

        runner = ErrorRunner()
        output = io.StringIO()
        inputs = iter(["s3", "buckets", "0", "0"])
        with redirect_stdout(output):
            run_console(
                input_fn=lambda _prompt: next(inputs),
                runner=runner,
            )
        self.assertEqual(runner.calls, 1)
        self.assertIn("AWS CLI error: AccessDenied", output.getvalue())
        self.assertIn("Goodbye.", output.getvalue())

    def test_runner_uses_no_shell_and_places_secret_in_private_file(self):
        selected = action("secrets", "create")
        observed = {}

        def fake_run(command, **kwargs):
            secret_path = command[command.index("--secret-string") + 1].removeprefix("file://")
            with open(secret_path, encoding="utf-8") as secret_file:
                observed["secret"] = secret_file.read()
            observed["mode"] = os.stat(secret_path).st_mode & 0o777
            observed["path"] = secret_path
            return subprocess.CompletedProcess(command, 0, stdout="created", stderr="")

        with patch("aws_shortcuts.runner.subprocess.run") as run:
            run.side_effect = fake_run
            output = AwsCliRunner().run(
                selected, {"name": "my-secret", "secret_value": "value-not-in-argv"}
            )

        argv = run.call_args.args[0]
        self.assertFalse(run.call_args.kwargs["shell"])
        secret_arg_index = argv.index("--secret-string") + 1
        self.assertTrue(argv[secret_arg_index].startswith("file://"))
        self.assertNotIn("value-not-in-argv", argv)
        self.assertEqual(observed["secret"], "value-not-in-argv")
        self.assertEqual(observed["mode"], 0o600)
        self.assertFalse(os.path.exists(observed["path"]))
        self.assertEqual(output, "created")

    def test_runner_builds_command_as_argument_list(self):
        selected = action("s3", "buckets")
        with patch("aws_shortcuts.runner.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "object.txt"
            run.return_value.stderr = ""
            AwsCliRunner().run(selected, {"uri": "s3://example-bucket"})

        self.assertEqual(
            run.call_args.args[0],
            ["aws", "s3", "ls"],
        )
        self.assertFalse(run.call_args.kwargs["shell"])

    def test_runner_rejects_missing_action_values(self):
        with self.assertRaisesRegex(AwsCliError, "Missing required value for uri"):
            AwsCliRunner().run(action("s3", "objects"), {})

    def test_runner_rejects_missing_sensitive_value_without_starting_cli(self):
        with patch("aws_shortcuts.runner.subprocess.run") as run:
            with self.assertRaisesRegex(AwsCliError, "Missing required value for secret_value"):
                AwsCliRunner().run(action("secrets", "create"), {"name": "example"})
        run.assert_not_called()

    def test_runner_builds_s3_listing_command_from_bucket_or_prefix(self):
        with patch("aws_shortcuts.runner.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = '{"Contents": []}'
            run.return_value.stderr = ""
            AwsCliRunner().run(
                action("s3", "objects"),
                {"uri": "s3://my-bucket/folder", "sort_by": "name"},
            )

        self.assertEqual(
            run.call_args.args[0],
            [
                "aws",
                "s3api",
                "list-objects-v2",
                "--bucket",
                "my-bucket",
                "--prefix",
                "folder",
                "--output",
                "json",
            ],
        )

    def test_runner_sorts_objects_by_name_case_insensitively(self):
        response = {
            "Contents": [
                {"Key": "zebra.txt", "LastModified": "2026-01-03", "Size": 3},
                {"Key": "Apple.txt", "LastModified": "2026-01-01", "Size": 1},
                {"Key": "banana.txt", "LastModified": "2026-01-02", "Size": 2},
            ]
        }
        with patch("aws_shortcuts.runner.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = json.dumps(response)
            run.return_value.stderr = ""
            output = AwsCliRunner().run(
                action("s3", "objects"),
                {"uri": "s3://my-bucket", "sort_by": "name"},
            )

        self.assertLess(output.index("Apple.txt"), output.index("banana.txt"))
        self.assertLess(output.index("banana.txt"), output.index("zebra.txt"))

    def test_runner_sorts_objects_by_date_in_requested_order(self):
        response = {
            "Contents": [
                {"Key": "new.txt", "LastModified": "2026-01-03", "Size": 3},
                {"Key": "old.txt", "LastModified": "2026-01-01", "Size": 1},
                {"Key": "middle.txt", "LastModified": "2026-01-02", "Size": 2},
            ]
        }
        with patch("aws_shortcuts.runner.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = json.dumps(response)
            run.return_value.stderr = ""
            output = AwsCliRunner().run(
                action("s3", "objects"),
                {"uri": "s3://my-bucket", "sort_by": "date", "date_order": "newest"},
            )

        self.assertLess(output.index("new.txt"), output.index("middle.txt"))
        self.assertLess(output.index("middle.txt"), output.index("old.txt"))

    def test_runner_sorts_objects_oldest_first(self):
        response = {
            "Contents": [
                {"Key": "new.txt", "LastModified": "2026-01-03", "Size": 3},
                {"Key": "old.txt", "LastModified": "2026-01-01", "Size": 1},
            ]
        }
        with patch("aws_shortcuts.runner.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = json.dumps(response)
            run.return_value.stderr = ""
            output = AwsCliRunner().run(
                action("s3", "objects"),
                {"uri": "s3://my-bucket", "sort_by": "date", "date_order": "oldest"},
            )

        self.assertLess(output.index("old.txt"), output.index("new.txt"))

    def test_runner_reports_empty_s3_listing(self):
        with patch("aws_shortcuts.runner.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = '{"Contents": []}'
            run.return_value.stderr = ""
            output = AwsCliRunner().run(
                action("s3", "objects"),
                {"uri": "s3://my-bucket", "sort_by": "name"},
            )

        self.assertEqual(output, "No objects found.")

    def test_runner_reports_invalid_s3_listing_json(self):
        with patch("aws_shortcuts.runner.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "not json"
            run.return_value.stderr = ""
            with self.assertRaisesRegex(AwsCliError, "invalid JSON"):
                AwsCliRunner().run(
                    action("s3", "objects"),
                    {"uri": "s3://my-bucket", "sort_by": "name"},
                )

    def test_lambda_payload_uses_file_and_response_is_collected(self):
        selected = action("lambda", "invoke")
        observed = {}

        def fake_run(command, **kwargs):
            payload_uri = command[command.index("--payload") + 1]
            payload_path = payload_uri.removeprefix("file://")
            with open(payload_path, encoding="utf-8") as payload_file:
                observed["payload"] = payload_file.read()
            response_path = command[-1]
            with open(response_path, "wb") as response_file:
                response_file.write(b'{"result":"ok"}')
            observed["response_path"] = response_path
            return subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")

        with patch("aws_shortcuts.runner.subprocess.run", side_effect=fake_run):
            output = AwsCliRunner().run(
                selected, {"function_name": "my-function", "payload": '{"input": 1}'}
            )

        self.assertEqual(observed["payload"], '{"input": 1}')
        self.assertIn('{"result":"ok"}', output)
        self.assertFalse(os.path.exists(observed["response_path"]))

    def test_runner_reports_missing_aws_cli(self):
        with patch("aws_shortcuts.runner.subprocess.run", side_effect=FileNotFoundError):
            with self.assertRaisesRegex(AwsCliError, "AWS CLI was not found"):
                AwsCliRunner().run(action("s3", "buckets"), {})

    def test_login_check_uses_sts_identity_command_without_shell(self):
        with patch("aws_shortcuts.runner.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = '{"Account": "redacted"}'
            run.return_value.stderr = ""
            AwsCliRunner().check_login()

        self.assertEqual(
            run.call_args.args[0],
            ["aws", "sts", "get-caller-identity", "--output", "json"],
        )
        self.assertFalse(run.call_args.kwargs["shell"])

    def test_login_check_reports_missing_aws_cli(self):
        with patch("aws_shortcuts.runner.subprocess.run", side_effect=FileNotFoundError):
            with self.assertRaisesRegex(AwsCliError, "AWS CLI was not found"):
                AwsCliRunner().check_login()

    def test_login_check_reports_nonzero_exit_without_output(self):
        with patch("aws_shortcuts.runner.subprocess.run") as run:
            run.return_value.returncode = 1
            run.return_value.stdout = ""
            run.return_value.stderr = ""
            with self.assertRaisesRegex(AwsCliError, "status 1"):
                AwsCliRunner().check_login()

    def test_login_check_reports_missing_credentials(self):
        with patch("aws_shortcuts.runner.subprocess.run") as run:
            run.return_value.returncode = 1
            run.return_value.stdout = ""
            run.return_value.stderr = "Unable to locate credentials"
            with self.assertRaisesRegex(AwsCliError, "Unable to locate credentials"):
                AwsCliRunner().check_login()

    def test_login_check_reports_timeout(self):
        with patch(
            "aws_shortcuts.runner.subprocess.run",
            side_effect=subprocess.TimeoutExpired("aws", 1),
        ):
            with self.assertRaisesRegex(AwsCliError, "authentication check timed out"):
                AwsCliRunner(timeout_seconds=1).check_login()

    def test_runner_surfaces_aws_cli_failure(self):
        with patch("aws_shortcuts.runner.subprocess.run") as run:
            run.return_value.returncode = 1
            run.return_value.stdout = ""
            run.return_value.stderr = "AccessDenied"
            with self.assertRaisesRegex(AwsCliError, "AccessDenied"):
                AwsCliRunner().run(action("s3", "buckets"), {})

    def test_runner_uses_stdout_when_cli_error_has_no_stderr(self):
        with patch("aws_shortcuts.runner.subprocess.run") as run:
            run.return_value.returncode = 1
            run.return_value.stdout = "service error"
            run.return_value.stderr = ""
            with self.assertRaisesRegex(AwsCliError, "service error"):
                AwsCliRunner().run(action("s3", "buckets"), {})

    def test_runner_reports_timeout(self):
        with patch(
            "aws_shortcuts.runner.subprocess.run",
            side_effect=subprocess.TimeoutExpired("aws", 1),
        ):
            with self.assertRaisesRegex(AwsCliError, "timed out"):
                AwsCliRunner(timeout_seconds=1).run(action("s3", "buckets"), {})


if __name__ == "__main__":
    unittest.main()
