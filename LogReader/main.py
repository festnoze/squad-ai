import os

def process_log_file():
    try:
        # Open and read the log file
        cur_dir = os.path.dirname(os.path.abspath(__file__))
        log_path = os.path.join(cur_dir, "logs-PIC-1.txt")
        with open(log_path, "r", encoding="utf-8", errors="replace") as file:
            content = file.read()
        
        # Split by lines (note that newlines are '\n' not '//n')
        lines = content.split('\\n')
        
        # Save the result
        with open("result.txt", "w", encoding="utf-8") as output_file:
            for line in lines:
                output_file.write(line + '\n')
        
        print("Log file processed successfully. Result saved to result.txt")
    
    except FileNotFoundError:
        print("Error: log-PIC-1.txt file not found")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    process_log_file()