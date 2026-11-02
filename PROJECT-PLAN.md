# Project plan: AWS CLI shortcut console app

## Problem and approach

The starter repository contains no application yet. Build a small Python console tool that makes a curated set of common AWS CLI operations easier to run through short aliases and numbered menus. It will cover S3, SQS, SNS, AWS Secrets Manager, and Lambda, while delegating authentication and actual AWS API calls to the user's installed/configured AWS CLI.

The app will execute selected operations through `subprocess` without a shell, validate required values, and ask before destructive actions. It will not collect or persist AWS credentials. Tests will replace the AWS CLI process with a mock so validation does not require credentials or modify cloud resources.

Prepare an assignment-ready write-up in the repository that can be transferred to Google Docs. Include project idea and requirements, modular architecture and per-module AI-assisted process, testing, key prompts, challenges/tool comparison, repository link, and honest instructions for capturing at least two functioning-system screenshots. Do not fabricate live AWS evidence or claim the app was tested against real AWS resources.

## Todos

1. Inspect the starter repository and existing files.
2. Define a finite set of common actions and the numbered/alias interaction for each requested AWS service.
3. Implement the Python console application and its safe AWS CLI invocation boundary.
4. Add/run mock-based tests that verify menu input, command construction, confirmation, and failures without real AWS calls.
5. Prepare assignment-ready documentation and evidence-capture guidance.

## Notes and considerations

- Language: Python.
- Scope: curated common operations, not a general-purpose arbitrary-command shell.
- Behavior: selected operations execute through AWS CLI; destructive operations require confirmation.
- AWS credentials remain in the user's normal AWS CLI configuration. Avoid logging secret values or putting secret material in process arguments where feasible.
- Keep cloud access optional for local tests; document prerequisites and the exact way to run the app.
- Preserve existing repository files and unrelated working-tree changes.
- The repository does not provide a Google Drive integration. Deliver the write-up as a document file suitable for copying into the required shared Google Drive document.
