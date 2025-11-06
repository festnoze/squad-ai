import requests  # type: ignore[import-untyped]
import time
from urllib.parse import urljoin
from bs4 import BeautifulSoup, Tag  # type: ignore[unused-ignore]
from selenium import webdriver  # type: ignore[unused-ignore]


class GenericWebScraper:
    def __init__(self) -> None:
        pass

    def retrieve_page_content_requests(self, url: str) -> str:
        response: requests.Response = requests.get(url)  # type: ignore[no-any-unimported]
        if response.status_code == 200:
            return str(response.text)
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
        return BeautifulSoup(html, "html.parser")

    def extract_single_href_from_url(self, page_url: str, link_text: str, use_selenium: bool = False, return_relative_link: bool = False) -> str | None:
        try:
            if not page_url.endswith("/") and not page_url.endswith(".html"):
                page_url += "/"
            response: requests.Response = requests.get(page_url, allow_redirects=True)  # type: ignore[no-any-unimported]
            soup: BeautifulSoup = self.scrape_page(page_url, use_selenium)
            link: Tag | None = soup.find("a", string=link_text)  # type: ignore[call-overload]
            if not link or not link.has_attr("href"):
                raise Exception(f"No link found with the text: {link_text}")

            if return_relative_link:
                return str(link["href"]) if link["href"] else None
            else:
                redirect_join_url = self.get_url_redirect_from_response_text(response.text)
                if redirect_join_url and redirect_join_url.endswith(".html"):
                    redirect_join_url = redirect_join_url.rsplit("/", 1)[0]
                    if not redirect_join_url.endswith("/") and not redirect_join_url.endswith(".html"):
                        redirect_join_url += "/"
                    page_url = urljoin(page_url, redirect_join_url)
                href_value = link["href"]
                if isinstance(href_value, str):
                    return urljoin(page_url, href_value)
                return None
        except Exception:
            return None

    def get_url_redirect_from_response_text(self, response_text: str) -> str:
        start_index = response_text.find("URL=")
        if start_index != -1:
            start_index += len("URL=")
            end_index = response_text.find('"', start_index)
            if end_index != -1:
                url = response_text[start_index:end_index]
                return url
        return ""

    def extract_pdf_link_from_page(self, page_url: str, use_selenium: bool = False) -> str | None:
        """Extract PDF URL from a page by finding the 'Imprimer' link.

        This method handles pages where the PDF link is embedded with text 'Imprimer'
        or title attribute containing 'Imprimer'.

        Args:
            page_url: The URL of the page containing the PDF link
            use_selenium: Whether to use Selenium for dynamic content

        Returns:
            The absolute PDF URL if found, None otherwise
        """
        try:
            if not page_url.endswith("/") and not page_url.endswith(".html"):
                page_url += "/"

            soup = self.scrape_page(page_url, use_selenium)

            # Try to find link with text "Imprimer"
            link: Tag | None = soup.find("a", string="Imprimer")  # type: ignore[call-overload]

            # If not found, try to find by span with text "Imprimer"
            if not link:
                span: Tag | None = soup.find("span", string="Imprimer")  # type: ignore[call-overload]
                if span:
                    link = span.find_parent("a")

            # If still not found, try to find by title attribute
            if not link:
                link = soup.find("a", attrs={"title": "Imprimer"})  # type: ignore[unused-ignore]

            if link and link.has_attr("href"):
                href = link["href"]
                # Convert relative URL to absolute
                if isinstance(href, str):
                    return str(urljoin(page_url, href))

            return None

        except Exception:
            return None

    def extract_opale_pdf_url_from_page_url(self, page_url: str, validate_url: bool = True) -> str | None:
        """Extract PDF URL from Opale page URL using the studiMgr.openPrint() transformation logic.

        The transformation follows the JavaScript code from studiMgr.js:
        - Replace "opale" with "opale-pdf"
        - Replace "co/filename.html" with "opale.pdf"

        Example:
            Input:  https://ressources.studi.fr/contenus/opale/HASH/co/page.html
            Output: https://ressources.studi.fr/contenus/opale-pdf/HASH/opale.pdf

        Args:
            page_url: The URL of the Opale HTML page
            validate_url: If True, validates that the PDF URL exists with HTTP HEAD request

        Returns:
            The PDF URL if transformation succeeds, None otherwise
        """
        try:
            # Check if this looks like an Opale page URL
            if "opale" not in page_url or "/co/" not in page_url:
                return None

            # Step 1: Replace "opale" with "opale-pdf"
            pdf_url = page_url.replace("opale", "opale-pdf")

            # Step 2: Replace "co/filename.html" with "opale.pdf"
            # Extract the filename part after /co/
            filename = pdf_url.split("/")[-1]
            pdf_url = pdf_url.replace(f"co/{filename}", "opale.pdf")

            # Optional: Validate that the PDF URL exists
            if validate_url:
                response = requests.head(pdf_url, timeout=5, allow_redirects=True)
                if response.status_code == 200 and "pdf" in response.headers.get("content-type", "").lower():
                    return pdf_url
                else:
                    return None

            return pdf_url

        except Exception:
            return None
