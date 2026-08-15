"""Server-side renderer: block tree JSON -> standalone HTML document.

OWNED BY: backend-core agent.

Pure-python recursive renderer for the canonical block tree schema
(docs/CONTRACTS.md section 2). Every node is
{"id", "type", "props", "style", "children"}; style keys are camelCase.

Design:
- All sync functions are pure (no IO). CMS data for collectionList blocks is
  passed in through a context dict so cms models stay decoupled.
- The single async entry point arender_page_html prefetches entries/assets
  (importing models_cms lazily inside the function) then calls the sync walk.
- All text passes through html.escape; the "text" block html is sanitized to
  the whitelist b/i/u/em/strong/a/br/p/ul/ol/li.
"""

import html
from html.parser import HTMLParser

# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

ALLOWED_STYLE_KEYS = {
    "paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
    "marginTop", "marginRight", "marginBottom", "marginLeft",
    "color", "backgroundColor", "fontSize", "fontWeight", "textAlign",
    "width", "maxWidth", "height", "borderRadius", "gap",
}

# Numeric values for these keys mean pixels; fontWeight stays unitless.
_UNITLESS_KEYS = {"fontWeight"}

_FORBIDDEN_VALUE_CHARS = (";", "{", "}", "\n", "\r")


def _camel_to_kebab(key: str) -> str:
    out = []
    for ch in key:
        if ch.isupper():
            out.append("-")
            out.append(ch.lower())
        else:
            out.append(ch)
    return "".join(out)


def _css_value(key: str, value) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        num = int(value) if float(value).is_integer() else value
        if key in _UNITLESS_KEYS:
            return str(num)
        return f"{num}px"
    if isinstance(value, str):
        if any(c in value for c in _FORBIDDEN_VALUE_CHARS):
            return None
        return value
    return None


def render_style(style: dict | None) -> str:
    """Map a style props dict to an inline CSS declaration string.

    Only whitelisted camelCase keys are emitted; numbers become px
    (fontWeight stays unitless); unsafe values are dropped.
    """
    if not style:
        return ""
    decls = []
    for key in style:
        if key not in ALLOWED_STYLE_KEYS:
            continue
        value = _css_value(key, style[key])
        if value is None or value == "":
            continue
        decls.append(f"{_camel_to_kebab(key)}:{value}")
    return ";".join(decls)


def _style_attr_from_css(css: str) -> str:
    return f' style="{html.escape(css, quote=True)}"' if css else ""


def _style_attr(node: dict) -> str:
    return _style_attr_from_css(render_style(node.get("style") or {}))


# ---------------------------------------------------------------------------
# Rich text sanitizer (text block)
# ---------------------------------------------------------------------------

_ALLOWED_TAGS = {"b", "i", "u", "em", "strong", "a", "br", "p", "ul", "ol", "li"}


class _RichTextSanitizer(HTMLParser):
    """Keeps only the whitelisted tags; escapes everything else."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in _ALLOWED_TAGS:
            return
        if tag == "a":
            href = ""
            for name, value in attrs:
                if name == "href" and value:
                    href = value
                    break
            if href.strip().lower().startswith("javascript:"):
                href = "#"
            self.out.append(f'<a href="{html.escape(href or "#", quote=True)}">')
        elif tag == "br":
            self.out.append("<br>")
        else:
            self.out.append(f"<{tag}>")

    def handle_startendtag(self, tag, attrs):
        if tag == "br":
            self.out.append("<br>")
        elif tag in _ALLOWED_TAGS:
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in _ALLOWED_TAGS and tag != "br":
            self.out.append(f"</{tag}>")

    def handle_data(self, data):
        self.out.append(html.escape(data))


def sanitize_rich_text(value: str) -> str:
    """Sanitize the text block's html to the allowed tag whitelist."""
    parser = _RichTextSanitizer()
    parser.feed(str(value or ""))
    parser.close()
    return "".join(parser.out)


# ---------------------------------------------------------------------------
# Per-type block renderers
# ---------------------------------------------------------------------------


def _render_children(node: dict, ctx: dict) -> str:
    return "".join(render_block(child, ctx) for child in node.get("children") or [])


def _render_page(node: dict, ctx: dict) -> str:
    return f'<div class="wb-page"{_style_attr(node)}>{_render_children(node, ctx)}</div>'


def _render_section(node: dict, ctx: dict) -> str:
    return f"<section{_style_attr(node)}>{_render_children(node, ctx)}</section>"


