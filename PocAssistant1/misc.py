import time

class misc:    
    def pause(duration = None):        
        time.sleep(duration)

    def get_formatted_time(duration):
        return time.strftime("%H:%M:%S", time.gmtime(duration))
    
    def get_str_file(file_name):
        try:
            with open(file_name, 'r', encoding='utf-8') as file_reader:
                content = file_reader.read()
                return content
        except FileNotFoundError:
            print(f"file: {file_name} cannot be found.")
            return None
        except Exception as e:
            print(f"Error happends while reading file: {file_name}: {e}")
            return None
        
    def get_elapsed_time(began_at, ended_at):        
        elapsed_time = ended_at - began_at
        formatted_elapsed_time = misc.get_formatted_time(elapsed_time)
        return formatted_elapsed_time
