from helpers.file_already_exists_policy import FileAlreadyExistsPolicy
from helpers.file_helper import file
from models.params_doc import MethodParametersDocumentation

class CSharpHelper:    
    #obsolete
    @staticmethod
    def remove_existing_summaries_from_all_code_files_and_save(paths_and_codes: dict):
        for file_path, code in paths_and_codes.items():
            lines = code.splitlines()
            lines = [line for line in lines if not line.strip().startswith('///')]
            newCode = '\n'.join(lines)
            file.write_file(newCode, file_path, FileAlreadyExistsPolicy.Override)

class CSharpXMLDocumentation:    
    summary: str = ""
    params: MethodParametersDocumentation
    returns: str = None
    example: str = None
    def __init__(self, summary: str = "", parameters_docs: MethodParametersDocumentation = None, returns: str = None, example: str = None):
        """
        Create an instance of CSharpXMLDocumentation with the following parameters:
        - summary: The method's summary.
        - parameters: A list of ParameterDocumentation objects representing the method's parameters.
        - returns: The method's return if any.
        - example: An example of method usage if any.
        """
        self.summary: str = summary
        self.params: MethodParametersDocumentation = parameters_docs
        self.returns: str = returns
        self.example: str = example

    def __str__(self):
        """
        Returns the C# style XML documentation string.
        """
        doc_str = ""        
        try:
            doc_str =f"/// <summary>\n/// {self.summary.replace('\n', '\n/// ')}\n/// </summary>\n"
            if self.params:
                for param in self.params.params_list:
                    doc_str += f"/// <param name=\"{param.param_name}\">{param.param_desc}</param>\n"
            if self.returns:
                doc_str += f"/// <returns>{self.returns}</returns>\n"
            if self.example:
                doc_str += f"/// <example>{self.example}</example>\n"
        except:
            pass
        return doc_str
    
    def to_xml(self):
        """
        Create a C# style XML documentation string from the provided parameters.
        """        
        return str(self)