# The Eye of the Swarm

## Releasing

Pushing a `v*` tag runs `.github/workflows/release.yml`, which builds the web archive
(`make web-archive`) and native executables for Linux x86_64, Windows x86_64 and macOS arm64
(`make exe` on each OS, through `.github/workflows/native-build.yml`). It attaches all four
archives to a GitHub release with generated notes, then pushes them to the itch.io channels
`html5`, `linux`, `windows` and `osx` of `tomasvotava/the-eye-of-the-swarm`. If any build fails,
nothing is published.

The macOS build is unsigned, so Gatekeeper blocks the first launch. On macOS 15 and later, try to
open the app once, then choose Open Anyway under System Settings > Privacy & Security. On earlier
versions, right-click the app and choose Open.

To cut a release, run `make bump PART=patch|minor|major` on an up-to-date, clean `master`. It bumps
`project.version` with `uv version --bump`, commits `pyproject.toml` and `uv.lock` straight to
`master`, and tags the commit `vX.Y.Z`. Nothing is pushed; push both with `git push --atomic origin
master vX.Y.Z` to trigger the release. The workflow fails if a tag doesn't match the project
version. To discard an unpushed bump, run `git tag -d vX.Y.Z && git reset --hard origin/master`.

One-time setup:

- The `itch.io` GitHub environment holds the `BUTLER_API_KEY` secret (an itch.io API key) and
  allows `master` and `v*` tags.
- After the first push to `html5`, mark that channel as playable in browser on the itch.io
  project page. Butler can't set this.
- Releasing pushes to `master` directly, so the branch protection needs a bypass for whoever
  releases, and the `v*` tag ruleset has to let them create tags.

To build the archive locally, run `make web-archive`; it writes `build/web.zip`. To build the
native executable for the host OS, run `make exe`; it writes `dist/eye-of-the-swarm-<os>.zip`.
Pull requests that touch the game or its build run the native build on all three OSes and upload
the archives as workflow artifacts, without publishing.
