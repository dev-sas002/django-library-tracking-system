## Contributing & Code Commit Guidelines

Thank you for contributing to the **Library Tracking System**. This document describes how to structure your commits, how to write tests, and how to manage commit timestamps so that the history remains clean, understandable, and realistic.

The guidelines below apply to all work on this repository (features, bug fixes, refactors, documentation, and tests).

---

## 1. Commit Structure

### 1.1 Small, focused, logical commits

- Each commit must represent **one clear task**:
  - A single **feature addition**.
  - A single **bug fix**.
  - A single **refactor**.
  - A single **test-focused** change (e.g., adding or improving tests).
- Do **not** mix unrelated changes in the same commit.
- Avoid large “mega-commits”. Instead:
  - Split changes into **feature**, **refactor**, **bug fix**, and **test** commits.
  - For example:
    - First refactor the code (and commit that).
    - Then fix a bug (and commit that).
    - Then add tests (and commit that).

This makes the history easier to review, revert, and reason about.

### 1.2 Commit message format

All commit messages must use the following format:

`Feature::Task::Task Description`

Where:
- **Feature** is a fixed prefix to indicate a user-facing or behavior-changing commit.
- **Task** is a short category describing the nature of the change.
- **Task Description** is a concise explanation of what was done.

Valid **Task** labels in this project include:
- `Refactor` – behavior-preserving cleanups and simplifications.
- `BugFix` – corrections to incorrect behavior or failing edge cases.
- `Test` – new or updated tests only.
- `Docs` – documentation-only changes.
- `Chore` – non-functional maintenance (deps, tooling, formatting).
- `Infra` – CI/CD, deployment, or infrastructure work.

Examples (library-specific):
- `Feature::Refactor::Simplified book search filters`
- `Feature::BugFix::Fixed overdue loan calculation`
- `Feature::Test::Added tests for loans API endpoint`
- `Feature::Docs::Documented library sync management command`

Use the **Task Description** in imperative mood (e.g., “Add tests for loans API endpoint”) and keep it concise. Use the commit body for deeper explanation when necessary.

---

## 2. Code Review & Best Practices

### 2.1 Python & Django

For backend code in this project:

- **Style**:
  - Follow **PEP 8** for Python code style.
  - Use meaningful names for variables, functions, and classes.
  - Keep functions and methods focused and reasonably small.
- **Django & DRF**:
  - Use Django models, serializers, and views according to best practices.
  - Keep business logic in appropriate layers (e.g., models, services, tasks) rather than bloating views.
  - Ensure DRF views and serializers validate input and handle errors gracefully.
- **Exception handling**:
  - Catch only the exceptions you can handle meaningfully.
  - Avoid broad `except Exception:` without logging or re-raising.
  - Return appropriate HTTP status codes from API endpoints (e.g., 400/404/500 where relevant).
- **Dependencies**:
  - Use third-party libraries judiciously and only when they add clear value.
  - Prefer built-in or standard-library solutions where appropriate.

### 2.2 MERN / Frontend (if applicable)

If you work on companion frontend or MERN-based services that integrate with this API:

- **Express / Node APIs**:
  - Use Express routers to structure endpoints.
  - Respect RESTful conventions: correct HTTP verbs, paths, and status codes.
  - Implement proper validation and error handling.
- **React**:
  - Build reusable, composable components.
  - Keep components focused; lift state up logically.
  - Avoid unnecessary re-renders and keep the UI responsive.

Although this repository is Django-based, the same commit and testing principles apply to any related MERN services.

### 2.3 AI / ML (if introduced)

If AI or machine learning components are added (e.g., recommendation, prediction, or classification logic):

- **Model training & evaluation**:
  - Separate training code from inference code.
  - Track metrics and compare models before deployment.
- **Deployment**:
  - Keep inference code efficient and scalable.
  - Avoid blocking calls on the request path for long-running ML tasks; use Celery where suitable.
- **Optimization**:
  - Profile bottlenecks before optimizing.
  - Use batching, caching, and vectorization when appropriate.

Document assumptions and model behaviors clearly so that other contributors can understand and maintain the AI components.

---

## 3. Refactoring Guidelines

- Identify and remove **dead code** (unused functions, variables, imports).
- Simplify complex logic into smaller, composable functions or methods.
- Eliminate duplication where possible (DRY principle).
- Avoid changing behavior in a refactor commit unless necessary:
  - If behavior must change, clearly document it in the commit message and tests.
- Keep **refactors in dedicated commits** so they are easy to review and separate from bug fixes or new features.

