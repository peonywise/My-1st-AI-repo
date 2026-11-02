# AWS Shortcut Console

AWS Shortcut Console is a small Python terminal app for common Amazon S3, SQS, SNS, Secrets Manager, and Lambda operations. Pick a service and action by number or short alias, enter only the requested values, and let the installed AWS CLI use your existing profile and credentials.

## Requirements

- Python 3.9 or later
- AWS CLI v2 installed and available as `aws`
- An authenticated AWS CLI session/profile and a default region configured
- IAM permissions for the actions you choose

Before using AWS actions, sign in with `aws login` or configure credentials with your normal AWS CLI setup. On startup, the app checks authentication by calling `aws sts get-caller-identity`; it displays a warning if the check fails, but still opens the menu. The app does not configure AWS or collect credentials. Tests mock the AWS CLI and require no AWS account. It has no third-party Python dependencies.

## Run

From the repository root:

```sh
python3 -m aws_shortcuts
```

Or install the project locally and use the command:

```sh
python3 -m pip install .
aws-shortcuts
```

Enter a service number or alias (`s3`, `sqs`, `sns`, `secrets`, `lambda`), then an action number or alias. Enter `0` to go back or exit. For example, choose `s3` → `buckets` to list buckets.
For S3 object listing, enter either a bucket name such as `my-bucket` or a full URI such as `s3://my-bucket/folder`; the app adds the `s3://` prefix when omitted. Choose `name` for case-insensitive alphabetical order, or `date` and then `newest`/`oldest` for last-modified order.

## Supported shortcuts

| Service | Actions |
|---|---|
| S3 | List buckets; list objects; upload/download a file; delete an object |
| SQS | List/create queues; send/receive messages; delete a queue |
| SNS | List/create topics; publish; subscribe an endpoint; delete a topic |
| Secrets Manager | List/retrieve secrets; create/update a secret; schedule deletion |
| Lambda | List functions; invoke a function with a JSON payload |

Operations that delete resources or invoke functions display a warning and require typing `yes`. Secrets Manager values and Lambda payloads are entered through a hidden prompt and passed to AWS CLI via short-lived, permission-restricted temporary files rather than process arguments. Retrieved secret values and command output are displayed in the terminal at the user's request.

This is a guided shortcut menu, not a general-purpose shell. Always verify the selected AWS profile, region, account, and resource identifiers before executing an operation. AWS permissions and service charges still apply.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

The tests mock the AWS CLI subprocess. They do not require AWS credentials and do not modify AWS resources. No live AWS integration test has been performed as part of this project.

## Assignment write-up and evidence

See [`ASSIGNMENT.md`](ASSIGNMENT.md) for the project description, module architecture, AI-assisted development process, tests, challenges, tool comparison, repository link, and genuine system screenshots.