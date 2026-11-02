import unittest

from aws_shortcuts.actions import (
    SERVICES,
    json_payload,
    non_empty,
    one_of,
    resource_name,
    s3_uri,
)


class ValidatorTests(unittest.TestCase):
    def test_non_empty_trims_values_and_rejects_whitespace(self):
        self.assertEqual(non_empty("  value  "), "value")
        with self.assertRaisesRegex(ValueError, "required"):
            non_empty(" \t ")

    def test_s3_uri_requires_scheme_and_bucket(self):
        self.assertEqual(s3_uri(" s3://bucket/path "), "s3://bucket/path")
        self.assertEqual(s3_uri("my-bucket"), "s3://my-bucket")
        self.assertEqual(s3_uri("my-bucket/folder"), "s3://my-bucket/folder")
        with self.assertRaisesRegex(ValueError, "required"):
            s3_uri(" ")
        for invalid in ("s3://", "bucket name"):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "S3 URI"):
                s3_uri(invalid)

    def test_resource_name_rejects_whitespace(self):
        self.assertEqual(resource_name("my-queue"), "my-queue")
        with self.assertRaisesRegex(ValueError, "whitespace"):
            resource_name("my queue")

    def test_json_payload_defaults_to_empty_object_and_validates_json(self):
        self.assertEqual(json_payload(""), "{}")
        self.assertEqual(json_payload(' {"enabled": true} '), '{"enabled": true}')
        with self.assertRaisesRegex(ValueError, "valid JSON"):
            json_payload("{invalid")

    def test_one_of_validator_is_case_insensitive_and_rejects_unknown_values(self):
        validator = one_of("name", "date")
        self.assertEqual(validator("NAME"), "name")
        with self.assertRaisesRegex(ValueError, "name, date"):
            validator("size")


class ActionCatalogTests(unittest.TestCase):
    def test_service_and_action_aliases_are_unique(self):
        self.assertEqual(len({service.alias for service in SERVICES}), len(SERVICES))
        for service in SERVICES:
            aliases = [action.alias for action in service.actions]
            with self.subTest(service=service.alias):
                self.assertEqual(len(set(aliases)), len(aliases))

    def test_every_command_placeholder_has_a_value_or_runner_handler(self):
        runner_placeholders = {"response_file", "bucket", "prefix"}
        for service in SERVICES:
            for action in service.actions:
                placeholders = {
                    token[1:-1]
                    for token in action.command
                    if token.startswith("{") and token.endswith("}")
                }
                supplied_values = {argument.name for argument in action.arguments}
                with self.subTest(service=service.alias, action=action.alias):
                    self.assertLessEqual(
                        placeholders,
                        supplied_values | runner_placeholders,
                    )

    def test_delete_actions_require_confirmation(self):
        for service in SERVICES:
            for action in service.actions:
                if action.alias == "delete":
                    with self.subTest(service=service.alias):
                        self.assertTrue(action.confirmation)

    def test_sensitive_arguments_use_hidden_prompts_and_runner_file_handling(self):
        for service in SERVICES:
            for action in service.actions:
                if action.sensitive_arguments:
                    sensitive_prompts = {
                        argument.name
                        for argument in action.arguments
                        if argument.sensitive
                    }
                    with self.subTest(service=service.alias, action=action.alias):
                        self.assertTrue(set(action.sensitive_arguments) <= sensitive_prompts)


if __name__ == "__main__":
    unittest.main()
