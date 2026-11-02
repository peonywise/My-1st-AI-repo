---
name: aws-cli-safe-usage
description: Safely run and compose AWS CLI v2 commands - verify login, pick profile/region, query JSON output, paginate, keep secrets out of argv, and confirm before destructive operations. Use this whenever the user asks to run, write, debug, or explain `aws` commands, or to work with S3, SQS, SNS, Secrets Manager, or Lambda from the terminal, even if they don't say "AWS CLI" explicitly.
---

# Safe AWS CLI usage

Help the user get AWS work done from the terminal without surprises: the right account, the right region, readable output, no leaked secrets, and no accidental deletions.

## 1. Check identity before anything else

Run this before the first real command in a session, and again if the profile changes:

```bash
aws sts get-caller-identity --output json
```

- If it fails with `NoCredentials`, `ExpiredToken`, or `Unable to locate credentials`, stop. Tell the user to run `aws login`, `aws sso login --profile <name>`, or `aws configure`. Do not try to work around missing credentials.
- Show the account ID and ARN to the user so they can confirm it is the intended account. This matters most before any write.
- Never print, echo, or store access keys, session tokens, or the contents of `~/.aws/credentials`.

## 2. Be explicit about profile and region

The defaults may not be what the user expects, so state them:

- Pass `--profile <name>` and `--region <region>` on each command, or export `AWS_PROFILE` and `AWS_REGION` once and say so.
- To see the current values, run `aws configure list`.
- If the region is unknown and the service is regional (SQS, SNS, Lambda, Secrets Manager), ask the user. S3 bucket operations follow the bucket's region automatically.

## 3. Prefer structured, filtered output

- Use `--output json` when you will parse the result. Use `--output table` or `text` only for human viewing.
- Filter on the server side when the API supports it, and on the client side with `--query` (JMESPath). Only use `jq` when `--query` can't express what you need.

```bash
aws lambda list-functions --query 'Functions[].{Name:FunctionName,Runtime:Runtime}' --output table
aws s3api list-objects-v2 --bucket my-bucket --prefix logs/ \
  --query 'sort_by(Contents,&LastModified)[-10:].[Key,LastModified,Size]' --output text
```

- The CLI paginates automatically. For large listings, use `--max-items` and `--starting-token`, or `--page-size`, to avoid huge outputs and throttling.

## 4. Keep secrets out of the command line

Command-line arguments show up in shell history and in `ps`. To keep secrets out of them:

- Write sensitive values (secret strings, payloads that contain credentials) to a temporary file with `0600` permissions and pass it as `file://path`. Delete the file afterwards.
- Use `fileb://` for binary blobs.
- Never paste secret values into chat summaries. Reference them by name or ARN instead.

```bash
umask 077; tmp=$(mktemp); printf '%s' "$SECRET" > "$tmp"
aws secretsmanager put-secret-value --secret-id my/secret --secret-string "file://$tmp"
rm -f "$tmp"
```

## 5. Confirm before destructive or costly actions

Treat these as destructive:

- `delete-*`, `remove-*`, `purge-queue`, `terminate-*`
- `aws s3 rm`, `aws s3 rb`
- `s3 sync --delete`
- `lambda invoke` (it can have side effects)
- anything that overwrites data

Before running one:

1. Show the exact command and the resolved account and region.
2. Use read-only previews where they exist: `--dryrun` for `s3 cp/mv/rm/sync`, `--dry-run` for EC2, or a `list-`/`describe-` call that shows what will be affected.
3. Ask the user to explicitly confirm, for example by typing `yes`. Do not assume confirmation from earlier messages.
4. Never add `--force`, `--recursive`, or `--force-delete-without-recovery` unless the user asked for it.

## 6. Common commands

| Service | Read | Write / destructive |
|---|---|---|
| S3 | `aws s3 ls`, `aws s3 ls s3://bucket/prefix/`, `aws s3api list-objects-v2 --bucket b --prefix p` | `aws s3 cp src s3://b/key`, `aws s3 rm s3://b/key` |
| SQS | `aws sqs list-queues`, `aws sqs get-queue-attributes --queue-url URL --attribute-names All` | `aws sqs send-message --queue-url URL --message-body file://msg.json`, `aws sqs purge-queue --queue-url URL` |
| SNS | `aws sns list-topics`, `aws sns list-subscriptions-by-topic --topic-arn ARN` | `aws sns publish --topic-arn ARN --message file://msg.txt`, `aws sns delete-topic --topic-arn ARN` |
| Secrets Manager | `aws secretsmanager list-secrets --query 'SecretList[].Name'`, `describe-secret --secret-id ID` | `get-secret-value` (output is sensitive; don't echo it), `delete-secret --secret-id ID --recovery-window-in-days 30` |
| Lambda | `aws lambda list-functions`, `aws lambda get-function --function-name F` | `aws lambda invoke --function-name F --payload file://p.json --cli-binary-format raw-in-base64-out out.json` |

Notes:

- An S3 bucket name without `s3://` works with `s3api --bucket`. The high-level `aws s3` commands need the full `s3://bucket/key` URI.
- In CLI v2, `lambda invoke` needs `--cli-binary-format raw-in-base64-out` for JSON payloads.

## 7. Diagnosing errors

- `AccessDenied` or `UnauthorizedOperation`: the call reached AWS, so this is an IAM permission issue. Report the action and resource, and don't retry with different credentials unprompted.
- `ResourceNotFoundException` or `NoSuchBucket`: check the region and the exact name or ARN.
- `ExpiredToken`: re-authenticate (see step 1).
- Add `--debug` only when needed, and scrub any signatures or tokens before sharing the output.

## 8. When scripting from code

- Invoke the CLI with an argument list and no shell, for example Python `subprocess.run([...], shell=False, timeout=...)`. Never build command strings by concatenating user input.
- Validate user-provided names, URIs, and JSON before calling AWS.
- In tests, mock `subprocess.run`. Never hit real AWS from unit tests.
