# Tentative de création de l'EPUB maintenant que l'environnement est prêt
from pathlib import Path
from ebooklib import epub

def create_epub_from_html(folder: str, output_epub: str) -> None:
    folder_path: Path = Path(folder)
    html_files: list[Path] = sorted(folder_path.glob("*.html"))
    print(f"Nombre de fichiers HTML trouvés : {len(html_files)}")
    
    book: epub.EpubBook = epub.EpubBook()
    book.set_title("Méthode Balance - Compilation")
    book.set_language("fr")
    chapters: list[epub.EpubHtml] = []

    for html_file in html_files:
        if html_file.name.startswith("output"):
            continue
        content: str = html_file.read_text(encoding="utf-8")
        chapter: epub.EpubHtml = epub.EpubHtml(
            title=html_file.stem, 
            file_name=f"{html_file.stem}.xhtml", 
            lang="fr"
        )
        chapter.set_content(content)
        book.add_item(chapter)
        chapters.append(chapter)

    book.toc = tuple(chapters)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    css: str = "body { font-family: Arial, sans-serif; }"
    nav_css: epub.EpubItem = epub.EpubItem(
        uid="style_nav", 
        file_name="style/nav.css", 
        media_type="text/css", 
        content=css
    )
    book.add_item(nav_css)

    book.spine = ["nav"] + chapters
    epub.write_epub(output_epub, book)
    print(f"EPUB créé avec succès : {output_epub}")
    print(f"Nombre de chapitres : {len(chapters)}")

create_epub_from_html("C:/Users/e.millerioux/Downloads/MTC Tan/html", "C:/Users/e.millerioux/Downloads/MTC Tan/dr_tan.epub")
