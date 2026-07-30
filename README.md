# GitHub Portfolio Reviewer

[![CI](https://github.com/longinhk/github-portfolio-reviewer/actions/workflows/ci.yml/badge.svg)](https://github.com/longinhk/github-portfolio-reviewer/actions/workflows/ci.yml)
![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)

A Streamlit student portfolio application that reviews how effectively a public
GitHub repository presents an engineering project to internship recruiters and
technical reviewers. It produces a transparent portfolio-presentation score out
of 100, evidence for every check, and a prioritized improvement plan.

**No AI API, model key, or paid inference service is required.** Every result
comes from explicit Python rules applied to read-only GitHub evidence.

> The score is a deterministic portfolio-presentation heuristic, not a measure
> of developer ability, code correctness, or hiring suitability. Its security
> section is not a security audit.

![GitHub Portfolio Reviewer interface](docs/repository-review.svg)

## Features

- Accepts `owner/repository`, repository-root, branch, or file GitHub URLs, and
  SSH clone strings. Branch and file URLs are normalized to the repository root;
  the review still analyzes the default branch.
- Collects repository metadata, the preferred README, the recursive file tree,
  and a bounded allowlist of small text files through the GitHub REST API.
- Reviews metadata, README quality, structure, tests, CI/CD, documentation, and
  basic security signals.
- Verifies selected test, Python, CI, dependency-update, and security signals
  without cloning or executing repository code. Ten inspection slots are
  reserved by evidence type so one large category cannot hide another.
- Shows points, evidence files, confidence, thresholds, and next steps behind
  every result.
- Offers General, Python, AI/ML, data-science, and backend internship review
  focuses. Focus changes recommendation order—not the comparable score.
- Exports deterministic Markdown and JSON reports without raw source content.
- Reuses recent public evidence for five minutes and retries only temporary
  connection or GitHub server failures once.
- Includes dark and light GitHub-inspired themes, check filters, search, and a
  mobile-responsive report.
- Handles missing repositories, invalid tokens, API limits, timeouts, empty
  repositories, missing READMEs, and truncated trees.
- Uses no database and does not intentionally persist GitHub tokens.

## Portfolio-presentation scoring rubric

| Category | Points | Examples of evidence |
| --- | ---: | --- |
| Repository metadata | 10 | Description, topics, license, archive status |
| README quality | 25 | Detail, setup, usage, badges, visuals |
| Project structure | 15 | Source layout, manifest, `.gitignore`, modularity |
| Tests | 15 | Test presence, implementation evidence, configuration, coverage |
| CI/CD | 10 | Workflow, pinned Actions, permissions, visible status badge |
| Documentation | 10 | Extended docs and project-governance files |
| Security | 15 | Policy, updates, risky filenames, bounded secret scan, lock file |
| **Total** | **100** | Pass = full points, partial = half, fail = zero |

Stars, forks, and issue counts are displayed but never scored. Popularity is not
a reliable measure of engineering quality. CI configuration is not proof that a
workflow passes, and suspicious filenames are not proof that they contain
secrets.

Ruleset 1.2 separates a check's result from how completely its evidence was
inspected:

| Confidence | Meaning |
| --- | --- |
| Verified | Direct metadata, path, or inspected content supports the result |
| Sampled | A bounded subset supports the result, but relevant evidence remains |
| Unverified | A relevant path exists, but no usable file content was inspected |
| Provisional | GitHub truncated the tree, so an apparent absence is uncertain |

Pass, partial, and fail determine points. Confidence explains evidence quality;
it does not silently change the rubric. The ruleset version is included in each
portable report so results can be interpreted against the rules that produced
them.

## Architecture

```text
Streamlit UI -> Review service -> GitHub client -> GitHub REST API
                     |
                     +-> Analyzer -> Scoring -> Suggestions
                              +-> Markdown / JSON reporting
                              \_______ domain models _______/
```

The analyzer and scoring rules contain no Streamlit or Requests code, which
makes them deterministic and independently testable. See
[`docs/architecture.md`](docs/architecture.md) for responsibilities and design
tradeoffs.

## External libraries

- **Streamlit** renders the interactive web interface from Python.
- **Requests** sends bounded, timeout-protected calls to GitHub's REST API.
- **Pytest** runs the offline automated test suite during development and CI.
- **pytest-cov** measures which production lines the Pytest suite exercises and
  enforces the documented coverage floor.
- **Ruff** performs linting, import organization, and deterministic formatting.
- **uv** creates the cross-platform lock file used for reproducible CI and
  Streamlit Community Cloud installation.
- **Setuptools** builds and installs the `src/`-layout Python package.

The project deliberately avoids a GitHub SDK: a small set of REST endpoints is
enough, and a small Requests adapter keeps error handling and response
validation visible. It also deliberately avoids AI SDKs: deterministic rules
make every point explainable, repeatable, fast, and free to run.

## Local setup

Python 3.12 or newer is required.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

To reproduce the exact CI dependency environment instead, install uv and sync
the committed lock file:

```bash
python -m pip install uv==0.11.32
uv sync --frozen --extra dev
```

## Run the application

```bash
streamlit run streamlit_app.py
```

## Usage

1. Open the local Streamlit URL printed in the terminal.
2. Enter `owner/repository` or a public repository URL.
3. Select a **Review focus**, then select **Run review**. The focus prioritizes
   suggestions but never changes the numerical rubric.
4. Use **Overview** for the score and highest-impact actions, **Checks** to
   filter the evidence-backed results, and **Recommendations** for the full
   improvement plan.
5. Download a deterministic Markdown or JSON report when you want to save or
   share the review.
6. Open **Settings** to change appearance or provide an optional GitHub token.

Try `longinhk/github-portfolio-reviewer` to review this project itself. A cold
review normally makes three base GitHub requests plus at most ten bounded
text-file requests. A temporary connection or GitHub server failure may retry
one request once. Repeating the same review in one browser session within five
minutes uses the local response cache.

### Optional local token

Copy the example secrets file and replace its placeholder:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Never commit `.streamlit/secrets.toml`; it is excluded by `.gitignore`. For
public repositories, use no token or a fine-grained, least-privilege token with
only the read access the app needs. A token is held in process/session memory for
GitHub requests, but is not intentionally logged, persisted, or included in
reports. Revoke it if exposure is suspected.

For a public demo, configure an optional maintainer token through Streamlit
Secrets instead of asking recruiters to paste personal credentials. This is a
GitHub token only; the application never asks for an AI service key.

## Quality checks

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest --cov=github_portfolio_reviewer --cov-report=term-missing
```

The tests inject fake HTTP sessions, block accidental real requests, and enforce
the coverage threshold in `.coveragerc`. This keeps them fast, repeatable, and
independent of GitHub availability or rate limits.

GitHub Actions runs the same three checks for pushes to `main` and pull
requests. The workflow has read-only repository permissions.

## Deploy to Streamlit Community Cloud

1. Push the repository to GitHub.
2. In Streamlit Community Cloud, create an app from that repository and branch.
3. Set the entry point to `streamlit_app.py` and choose Python 3.12.
4. Optionally add `GITHUB_TOKEN = "..."` in the app's Secrets settings. Never
   commit the real value.
5. Choose a free `*.streamlit.app` subdomain, deploy, and test from a private
   browser window with small, large, valid, and invalid repository inputs.
6. Add the live URL to this README and the GitHub About section only after the
   deployment has succeeded.

Current Streamlit Community Cloud dependency discovery prioritizes `uv.lock`, so
the committed lock file supplies the reproducible environment and installs this
package from its `pyproject.toml`. See Streamlit's
[dependency-file order](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies)
and [secrets guidance](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management).
Deployment requires the repository owner's GitHub and Streamlit accounts. This
repository does not claim to be deployed until a working public URL is added.

## Required cost

The required monetary cost for this student/CV version is **US$0 per month**.

| Component | Required cost |
| --- | ---: |
| Python and open-source project libraries | $0 |
| Public GitHub repository and standard-runner CI | $0 |
| GitHub REST API | $0 |
| Streamlit Community Cloud and a `streamlit.app` address | $0 |
| AI API, model key, and database | $0 |
| **Required total** | **$0/month** |

GitHub currently documents a primary limit of 60 unauthenticated REST requests
per hour per originating IP and generally 5,000 per hour for authenticated
users. The optional token costs nothing, but it consumes the owner's allowance.
Streamlit Community Cloud is free, but inactive apps sleep and free resource
limits may change. Internet access, electricity, development time, a separately
purchased domain, paid monitoring, or different hosting are personal or
optional costs rather than requirements.

Sources: [Streamlit Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud),
[Streamlit limits and app hibernation](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app),
[GitHub REST API limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api),
and [GitHub Actions public-repository runners](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job).

## Student project scope and limitations

This project demonstrates Python architecture, API integration, deterministic
analysis, testing, CI, and deployment preparation. It is not a production
hiring, code-review, compliance, or security product.

- Only public GitHub repositories are supported.
- Reviews use the default branch. A branch or file URL identifies the repository
  but does not request analysis of that specific branch or file.
- Content inspection is intentionally limited to ten small text files with fixed
  slots: one security policy, one dependency updater, one `pyproject.toml`, one
  explicit test configuration, one coverage configuration, two workflows, and
  three test sources. Unused slots are not borrowed by another category.
- Python test inspection recognizes implementation signals but does not execute
  tests or prove correctness.
- Workflow and configuration parsing is deliberately conservative and may
  return partial credit when evidence is ambiguous.
- The high-confidence secret scan is bounded and is not a substitute for Git
  history scanning, dependency auditing, or a professional security review.
- Test/example certificate and key fixtures are treated as advisory evidence,
  but production-like paths remain failures requiring manual investigation.
- GitHub may truncate file trees for very large repositories; those reports are
  clearly marked provisional.
- Heuristics favor common project conventions and can produce false positives or
  false negatives for unusual ecosystems.
- The reviewer does not inspect every file, commit, branch, issue, pull request,
  branch-protection rule, or organization-level community setting.
- It cannot judge a developer's ability, originality, project usefulness, or
  suitability for employment, and it cannot guarantee uptime within free
  hosting and API limits.

Reports should be used as structured portfolio feedback, not as hiring evidence
or a security certification.

## Honest portfolio claims

It is accurate to say that this project uses Python 3.12, Streamlit, the GitHub
REST API, typed domain models, bounded evidence collection, deterministic
versioned scoring, offline automated tests, Ruff, and GitHub Actions.

Do not describe it as AI-powered, a complete repository analysis, a production
security scanner, an objective measure of code quality, 100% accurate, or used
by recruiters without real evidence. Do not claim 100% test coverage, guaranteed
secret detection, guaranteed uptime, or a live deployment until those statements
are independently true.

## Project documentation

- [Architecture and design decisions](docs/architecture.md)
- [Contribution guide](CONTRIBUTING.md)
- [Code of conduct](CODE_OF_CONDUCT.md)
- [Change history](CHANGELOG.md)
- [Security policy](SECURITY.md)

## Optional future work

- Let users compare two snapshots of the same repository.
- Add JavaScript/TypeScript-specific content checks beside the Python checks.
- Display live GitHub Actions status when API allowance permits.
- Calibrate rules against a larger, versioned corpus of representative
  repositories.

Accounts, payments, a database, an AI service, Docker, and microservices are not
needed for the CV version.

## License

This project is available under the [MIT License](LICENSE). Copyright © 2026
`longinhk`.
