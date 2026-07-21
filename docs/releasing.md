# Release process

Releases are deliberate maintainer actions. Passing CI does not by itself
authorize publishing packages, creating remote releases, or pushing tags.

## Prepare

1. Choose the release version and move relevant `Unreleased` entries in
   `CHANGELOG.md` into a dated version section.
2. Confirm `pyproject.toml`, `grab2md --version`, `python -m grab2md --version`,
   wheel metadata, and extension metadata have the intended versions.
3. Recheck `grab2md` availability and ownership on TestPyPI and PyPI. A 404
   observed before release is not a reservation.
4. Start from a clean checkout with only the intended release commit.
5. Confirm the exact release commit is on protected `main` with every required
   hosted check successful; a green run on a different SHA is not evidence for
   the artifact being published.

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

## Stage and publish

1. Upload the already-checked artifacts to TestPyPI without rebuilding:

   ```bash
   poetry run twine upload --repository testpypi dist/*
   ```

   Install the exact uploaded version in a fresh environment. Do not pass a
   token on the command line; use Twine's environment/keyring configuration.
2. Exercise `grab2md --help`, `grab2md --version`, `python -m grab2md --help`,
   local conversion, and a local-server URL conversion.
3. Obtain explicit maintainer approval for the public release.
4. Create a signed tag when signing is configured, otherwise an annotated tag:

   ```bash
   git tag -s vX.Y.Z -m "grab2md X.Y.Z"
   # or: git tag -a vX.Y.Z -m "grab2md X.Y.Z"
   ```

5. Push the approved tag, publish the already-tested artifacts to PyPI, and
   create the release using the same changelog text and checksums.
6. Install from PyPI in a new environment and repeat the entry-point smoke test.

If any artifact, version, checksum, or smoke result differs, stop the release;
do not rebuild under the same version.

## Post-alpha provenance hardening

After the first authorized alpha establishes the `grab2md` project identity on
PyPI, replace long-lived upload credentials with
[PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/) through a
protected GitHub release environment. Add
[GitHub artifact attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations)
for the distributions built by that workflow.

That automation must preserve this release policy: a maintainer explicitly
authorizes publication, and the workflow publishes the exact artifacts that
passed the protected release gates without rebuilding them. This is
post-alpha hardening, not authorization to publish the first alpha.
