import random
import sys
from collections.abc import Iterator

from rich.console import Console

from eye.persistence.port import SaveStore
from eye.session.game import Game
from eye.session.generation import Generation
from eye.tui import render, save, skilltree_menu
from eye.tui._input import next_line
from eye.tui.chooser import TUIActionChooser


def main() -> None:
    run(Console(), iter(sys.stdin), random.Random())  # noqa: S311 -- game RNG, not cryptographic


def run(
    console: Console,
    input_source: Iterator[str],
    rng: random.Random,
    save_store: SaveStore | None = None,
) -> None:
    chooser = TUIActionChooser(console, input_source)
    game = save.load_or_new(rng, chooser, save_store)

    try:
        _play(console, game, input_source, save_store)
    except KeyboardInterrupt:
        console.print("\nProgress since your last generation ended is not saved.")


def _play(console: Console, game: Game, input_source: Iterator[str], save_store: SaveStore | None) -> None:
    while True:
        generation = game.start_generation()
        _play_generation(console, generation, input_source)

        render.generation_ended(console, generation)
        render.events(console, game.end_generation(generation))
        save.persist(game, save_store)

        skilltree_menu.run(console, game.skill_tree, input_source, on_purchase=lambda: save.persist(game, save_store))

        if not _prompt_yes_no(console, input_source, "Play another generation?"):
            return


def _play_generation(console: Console, generation: Generation, input_source: Iterator[str]) -> None:
    while not generation.died:
        for chunk in generation.advance():
            render.events(console, chunk)
        if generation.died:
            break
        if generation.is_seed_ready:
            if _prompt_yes_no(console, input_source, "Plant your seed here?"):
                render.events(console, generation.plant_seed())
        else:
            _await_keypress(console, input_source)


def _prompt_yes_no(console: Console, input_source: Iterator[str], question: str) -> bool:
    console.print(f"{question} [y/n]")
    return next_line(input_source, "app.run").strip().lower() in ("y", "yes")


def _await_keypress(console: Console, input_source: Iterator[str]) -> None:
    console.print("Press enter to continue...")
    next_line(input_source, "app.run")
