import pytest

from motioncues import config, layout, sprites

SCREEN = (1280, 800)


# --------------------------------------------------------------------------
# layout
# --------------------------------------------------------------------------

def test_dot_count_is_per_edge():
    appearance = config.validate({})["appearance"]
    appearance["count"] = 10
    appearance["edges"] = ["left", "right"]
    assert len(layout.dot_positions(*SCREEN, appearance)) == 20

    appearance["edges"] = ["left", "right", "top", "bottom"]
    assert len(layout.dot_positions(*SCREEN, appearance)) == 40


def test_dots_sit_at_the_configured_padding_from_each_edge():
    appearance = config.validate({})["appearance"]
    appearance["edges"] = ["left", "right", "top", "bottom"]
    appearance["edge_padding"] = 30.0
    points = layout.dot_positions(*SCREEN, appearance)

    assert any(x == 30.0 for x, _ in points)
    assert any(x == SCREEN[0] - 30.0 for x, _ in points)
    assert any(y == 30.0 for _, y in points)
    assert any(y == SCREEN[1] - 30.0 for _, y in points)


def test_dots_stay_on_screen_and_respect_the_end_margin():
    appearance = config.validate({})["appearance"]
    appearance["edges"] = ["left"]
    appearance["margin_fraction"] = 0.1
    points = layout.dot_positions(*SCREEN, appearance)

    ys = [y for _, y in points]
    assert min(ys) >= SCREEN[1] * 0.1
    assert max(ys) <= SCREEN[1] * 0.9


def test_single_dot_is_centred_on_its_edge():
    appearance = config.validate({})["appearance"]
    appearance["count"] = 1
    appearance["edges"] = ["left"]
    points = layout.dot_positions(*SCREEN, appearance)
    assert len(points) == 1
    assert points[0][1] == pytest.approx(SCREEN[1] / 2, abs=1.0)


@pytest.mark.parametrize("style", ["even", "corners", "clustered"])
def test_every_layout_produces_the_requested_number_of_dots(style):
    appearance = config.validate({})["appearance"]
    appearance["layout"] = style
    appearance["count"] = 11
    appearance["edges"] = ["left"]
    assert len(layout.dot_positions(*SCREEN, appearance)) == 11


def test_corner_layout_keeps_dots_away_from_the_middle():
    appearance = config.validate({})["appearance"]
    appearance["layout"] = "corners"
    appearance["count"] = 12
    appearance["edges"] = ["left"]
    ys = [y for _, y in layout.dot_positions(*SCREEN, appearance)]
    middle = [y for y in ys if 0.4 * SCREEN[1] < y < 0.6 * SCREEN[1]]
    assert not middle


# --------------------------------------------------------------------------
# sprites
# --------------------------------------------------------------------------

def channels(sprite):
    return [tuple(sprite.data[i:i + 4]) for i in range(0, len(sprite.data), 4)]


def test_sprite_is_square_padded_and_centred():
    sprite = sprites.render_sprite(10.0, "circle", (255, 255, 255), 1.0, padding=6)
    assert sprite.width == sprite.height
    assert sprite.width >= 10 + 12
    assert sprite.center_x == sprite.width / 2


def test_sprite_alpha_never_exceeds_requested_opacity():
    sprite = sprites.render_sprite(12.0, "circle", (255, 255, 255), 0.5)
    assert max(alpha for *_rgb, alpha in channels(sprite)) <= int(0.5 * 255) + 1


def test_sprite_channels_are_premultiplied():
    """Colour channels above alpha would produce halos on a compositor."""

    sprite = sprites.render_sprite(14.0, "circle", (255, 255, 255), 0.4)
    for blue, green, red, alpha in channels(sprite):
        assert blue <= alpha and green <= alpha and red <= alpha


def test_sprite_colour_is_carried_through():
    sprite = sprites.render_sprite(16.0, "square", (255, 0, 0), 1.0)
    opaque = [px for px in channels(sprite) if px[3] > 250]
    assert opaque
    for blue, green, red, _alpha in opaque:
        assert red > 250 and green < 5 and blue < 5


def test_sprite_border_is_transparent_so_a_blit_erases_the_old_position():
    sprite = sprites.render_sprite(8.0, "circle", (255, 255, 255), 1.0, padding=4)
    width = sprite.width
    pixels = channels(sprite)
    corners = [pixels[0], pixels[width - 1], pixels[-width], pixels[-1]]
    assert all(pixel[3] == 0 for pixel in corners)


def test_ring_is_hollow_but_circle_is_not():
    ring = sprites.render_sprite(20.0, "ring", (255, 255, 255), 1.0)
    circle = sprites.render_sprite(20.0, "circle", (255, 255, 255), 1.0)
    centre = int(ring.center_y) * ring.width + int(ring.center_x)
    assert ring.data[centre * 4 + 3] == 0
    assert circle.data[centre * 4 + 3] > 250


@pytest.mark.parametrize("shape", ["circle", "ring", "square", "diamond"])
def test_every_shape_renders_something(shape):
    sprite = sprites.render_sprite(12.0, shape, (255, 255, 255), 1.0)
    assert any(sprite.data[i + 3] for i in range(0, len(sprite.data), 4))


def test_square_covers_more_area_than_circle_and_diamond():
    def coverage(shape):
        sprite = sprites.render_sprite(20.0, shape, (255, 255, 255), 1.0)
        return sum(sprite.data[i + 3] for i in range(0, len(sprite.data), 4))

    assert coverage("square") > coverage("circle") > coverage("diamond")


def test_alpha_scaling_dims_uniformly_and_stays_premultiplied():
    sprite = sprites.render_sprite(14.0, "circle", (255, 255, 255), 1.0)
    faded = sprites.scale_sprite_alpha(sprite, 0.5)

    assert faded.width == sprite.width
    for blue, green, red, alpha in channels(faded):
        assert blue <= alpha and green <= alpha and red <= alpha
    assert max(a for *_c, a in channels(faded)) == pytest.approx(127, abs=2)


def test_alpha_scaling_is_a_no_op_at_full_strength():
    sprite = sprites.render_sprite(10.0, "circle", (255, 255, 255), 1.0)
    assert sprites.scale_sprite_alpha(sprite, 1.0) is sprite


def test_sprite_for_reads_the_appearance_block():
    appearance = config.validate({})["appearance"]
    appearance.update(size=20.0, shape="square", color="#FF0000", opacity=1.0)
    sprite = sprites.sprite_for(appearance)
    opaque = [px for px in channels(sprite) if px[3] > 250]
    assert opaque and all(px[2] > 250 for px in opaque)


def test_tile_padding_covers_a_frame_of_travel():
    """A blit must erase the previous frame, so padding >= per-frame motion."""

    from motioncues.overlay import TILE_PADDING

    cfg = config.validate({})
    max_travel = cfg["motion"]["max_travel"]
    tau_response = 0.02 + 0.6 * cfg["motion"]["smoothing"]
    import math
    per_frame = max_travel * (1.0 - math.exp(-(1.0 / 60.0) / tau_response))
    assert per_frame <= TILE_PADDING
