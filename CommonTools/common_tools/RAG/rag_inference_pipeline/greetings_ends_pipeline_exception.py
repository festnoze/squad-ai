from common_tools.helpers.ressource_helper import Ressource
from common_tools.rag.rag_inference_pipeline.end_pipeline_exception import EndPipelineException

class GreetingsEndsPipelineException(EndPipelineException):
    def __init__(self):
        message = Ressource.get_ressource_file_content('greetings_default_message.txt')
        super().__init__("_salutations_", message)