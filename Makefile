.PHONY: serve web-archive bump run play dev-assets

run:
	uv run python -m eye.main

serve:
	uv run pygbag .

web-archive:
	uv run pygbag --archive .

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
