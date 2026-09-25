.PHONY: serve web-archive exe bump run play dev-assets

run:
	uv run python -m eye.main

serve:
	uv run pygbag .

web-archive:
	uv run pygbag --archive .

exe:
	uv run pyinstaller --noconfirm --distpath dist --workpath build/pyinstaller eye.spec
# ditto keeps the .app's symlinks, which its code signature covers; zipfile would copy their targets.
ifeq ($(shell uname -s),Darwin)
	ditto -c -k --sequesterRsrc --keepParent "dist/The Eye of the Swarm.app" dist/eye-of-the-swarm-osx.zip
else
	uv run python -c "import shutil, sys; os_name = {'linux': 'linux', 'win32': 'windows'}[sys.platform]; shutil.make_archive(f'dist/eye-of-the-swarm-{os_name}', 'zip', 'dist', 'eye-of-the-swarm')"
endif

bump:
	@test -n "$(PART)" || { echo "usage: make bump PART=patch|minor|major" >&2; exit 1; }
	@test "$$(git branch --show-current)" = master || { echo "bump: not on master" >&2; exit 1; }
	@test -z "$$(git status --porcelain)" || { echo "bump: working tree is not clean" >&2; exit 1; }
	@git fetch -q origin master
	@test "$$(git rev-parse HEAD)" = "$$(git rev-parse origin/master)" || { echo "bump: master is not level with origin/master" >&2; exit 1; }
	uv version --bump $(PART)
	git add pyproject.toml uv.lock
	git commit -m "chore: bump version to $$(uv version --short)" || { git restore --staged --worktree pyproject.toml uv.lock; exit 1; }
	git tag "v$$(uv version --short)"
	@echo "Tagged v$$(uv version --short). Push with: git push --atomic origin master v$$(uv version --short)"

play:
	uv run python -m eye.tui

dev-assets:
	EYE_DEV_ASSET_VIEWER=1 uv run python -m eye.main
