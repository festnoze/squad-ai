import os

class file:
    def get_as_str(filename):
        """
        Get the specified file content as string

        Args:
            filename (str): the name of the file in the current directory
        """
        try:
            with open(filename, 'r', encoding='utf-8') as file_reader:
                content = file_reader.read()
                return content
        except FileNotFoundError:
            print(f"file: {filename} cannot be found.")
            return None
        except Exception as e:
            print(f"Error happends while reading file: {filename}: {e}")
            return None
        
    def write_file(content, path, filename):
        """
        Writes content to a file specified by path and filename.

        Args:
            content (str): The content to write to the file.
            path (str): The directory path where the file should be created.
            filename (str): The name of the file, including its extension.
        """
        # Ensure the directory exists
        os.makedirs(path, exist_ok=True)
        
        # Construct the full path
        full_path = os.path.join(path, filename)
        
        # Write the content to the file
        with open(full_path, 'w', encoding='utf-8') as file:
            file.write(content)
    