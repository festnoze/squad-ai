import numpy as np
import pytest

from ascii_overlay.glyphs import CELL_SIZES, get_table
from ascii_overlay.matcher import (
    MatchParams,
    MatchState,
    frame_to_indices,
    luminance,
    match_blocks,
    render,
    to_blocks,
    to_text,
)


def frame_from_indices(indices, table, dark_ink=False):
    """Build a BGRA frame that displays exactly these glyphs (what the overlay would show)."""
    img = render(indices, table, dark_ink)
    return np.repeat(img[..., None], 4, axis=2).astype(np.uint8)


def test_luminance_range_and_weights():
    f = np.zeros((2, 2, 4), dtype=np.uint8)
    f[0, 0] = (255, 255, 255, 255)
    f[0, 1] = (0, 0, 255, 255)  # BGRA: pure red
    f[1, 0] = (255, 0, 0, 255)  # BGRA: pure blue
    y = luminance(f)
    assert y.dtype == np.float32 and y.shape == (2, 2)
    assert y[0, 0] > 0.99
    assert y[1, 1] == 0.0
    assert 0.25 < y[0, 1] < 0.35  # red weighs ~0.3
    assert 0.08 < y[1, 0] < 0.15  # blue weighs ~0.11
    # Strided views (a region of a larger capture) must give the same result.
    big = np.zeros((4, 4, 4), dtype=np.uint8)
    big[1:3, 1:3] = f
    assert np.array_equal(luminance(big[1:3, 1:3]), y)


def test_to_blocks_is_row_major_cells():
    g = np.arange(32 * 16, dtype=np.float32).reshape(32, 16)
    b = to_blocks(g, 8, 16)
    assert b.shape == (4, 128)
    assert b[0, 0] == g[0, 0] and b[1, 0] == g[0, 8] and b[2, 0] == g[16, 0]


