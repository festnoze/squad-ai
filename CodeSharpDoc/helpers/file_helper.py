import os
import shutil
import glob
import csv

from helpers.txt_helper import txt

class file:
    @staticmethod
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
        
    @staticmethod
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
        
        # Remove the file if it already exists
        if os.path.exists(filepath):
            os.remove(filepath)

        # Write the content to the file
        with open(filepath, 'w', encoding='utf-8-sig') as file:
            file.write(content)

    def write_csv(filepath, data):
        with open(filepath, 'w', newline='\r\n', encoding='utf-8-sig') as file:
            writer = csv.writer(file)
            #writer.writerows(data)
            for line in data:
                writer.writerow([line])

    def read_csv(filepath):
        with open(filepath, 'r', newline='\r\n', encoding='utf-8-sig') as file:
            reader = csv.reader(file)
            data = list(reader)
        return data
    
    @staticmethod
    def save_contents_within_files(paths_and_new_codes: list):
        txt.print_with_spinner(f"Saving and override the {len(paths_and_new_codes)} files:")
        for file_path in paths_and_new_codes:
            file.write_file(paths_and_new_codes[file_path], file_path)
        txt.stop_spinner_replace_text(f"{len(paths_and_new_codes)} files overrided and saved successfully.")

    @staticmethod
    def delete_all_files_with_extension(extension, folder_path):
        files_to_delete = glob.glob(os.path.join(folder_path, f"{extension}"))
        for file_to_delete in files_to_delete:
            os.remove(file_to_delete)
    
    @staticmethod
    def delete_file(path_and_name):
        if file.file_exists(path_and_name):
            os.remove(path_and_name)
    
    @staticmethod
    def file_exists(filepath):
        return os.path.exists(filepath)
    
    @staticmethod
    def delete_folder(folder_path):
        if os.path.exists(folder_path):
            shutil.rmtree(folder_path) # Delete the folder and all its contents

    @staticmethod
    def delete_files_in_folder(folder_path):
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
    
    @staticmethod
    def get_all_folder_and_subfolders_files_path(path, extension=None):
        all_files = []        
        for root, dirs, files in os.walk(path):
            for file in files:
                if extension is None or file.endswith(extension):
                    all_files.append(os.path.join(root, file))        
        return all_files
    
    def copy_folder_files_and_folders_to_folder(source_folder, destination_folder):
        if not os.path.exists(destination_folder):
            os.makedirs(destination_folder)
        shutil.copytree(source_folder, destination_folder, dirs_exist_ok=True)
    
    @staticmethod
    def get_files_paths_and_contents(file_path, extension):
        txt.print_with_spinner(f"Loading {extension} files ...")
        paths_and_contents = {}
        files = file.get_all_folder_and_subfolders_files_path(file_path, '.' + extension)
        for file_path in files:
            file_path = file_path.replace('\\', '/')
            paths_and_contents[file_path] = file.get_as_str(file_path)
        txt.stop_spinner_replace_text(f"{len(paths_and_contents)} {extension} files loaded successfully.")
        return paths_and_contents
    
    @staticmethod
    def get_files_contents(file_path, extension):
        contents = []
        files = file.get_all_folder_and_subfolders_files_path(file_path, '.' + extension)
        for file_path in files:
            contents.append(file.get_as_str(file_path))
        return contents