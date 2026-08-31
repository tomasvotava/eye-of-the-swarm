.PHONY: serve run play

run:
	uv run python -m eye.main

serve:
	uv run pygbag eye

play:
	uv run python -m eye.tui