Provide short but clear comments only where intent would be unclear from reading the code. Do **not** narrate obvious behavior in comments.

---

## 4. Unit Testing Requirements

For every meaningful change, ensure there are corresponding tests:

- **When to add or update tests**:
  - New feature → add new tests.
  - Bug fix → add or adjust tests that reproduce the bug and verify the fix.
  - Refactor → keep tests passing; add new tests if you are tightening behavior.
- **Frameworks**:
  - Use Django’s built-in test framework and/or `pytest` for Python tests.
  - Prefer small, focused test cases that are fast and deterministic.
- **Automation**:
  - Run the full test suite before committing.
  - Do not commit code if tests are failing.

Examples of test-focused commit messages:
- `Feature::Test::Added unit tests for registration API`
- `Feature::Test::Increased coverage for loan overdue calculations`

---

## 5. Special Instructions for Git Commits (Time-Travel)

Sometimes you will be asked to keep commits within a specific **date range**, for example:

- **Start Date**: `YYYY-MM-DD`
- **End Date**: `YYYY-MM-DD`

When a date range is provided:

- Ensure **all commits** have timestamps that fall within that range.
- Maintain a **realistic chronological development story**:
  - Start with initial refactors or foundational changes.
  - Follow with bug fixes and feature work.
  - Add tests and final polish toward the end of the range.
- To simulate historical development, set both `GIT_AUTHOR_DATE` and `GIT_COMMITTER_DATE` when creating commits.
  - Use a UTC timestamp in ISO 8601 format, for example: `2023-10-03T10:30:00Z`.
  - Keep `GIT_AUTHOR_DATE` and `GIT_COMMITTER_DATE` identical for each commit unless you have a deliberate reason to differ.

Always keep the logical order of development intact, even when adjusting dates:

- Do not reorder commits in a way that breaks the narrative (e.g., tests before the code they test, or bug fixes before the code that introduces the bug).

---

## 6. Example Commit Flow with Timestamps

Given:

- **Start Date**: `2023-10-01`
- **End Date**: `2023-10-15`

A well-structured series of commits might look like this:

1. **Initial Refactor Commit**
   - Timestamp: `2023-10-01T09:00:00Z`
   - Message: `Feature::Refactor::Simplified book search filters`
   - Description: Clean up and simplify the filtering logic for book searches without changing external behavior, preparing for future fixes and enhancements.

2. **Bug Fix Commit**
   - Timestamp: `2023-10-03T10:30:00Z`
   - Message: `Feature::BugFix::Fixed edge case in loan creation API`
   - Description: Address a specific failure mode in the loans endpoint (for example, when creating overlapping or invalid loans).

3. **Unit Test Commit**
   - Timestamp: `2023-10-05T14:00:00Z`
   - Message: `Feature::Test::Added tests for loan overdue logic`
   - Description: Add tests that reproduce the original issue and verify the fix for overdue calculations. Ensure coverage for typical and edge-case loan scenarios.

4. **Final Bug Fix / Polish Commit**
   - Timestamp: `2023-10-15T17:45:00Z`
   - Message: `Feature::BugFix::Fixed caching issue in loans API responses`
   - Description: Resolve any remaining issues (e.g., caching, performance, reliability) in the loans API identified during testing or code review.

Key points:
- Each commit is **logically separated** (refactor → bug fix → tests → final bug fix).
- Each commit has a **clear, descriptive message** using the required format.
- Timestamps stay within the specified range and follow a realistic development timeline.

---

## 7. Final Deliverables Expectations

For any significant task or feature, ensure that the following are true before you consider the work complete:

- **Code Improvements**:
  - Code follows best practices (PEP 8, Django conventions, clear structure).
  - Refactors have simplified or clarified the implementation.
- **Unit Tests**:
  - Automated tests cover new behavior and relevant edge cases.
  - All tests pass locally before pushing.
- **Commit History**:
  - Commits are small, focused, and logically ordered.
  - Messages use the `Feature::Task::Task Description` format.
  - When required, commit timestamps respect the specified date range and tell a coherent story.
- **Clear Reasoning**:
  - The “why” behind changes is clear from the combination of code, tests, and commit messages.

---

## 8. Future Improvements (Recommended)

To further enforce these practices, we may introduce:

- A **pre-commit** configuration to automatically run linters, formatters, and basic checks before allowing a commit.
- **Continuous Integration (CI)** (e.g., GitHub Actions) to run tests and quality checks on every push or pull request.

These enhancements will be added when needed. Until then, please follow the guidelines in this document manually and keep the repository’s history clean and maintainable.

