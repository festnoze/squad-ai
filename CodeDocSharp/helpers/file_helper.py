import os
import shutil
import glob

class file:
    def get_as_str(filepath):
        """
        Get the specified file content as string

        Args:
            filename (str): the name of the file in the current directory
        """
        try:
            with open(f"{filepath}", 'r', encoding='utf-8') as file_reader:
                content = file_reader.read()
                return content
        except FileNotFoundError:
            print(f"file: {filepath} cannot be found.")
            return None
        except Exception as e:
            print(f"Error happends while reading file: {filepath}: {e}")
            return None
        
    def write_file(content, filepath):
        """
        Writes content to a file specified by path and filename.

        Args:
            content (str): The content to write to the file.
            path (str): The directory path where the file should be created.
            filename (str): The name of the file, including its extension.
        """
        # Ensure the directory exists
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        # Write the content to the file
        with open(filepath, 'w', encoding='utf-8') as file:
            file.write(content)

    def delete_all_files_with_extension(extension, folder_path):
        files_to_delete = glob.glob(os.path.join(folder_path, f"{extension}"))
        for file_to_delete in files_to_delete:
            os.remove(file_to_delete)
    
    def delete_file(path_and_name):
        if file.file_exists(path_and_name):
            os.remove(path_and_name)
    
    def file_exists(filepath):
        return os.path.exists(filepath)
    
    def delete_folder(folder_path):
        if os.path.exists(folder_path):
            shutil.rmtree(folder_path) # Delete the folder and all its contents

    def delete_folder_contents(folder_path):
        if os.path.exists(folder_path):
            for filename in os.listdir(folder_path):
                file_path = os.path.join(folder_path, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    print(f'{file_path} deletion failed: {e}')

    def get_folder_all_files_and_subfolders(path):
        file_list = []
        dir_list = []
        
        if not os.path.exists(path):
            return file_list, dir_list
        if os.path.isfile(path):
            return file_list, dir_list
        
        for root, dirs, files in os.walk(path):
            for file in files: file_list.append(os.path.join(root, file))
            for dir in dirs: dir_list.append(os.path.join(root, dir))
        return file_list, dir_list