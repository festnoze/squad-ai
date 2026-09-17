import numpy as np
import pytest

from ascii_overlay.glyphs import (
    CELL_SIZES,
    MAX_CELL_HEIGHT,
    MIN_CELL_HEIGHT,
    PRINTABLE,
    blur_adjoint_3x3,
    blur_matrix,
    box_blur_3x3,
    build_table,
    cell_for_height,
    fold_blur,
    get_table,
    load_table,
    save_table,
)


@pytest.mark.parametrize("cell", CELL_SIZES)
def test_table_shapes_and_binary_values(cell):
    table = get_table(*cell)
    cw, ch = cell
    assert table.bitmaps.shape == (table.count, ch, cw)
    assert table.features.shape == (table.count, ch * cw)
    assert table.coverage.shape == (table.count,)
    assert set(np.unique(table.bitmaps)).issubset({0, 255})
    assert table.features.min() >= 0.0 and table.features.max() <= 1.0


def test_space_is_index_zero_and_blank():
    table = get_table(8, 16)
    assert table.chars[0] == " "
    assert table.coverage[0] == 0.0
    assert not table.bitmaps[0].any()


def test_no_duplicate_bitmaps_and_most_glyphs_survive():
    table = get_table(8, 16)
    keys = {table.bitmaps[k].tobytes() for k in range(table.count)}
    assert len(keys) == table.count
    # Binarisation may merge a few glyphs (e.g. ' and `), never dozens.
    assert table.count >= len(PRINTABLE) - 6, table.chars


def test_coverage_orders_dense_over_sparse():
    table = get_table(8, 16)
    cov = {c: table.coverage[table.index_of(c)] for c in "@#.:- " if c in table.chars}
    assert cov["@"] > cov[":"] > cov["."] > cov[" "]
    assert cov["#"] > cov["-"]


def test_glyph_shapes_land_where_expected():
    """Position matters, not just ratio: a '_' sits at the bottom, a '^' in the upper half."""
    table = get_table(8, 16)
    under = table.bitmaps[table.index_of("_")] > 0
    caret = table.bitmaps[table.index_of("^")] > 0
    rows_under = np.nonzero(under.any(axis=1))[0]
    rows_caret = np.nonzero(caret.any(axis=1))[0]
    assert rows_under.min() >= 16 * 0.6
    assert rows_caret.max() <= 16 * 0.6
    pipe = table.bitmaps[table.index_of("|")] > 0
    cols_pipe = np.nonzero(pipe.any(axis=0))[0]
    assert cols_pipe.max() - cols_pipe.min() <= 2  # a thin vertical stroke


def test_box_blur_preserves_mean_and_bounds():
    rng = np.random.default_rng(0)
    img = rng.random((5, 16, 8), dtype=np.float32)
    out = box_blur_3x3(img)
    assert out.shape == img.shape
    assert out.min() >= 0.0 and out.max() <= 1.0
    # With edge replication a constant image is unchanged.
    const = np.full((2, 16, 8), 0.3, dtype=np.float32)
    assert np.allclose(box_blur_3x3(const), 0.3, atol=1e-6)


def test_save_and_load_roundtrip(tmp_path):
    table = build_table(8, 16)
    path = tmp_path / "t.npz"
    save_table(table, path)
    back = load_table(path)
    assert back.chars == table.chars
    assert np.array_equal(back.bitmaps, table.bitmaps)
    assert np.allclose(back.features, table.features)
    assert np.allclose(back.match_features, table.match_features)
    assert (back.cell_w, back.cell_h) == (8, 16)


def test_blur_matrix_reproduces_the_box_blur():
    rng = np.random.default_rng(3)
    block = rng.random((16, 8), dtype=np.float32)
    m = blur_matrix(8, 16)
    assert m.shape == (128, 128)
    assert np.allclose(m @ block.ravel(), box_blur_3x3(block).ravel(), atol=1e-5)


def test_folded_blur_gives_the_same_dot_products():
    """dot(blur(b), g) == dot(b, fold(g)) for every glyph: the frame never needs blurring."""
    table = get_table(8, 16)
    rng = np.random.default_rng(4)
    blocks = rng.random((50, 128), dtype=np.float32)
    blurred = box_blur_3x3(blocks.reshape(50, 16, 8)).reshape(50, 128)
    lhs = blurred @ table.features.T
    rhs = blocks @ table.match_features.T
    assert np.allclose(lhs, rhs, atol=1e-4)
    assert np.allclose(table.match_features, fold_blur(table.features, 8, 16))


def test_blur_adjoint_matches_the_matrix_form():
    """dot(blur(a), b) == dot(a, adjoint(b)), checked against the explicit matrix at 8x16."""
    rng = np.random.default_rng(5)
    a = rng.random((16, 8), dtype=np.float32)
    b = rng.random((16, 8), dtype=np.float32)
    lhs = float((box_blur_3x3(a) * b).sum())
    rhs = float((a * blur_adjoint_3x3(b)).sum())
    assert abs(lhs - rhs) < 1e-4
    m = blur_matrix(8, 16)
    assert np.allclose(blur_adjoint_3x3(b).ravel(), m.T @ b.ravel(), atol=1e-5)
    feats = rng.random((3, 128), dtype=np.float32)
    assert np.allclose(fold_blur(feats, 8, 16), feats @ m, atol=1e-5)


def test_cell_for_height_clamps_and_keeps_the_aspect():
    assert cell_for_height(16) == (8, 16)
    assert cell_for_height(8) == (4, 8)
    assert cell_for_height(1) == cell_for_height(MIN_CELL_HEIGHT)
    assert cell_for_height(10_000) == cell_for_height(MAX_CELL_HEIGHT)
    w, h = cell_for_height(37)
    assert h == 37 and abs(w / h - 0.5) < 0.05


@pytest.mark.parametrize("height", [MIN_CELL_HEIGHT, 5, 7, 23, 64, MAX_CELL_HEIGHT])
def test_tables_build_at_any_height(height):
    cw, ch = cell_for_height(height)
    table = build_table(cw, ch)
    assert table.bitmaps.shape == (table.count, ch, cw)
    assert table.match_features.shape == (table.count, cw * ch)
    assert table.chars[0] == " " and table.coverage[0] == 0.0
    assert table.count >= 8  # even 4x8 keeps a usable ramp of distinct glyphs
    assert 0.15 < float(table.coverage.max()) <= 0.7  # tiny cells can be 60 % ink
