# Contributing

## Testing

Every change must include sufficient test coverage. Tests fall into three categories depending on what is being verified:

- **Functional tests** — end-to-end tests that exercise the application through its public interfaces (views, management commands, API endpoints, Celery tasks). Use these to verify the full request/response cycle and end-to-end behaviour.
- **Integration tests** — tests that cover queries and operations involving the database. Use these to verify persistence logic and ORM behaviour.
- **Unit tests** — fast, isolated tests for logic edge cases that don't require a database or external dependencies.

Choose the category that fits the scope of the change. Prefer unit tests where the logic can be exercised in isolation; reach for integration or functional tests when the interaction with the database or the full request/response cycle is what matters.

New code must be covered by automatic tests. PRs that add or change behaviour without accompanying tests will not be merged.

---

## Local environment

The contributing workflow requires the **full install** (PostgreSQL + Celery). Follow the [full install instructions](../README.md#full-install-for-development-and-large-collections) in the README, then install the development dependencies:

```bash
pip install -r requirements-dev.txt
```

### Running the tests

```bash
make test
# or directly:
pytest
```

### JavaScript tests

The browser-side camera code has its own suite, run by Node's built-in test
runner:

```bash
make test-js
```

**Node is a contributor requirement, not an install requirement.** Filmcase
serves that code as plain static files with no build step, so nobody running the
app needs Node. You only need it to run these tests, and only if you touch the
browser-side camera code.

The version lives in `.nvmrc`, which CI reads too, so the two cannot drift apart.
Install it whichever way suits you:

```bash
nvm install                 # reads .nvmrc, no sudo, per-user
# or
sudo apt install nodejs     # Ubuntu's, which may be older than .nvmrc asks for
```

If Node is missing or too old, `make test-js` says so and stops. That check earns
its place: the test runner only accepts a glob from 22 onwards, and on an older
Node the failure looks like a missing module rather than a version problem.

There are no dependencies. No bundler, no `npm install`, no `node_modules`, and
the browser loads the same files the tests import. `npm test` works if you have
npm, but nothing requires it.

Four fixtures in `tests/fixtures/camera/` are asserted by *both* suites, covering
the PTP wire format, the recipe conversion, the validation outcomes and the push
sequence. They exist because the write path is implemented twice, and a change to
one side that the other does not follow would otherwise be silent. If you change
the Python write path, expect the JavaScript suite to fail; regenerate the
fixture with its `generate_*.py` script only once you are sure the new values are
the ones you meant to send.

### Import linter

The project enforces a **layered architecture** through [import-linter](https://import-linter.readthedocs.io/). The layers and the direction dependencies must flow are defined in `setup.cfg`:

```
src.interfaces  →  (can import from layers below)
src.application →  (can import from layers below)
src.domain      →  (can import from layers below)
src.data        →  (innermost — no upward imports)
```

Each layer may only import from the layers below it. Importing upward (e.g. `domain` importing from `application`) is forbidden. See the [layered approach guide](https://github.com/octoenergy/public-conventions/blob/main/conventions/patterns.md#layered-approach) for a detailed explanation of what belongs in each layer.

To run the import linter:

```bash
lint-imports
```

### Type checking

The project uses [mypy](https://mypy.readthedocs.io/) with strict mode enabled. To check types:

```bash
mypy .
```

All new code must be fully type-annotated and pass mypy without errors.

### Migrations

Whenever you add or change a model, create a migration:

```bash
python manage.py makemigrations
```

Include the generated migration file in your PR. Never edit migrations by hand after they have been reviewed; create a new one instead.

---

## Opening a pull request

### Use a branch from your forked repository

Work on a branch in your own fork of the repository. Do not push feature branches directly to the upstream repo.

### Follow the coding conventions

All PRs must satisfy the [Kraken Technologies coding conventions](https://github.com/octoenergy/public-conventions) in full. Read them before opening a PR. In particular:

- **Layered architecture** — place new code in the correct layer. Dependencies must flow inward only.
- **Django conventions** — serialize template context; don't pass model instances into templates.
- **Python conventions** — follow the style and idioms described in the Python and static typing convention files.

### Commit and PR structure

Follow the [pull request conventions](https://github.com/octoenergy/public-conventions/blob/main/conventions/pull-requests.md). The most important points:

- **One thing per commit.** Each commit should express a single thought that a reviewer can hold in their head. Write commit subjects in the imperative mood ("Add recipe export endpoint", not "Added…").
- **Clean history.** Fix mistakes by rebasing and rewriting history — don't add "fix typo" or "address review comments" commits. Use `git rebase -i` to squash before requesting review.
- **Rebase, don't merge.** Keep your branch up to date by rebasing on `main`, not by merging it. Merge commits in a feature branch make the history harder to read.
- **Keep PRs small.** If a change grows beyond a few hundred lines, consider splitting it into chained PRs.
- **PR description.** Explain what the change does and why. Reviewers need context, not just a diff.
- **Open as draft** until the PR is potentially ready to merge. Only mark it ready for review once CI passes.

---

## Review conventions

Review comments use a structured prefix system so their intent and weight are immediately clear.

| Prefix | What's required before merging |
|---|---|
| `(convention)` | A code change fixing the violation. Links to the specific [public convention](https://github.com/octoenergy/public-conventions) rule. |
| `(blocking)` | A code change fixing the functional issue. |
| `(suggestion)` | Either a code change (if accepted) or a response explaining why it wasn't taken. |
| `(question)` | A response — no code change required, but the question must be answered before the PR is approved. |

Any prefix can be qualified with `[non-blocking]`, which means the PR may be merged before the comment is resolved. A response is still expected afterward.

**Acknowledge every comment.** Every review comment needs a reply — either a code change, an explanation, or at minimum a 👍 to confirm you've seen it.

---

## Use of AI

AI assistance is allowed and welcome. That said, the person submitting the PR is the code owner and is fully responsible for every line in it. Before opening a PR, make sure you understand the entire diff — what it does, why it does it that way, and what the trade-offs are.

Use AI as a tool to support your ideas, not to replace your judgement. If you can't explain a change in your own words, it isn't ready to submit.
