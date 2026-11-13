# AI Usage Disclosure

AI tools are allowed. We want to know **how** you used them, because using them well is a
skill. Honest answers are never held against you. Discovering undisclosed use is.

## Tools used
ChatGPT (OpenAI)

## What I used them for
- Understanding the assignment requirements and breaking the work into manageable implementation steps.

- Discussing Python implementation approaches for the ingestion and reporting pipeline.

- Getting help with phone number normalization, date validation, decimal parsing, and event-to-lead matching edge cases.

- Reviewing test scenarios and improving test coverage for duplicate handling, disposition overrides, and orphan event recovery.

- Refining technical documentation, setup instructions, and the submission write-up.
## What I wrote or decided myself
- Selected Assignment A based on the requirements and implementation scope.

- Made design decisions around SQLite persistence, encrypted PII storage, and deterministic phone matching.

- Reviewed the ingestion and reporting workflow.

- Identified important edge cases and testing requirements.

- Reviewed the implementation and adapted suggestions to the assignment requirements.
## Where the AI was wrong or unhelpful
- Some suggestions were too generic and needed adjustment to match the assignment's specific requirements.

- I reviewed suggestions involving phone normalization, date validation, and event-to-lead matching against the expected input formats and edge cases.

- I did not assume generated suggestions were correct without reviewing them.
## How I verified AI-generated code
- Ran the automated test suite using python -m pytest solution/tests -q.

- Ran the data-generation, ingestion, and reporting commands locally.

- Checked the generated report files and their expected output structure.

- Reviewed important implementation paths, including duplicate ingestion, invalid input handling, disposition precedence, and orphan event recovery.
