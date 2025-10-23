import requests
from io import BytesIO
from pdfminer.high_level import extract_text_to_fp
from pdfminer.layout import LAParams
import markdownify
import unicodedata
import re


class DocTypeConverter:
    def __init__(self):
        self.texts_to_remove = ["Tous droits réservés à STUDI - Reproduction interdite", "© Studi – Reproduction interdite"]

    def get_html_from_pdf_url(self, pdf_url: str) -> str:
        try:
            response = requests.get(pdf_url)
            response.raise_for_status()
            pdf_bytes = BytesIO(response.content)
            output_html = BytesIO()
            laparams = LAParams()
            extract_text_to_fp(pdf_bytes, output_html, laparams=laparams, output_type="html", codec="utf-8")
            html_content = output_html.getvalue().decode("utf-8")
            # Normalise les ligatures Unicode après extraction PDF
            html_content = self.normalize_ligatures(html_content)
            return html_content
        except Exception as e:
            print(f"Failed to extract PDF content from {pdf_url}: {e}")
            return None

    def normalize_ligatures(self, text: str) -> str:
        """
        Normalise les ligatures Unicode (ﬁ, ﬂ, ﬃ, etc.) en caractères ASCII standard (fi, fl, ffi, etc.)
        Utilise la forme NFKC (Normalization Form KC - Compatibility Composition)
        """
        if not text:
            return text
        return unicodedata.normalize("NFKC", text)

    def convert_html_to_markdown(self, html_content: str) -> str:
        markdown_text = markdownify.markdownify(html_content, heading_style="ATX")
        # Normalise les ligatures Unicode après conversion vers Markdown (comme : 'fi')
        markdown_text = self.normalize_ligatures(markdown_text)
        # Supprime le contenu inutile
        markdown_text = self.remove_useless_content_from_markdown(markdown_text)
        return markdown_text

    def remove_useless_content_from_markdown(self, markdown_content: str) -> str:
        # Supprime les textes fixes
        for text_to_remove in self.texts_to_remove:
            markdown_content = markdown_content.replace(text_to_remove, "")

        # Supprime tous les "Page X" où X est un ou plusieurs chiffres
        markdown_content = re.sub(r"Page\s+\d+", "", markdown_content)

        # Réduit les sauts de lignes multiples (3+) à maximum 2 sauts de lignes
        while "\n\n\n" in markdown_content:
            markdown_content = markdown_content.replace("\n\n\n", "\n\n")

        return markdown_content
