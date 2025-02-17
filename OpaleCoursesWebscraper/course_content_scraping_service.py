import json
import os
import uuid
from models.course_content_models import CourseContent

class CourseContentScrapingService:
    @staticmethod
    def scrape_opale_course_from_url(opale_course_url:str):
        from generic_web_scraper import GenericWebScraper
        use_selenium = True
        scraper = GenericWebScraper()
        
        content_url = scraper.extract_single_href_from_url(opale_course_url, "Commencer le cours", use_selenium=use_selenium)
        
        pdf_url = scraper.extract_single_href_from_url(content_url, "Imprimer", use_selenium=use_selenium)
        #scraped_opale_course_content_md, scraped_opale_course_content_html = scraper.get_pdf_as_markdown_from_url(pdf_url)
        scraped_opale_course_content_html = scraper.get_pdf_as_html_from_url(pdf_url)
        scraped_opale_course_content_md = scraper.convert_html_to_markdown(scraped_opale_course_content_html)
        return pdf_url, scraped_opale_course_content_md, scraped_opale_course_content_html

    @staticmethod    
    def save_course_content(course_content_text:str, course_content_html:str, filename_wo_extension:str = None, relative_path:str = "outputs/", save_as_md:bool = True, save_as_html:bool = True):
        if not filename_wo_extension:
            filename_wo_extension = "course_content_" + uuid.uuid4().hex[:8]
        if save_as_md:
            with open(f"{relative_path}{filename_wo_extension}.md", "w", encoding="utf-8") as text_file:
                text_file.write(course_content_text)
        
        if save_as_html:
            with open(f"{relative_path}{filename_wo_extension}.html", "w", encoding="utf-8") as html_file:
                html_file.write(course_content_html)
        return filename_wo_extension

    @staticmethod
    def scrape_and_save_course_content_from_url(opale_course_url:str, ressource_name:str = None, relative_path:str = "outputs/", save_as_md:bool = True, save_as_html:bool = True):
        pdf_url, course_content_text, course_content_html = CourseContentScrapingService.scrape_opale_course_from_url(opale_course_url)
        filename_wo_extension = CourseContentScrapingService.save_course_content(course_content_text, course_content_html, ressource_name, relative_path, save_as_md, save_as_html)
        return pdf_url, course_content_text, course_content_html
        
    @staticmethod
    def analyse_parcour_composition(parcour_composition_filename: str, save_analysed_course: bool = True, load_analysed_course_instead_if_exist: bool = True) -> CourseContent:
        if not '.' in parcour_composition_filename: 
            parcour_composition_filename += ".json"
        analysed_parcour_filename = 'analysed_' + parcour_composition_filename

        if load_analysed_course_instead_if_exist and os.path.exists('outputs/' + analysed_parcour_filename):
            with open('outputs/' + analysed_parcour_filename, "r", encoding="utf-8") as read_json_file:
                loaded_data = json.load(read_json_file)
                course_content = CourseContent.from_dict(loaded_data)
        else:            
            from course_content_parser import CourseContentParser
            with open("inputs/" + parcour_composition_filename, "r", encoding="utf-8") as read_json_file:
                json_data = json.load(read_json_file)
                course_content = CourseContentParser.parse_course_content(json_data)
                if save_analysed_course:
                    serialized_data = course_content.to_dict()
                    with open('outputs/' + analysed_parcour_filename, 'w') as write_analysed_file:
                        json.dump(serialized_data, write_analysed_file, indent=4)

        return analysed_parcour_filename, course_content
    
    @staticmethod
    def scrape_parcour_all_courses_opale(analysed_course_file_path:str):
        if not os.path.exists('outputs/' + analysed_course_file_path):
            raise Exception(f"Analysed course file not found: {analysed_course_file_path}")
        
        analysed_course_content: CourseContent = None
        with open('outputs/' + analysed_course_file_path, "r", encoding="utf-8") as analysed_json_file:
            loaded_analysed_json = json.load(analysed_json_file)
            analysed_course_content = CourseContent.from_dict(loaded_analysed_json)
        
        if not analysed_course_content:
            raise Exception(f"Failed to load analysed course content from file: {analysed_course_file_path}")
        
        # Create a folder for the courses contents of the parcours
        valid_parcour_filename = CourseContentScrapingService.build_valid_filename(analysed_course_content.name)
        if not os.path.exists(f"outputs/{valid_parcour_filename}"):
            os.makedirs(f"outputs/{valid_parcour_filename}")

        # Scrape and save course content for each opale course in the parcours (no parallelism)
        print(f"> Start scraping all opale courses of parcours: '{analysed_course_content.name}' for its content:")
        course_scraping_fails_count = 0
        for ressource in analysed_course_content.ressource_objects:
            if ressource.type == "opale":
                valid_course_content_filename = CourseContentScrapingService.build_valid_filename(ressource.name)
                if os.path.exists(f"outputs/{valid_parcour_filename}/{valid_course_content_filename}.md"):
                    print(f"Course content already exists for: {ressource.name}")
                    continue
                else:
                    try:
                        CourseContentScrapingService.scrape_and_save_course_content_from_url(ressource.url, valid_course_content_filename, f"outputs/{valid_parcour_filename}/")
                        print(f"  - Course content scraped & saved for: '{ressource.name}'")
                    except Exception as e:
                        course_scraping_fails_count += 1
                        print(f"  - Failed to scrape course content for: '{ressource.name}': {e}")
        print(f"> Finished scraping all opale courses of parcours: '{analysed_course_content.name}'")
        return course_scraping_fails_count

    #TODO: could be moved to common_tools in file_helper
    @staticmethod
    def build_valid_filename(text_to_filename: str) -> str:
        """
        Transforms a string into a Windows-compatible filename.
        
        - Removes characters not allowed in Windows filenames: <>:"/\\|?*
        - Removes control characters (ASCII 0-31)
        - Strips trailing dots and spaces
        - If the result is a reserved name (CON, PRN, AUX, NUL, COM1-9, LPT1-9), appends an underscore.
        - If the result is empty, returns a default name.
        """
        import re
        # Remove invalid characters: < > : " / \ | ? *
        sanitized_filename = re.sub(r'[<>:"/\\|?*]', '', text_to_filename)
        
        # Remove control characters (ASCII 0-31)
        sanitized_filename = re.sub(r'[\x00-\x1f]', '', sanitized_filename)
        
        # Strip trailing periods and spaces
        sanitized_filename = sanitized_filename.rstrip('. ')
        
        # If the sanitized string is empty, set a default filename
        if not sanitized_filename:
            sanitized_filename = "default_filename"
        
        # Reserved names in Windows (case insensitive)
        reserved = {"CON", "PRN", "AUX", "NUL"}
        reserved |= {f"COM{i}" for i in range(1, 10)}
        reserved |= {f"LPT{i}" for i in range(1, 10)}
        
        # If the sanitized name matches a reserved name, append an underscore.
        if sanitized_filename.upper() in reserved:
            sanitized_filename += "_"
        
        return sanitized_filename