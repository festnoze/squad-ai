from common_tools.helpers.ressource_helper import Ressource
from common_tools.rag.rag_inference_pipeline.end_pipeline_exception import EndPipelineException

class EndMessageEndsPipelineException(EndPipelineException):
    def __init__(self):        
        message = Ressource.load_ressource_file('end_conversation_default_message.txt')
        super().__init__("_fin_echange_", message)