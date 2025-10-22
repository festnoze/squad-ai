import json
import os
import uuid
#
from generic_web_scraper import GenericWebScraper
from models.course_content_models import CourseContent
from course_content_parser import CourseContentParser
from common_tools.helpers.file_helper import file

class CourseContentScrapingService:
    scraper = GenericWebScraper()   
    @staticmethod
    def get_opale_course_pdf_from_url(opale_course_url:str):
        use_selenium = True     
        content_url = CourseContentScrapingService.scraper.extract_single_href_from_url(opale_course_url, "Commencer le cours", use_selenium=use_selenium)
        pdf_url = CourseContentScrapingService.scraper.extract_single_href_from_url(content_url, "Imprimer", use_selenium=use_selenium)
        return pdf_url

    
    @staticmethod
    def get_html_from_pdf_url(pdf_url:str):
        return CourseContentScrapingService.scraper.get_html_from_pdf_url(pdf_url)

    @staticmethod
    def get_md_from_html(html_content):
        return CourseContentScrapingService.scraper.convert_html_to_markdown(html_content)

    @staticmethod
    def scrape_course_content_from_url(opale_course_url:str, ressource_name:str = None, save_html_and_md_as_files: bool = False, relative_path:str = "outputs/"):
        if file.exists(relative_path + ressource_name + ".md"):
            return
        pdf_url = CourseContentScrapingService.get_opale_course_pdf_from_url(opale_course_url)
        course_content_md, course_content_html = CourseContentScrapingService.build_and_save_html_and_md_from_pdf_url(pdf_url, ressource_name, save_html_and_md_as_files, relative_path)
        return pdf_url, course_content_md, course_content_html
        
    @staticmethod
    def build_and_save_html_and_md_from_pdf_url(pdf_url:str, ressource_name:str = None, save_html_and_md_as_files: bool = False, relative_path:str = "outputs/"):
        course_content_html = CourseContentScrapingService.get_html_from_pdf_url(pdf_url)
        course_content_md = CourseContentScrapingService.get_md_from_html(course_content_html)

        if save_html_and_md_as_files:
            with open(f"{relative_path}{ressource_name or ("course_content_" + uuid.uuid4().hex[:8])}.html", "w", encoding="utf-8") as html_file:
                html_file.write(course_content_html)
            with open(f"{relative_path}{ressource_name or ("course_content_" + uuid.uuid4().hex[:8])}.md", "w", encoding="utf-8") as md_file:
                md_file.write(course_content_md)
        
        return course_content_md, course_content_html
        
    @staticmethod
    def analyse_parcours_file_composition(parcour_composition_filename: str, save_analysed_course: bool = True, load_analysed_course_instead_if_exist: bool = True) -> dict[str, CourseContent]:
        analysed_parcour_content_by_parcour_name: dict[str, CourseContent] = {}
        if '.' not in parcour_composition_filename: 
            parcour_composition_filename += ".json"
        analysed_parcour_filename = 'analysed_' + parcour_composition_filename

        if load_analysed_course_instead_if_exist and os.path.exists('outputs/' + analysed_parcour_filename):
            with open('outputs/' + analysed_parcour_filename, "r", encoding="utf-8") as read_json_file:
                loaded_data = json.load(read_json_file)
                course_content = CourseContent.from_dict(loaded_data)
        else:            
            with open("inputs/" + parcour_composition_filename, "r", encoding="utf-8") as read_json_file:
                json_data = json.load(read_json_file)
                parcours_list = json_data.get('parcours', [])
                for parcour_data in parcours_list:
                    course_content = CourseContentParser.parse_parcour_content(parcour_data)
                    analysed_parcour_content_by_parcour_name[parcour_data['name']] = course_content
                    if save_analysed_course:
                        serialized_data = course_content.to_dict(include_user_registration_infos=False)
                        with open('outputs/' + parcour_data['name'] + '.json', 'w') as write_analysed_file:
                            json.dump(serialized_data, write_analysed_file, indent=4)

        return analysed_parcour_content_by_parcour_name
    
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
        valid_parcour_filename = file.build_valid_filename(analysed_course_content.name)
        parcour_out_dir = f"outputs/{valid_parcour_filename}/"
        if not os.path.exists(parcour_out_dir):
            os.makedirs(parcour_out_dir)

        # Scrape and save course content for each opale course in the parcours (no parallelism)
        print(f">>> Start scraping all  and pdf courses of parcours: '{analysed_course_content.name}' for its content:")
        course_scraping_fails_count = 0
        for ressource in analysed_course_content.ressource_objects:
            try:
                valid_course_content_filename = file.build_valid_filename(ressource.name)
                if file.exists(f"{parcour_out_dir}{valid_course_content_filename}.md"):
                    print(f"  - Course content already exists for: '{ressource.name}'")
                    continue

                if ressource.type == "pdf":
                    _, _ = CourseContentScrapingService.build_and_save_html_and_md_from_pdf_url(ressource.url, ressource.name, parcour_out_dir)
                    print(f"  - PDF course content scraped & saved for: '{ressource.name}'")
                elif ressource.type == "opale":                    
                    if CourseContentScrapingService.scrape_course_content_from_url(ressource.url, valid_course_content_filename, True, parcour_out_dir):
                        print(f"  - Opale course content scraped & saved for: '{ressource.name}'")
                else:
                    print(f"  - /!\\ Course content of type: '{ressource.type}' was not scraped. It is not an opale or pdf course: {ressource.name}")
                
            except Exception as e:
                course_scraping_fails_count += 1
                print(f"  - Failed to scrape course content for: '{ressource.name}': {e}")
        print(f"> Finished scraping all opale courses of parcours: '{analysed_course_content.name}'")
        return course_scraping_fails_count

    #TODO: could be moved to common_tools in file_helper