def _render_row(node: dict, ctx: dict) -> str:
    css = render_style(node.get("style") or {})
    css = f"display:flex;{css}" if css else "display:flex"
    return f"<div{_style_attr_from_css(css)}>{_render_children(node, ctx)}</div>"


def _render_column(node: dict, ctx: dict) -> str:
    props = node.get("props") or {}
    fraction = props.get("widthFraction", 1)
    if not isinstance(fraction, (int, float)) or isinstance(fraction, bool) or fraction <= 0:
        fraction = 1
    num = int(fraction) if float(fraction).is_integer() else fraction
    css = render_style(node.get("style") or {})
    flex = f"flex:{num} 1 0"
    css = f"{flex};{css}" if css else flex
    return f"<div{_style_attr_from_css(css)}>{_render_children(node, ctx)}</div>"


def _render_heading(node: dict, ctx: dict) -> str:
    props = node.get("props") or {}
    level = props.get("level", 2)
    if not isinstance(level, int) or isinstance(level, bool) or not 1 <= level <= 4:
        level = 2
    text = html.escape(str(props.get("text", "")))
    return f"<h{level}{_style_attr(node)}>{text}</h{level}>"


def _render_text(node: dict, ctx: dict) -> str:
    props = node.get("props") or {}
    return f"<div{_style_attr(node)}>{sanitize_rich_text(props.get('html', ''))}</div>"


def _render_image(node: dict, ctx: dict) -> str:
    props = node.get("props") or {}
    src = html.escape(str(props.get("src", "")), quote=True)
    alt = html.escape(str(props.get("alt", "")), quote=True)
    return f'<img src="{src}" alt="{alt}"{_style_attr(node)}>'


def _render_button(node: dict, ctx: dict) -> str:
    props = node.get("props") or {}
    label = html.escape(str(props.get("label", "")))
    href = html.escape(str(props.get("href", "#")), quote=True)
    style = dict(node.get("style") or {})
    align = style.pop("textAlign", None)
    inner_css = render_style(style)
    inner_css = (
        f"display:inline-block;text-decoration:none;{inner_css}"
        if inner_css
        else "display:inline-block;text-decoration:none"
    )
    anchor = f'<a href="{href}"{_style_attr_from_css(inner_css)}>{label}</a>'
    wrapper_css = ""
    if isinstance(align, str) and align and not any(c in align for c in _FORBIDDEN_VALUE_CHARS):
        wrapper_css = f"text-align:{align}"
    return f"<div{_style_attr_from_css(wrapper_css)}>{anchor}</div>"


def _render_spacer(node: dict, ctx: dict) -> str:
    return f"<div{_style_attr(node)}></div>"


def _render_divider(node: dict, ctx: dict) -> str:
    style = dict(node.get("style") or {})
    color = style.pop("color", "#e5e7eb")
    color_value = _css_value("color", color) or "#e5e7eb"
    css = render_style(style)
    hr = f"border:none;border-top:1px solid {color_value}"
    css = f"{hr};{css}" if css else hr
    return f"<hr{_style_attr_from_css(css)}>"


def _render_navbar(node: dict, ctx: dict) -> str:
    props = node.get("props") or {}
    brand = html.escape(str(props.get("brand", "")))
    links_html = []
    for link in props.get("links") or []:
        if not isinstance(link, dict):
            continue
        label = html.escape(str(link.get("label", "")))
        href = html.escape(str(link.get("href", "#")), quote=True)
        links_html.append(f'<a href="{href}">{label}</a>')
    return (
        f"<nav{_style_attr(node)}>"
        f'<div class="wb-nav-inner">'
        f'<span class="wb-nav-brand">{brand}</span>'
        f'<span class="wb-nav-links">{"".join(links_html)}</span>'
        f"</div></nav>"
    )


def _render_footer(node: dict, ctx: dict) -> str:
    props = node.get("props") or {}
    text = html.escape(str(props.get("text", "")))
    return f"<footer{_style_attr(node)}>{text}</footer>"


def _render_form(node: dict, ctx: dict) -> str:
    props = node.get("props") or {}
    title = html.escape(str(props.get("title", "")))
    submit_label = html.escape(str(props.get("submitLabel", "Send")))
    parts = [f'<form class="wb-form"{_style_attr(node)}>']
    if title:
        parts.append(f"<h3>{title}</h3>")
    parts.append('<label>Name<input type="text" name="name"></label>')
    parts.append('<label>Email<input type="email" name="email"></label>')
    parts.append('<label>Message<textarea name="message"></textarea></label>')
    parts.append(f'<button type="submit">{submit_label}</button>')
    parts.append("</form>")
    return "".join(parts)


