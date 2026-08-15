"""Tests for the pure renderer (app/services/render.py) and asset URL rewrite.

OWNED BY: backend-core agent. These tests exercise the sync renderer directly
with passed-in data so they stay decoupled from the cms module.
"""

from app.services.export import rewrite_asset_urls
from app.services.render import (
    render_block,
    render_page_html,
    render_style,
    sanitize_rich_text,
)


def node(block_type, props=None, style=None, children=None, node_id="n1"):
    return {
        "id": node_id,
        "type": block_type,
        "props": props or {},
        "style": style or {},
        "children": children or [],
    }


# ---------------------------------------------------------------------------
# render_style
# ---------------------------------------------------------------------------


def test_render_style_px_and_passthrough():
    css = render_style(
        {"paddingTop": 48, "backgroundColor": "#f9fafb", "width": "100%", "textAlign": "center"}
    )
    assert "padding-top:48px" in css
    assert "background-color:#f9fafb" in css
    assert "width:100%" in css
    assert "text-align:center" in css


def test_render_style_font_weight_unitless():
    assert render_style({"fontWeight": 700}) == "font-weight:700"


def test_render_style_drops_unknown_and_unsafe():
    css = render_style(
        {"position": "fixed", "color": "red;}body{", "fontSize": 16, "backgroundColor": "#fff"}
    )
    assert "position" not in css
    assert "body" not in css
    assert "font-size:16px" in css


def test_render_style_empty():
    assert render_style({}) == ""
    assert render_style(None) == ""


# ---------------------------------------------------------------------------
# sanitize_rich_text
# ---------------------------------------------------------------------------


def test_sanitize_keeps_whitelist():
    out = sanitize_rich_text("<p>Hi <strong>there</strong> <em>you</em></p>")
    assert out == "<p>Hi <strong>there</strong> <em>you</em></p>"


def test_sanitize_strips_script_and_attrs():
    out = sanitize_rich_text('<script>alert(1)</script><p onclick="x()">ok</p>')
    assert "<script" not in out
    assert "onclick" not in out
    assert "alert(1)" in out  # inner text escaped, kept as text
    assert "<p>ok</p>" in out


def test_sanitize_anchor_href_kept_javascript_blocked():
    out = sanitize_rich_text('<a href="https://example.com">x</a>')
    assert '<a href="https://example.com">x</a>' == out
    out = sanitize_rich_text('<a href="javascript:alert(1)">x</a>')
    assert 'href="#"' in out


def test_sanitize_escapes_plain_text():
    assert sanitize_rich_text("a < b & c") == "a &lt; b &amp; c"


# ---------------------------------------------------------------------------
# per-type blocks
# ---------------------------------------------------------------------------


def test_heading_escapes_and_levels():
    out = render_block(node("heading", {"text": "<Hello>", "level": 3}))
    assert out.startswith("<h3")
    assert "&lt;Hello&gt;" in out
    # bad level falls back to 2
    out = render_block(node("heading", {"text": "x", "level": 9}))
    assert out.startswith("<h2")


def test_text_block_sanitized():
    out = render_block(node("text", {"html": "<p>ok</p><script>bad()</script>"}))
    assert "<p>ok</p>" in out
    assert "<script" not in out


def test_image_block():
    out = render_block(
        node("image", {"src": "/api/uploads/1/pic.png", "alt": 'a "quote"'}, {"width": "100%"})
    )
    assert '<img src="/api/uploads/1/pic.png"' in out
    assert "&quot;quote&quot;" in out
    assert "width:100%" in out


def test_button_block():
    out = render_block(
        node(
            "button",
            {"label": "Go", "href": "/about"},
            {"backgroundColor": "#2563eb", "textAlign": "center"},
        )
    )
    assert '<a href="/about"' in out
    assert ">Go</a>" in out
    assert "text-align:center" in out
    assert "background-color:#2563eb" in out


def test_spacer_and_divider():
    out = render_block(node("spacer", {}, {"height": 48}))
    assert "height:48px" in out
    out = render_block(node("divider", {}, {"color": "#e5e7eb", "marginTop": 16}))
    assert out.startswith("<hr")
    assert "border-top:1px solid #e5e7eb" in out
    assert "margin-top:16px" in out


def test_navbar_and_footer():
    out = render_block(
        node(
            "navbar",
            {"brand": "My Site", "links": [{"label": "Home", "href": "/"}]},
        )
    )
    assert "<nav" in out
    assert "My Site" in out
    assert '<a href="/">Home</a>' in out
    out = render_block(node("footer", {"text": "(c) 2026"}))
    assert "<footer" in out
    assert "(c) 2026" in out


def test_form_block():
    out = render_block(node("form", {"title": "Contact us", "submitLabel": "Send"}))
    assert "<form" in out
    assert "Contact us" in out
    assert 'name="name"' in out
    assert 'name="email"' in out
    assert 'name="message"' in out
    assert ">Send</button>" in out


