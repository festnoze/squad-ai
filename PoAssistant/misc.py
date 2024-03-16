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
        return json.loads(misc.str_to_json_str(json_string))
    
    def str_to_json_str(json_string):
        #remove code block added by ChatGPT to identify json code
        begin_json_code_block = "```json"
        end_code_block = "```"
        return json_string.replace(begin_json_code_block, "").replace(end_code_block, "")#.replace("'", "\"")

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
