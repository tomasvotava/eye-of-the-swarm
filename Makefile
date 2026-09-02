.PHONY: serve run play dev-assets

run:
	uv run python -m eye.main

serve:
	uv run pygbag eye

play:
	uv run python -m eye.tui

dev-assets:
	EYE_DEV_ASSET_VIEWER=1 uv run python -m eye.main