def _clamp_limit(value) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        return 6
    return max(1, min(50, value))


def _render_collection_list(node: dict, ctx: dict) -> str:
    """Render the collectionList block per decisions-cms.md section 4.

    Never raises on stale bindings. Data comes from ctx:
    - ctx["collections"]: {collection_id: {"field_types": {key: type}, "entries": [data dict]}}
    - ctx["assets"]: {asset_id: url}
    """
    props = node.get("props") or {}
    style_attr = _style_attr(node)
    collection_id = props.get("collectionId")
    collections = ctx.get("collections") or {}
    if collection_id is None or collection_id not in collections:
        return (
            f'<div class="collection-list collection-list-empty"{style_attr}>'
            "No collection bound</div>"
        )
    coll = collections[collection_id]
    field_types = coll.get("field_types") or {}
    entries = (coll.get("entries") or [])[: _clamp_limit(props.get("limit", 6))]
    if not entries:
        return (
            f'<div class="collection-list collection-list-empty"{style_attr}>'
            "No entries</div>"
        )
    template = props.get("itemTemplate") or {}
    title_key = template.get("title") or None
    text_key = template.get("text") or None
    image_key = template.get("image") or None
    assets = ctx.get("assets") or {}

    items = []
    for data in entries:
        if not isinstance(data, dict):
            continue
        parts = []
        title_value = data.get(title_key) if title_key else None
        # image slot first
        if image_key and data.get(image_key) is not None:
            raw = data.get(image_key)
            src = None
            if isinstance(raw, bool):
                src = None
            elif isinstance(raw, int):
                src = assets.get(raw)
            elif isinstance(raw, str) and raw:
                src = raw
            if src:
                alt = html.escape(str(title_value), quote=True) if title_value is not None else ""
                parts.append(
                    f'<img class="cl-item-image" src="{html.escape(str(src), quote=True)}" alt="{alt}">'
                )
        if title_key and title_value is not None:
            parts.append(f'<h3 class="cl-item-title">{html.escape(str(title_value))}</h3>')
        if text_key and data.get(text_key) is not None:
            raw = data.get(text_key)
            if field_types.get(text_key) == "richtext":
                text_html = str(raw)
            else:
                text_html = html.escape(str(raw))
            parts.append(f'<div class="cl-item-text">{text_html}</div>')
        items.append(f'<div class="cl-item">{"".join(parts)}</div>')

    return f'<div class="collection-list"{style_attr}>{"".join(items)}</div>'


_BLOCK_RENDERERS = {
    "page": _render_page,
    "section": _render_section,
    "row": _render_row,
    "column": _render_column,
    "heading": _render_heading,
    "text": _render_text,
    "image": _render_image,
    "button": _render_button,
    "spacer": _render_spacer,
    "divider": _render_divider,
    "navbar": _render_navbar,
    "footer": _render_footer,
    "form": _render_form,
    "collectionList": _render_collection_list,
}


def render_block(node: dict, ctx: dict | None = None) -> str:
    """Render one block node (and its children) to an HTML fragment."""
    if not isinstance(node, dict):
        return ""
    ctx = ctx or {}
    block_type = node.get("type")
    renderer = _BLOCK_RENDERERS.get(block_type)
    if renderer is None:
        comment = html.escape(str(block_type))
        return f"<!-- unknown block: {comment} -->{_render_children(node, ctx)}"
    return renderer(node, ctx)


# ---------------------------------------------------------------------------
# Document wrapper
# ---------------------------------------------------------------------------

_BASE_CSS = """
*, *::before, *::after { box-sizing: border-box; }
body { margin: 0; font-family: var(--font, system-ui), sans-serif; color: #111; }
img { max-width: 100%; }
h1, h2, h3, h4, p { margin-top: 0; }
.wb-nav-inner { display: flex; align-items: center; justify-content: space-between; }
.wb-nav-brand { font-weight: 700; }
.wb-nav-links a { margin-left: 16px; color: inherit; text-decoration: none; }
.wb-form label { display: block; margin-bottom: 12px; font-size: 14px; }
.wb-form input, .wb-form textarea { display: block; width: 100%; margin-top: 4px; padding: 8px;
  border: 1px solid #d1d5db; border-radius: 4px; font: inherit; }
.wb-form button { background: var(--primary-color, #2563eb); color: #fff; border: none;
  padding: 10px 20px; border-radius: 6px; font: inherit; cursor: pointer; }
.collection-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: var(--spacing, 16px); }
.collection-list-empty { display: block; color: #6b7280; }
.cl-item-image { width: 100%; height: auto; display: block; }
"""


