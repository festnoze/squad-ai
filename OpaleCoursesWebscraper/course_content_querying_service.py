from models.course_content_models import CourseContent
from common_tools.helpers.file_helper import file

class CourseContentQueryingService:
    @staticmethod
    def answer_user_query_on_specified_course(user_query:str, course_content_filename:str):
        course_content:CourseContent = CourseContentQueryingService.load_course_content(course_content_filename)

    @staticmethod
    def load_course_content(course_content_filename:str) -> CourseContent:
        if not '.' in course_content_filename: 
            course_content_filename += ".md"
        course_content = file.get_as_string("outputs/" + course_content_filename)
        return course_content