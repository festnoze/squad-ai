from models.course_content_models import CourseContent
#
from common_tools.helpers.file_helper import file
from common_tools.helpers.llm_helper import Llm
from common_tools.helpers.ressource_helper import Ressource
from common_tools.helpers.execute_helper import Execute
#
from langchain_core.runnables import RunnablePassthrough
from langchain_core.prompts import ChatPromptTemplate
from langchain.schema.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.messages.base import BaseMessage

class CourseContentQueryingService:
    course_query_system_messages:str = None

    @staticmethod
    async def answer_user_query_on_specified_course_async_streaming(llm, user_query:str, parcours_name, parcours_description, course_content:str, is_stream_decoded:bool = False, all_chunks_output: list[str] = []):
        if not CourseContentQueryingService.course_query_system_messages:
            CourseContentQueryingService.course_query_system_messages = Ressource.load_ressource_file('rag_augmented_generation_query_generic.txt')
        
        prompt = CourseContentQueryingService.course_query_system_messages
        prompt = prompt.replace('user_query', user_query)
        prompt = prompt.replace('parcours_name', parcours_name)
        prompt = prompt.replace('parcours_description', parcours_description)
        prompt = prompt.replace('course_content', course_content)

        rag_custom_prompt = ChatPromptTemplate.from_template(prompt)

        llm_chain = rag_custom_prompt | llm | RunnablePassthrough()

        async for chunk in Llm.invoke_as_async_stream('Answer user course query', llm_chain):
            chunk_final = chunk if not is_stream_decoded else chunk.decode('utf-8').replace(Llm.new_line_for_stream_over_http, '\n')
            all_chunks_output.append(chunk_final)
            yield chunk_final 

    @staticmethod
    def answer_user_query_on_specified_course_sync_streaming(llm, user_query:str, parcours_name, parcours_description, course_content:str, is_stream_decoded:bool = False, all_chunks_output: list[str] = []):
        if not CourseContentQueryingService.course_query_system_messages:
            CourseContentQueryingService.course_query_system_messages = file.get_as_str('prompts/query_course_content_prompt.txt', remove_comments=True)
        
        system_messages = CourseContentQueryingService.course_query_system_messages
        system_messages = system_messages.replace('{user_query}', user_query) # useless, as the user query is not in the prompt
        system_messages = system_messages.replace('{parcours_name}', parcours_name)
        system_messages = system_messages.replace('{parcours_description}', parcours_description)
        system_messages = system_messages.replace('{course_content}', course_content)

        messages: list[BaseMessage] = []
        for message in system_messages.split('<separator>'):
            messages.append(SystemMessage(message))
        messages.append(HumanMessage(user_query))

        #rag_custom_prompt = ChatPromptTemplate.from_template(CourseContentQueryingService.course_query_system_messages)

        #llm_chain = rag_custom_prompt | llm | RunnablePassthrough()

        all_chunks = []
        #sync_generator = Execute.async_generator_wrapper_to_sync(Llm.invoke_as_async_stream, 'Answer user course query', llm_chain, input_variables, all_chunks, False)
        
        sync_generator = Execute.async_generator_wrapper_to_sync(Llm.invoke_as_async_stream, 'Answer user course query', llm, messages, all_chunks, False)
        return sync_generator

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