import time
import json
from datetime import datetime

class misc: 
    # def print_message(message: Message):
    #     print(f"{message.role} ({message.elapsed_seconds}s.):\n{message.content}\n")
    
    
    # def get_message_as_json(message: Message):
    #     return  {
    #                 "source": message.role,
    #                 "content": message.content,
    #                 "duration": message.elapsed_seconds
    #             }

    def pause(duration):        
        time.sleep(duration)

    # def get_formatted_time(duration):
    #     return time.strftime("%M:%S", time.gmtime(duration))
        
    # def get_elapsed_time_str(began_at_timestamp, ended_at_timestamp): 
    #     if not ended_at_timestamp:
    #         return "-"       
    #     elapsed_time = ended_at_timestamp - began_at_timestamp
    #     formatted_elapsed_time = misc.get_formatted_time(elapsed_time)
    #     return formatted_elapsed_time
        
    def get_elapsed_time_seconds(began_at: datetime, ended_at: datetime) -> int:
        if not ended_at:
            return -1
        elapsed_time = ended_at - began_at
        return int(elapsed_time)
    
    def array_to_bullet_list_str(str_array):
        bullet_point_list_str = ""
        for item in str_array:
            bullet_point_list_str += f"• {item}\n"
        return bullet_point_list_str
    
    def extract_json_from_text(json_string):
        str_text_removed = misc.remove_json_block(json_string)
        str_text_removed = misc.remove_text_around_json(str_text_removed)
        return json.loads(str_text_removed)
    
    def remove_json_block(json_string):
        #remove code block added by ChatGPT to identify json code
        begin_json_code_block = "```json"
        end_code_block = "```"
        index = json_string.find(begin_json_code_block)
        if index != -1:
            new_start_index = index + len(begin_json_code_block)
            json_string = json_string[new_start_index:]
            end_index = json_string.find(end_code_block)
            if end_index != -1:
                json_string = json_string[:end_index]                
        return json_string

    def remove_text_around_json(json_str):
        return misc.remove_text_before_json(misc.remove_text_after_json(json_str))
    
    def remove_text_before_json(json_str):
        index_item = json_str.find('{')
        index_array = json_str.find('[')
        if index_item == -1 and index_array == -1:
            return json_str
        return json_str[min(index_item, index_array):]
    
    def remove_text_after_json(json_str):
        index_item = json_str.rfind('}')
        index_array = json_str.rfind(']')
        if index_item == -1 and index_array == -1:
            return json_str
        return json_str[:max(index_item, index_array) + 1]
    
    def json_to_str(json_obj):
        return json.dumps(json_obj, ensure_ascii=False, indent=4)
    
    def str_to_gherkin(gherkin_string):
        #remove code block added by ChatGPT to identify json code
        single_quotation_mark = "'"
        gherkin_single_quotation_mark = "’"
        markdown_bold = "**"
        end_code_block = "```"
        gherkin_string = gherkin_string.replace(single_quotation_mark, gherkin_single_quotation_mark).replace(markdown_bold, "").replace(end_code_block, "")
        for i in range(1, 10):
            gherkin_string = gherkin_string.replace(f" {str(i)}", "")
        return gherkin_string
        
    def output_parser_gherkin(feature_content: str):
        return feature_content.replace(" :", ":").replace("gherkin", "").replace("Feature:", "Fonctionnalité:").replace("Scenario:", "Scénario:")
                
