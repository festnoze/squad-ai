import requests
import time
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from selenium import webdriver


class GenericWebScraper:
    def __init__(self) -> None:
        pass

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
        return BeautifulSoup(html, "html.parser")

    def extract_single_href_from_url(self, page_url: str, link_text: str, use_selenium: bool = False, return_relative_link: bool = False) -> str | None:
        try:
            if not page_url.endswith("/") and not page_url.endswith(".html"):
                page_url += "/"
            response: requests.Response = requests.get(page_url, allow_redirects=True)
            soup: BeautifulSoup = self.scrape_page(page_url, use_selenium)
            link: BeautifulSoup = soup.find("a", string=link_text)
            if not link or not link.has_attr("href"):
                raise Exception(f"No link found with the text: {link_text}")

            if return_relative_link:
                return link["href"]
            else:
                redirect_join_url = self.get_url_redirect_from_response_text(response.text)
                if redirect_join_url and redirect_join_url.endswith(".html"):
                    redirect_join_url = redirect_join_url.rsplit("/", 1)[0]
                    if not redirect_join_url.endswith("/") and not redirect_join_url.endswith(".html"):
                        redirect_join_url += "/"
                    page_url = urljoin(page_url, redirect_join_url)
                return urljoin(page_url, link["href"])
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
