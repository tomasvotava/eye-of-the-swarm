.PHONY: serve run

run:
	uv run python -m eye.main

serve:
	uv run pygbag eye
