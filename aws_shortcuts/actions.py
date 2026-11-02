"""Curated AWS operations exposed by the interactive console."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


Validator = Callable[[str], str]


def one_of(*choices: str) -> Validator:
    allowed = {choice.lower() for choice in choices}

    def validate(value: str) -> str:
        value = non_empty(value).lower()
        if value not in allowed:
            raise ValueError(f"Choose one of: {', '.join(choices)}.")
        return value

    return validate


def non_empty(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("A value is required.")
    return value


def s3_uri(value: str) -> str:
    value = non_empty(value)
    if value.startswith("s3://"):
        if len(value) <= len("s3://"):
            raise ValueError("Enter a bucket name or S3 URI such as s3://my-bucket/path.")
        return value
    if any(character.isspace() for character in value):
        raise ValueError("Enter a bucket name or S3 URI such as s3://my-bucket/path.")
    value = f"s3://{value}"
    return value


def resource_name(value: str) -> str:
    value = non_empty(value)
    if any(character.isspace() for character in value):
        raise ValueError("Resource names cannot contain whitespace.")
    return value


def json_payload(value: str) -> str:
    import json

    value = value.strip() or "{}"
    try:
        json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError(f"Enter valid JSON ({error.msg}).") from error
    return value


@dataclass(frozen=True)
class Argument:
    name: str
    prompt: str
    validator: Validator = non_empty
    sensitive: bool = False


@dataclass(frozen=True)
class Action:
    alias: str
    title: str
    command: tuple[str, ...]
    arguments: tuple[Argument, ...] = ()
    confirmation: str | None = None
    sensitive_arguments: tuple[str, ...] = ()
    response_file: bool = False
    sort_objects: bool = False


@dataclass(frozen=True)
class Service:
    alias: str
    title: str
    actions: tuple[Action, ...]


def arg(name: str, prompt: str, validator: Validator = non_empty) -> Argument:
    return Argument(name=name, prompt=prompt, validator=validator)


def secret_arg(
    name: str,
    prompt: str,
    validator: Validator = non_empty,
) -> Argument:
    return Argument(name=name, prompt=prompt, validator=validator, sensitive=True)


SERVICES = (
    Service(
        "s3",
        "Amazon S3",
        (
            Action("buckets", "List buckets", ("s3", "ls")),
            Action(
                "objects",
                "List and sort objects in a bucket",
                (
                    "s3api",
                    "list-objects-v2",
                    "--bucket",
                    "{bucket}",
                    "--prefix",
                    "{prefix}",
                    "--output",
                    "json",
                ),
                (
                    arg("uri", "Bucket or prefix (bucket name or s3://...): ", s3_uri),
                    arg("sort_by", "Sort by (name/date): ", one_of("name", "date")),
                ),
                sort_objects=True,
            ),
            Action(
                "upload",
                "Upload a file",
                ("s3", "cp", "{local_path}", "{uri}"),
                (arg("local_path", "Local file path: "), arg("uri", "Destination S3 URI: ", s3_uri)),
            ),
            Action(
                "download",
                "Download a file",
                ("s3", "cp", "{uri}", "{local_path}"),
                (arg("uri", "Source S3 URI: ", s3_uri), arg("local_path", "Local destination path: ")),
            ),
            Action(
                "delete",
                "Delete an S3 object",
                ("s3", "rm", "{uri}"),
                (arg("uri", "Object S3 URI: ", s3_uri),),
                confirmation="This permanently deletes the selected S3 object.",
            ),
        ),
    ),
    Service(
        "sqs",
        "Amazon SQS",
        (
            Action("queues", "List queues", ("sqs", "list-queues", "--output", "table")),
            Action(
                "create",
                "Create a queue",
                ("sqs", "create-queue", "--queue-name", "{name}"),
                (arg("name", "Queue name: ", resource_name),),
            ),
            Action(
                "send",
                "Send a message",
                ("sqs", "send-message", "--queue-url", "{queue_url}", "--message-body", "{message}"),
                (arg("queue_url", "Queue URL: "), arg("message", "Message body: ")),
            ),
            Action(
                "receive",
                "Receive messages",
                (
                    "sqs",
                    "receive-message",
                    "--queue-url",
                    "{queue_url}",
                    "--max-number-of-messages",
                    "5",
                    "--wait-time-seconds",
                    "10",
                    "--output",
                    "table",
                ),
                (arg("queue_url", "Queue URL: "),),
            ),
            Action(
                "delete",
                "Delete a queue",
                ("sqs", "delete-queue", "--queue-url", "{queue_url}"),
                (arg("queue_url", "Queue URL: "),),
                confirmation="This deletes the queue and its messages.",
            ),
        ),
    ),
    Service(
        "sns",
        "Amazon SNS",
        (
            Action("topics", "List topics", ("sns", "list-topics", "--output", "table")),
            Action(
                "create",
                "Create a topic",
                ("sns", "create-topic", "--name", "{name}"),
                (arg("name", "Topic name: ", resource_name),),
            ),
            Action(
                "publish",
                "Publish a message",
                ("sns", "publish", "--topic-arn", "{topic_arn}", "--message", "{message}"),
                (arg("topic_arn", "Topic ARN: "), arg("message", "Message body: ")),
            ),
            Action(
                "subscribe",
                "Subscribe an endpoint",
                (
                    "sns",
                    "subscribe",
                    "--topic-arn",
                    "{topic_arn}",
                    "--protocol",
                    "{protocol}",
                    "--notification-endpoint",
                    "{endpoint}",
                ),
                (
                    arg("topic_arn", "Topic ARN: "),
                    arg("protocol", "Protocol (e.g. email, https, sqs): ", resource_name),
                    arg("endpoint", "Endpoint address or ARN: "),
                ),
            ),
            Action(
                "delete",
                "Delete a topic",
                ("sns", "delete-topic", "--topic-arn", "{topic_arn}"),
                (arg("topic_arn", "Topic ARN: "),),
                confirmation="This deletes the topic and its subscriptions.",
            ),
        ),
    ),
    Service(
        "secrets",
        "AWS Secrets Manager",
        (
            Action("list", "List secrets", ("secretsmanager", "list-secrets", "--output", "table")),
            Action(
                "get",
                "Retrieve a secret value",
                ("secretsmanager", "get-secret-value", "--secret-id", "{secret_id}", "--query", "SecretString", "--output", "text"),
                (arg("secret_id", "Secret name or ARN: "),),
            ),
            Action(
                "create",
                "Create a secret",
                ("secretsmanager", "create-secret", "--name", "{name}", "--secret-string", "{secret_value}"),
                (arg("name", "Secret name: ", resource_name), secret_arg("secret_value", "Secret value: ")),
                sensitive_arguments=("secret_value",),
            ),
            Action(
                "update",
                "Update a secret value",
                ("secretsmanager", "put-secret-value", "--secret-id", "{secret_id}", "--secret-string", "{secret_value}"),
                (arg("secret_id", "Secret name or ARN: "), secret_arg("secret_value", "New secret value: ")),
                sensitive_arguments=("secret_value",),
            ),
            Action(
                "delete",
                "Schedule secret deletion",
                ("secretsmanager", "delete-secret", "--secret-id", "{secret_id}"),
                (arg("secret_id", "Secret name or ARN: "),),
                confirmation="This schedules deletion using AWS's default recovery window.",
            ),
        ),
    ),
    Service(
        "lambda",
        "AWS Lambda",
        (
            Action("functions", "List functions", ("lambda", "list-functions", "--output", "table")),
            Action(
                "invoke",
                "Invoke a function",
                (
                    "lambda",
                    "invoke",
                    "--function-name",
                    "{function_name}",
                    "--cli-binary-format",
                    "raw-in-base64-out",
                    "--payload",
                    "{payload}",
                    "{response_file}",
                ),
                (
                    arg("function_name", "Function name or ARN: ", resource_name),
                    secret_arg("payload", "JSON payload (press Enter for {}): ", json_payload),
                ),
                confirmation="Invoking a function may trigger application side effects and incur charges.",
                sensitive_arguments=("payload",),
                response_file=True,
            ),
        ),
    ),
)
