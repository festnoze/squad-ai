from models.course_content_models import CourseContent
from common_tools.helpers.file_helper import file

from common_tools.helpers import file
class CourseContentQueryingService:
    @staticmethod
    def answer_user_query_on_specified_course(user_query:str, course_content:str):
        pass

    @staticmethod
    def load_course_content_markdown(course_content_path:str, course_content_filename:str) -> CourseContent:
        if '.' in course_content_filename: 
            course_content_filename = course_content_filename.split('.')[0]    
        md_course_content_filename = course_content_filename + ".md"
        md_course_content_file_path = f"{course_content_path}/{md_course_content_filename}"

        if not file.exists(md_course_content_file_path):
            return None
        
        course_content = file.get_as_str(md_course_content_file_path)
        return course_content

    @staticmethod
    def load_course_content_html(course_content_path:str, course_content_filename_wo_extension:str) -> CourseContent:
        if '.' in course_content_filename_wo_extension: 
            course_content_filename_wo_extension = course_content_filename_wo_extension.split('.')[0]        
        html_course_content_filename = course_content_filename_wo_extension + ".html"
        html_course_content_file_path = f"{course_content_path}/{html_course_content_filename}"
        
        if not file.exists(html_course_content_file_path):
            return None
        
        course_content = file.get_as_str(html_course_content_file_path)
        return course_content
    
    @staticmethod
    def load_course_content(course_content_path:str, course_content_filename_wo_extension:str) -> CourseContent:
        course_content_html = CourseContentQueryingService.load_course_content_html(course_content_path, course_content_filename_wo_extension)
        
        if course_content_html:
            course_content = course_content_html
            type = 'html'
        else:
            course_content_md = CourseContentQueryingService.load_course_content_markdown(course_content_path, course_content_filename_wo_extension)
            if not course_content_md:
                raise Exception(f"Course content file not found: '{course_content_filename_wo_extension}' neither as .md nor as .html")
            course_content = course_content_md
            type = 'md'

        return course_content, type