import json
import os
import uuid
from typing import TYPE_CHECKING

#
from common_tools.helpers.file_helper import file  # type: ignore[import-untyped]
from data_ingestion.models.course_content_model import CourseContent
from data_ingestion.generic_web_scraper import GenericWebScraper
from data_ingestion.doc_type_converter import DocTypeConverter

if TYPE_CHECKING:
    from infrastructure.content_repository import ContentRepository


class CourseContentScrapingService:
    scraper: GenericWebScraper = GenericWebScraper()
    doc_converter: DocTypeConverter = DocTypeConverter()

    @staticmethod
    def get_opale_course_pdf_from_url(opale_course_url: str) -> str | None:
        """Extract PDF URL from an Opale course page.

        Handles two types of Opale pages:
        1. Pages with /co/ in URL: Direct content pages (fast URL transformation)
        2. Landing pages: Navigate via "Commencer le cours" then extract PDF link

        Args:
            opale_course_url: URL to the Opale course landing page or content page

        Returns:
            PDF URL if extraction succeeds, None otherwise
        """
        # Try fast URL transformation first (if we're already on a content page)
        if "/co/" in opale_course_url:
            pdf_url = CourseContentScrapingService.scraper.extract_opale_pdf_url_from_page_url(opale_course_url)
            if pdf_url:
                return pdf_url

        # For landing pages, navigate to the content page first
        use_selenium = True

        # Step 1: Click "Commencer le cours" to get to content page
        # This handles the button: <a rel="next" ... href="..."><span>Commencer le cours</span></a>
        content_url = CourseContentScrapingService.scraper.extract_single_href_from_url(opale_course_url, "Commencer le cours", use_selenium=use_selenium)
        if not content_url:
            return None

        # Step 2: Try URL transformation on the content page (works for standard /co/ pages)
        pdf_url = CourseContentScrapingService.scraper.extract_opale_pdf_url_from_page_url(content_url)
        if pdf_url:
            return pdf_url

        # Step 3: Extract PDF link from the content page
        # This handles pages with relative PDF paths like "module_web/module_web.pdf"
        pdf_url = CourseContentScrapingService.scraper.extract_pdf_link_from_page(content_url, use_selenium=use_selenium)
        if pdf_url:
            return pdf_url

        # Step 4: Final fallback - try the old method of finding "Imprimer" link text
        pdf_url = CourseContentScrapingService.scraper.extract_single_href_from_url(content_url, "Imprimer", use_selenium=use_selenium)
        return pdf_url

    @staticmethod
    def get_html_from_pdf_url(pdf_url: str) -> str | None:
        return CourseContentScrapingService.doc_converter.get_html_from_pdf_url(pdf_url)

    @staticmethod
    def get_md_from_html(html_content: str) -> str:
        return CourseContentScrapingService.doc_converter.convert_html_to_markdown(html_content)

    @staticmethod
    async def scrape_course_content_from_url(
        opale_course_url: str,
        ressource_name: str | None = None,
        save_html_and_md_as_files: bool = False,
        relative_path: str = "outputs/",
        content_repository: "ContentRepository | None" = None,
    ) -> tuple[str, str, str] | None:
        """Scrape course content from Opale URL.

        Args:
            opale_course_url: URL of the Opale course
            ressource_name: Name of the resource (for file naming if saving)
            save_html_and_md_as_files: Whether to save HTML and MD files to disk (default: False)
            relative_path: Path to save files if save_html_and_md_as_files is True
            content_repository: Repository to check if content exists in database (optional)

        Returns:
            Tuple of (pdf_url, markdown_content, html_content) if successful, None otherwise
        """
        # Check if content already exists in database (if repository provided)
        if content_repository:
            filter = {"ressource_url": opale_course_url}
            exists = await content_repository.adoes_content_exist_by_filter(filter)
            if exists:
                return None  # Already exists in database, skip scraping

        # Extract PDF URL from Opale course
        pdf_url = CourseContentScrapingService.get_opale_course_pdf_from_url(opale_course_url)
        if not pdf_url:
            return None

        # Build HTML and MD from PDF
        res = CourseContentScrapingService.build_and_save_html_and_md_from_pdf_url(pdf_url, ressource_name, save_html_and_md_as_files, relative_path)
        if res:
            course_content_md, course_content_html = res
            return pdf_url, course_content_md, course_content_html
        return None

    @staticmethod
    def build_and_save_html_and_md_from_pdf_url(pdf_url: str, ressource_name: str | None = None, save_html_and_md_as_files: bool = False, relative_path: str = "outputs/") -> tuple[str, str] | None:
        course_content_html = CourseContentScrapingService.get_html_from_pdf_url(pdf_url)
        if not course_content_html:
            return None
        course_content_md = CourseContentScrapingService.get_md_from_html(course_content_html)

        if not ressource_name:
            ressource_name = "course_content_" + uuid.uuid4().hex[:8]

        if save_html_and_md_as_files:
            with open(f"{relative_path}{ressource_name}.html", "w", encoding="utf-8") as html_file:
                html_file.write(course_content_html)
            with open(f"{relative_path}{ressource_name}.md", "w", encoding="utf-8") as md_file:
                md_file.write(course_content_md)

        return course_content_md, course_content_html

    @staticmethod
    def scrape_parcour_all_courses_opale(analysed_course_file_path: str) -> int:
        if not os.path.exists("outputs/" + analysed_course_file_path):
            raise Exception(f"Analysed course file not found: {analysed_course_file_path}")

        analysed_course_content: CourseContent
        with open("outputs/" + analysed_course_file_path, "r", encoding="utf-8") as analysed_json_file:
            loaded_analysed_json = json.load(analysed_json_file)
            analysed_course_content = CourseContent.from_dict(loaded_analysed_json)

        if not analysed_course_content:
            raise Exception(f"Failed to load analysed course content from file: {analysed_course_file_path}")

        # Create a folder for the courses contents of the parcours
        valid_parcour_filename = file.build_valid_filename(analysed_course_content.name)
        parcour_out_dir = f"outputs/{valid_parcour_filename}/"
        if not os.path.exists(parcour_out_dir):
            os.makedirs(parcour_out_dir)

        # Scrape and save course content for each opale course in the parcours (no parallelism)
        print(f">>> Start scraping all  and pdf courses of parcours: '{analysed_course_content.name}' for its content:")
        course_scraping_fails_count: int = 0
        for ressource in analysed_course_content.ressource_objects:
            try:
                valid_course_content_filename = file.build_valid_filename(ressource.name)
                if file.exists(f"{parcour_out_dir}{valid_course_content_filename}.md"):
                    print(f"  - Course content already exists for: '{ressource.name}'")
                    continue

                if ressource.type == "pdf":
                    if CourseContentScrapingService.build_and_save_html_and_md_from_pdf_url(ressource.url, ressource.name, False, parcour_out_dir):
                        print(f"  - PDF course content scraped & saved for: '{ressource.name}'")
                    else:
                        course_scraping_fails_count += 1
                        print(f"  - Failed to scrape PDF course content for: '{ressource.name}'")
                elif ressource.type == "opale":
                    if CourseContentScrapingService.scrape_course_content_from_url(ressource.url, valid_course_content_filename, True, parcour_out_dir):
                        print(f"  - Opale course content scraped & saved for: '{ressource.name}'")
                    else:
                        course_scraping_fails_count += 1
                        print(f"  - Failed to scrape Opale course content for: '{ressource.name}'")
                else:
                    course_scraping_fails_count += 1
                    print(f"  - /!\\ Course content of type: '{ressource.type}' was not scraped. It is not an opale or pdf course: {ressource.name}")

            except Exception as e:
                course_scraping_fails_count += 1
                print(f"  - Failed to scrape course content for: '{ressource.name}': {e}")
        print(f"> Finished scraping all opale courses of parcours: '{analysed_course_content.name}'")
        return course_scraping_fails_count

    # TODO: could be moved to common_tools in file_helper
