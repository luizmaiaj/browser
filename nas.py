import os
from io import BytesIO
from datetime import datetime
import hashlib
import json
from smb.SMBConnection import SMBConnection

def calculate_file_hash(conn, service_name, file_path):
    file_obj = BytesIO()
    conn.retrieveFile(service_name, file_path, file_obj)
    file_obj.seek(0)
    return hashlib.md5(file_obj.read()).hexdigest()

def delete_files_by_size(conn, service_name, image_data, size_limit):
    impacted_files = [file_info for file_info in image_data if file_info['size'] <= size_limit]

    if impacted_files:
        print("The following files will be deleted based on the size limit:")
        for file_info in impacted_files:
            print(f"{file_info['path']} (Size: {file_info['size']} bytes)")

        confirm_delete = input("Do you want to proceed with deleting these files? (yes/no): ").strip().lower()
        if confirm_delete == 'yes':
            for file_info in impacted_files:
                conn.deleteFiles(service_name, file_info['path'])
                print(f"Deleted {file_info['path']} (Size: {file_info['size']} bytes)")
    else:
        print("No files meet the size criteria for deletion.")

def find_duplicates(image_data):
    hash_map = {}
    for file_info in image_data:
        file_hash = file_info['hash']
        if file_hash in hash_map:
            hash_map[file_hash].append(file_info)
        else:
            hash_map[file_hash] = [file_info]

    duplicates = [files for files in hash_map.values() if len(files) > 1]
    return duplicates

def delete_duplicates(conn, service_name, duplicate_group, date_choice):
    if date_choice == 'older':
        duplicate_group.sort(key=lambda x: datetime.fromtimestamp(x['creation_date']))
    elif date_choice == 'newer':
        duplicate_group.sort(key=lambda x: datetime.fromtimestamp(x['creation_date']), reverse=True)

    for file_info in duplicate_group[1:]:
        conn.deleteFiles(service_name, file_info['path'])
        print(f"Deleted {file_info['path']}")

def copy_files_to_nas_photos_library(nas_ip, nas_username, nas_password, local_folder, nas_folder_name, delete_small_images, move_files=False):

    conn = SMBConnection(nas_username, nas_password, 'local_machine', 'remote_machine', use_ntlm_v2=True)
    assert conn.connect(nas_ip, 139)

    # List folders in the Photos library
    print("\nFolders in Photos Library:")
    photos_folders = conn.listPath('home', '/Photos/PhotoLibrary')
    folder_names = []
    for folder in photos_folders:
        if folder.isDirectory and folder.filename not in ['.', '..']:
            print(f"- {folder.filename}")
            folder_names.append(folder.filename)

    # Check if the specified folder already exists, if not, create it
    if nas_folder_name not in folder_names:
        new_folder_path = f"/Photos/PhotoLibrary/{nas_folder_name}"
        conn.createDirectory('home', new_folder_path)
    else:
        new_folder_path = f"/Photos/PhotoLibrary/{nas_folder_name}"

    # Retrieving the list of existing files
    existing_files = conn.listPath('home', new_folder_path)

    # Copy or move files to the selected or new folder, skipping existing files
    for filename in os.listdir(local_folder):
        local_file_path = os.path.join(local_folder, filename)
        if os.path.isfile(local_file_path):
            if delete_small_images and os.path.getsize(local_file_path) < 10000:
                print(f"Deleting small image file: {filename}")
                os.remove(local_file_path)
                continue

            remote_file_path = f"{new_folder_path}/{filename}"
            try:
                existing_filenames = [file.filename for file in existing_files]
                if filename in existing_filenames:
                    print(f"File {filename} already exists in {nas_folder_name}. Skipping.")
                    continue
            except Exception as e:
                print(f"Error checking existing files: {e}")
                continue

            with open(local_file_path, 'rb') as file_obj:
                file_bytes = file_obj.read()
                conn.storeFile('home', remote_file_path, BytesIO(file_bytes))

            if move_files:
                os.remove(local_file_path)
                print(f"Moved {filename} to {nas_folder_name}")
            else:
                print(f"Copied {filename} to {nas_folder_name}")

    if move_files:
        # Remove the local folder after all files have been moved
        try:
            os.rmdir(local_folder)
            print(f"Deleted local folder: {local_folder}")
        except OSError as e:
            print(f"Error deleting folder {local_folder}: {e}")

    conn.close()

def cleanup_nas_images(nas_ip, nas_username, nas_password):

    conn = SMBConnection(nas_username, nas_password, 'local_machine', 'remote_machine', use_ntlm_v2=True)
    assert conn.connect(nas_ip, 139)

    nas_folder_path = '/Photos/PhotoLibrary'
    image_data = []

    def traverse_nas_folder(folder_path):
        nas_files = conn.listPath('home', folder_path)
        for file in nas_files:
            if file.filename not in ['.', '..']:
                file_path = f"{folder_path}/{file.filename}"

                print(f"Processing file: {file_path}")

                if file.isDirectory:
                    traverse_nas_folder(file_path)
                else:
                    file_hash = calculate_file_hash(conn, 'home', file_path)
                    print(f"Hash for file {file_path}: {file_hash}")
                    image_data.append({
                        'path': file_path,
                        'hash': file_hash,
                        'creation_date': file.create_time,
                        'size': file.file_size
                    })

    choice = input("Do you want to load the latest nas_images.json or recalculate the hashes? (load/recalculate): ").strip().lower()
    if choice == 'load' and os.path.exists('nas_images.json'):
        with open(file='nas_images.json', mode='r', encoding='utf-8') as f:
            image_data = json.load(f)
        print("Loaded image data from nas_images.json.")
    else:
        print("Recalculating hashes...")
        traverse_nas_folder(nas_folder_path)

        with open(file='nas_images.json', mode='w', encoding='utf-8') as f:
            json.dump(image_data, f, default=str)

    duplicates = find_duplicates(image_data)

    if duplicates:
        print("Duplicate files found:")
        date_choice = input("Delete older or newer files? (older/newer): ").strip().lower()

        for dup_group in duplicates:
                for idx, file_info in enumerate(dup_group):
                    print(f"{idx + 1}. {file_info['path']} (Created on {file_info['creation_date']}, Size: {file_info['size']} bytes)")

        delete_choice = input("Do you want to delete the duplicates? (yes/no): ").strip().lower()

        if delete_choice == 'yes':
            for dup_group in duplicates:
                delete_duplicates(conn, 'home', dup_group, date_choice)

    # Ask the user if they want to delete files based on size
    size_delete_choice = input("Do you want to delete files based on size? (yes/no): ").strip().lower()
    if size_delete_choice == 'yes':
        size_limit = int(input("Enter the size limit in bytes: ").strip())
        delete_files_by_size(conn, 'home', image_data, size_limit)

    conn.close()
