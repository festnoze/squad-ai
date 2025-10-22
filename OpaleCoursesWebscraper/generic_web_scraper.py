import requests
import time
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from selenium import webdriver
from io import BytesIO
#from pdfminer.high_level import extract_text
from pdfminer.high_level import extract_text_to_fp
from pdfminer.layout import LAParams
import markdownify
import unicodedata
import re
#from markdown_it import MarkdownIt

class GenericWebScraper:
    
    texts_to_remove = ["Tous droits réservés à STUDI - Reproduction interdite"]

    def __init__(self) -> None:
        #self.markdown_it = MarkdownIt()
        pass

    def normalize_ligatures(self, text: str) -> str:
        """
        Normalise les ligatures Unicode (ﬁ, ﬂ, ﬃ, etc.) en caractères ASCII standard (fi, fl, ffi, etc.)
        Utilise la forme NFKC (Normalization Form KC - Compatibility Composition)
        """
        if not text:
            return text
        return unicodedata.normalize('NFKC', text)

    def retrieve_page_content_requests(self, url: str) -> str:
        response: requests.Response = requests.get(url)
        if response.status_code == 200:
                return response.text
        raise Exception(f"Failed to retrieve page: {url}")

    def retrieve_page_content_selenium(self, url: str) -> str:
        driver: webdriver.Chrome = webdriver.Chrome()
        driver.get(url)
        time.sleep(2)
        content: str = driver.page_source
        driver.quit()
        return content

    def scrape_page(self, url: str, use_selenium: bool = False) -> BeautifulSoup:
        html: str = self.retrieve_page_content_selenium(url) if use_selenium else self.retrieve_page_content_requests(url)
        return BeautifulSoup(html, 'html.parser')
    
    def extract_single_href_from_url(self, page_url: str, link_text: str, use_selenium: bool = False, return_relative_link: bool = False) -> str:
        if not page_url.endswith('/') and not page_url.endswith('.html'): 
            page_url += '/'
        response: requests.Response = requests.get(page_url, allow_redirects=True)
        soup: BeautifulSoup = self.scrape_page(page_url, use_selenium)
        link: BeautifulSoup = soup.find('a', string=link_text)
        if not link or not link.has_attr('href'):
            raise Exception(f"No link found with the text: {link_text}")
        
        if return_relative_link:
            return link['href']
        else:                
            redirect_join_url = self.get_url_redirect_from_response_text(response.text)
            if redirect_join_url and redirect_join_url.endswith('.html'):
                redirect_join_url = redirect_join_url.rsplit('/', 1)[0]  
                if not redirect_join_url.endswith('/') and not redirect_join_url.endswith('.html'): 
                    redirect_join_url += '/'
                page_url = urljoin(page_url, redirect_join_url)
            return urljoin(page_url, link['href'])
        
    def get_url_redirect_from_response_text(self, response_text: str) -> str:
        start_index = response_text.find('URL=')
        if start_index != -1:
            start_index += len('URL=')
            end_index = response_text.find('"', start_index)
            if end_index != -1:
                url = response_text[start_index:end_index]
                return url
        return ""  
    
    # def get_pdf_as_markdown_from_url(self, pdf_url: str) -> str:  
    #     #
    #     try:
    #         response: requests.Response = requests.get(pdf_url)
    #         response.raise_for_status()
    #         pdf_bytes: BytesIO = BytesIO(response.content)
    #         text: str = extract_text(pdf_bytes)

    #         for text_to_remove in self.texts_to_remove:
    #             text = text.replace(text_to_remove, "")

    #         html_doc = self.markdown_it.render(text)
    #     except Exception as e:
    #         print(f"Failed to extract PDF content from {pdf_url}")
    #         return None, None
        
    #     return text, html_doc
    
    def get_html_from_pdf_url(self, pdf_url: str) -> str:
        try:
            response = requests.get(pdf_url)
            response.raise_for_status()
            pdf_bytes = BytesIO(response.content)
            output_html = BytesIO()
            laparams = LAParams()
            extract_text_to_fp(pdf_bytes, output_html, laparams=laparams, output_type='html', codec='utf-8')
            html_content = output_html.getvalue().decode('utf-8')
            # Normalise les ligatures Unicode après extraction PDF
            html_content = self.normalize_ligatures(html_content)
            return html_content
        except Exception as e:
            print(f"Failed to extract PDF content from {pdf_url}: {e}")
            return None

    def convert_html_to_markdown(self, html_content: str) -> str:
        markdown_text = markdownify.markdownify(html_content, heading_style="ATX")
        # Normalise les ligatures Unicode après conversion vers Markdown (comme : 'fi')
        markdown_text = self.normalize_ligatures(markdown_text)
        # Supprime le contenu inutile
        markdown_text = self.remove_useless_content_from_markdown(markdown_text)
        return markdown_text

    texts_to_remove = ["Tous droits réservés à STUDI - Reproduction interdite", "© Studi – Reproduction interdite"]
    def remove_useless_content_from_markdown(self, markdown_content: str) -> str:
        # Supprime les textes fixes
        for text_to_remove in self.texts_to_remove:
            markdown_content = markdown_content.replace(text_to_remove, "")

        # Supprime tous les "Page X" où X est un ou plusieurs chiffres
        markdown_content = re.sub(r'Page\s+\d+', '', markdown_content)

        # Réduit les sauts de lignes multiples (3+) à maximum 2 sauts de lignes
        while '\n\n\n' in markdown_content:
            markdown_content = markdown_content.replace('\n\n\n', '\n\n')

        return markdown_content