def test_identity_every_glyph_is_recovered_from_its_own_pixels():
    """Feeding the matcher the displayed glyph must give back that glyph, for all of them."""
    table = get_table(8, 16)
    k = table.count
    cols = 12
    rows = -(-k // cols)
    idx = np.zeros((rows, cols), dtype=np.int32)
    idx.flat[:k] = np.arange(k)
    frame = frame_from_indices(idx, table)
    params = MatchParams(hysteresis=0.0)
    out = frame_to_indices(frame, table, params)
    assert np.array_equal(out, idx)


def test_identity_holds_in_negative_on_a_black_on_white_picture():
    table = get_table(8, 16)
    idx = np.array([[table.index_of(c) for c in "Hello/"], [table.index_of(c) for c in "|_^~@ "]])
    frame = frame_from_indices(idx, table, dark_ink=True)  # black glyphs on white
    out = frame_to_indices(frame, table, MatchParams(hysteresis=0.0, negative=True))
    assert np.array_equal(out, idx)


def test_black_ink_is_display_only_and_negative_is_source_only():
    """Black ink must not change the chosen glyphs; negative must, by inverting the source."""
    table = get_table(8, 16)
    frame = np.zeros((32, 64, 4), dtype=np.uint8)
    frame[:, :32, :3] = 255  # left half white, right half black
    idx = frame_to_indices(frame, table, MatchParams(hysteresis=0.0))
    densest = int(table.coverage.argmax())
    assert (idx[:, :4] == densest).all() and (idx[:, 4:] == 0).all()
    white_on_black = render(idx, table, dark_ink=False)
    black_on_white = render(idx, table, dark_ink=True)
    assert np.array_equal(black_on_white, 255 - white_on_black)  # same glyphs, colours swapped
    neg = frame_to_indices(frame, table, MatchParams(hysteresis=0.0, negative=True))
    assert (neg[:, :4] == 0).all() and (neg[:, 4:] == densest).all()  # dark pixels are now the ink


def test_black_frame_gives_spaces_and_white_frame_gives_densest_glyph():
    table = get_table(8, 16)
    black = np.zeros((32, 64, 4), dtype=np.uint8)
    out = frame_to_indices(black, table, MatchParams())
    assert (out == 0).all()
    white = np.full((32, 64, 4), 255, dtype=np.uint8)
    out = frame_to_indices(white, table, MatchParams())
    densest = int(table.coverage.argmax())
    assert (out == densest).all()


def test_position_beats_ratio_for_a_bottom_stroke():
    """A bright line along the cell floor must pick an underscore-like glyph, not a mid-cell one of equal ink."""
    table = get_table(8, 16)
    frame = np.zeros((16, 8, 4), dtype=np.uint8)
    frame[13:15, :, :3] = 255
    out = frame_to_indices(frame, table, MatchParams(hysteresis=0.0))
    ch = table.chars[out[0, 0]]
    assert ch in "_.,", ch


def _flat_coverages(table, params, levels):
    covs = []
    for level in levels:
        frame = np.full((16 * 4, 8 * 4, 4), level, dtype=np.uint8)
        out = frame_to_indices(frame, table, params)
        assert (out == out[0, 0]).all(), "a flat area must be one single glyph"
        covs.append(float(table.coverage[out[0, 0]]))
    return covs


def test_auto_tone_spans_space_to_densest_glyph():
    """Black -> space, white -> densest glyph, and every grey in between, monotonically."""
    table = get_table(8, 16)
    cov_max = float(table.coverage.max())
    levels = (0, 5, 40, 80, 128, 180, 220, 255)
    covs = _flat_coverages(table, MatchParams(hysteresis=0.0), levels)
    assert covs[0] == 0.0 and covs[1] == 0.0  # black and near-black are the space
    assert covs[-1] == cov_max  # white is the densest glyph
    assert all(a <= b for a, b in zip(covs, covs[1:])), covs
    assert 0.0 < covs[2] <= 0.25 * cov_max  # dark grey is nearly empty
    assert 0.35 * cov_max <= covs[4] <= 0.65 * cov_max  # mid grey is mid density
    assert covs[5] < cov_max  # bright grey is not yet saturated
    assert len(set(covs)) >= 6  # the ramp really uses the range


def test_literal_mode_keeps_the_exact_ink_ratio_and_saturates_early():
    table = get_table(8, 16)
    cov_max = float(table.coverage.max())
    covs = _flat_coverages(table, MatchParams(hysteresis=0.0, auto_tone=False), (0, 30, 60, 128, 200, 255))
    assert covs[0] == 0.0
    assert all(a <= b for a, b in zip(covs, covs[1:])), covs
    assert 0.0 < covs[1] < covs[2] < cov_max
    assert covs[3] == covs[4] == covs[5] == cov_max  # everything above ~30 % is the densest glyph


def test_exposure_still_dims_the_output():
    table = get_table(8, 16)
    frame = np.full((16 * 4, 8 * 4, 4), 200, dtype=np.uint8)
    plain = frame_to_indices(frame, table, MatchParams(hysteresis=0.0))
    dim = frame_to_indices(frame, table, MatchParams(hysteresis=0.0, exposure=0.3))
    assert table.coverage[plain].mean() > table.coverage[dim].mean() > 0.0


def test_a_stroke_keeps_its_shape_whatever_the_background_level():
    """A vertical stroke on a grey background must still be a vertical-stroke glyph, not a dot or a blob."""
    table = get_table(8, 16)
    vertical = {c for c in "|Il!1[]" if c in table.chars}
    for bg in (0, 60, 120):
        frame = np.full((16, 8, 4), bg, dtype=np.uint8)
        frame[1:15, 4:5, :3] = 255  # one pixel wide, fourteen tall, on the column of the font's '|'
        out = frame_to_indices(frame, table, MatchParams(hysteresis=0.0))
        ch = table.chars[out[0, 0]]
        ink = table.bitmaps[out[0, 0]] > 0
        rows = np.nonzero(ink.any(axis=1))[0]
        central = ink[:, 3:5].sum() / ink.sum()  # ink share in the two columns around the stroke
        # On a brighter background the tone term may pick a denser vertical glyph (e.g. '}'),
        # never a dot or a blob: tall, and most of the ink on the stroke's columns.
        assert ch in vertical or (rows.max() - rows.min() >= 8 and central >= 0.6), (bg, ch, central)


def test_identity_holds_in_auto_tone_at_every_cell_size():
    """A displayed glyph has full contrast, so shape alone decides and gives it back."""
    from ascii_overlay.glyphs import cell_for_height

    for cell in (*CELL_SIZES, cell_for_height(4), cell_for_height(11), cell_for_height(64)):
        table = get_table(*cell)
        idx = np.arange(table.count, dtype=np.int32).reshape(1, -1)
        frame = frame_from_indices(idx, table)
        out = frame_to_indices(frame, table, MatchParams(hysteresis=0.0))
        assert np.array_equal(out, idx), cell


def test_hysteresis_keeps_previous_glyph_within_margin():
    table = get_table(8, 16)
    # Literal mode: the blocks below are blurred glyph maps, which auto tone would stretch.
    params = MatchParams(hysteresis=0.5, blur=False, auto_tone=False)
    state = MatchState()
    d = table.dim
    a, b = table.index_of("a"), table.index_of("e")
    # Frame 1: exactly 'a'. Frame 2: a block half way between 'a' and 'e' → near tie.
    blocks1 = table.features[[a]]
    blocks2 = 0.5 * (table.features[[a]] + table.features[[b]])
    out1 = match_blocks(blocks1, table, params, state)
    assert out1[0] == a
    out2 = match_blocks(blocks2, table, params, state)
    assert out2[0] == a  # kept by hysteresis
    # Without hysteresis the tie may go either way but the state does not force it.
    out3 = match_blocks(table.features[[b]], table, MatchParams(hysteresis=0.0, blur=False, auto_tone=False), MatchState())
    assert out3[0] == b
    assert state.prev_idx is not None and state.prev_idx.shape == (1,)
    assert d == 128


def test_state_resets_when_grid_changes():
    table = get_table(8, 16)
    state = MatchState()
    f1 = np.zeros((32, 64, 4), dtype=np.uint8)
    frame_to_indices(f1, table, MatchParams(), state)
    assert state.shape == (2, 8)
    f2 = np.zeros((48, 64, 4), dtype=np.uint8)
    frame_to_indices(f2, table, MatchParams(), state)
    assert state.shape == (3, 8) and state.prev_idx.shape == (24,)


def test_render_is_strictly_two_colours_and_text_matches():
    table = get_table(8, 16)
    idx = np.array([[table.index_of(c) for c in "AB"], [table.index_of(c) for c in " #"]])
    img = render(idx, table)
    assert img.shape == (32, 16)
    assert set(np.unique(img)).issubset({0, 255})
    assert to_text(idx, table) == "AB\n #"
    inv = render(idx, table, dark_ink=True)
    assert np.array_equal(inv, 255 - img)


@pytest.mark.parametrize("cell", [(4, 8), (16, 32)])
def test_identity_at_other_cell_sizes(cell):
    table = get_table(*cell)
    idx = np.arange(table.count, dtype=np.int32).reshape(1, -1)
    frame = frame_from_indices(idx, table)
    out = frame_to_indices(frame, table, MatchParams(hysteresis=0.0))
    assert np.array_equal(out, idx)
