"""Whole-site zip export.

OWNED BY: backend-core agent.

Builds an in-memory zip of every rendered page plus the project's uploaded
asset files. Asset URLs (/api/uploads/{project_id}/...) are rewritten to
relative assets/ paths so the exported site is standalone.
"""

import io
import zipfile

from sqlalchemy import select

from app.db import UPLOADS_DIR
from app.models_core import Page
from app.services.render import arender_page_html


def rewrite_asset_urls(html_doc: str, project_id: int) -> str:
    """Rewrite served upload URLs to the relative assets/ folder of the zip."""
    return html_doc.replace(f"/api/uploads/{project_id}/", "assets/")


async def aexport_site_zip(session, project) -> bytes:
    """Render all project pages and bundle them with assets into zip bytes.

    index.html is the home page (fallback: the first page when none is
    flagged home); every other page is {page_slug}.html.
    """
    result = await session.execute(
        select(Page).where(Page.project_id == project.id).order_by(Page.id)
    )
    pages = list(result.scalars().all())

    home = next((p for p in pages if p.is_home), pages[0] if pages else None)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for page in pages:
            html_doc = await arender_page_html(session, project, page)
            html_doc = rewrite_asset_urls(html_doc, project.id)
            filename = "index.html" if page is home else f"{page.slug}.html"
            archive.writestr(filename, html_doc)

        uploads_dir = UPLOADS_DIR / str(project.id)
        if uploads_dir.is_dir():
            for file_path in sorted(uploads_dir.iterdir()):
                if file_path.is_file():
                    archive.write(file_path, arcname=f"assets/{file_path.name}")

    return buffer.getvalue()
