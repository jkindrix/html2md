# Security policy

## Supported versions

grab2md has no stable public release. Security fixes are developed only on the
current `main` branch and the latest source-alpha line. Older tags are retained
for provenance and should not be assumed to receive backports.

## Report a vulnerability privately

Email `jkindrix@gmail.com` with the subject `grab2md security report`. Include:

- the affected commit or version;
- the acquisition path or extension mode involved;
- reproduction steps and the expected security boundary;
- impact and any known prerequisites; and
- whether coordinated disclosure has a deadline.

Do not include real cookies, tokens, browser databases, private storage-state
files, or sensitive page content. Use synthetic fixtures and redact logs. Do
not open a public issue until the maintainer has acknowledged that disclosure
is safe.

This is a volunteer alpha project with no guaranteed response SLA. Expect an
acknowledgement target of seven days; if no acknowledgement arrives, send one
follow-up. TestPyPI artifacts are staging-only, and production package
publication and operational use remain unsupported. Users should assess the
documented network and credential boundaries before using the source on
sensitive workloads.
