from pathlib import Path

import pygame
import pytest

from eye.combat.effects import EffectName
from eye.gui.assets import build_art_atlas
from eye.gui.effect_legend import draw_effect_legend, legend_effects
from eye.gui.widgets import SpriteBuffIcon


def test_legend_effects_lists_each_effect_once_in_effect_name_order() -> None:
    effects = [EffectName.RUNT, EffectName.TOXICITY, EffectName.RUNT]

    assert legend_effects(effects) == (EffectName.TOXICITY, EffectName.RUNT)


@pytest.mark.parametrize("effects", [(), tuple(EffectName)])
def test_draw_effect_legend_does_not_raise_from_empty_to_every_effect(effects: tuple[EffectName, ...]) -> None:
    atlas = build_art_atlas(Path("eye/gui/sprites"))

    draw_effect_legend(pygame.Surface((640, 480)), effects, lambda effect: SpriteBuffIcon(atlas, effect))
