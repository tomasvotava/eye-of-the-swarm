# The Eye of the Swarm

## Releasing

Pushing a `v*` tag runs `.github/workflows/release.yml`, which builds the web archive
(`make web-archive`), attaches it to a GitHub release with generated notes, and pushes it to the
itch.io `html5` channel of `tomasvotava/the-eye-of-the-swarm`.

1. Bump the version: `uv version <X.Y.Z>`, commit, and merge to `master`.
2. Tag the merged commit and push the tag: `git tag vX.Y.Z && git push origin vX.Y.Z`.
   The workflow fails if the tag doesn't match the project version.

One-time setup:

- The `itch.io` GitHub environment holds the `BUTLER_API_KEY` secret (an itch.io API key) and
  allows `master` and `v*` tags.
- After the first push to `html5`, mark that channel as playable in browser on the itch.io
  project page. Butler can't set this.

To build the archive locally, run `make web-archive`; it writes `build/web.zip`.
