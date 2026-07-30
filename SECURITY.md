# Security policy

## Scope

This application analyzes public repository metadata, README text, file paths,
and a bounded allowlist of small text files. Its high-confidence pattern checks
are not a complete secret scan, dependency audit, or security certification. A
risky filename or pattern is only a prompt for manual inspection.

## Reporting a vulnerability

Do not post access tokens, suspected secrets, or exploit details in a public
issue. Use GitHub's private vulnerability reporting for this repository when it
is enabled. If it is unavailable, open a public issue containing no sensitive
details and ask the maintainer for a private contact channel.

Include the affected version, impact, and safe reproduction steps. Please allow
the maintainer time to investigate before public disclosure.

## Token handling

The optional GitHub token is sent only in the GitHub API authorization header.
The application does not intentionally log, persist, or include it in reports.
Use the least privilege needed for reading public repository metadata and revoke
the token if you suspect exposure.

The application does not use an AI API or accept an AI model key.
