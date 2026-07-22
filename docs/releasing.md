# Release process

Releases are deliberate maintainer actions. Passing CI does not by itself
authorize publishing packages, creating remote releases, or pushing tags.

## Prepare

1. Choose the release version and move relevant `Unreleased` entries in
   `CHANGELOG.md` into a dated version section.
2. Confirm `pyproject.toml`, `grab2md --version`, `python -m grab2md --version`,
   wheel metadata, and extension metadata have the intended versions.
3. Recheck the `grab2md` project state and Trusted Publisher mapping on both
   indexes. TestPyPI already hosts staging rehearsals and must authorize
   repository `jkindrix/grab2md`, workflow `publish.yml`, and environment
   `testpypi`. Production PyPI must have the equivalent pending or established
   mapping for environment `pypi`. A pending publisher does not reserve a new
   project name, so confirm production availability immediately before the
   first upload.
4. Start from a clean checkout with only the intended release commit.
5. Confirm the exact release commit is on protected `main` with every required
   hosted check successful; a green run on a different SHA is not evidence for
   the artifact being published.
6. Confirm the GitHub `pypi` environment requires explicit approval. The
   `testpypi` environment may omit approval, but both environments must match
   their index-side Trusted Publisher configuration exactly.

## Verify and build

```bash
poetry sync --with dev
poetry check
poetry run pre-commit run --all-files
poetry run pre-commit run --all-files --hook-stage pre-push
node --test extension/tests/*.test.js
node extension/tests/chromium-smoke.js
./deploy.sh --dry-run
poetry run twine check dist/*
poetry run python scripts/release_smoke.py dist/*.whl \
  --expected-version "$(poetry version --short)"
sha256sum dist/* > dist/SHA256SUMS
```

Record the commit, operating system, Python version, Poetry version, commands,
test totals, and checksums in the release notes.

The successful `Build and wheel smoke test` job retains the wheel and source
distribution together as the `release-distributions` artifact for 30 days.
Record that CI run ID. The publishing workflow downloads that exact bundle and
refuses unsuccessful, non-`main`, mismatched-SHA, or mismatched-version runs.

## Stage on TestPyPI

Test indexes are immutable just like production indexes. A version used for an
earlier rehearsal cannot be rebuilt or reused for production. Before the final
staging pass, choose a version absent from both indexes, date its changelog
section, build it once on protected `main`, and use that exact CI artifact for
both TestPyPI and PyPI.

1. From the release commit on `main`, manually dispatch `publish.yml` with
   target `testpypi`, the successful CI run ID, and the exact version. Approve
   the protected environment if configured. The existing TestPyPI project
   accepts the upload through OIDC; no long-lived token is required. On a new
   index, a matching pending publisher can create the project on first use.
2. Install the exact uploaded version in a fresh environment and exercise
   `grab2md --help`, `grab2md --version`, `python -m grab2md --help`, local
   conversion, and a local-server URL conversion.
3. Compare the index artifact hashes with the hashes printed by the publish
   workflow. If any artifact, version, checksum, or smoke result differs, stop
   the release; do not rebuild under the same version.

For a manual local rehearsal that does not upload anything:

```bash
./deploy.sh --dry-run
```

## Authorize and publish to PyPI

1. Obtain explicit maintainer approval for the public release.
2. Create a signed tag when signing is configured, otherwise an annotated tag:

   ```bash
   git tag -s vX.Y.Z -m "grab2md X.Y.Z"
   # or: git tag -a vX.Y.Z -m "grab2md X.Y.Z"
   ```

3. Push the approved tag. From that exact tag, manually dispatch `publish.yml`
   with target `pypi`, the same successful CI run ID, and the exact version.
   The workflow requires the tag, CI, and artifact commit SHA to agree and then
   pauses at the protected `pypi` environment for approval.
4. Create the GitHub release using the same changelog text and the workflow's
   checksums.
5. Install from PyPI in a new environment and repeat the entry-point smoke test.

If any artifact, version, checksum, or smoke result differs, stop the release;
do not rebuild under the same version.

## Provenance boundary

The first alpha and later releases use
[PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/) through
protected GitHub environments. The pinned official publishing action creates
and uploads PEP 740 attestations for both distributions. Pending publishers can
create a new project on first use, but they do not reserve the project name.

The workflow does not turn green CI into publication authority: a maintainer
still selects the target and exact CI run, public publication additionally
requires the matching signed or annotated tag, and the protected `pypi`
environment supplies the final approval. No release artifact is rebuilt during
publication.
