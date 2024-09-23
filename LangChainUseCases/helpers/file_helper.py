import json
import os
import shutil
import glob
import csv

from helpers.file_already_exists_policy import FileAlreadyExistsPolicy
from helpers.txt_helper import txt

class file:
    def get_as_str(filename, encoding='utf-8'):
        """
        Get the specified file content as string

        Args:
            filename (str): the name of the file in the current directory
        """
        if '/' in filename or '\\' in filename:
            path = filename
        else:
            path = f"inputs\\{filename}" 
        try:
            with open(path, 'r', encoding=encoding) as file_reader:
                content = file_reader.read()
                return content
        except FileNotFoundError:
            print(f"file: {filename} cannot be found.")
            return None
        except Exception as e:
            print(f"Error happends while reading file: {filename}: {e}")
            return None
        
    def get_as_json(file_path):
        """Get the specified file content as a JSON object."""
        with open(f"inputs\\{file_path}", 'r') as file:
            data = json.load(file)
        return data
      
    @staticmethod
    def write_file(content: str, filepath: str, file_exists_policy: FileAlreadyExistsPolicy):
        """
        Writes content to a file specified by path and filename.

        Args:
            content (str): The content to write to the file.
            path (str): The directory path where the file should be created.
            filename (str): The name of the file, including its extension.
        """
        # Ensure the directory exists
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        # Apply policy in case the file already exists
        if os.path.exists(filepath):
            if file_exists_policy == FileAlreadyExistsPolicy.Override:
                pass # continue overwrites the file
            elif file_exists_policy == FileAlreadyExistsPolicy.Skip:
                txt.print(f"File '{filepath}' already exists. Skipping writing as per policy.")
                return # skip writing the file
            elif file_exists_policy == FileAlreadyExistsPolicy.AutoRename:
                filepath = file._get_unique_filename(filepath)
                txt.print(f"File '{filepath}' exists. Renaming to '{filepath}' as per policy.")
            elif file_exists_policy == FileAlreadyExistsPolicy.Fail:
                raise FileExistsError(f"File '{filepath}' already exists. Failing as per policy.")            
        
        # Transform dict into its json string representation
        if isinstance(content, dict):
            content = json.dumps(content, indent=4) 

        elif isinstance(content, list):
            content = json.dumps(content, indent=4)

        # Write the content to the file
        with open(filepath, 'w', encoding='utf-8-sig') as file_handler:
            file_handler.write(content)

    @staticmethod
    def _get_unique_filename(filepath: str) -> str:
        """
        Generate a unique filename by appending a number if the file already exists.
        
        Args:
            filepath (str): The original filepath to check for uniqueness.
        
        Returns:
            str: A new unique filepath.
        """
        base, extension = os.path.splitext(filepath)
        counter = 1
        new_filepath = f"{base}_{counter}{extension}"
        while os.path.exists(new_filepath):
            counter += 1
            new_filepath = f"{base}_{counter}{extension}"
        return new_filepath

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