def test_containers_render_children():
    tree = node(
        "section",
        style={"paddingTop": 48},
        children=[
            node(
                "row",
                style={"gap": 24},
                children=[
                    node("column", {"widthFraction": 2}, children=[node("heading", {"text": "In col"})])
                ],
            )
        ],
    )
    out = render_block(tree)
    assert out.startswith("<section")
    assert "display:flex" in out
    assert "flex:2 1 0" in out
    assert "In col" in out


def test_unknown_block_renders_comment_and_children():
    out = render_block(node("wat", children=[node("heading", {"text": "child"})]))
    assert "<!-- unknown block: wat -->" in out
    assert "child" in out


# ---------------------------------------------------------------------------
# collectionList
# ---------------------------------------------------------------------------


def cl_node(props):
    return node("collectionList", props, {"gap": 24})


def test_collection_list_unbound():
    out = render_block(cl_node({"collectionId": None}))
    assert "collection-list-empty" in out
    assert "No collection bound" in out


def test_collection_list_stale_binding():
    out = render_block(cl_node({"collectionId": 42}), {"collections": {}})
    assert "No collection bound" in out


def test_collection_list_no_entries():
    ctx = {"collections": {1: {"field_types": {"title": "text"}, "entries": []}}}
    out = render_block(cl_node({"collectionId": 1, "itemTemplate": {"title": "title"}}), ctx)
    assert "No entries" in out


def test_collection_list_renders_items():
    ctx = {
        "collections": {
            1: {
                "field_types": {"title": "text", "body": "richtext", "cover": "image"},
                "entries": [
                    {"title": "<First>", "body": "<p>Rich</p>", "cover": 7},
                    {"title": "Second", "body": "<p>More</p>", "cover": "https://x/img.png"},
                ],
            }
        },
        "assets": {7: "/api/uploads/3/abc_pic.png"},
    }
    props = {
        "collectionId": 1,
        "limit": 6,
        "itemTemplate": {"title": "title", "text": "body", "image": "cover"},
    }
    out = render_block(cl_node(props), ctx)
    assert out.count('class="cl-item"') == 2
    # title escaped
    assert "&lt;First&gt;" in out
    # richtext inserted as-is
    assert "<p>Rich</p>" in out
    # image slot: int resolved through assets map, string used directly
    assert 'src="/api/uploads/3/abc_pic.png"' in out
    assert 'src="https://x/img.png"' in out
    # alt is the title slot value
    assert 'alt="Second"' in out


def test_collection_list_non_richtext_text_slot_escaped():
    ctx = {
        "collections": {
            2: {
                "field_types": {"subtitle": "text"},
                "entries": [{"subtitle": "plain & <b>simple</b>"}],
            }
        }
    }
    props = {"collectionId": 2, "itemTemplate": {"text": "subtitle"}}
    out = render_block(cl_node(props), ctx)
    assert "plain &amp; &lt;b&gt;simple&lt;/b&gt;" in out


def test_collection_list_missing_asset_skips_image():
    ctx = {
        "collections": {1: {"field_types": {"cover": "image"}, "entries": [{"cover": 99}]}},
        "assets": {},
    }
    props = {"collectionId": 1, "itemTemplate": {"image": "cover"}}
    out = render_block(cl_node(props), ctx)
    assert "<img" not in out
    assert 'class="cl-item"' in out


def test_collection_list_limit_clamped():
    entries = [{"title": f"T{i}"} for i in range(10)]
    ctx = {"collections": {1: {"field_types": {"title": "text"}, "entries": entries}}}
    props = {"collectionId": 1, "limit": 3, "itemTemplate": {"title": "title"}}
    out = render_block(cl_node(props), ctx)
    assert out.count('class="cl-item"') == 3
    # invalid limit falls back to default 6
    props = {"collectionId": 1, "limit": "lots", "itemTemplate": {"title": "title"}}
    out = render_block(cl_node(props), ctx)
    assert out.count('class="cl-item"') == 6


# ---------------------------------------------------------------------------
# full document + export rewrite
# ---------------------------------------------------------------------------


def test_render_page_html_document():
    tree = {
        "id": "root",
        "type": "page",
        "props": {},
        "style": {},
        "children": [node("heading", {"text": "Welcome"})],
    }
    theme = {"primary_color": "#ff0000", "font": "Georgia", "base_spacing": 20}
    doc = render_page_html(tree, page_name="Home & Co", theme=theme)
    assert doc.startswith("<!doctype html>")
    assert "<title>Home &amp; Co</title>" in doc
    assert "--primary-color: #ff0000" in doc
    assert "--font: Georgia" in doc
    assert "--spacing: 20px" in doc
    assert "Welcome" in doc
    assert "</html>" in doc


def test_rewrite_asset_urls():
    html_doc = '<img src="/api/uploads/3/abc_pic.png"> <img src="/api/uploads/4/other.png">'
    out = rewrite_asset_urls(html_doc, 3)
    assert 'src="assets/abc_pic.png"' in out
    # other project's urls untouched
    assert '/api/uploads/4/other.png' in out