def render_page_html(
    tree: dict,
    *,
    page_name: str = "Page",
    theme: dict | None = None,
    collections: dict | None = None,
    assets: dict | None = None,
) -> str:
    """Render a full standalone HTML document from a block tree (pure sync).

    collections / assets carry pre-fetched CMS data for collectionList blocks
    (see _render_collection_list); pass None when the page uses none.
    """
    theme = theme or {}
    primary = _css_value("color", theme.get("primary_color", "#2563eb")) or "#2563eb"
    font = _css_value("color", theme.get("font", "system-ui")) or "system-ui"
    spacing = theme.get("base_spacing", 16)
    if not isinstance(spacing, (int, float)) or isinstance(spacing, bool):
        spacing = 16
    spacing_num = int(spacing) if float(spacing).is_integer() else spacing
    theme_css = (
        ":root { "
        f"--primary-color: {primary}; --font: {font}; --spacing: {spacing_num}px; "
        "}"
    )
    ctx = {"collections": collections or {}, "assets": assets or {}}
    body = render_block(tree or {}, ctx)
    title = html.escape(str(page_name))
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{title}</title>\n"
        f"<style>{theme_css}\n{_BASE_CSS}</style>\n"
        f"</head>\n<body>\n{body}\n</body>\n</html>\n"
    )


# ---------------------------------------------------------------------------
# Async entry point (prefetches CMS data, lazily importing models_cms)
# ---------------------------------------------------------------------------


def _collect_collection_ids(node: dict, found: set) -> None:
    if not isinstance(node, dict):
        return
    if node.get("type") == "collectionList":
        cid = (node.get("props") or {}).get("collectionId")
        if isinstance(cid, int) and not isinstance(cid, bool):
            found.add(cid)
    for child in node.get("children") or []:
        _collect_collection_ids(child, found)


async def aload_render_context(session, project_id: int, tree: dict) -> tuple[dict, dict]:
    """Prefetch (collections, assets) data used by collectionList blocks.

    models_cms is imported lazily so the core renderer works even while the
    cms module is not implemented yet (blocks then render "No collection bound").
    """
    from sqlalchemy import select

    collection_ids: set = set()
    _collect_collection_ids(tree or {}, collection_ids)

    try:
        from app import models_cms
    except ImportError:
        models_cms = None

    collections: dict = {}
    if collection_ids:
        collection_model = getattr(models_cms, "Collection", None) if models_cms else None
        entry_model = getattr(models_cms, "Entry", None) if models_cms else None
        if collection_model is not None and entry_model is not None:
            result = await session.execute(
                select(collection_model).where(
                    collection_model.id.in_(collection_ids),
                    collection_model.project_id == project_id,
                )
            )
            for coll in result.scalars().all():
                fields = coll.fields or []
                field_types = {
                    f.get("key"): f.get("type") for f in fields if isinstance(f, dict)
                }
                entries_result = await session.execute(
                    select(entry_model)
                    .where(entry_model.collection_id == coll.id)
                    .order_by(entry_model.created_at.desc(), entry_model.id.desc())
                    .limit(50)
                )
                entries = [e.data or {} for e in entries_result.scalars().all()]
                collections[coll.id] = {"field_types": field_types, "entries": entries}

    assets: dict = {}
    asset_model = getattr(models_cms, "Asset", None) if models_cms else None
    if asset_model is not None:
        assets_result = await session.execute(
            select(asset_model).where(asset_model.project_id == project_id)
        )
        assets = {a.id: f"/api/uploads/{a.path}" for a in assets_result.scalars().all()}
    return collections, assets


async def arender_page_html(session, project, page) -> str:
    """Render a Page row to a full HTML document, prefetching CMS data."""
    tree = page.content or {}
    collections, assets = await aload_render_context(session, project.id, tree)
    return render_page_html(
        tree,
        page_name=page.name,
        theme=project.theme or {},
        collections=collections,
        assets=assets,
    )
