import time
import json

class misc:    
    def pause(duration = None):        
        time.sleep(duration)

    def get_formatted_time(duration):
        return time.strftime("%M:%S", time.gmtime(duration))
        
    def get_elapsed_time(began_at_timestamp, ended_at_timestamp): 
        if not ended_at_timestamp:
            return "-"       
        elapsed_time = ended_at_timestamp - began_at_timestamp
        formatted_elapsed_time = misc.get_formatted_time(elapsed_time)
        return formatted_elapsed_time
    
    def array_to_bullet_list_str(str_array):
        bullet_point_list_str = ""
        for item in str_array:
            bullet_point_list_str += f"• {item}\n"
        return bullet_point_list_str
    
    def str_to_json(json_string):
        #remove code block added by ChatGPT to identify json code
        begin_json_code_block = "```json"
        end_json_code_block = "```"
        json_string = json_string.replace(begin_json_code_block, "").replace(end_json_code_block, "")
        return json.loads(json_string)
