import asyncio
import csv
import hashlib
import json
import os
from datetime import datetime
from io import BytesIO
from urllib.parse import urljoin, urlparse

import aiohttp
import validators
from bs4 import BeautifulSoup
from dotenv import find_dotenv, load_dotenv
from PIL import ImageFile
from smb.SMBConnection import SMBConnection

load_dotenv(find_dotenv(raise_error_if_not_found=True))

NAS_IP = os.getenv('NAS_IP')
NAS_USERNAME = os.getenv('NAS_USERNAME')
NAS_PASSWORD = os.getenv('NAS_PASSWORD')
DEFAULT_MAX_DEPTH = int(os.getenv('DEFAULT_MAX_DEPTH'))
DEFAULT_NUMBER_OF_WORKERS = int(os.getenv('DEFAULT_NUMBER_OF_WORKERS'))
IMAGE_INFO_FILE = os.getenv('IMAGE_INFO_FILE')
URL_LIST_FILE = os.getenv('URL_LIST_FILE')

# Ensure truncated images are handled properly
ImageFile.LOAD_TRUNCATED_IMAGES = True

visited_urls = set()
img_urls = set()
lock = asyncio.Lock()

def load_image_info():
    if os.path.exists(IMAGE_INFO_FILE):
        with open(file=IMAGE_INFO_FILE, mode='r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_image_info(image_info):
    with open(file=IMAGE_INFO_FILE, mode='w', encoding='utf-8') as f:
        json.dump(image_info, f)

async def fetch_url(session, url):
    async with session.get(url) as response:
        return await response.text()

async def process_url(session, url, depth, max_depth, image_info):
    async with lock:
        if url in visited_urls or depth > max_depth:
            return [], []
        visited_urls.add(url)

    print(f"Processing page: {url} at depth {depth}")
    try:
        html = await fetch_url(session, url)
        soup = BeautifulSoup(html, 'html.parser')

        new_img_urls = set()
        async with lock:
            for img in soup.find_all('img'):
                img_url = urljoin(url, img.get('src'))
                if img_url not in img_urls and img_url not in image_info:
                    new_img_urls.add(img_url)
                    img_urls.add(img_url)

        new_urls = []
        async with lock:
            for link in soup.find_all('a'):
                next_page_url = urljoin(url, link.get('href')).rstrip('/')
                if next_page_url not in visited_urls:
                    new_urls.append((next_page_url, depth + 1))

        return list(new_img_urls), new_urls
    except Exception as e:
        print(f"Failed to fetch URL: {url}, error: {e}")
        return [], []

async def download_image(session, img_url, folder_name, image_info):
    try:
        async with session.get(img_url) as response:
            img_content = await response.read()

        img_hash = calculate_image_hash(img_content)
        
        base_name = os.path.basename(urlparse(img_url).path)
        img_name = os.path.join(folder_name, base_name)

        # Check for existing files and prepend numbers if necessary
        if os.path.exists(img_name):
            prefix = 1
            while os.path.exists(img_name):
                img_name = os.path.join(folder_name, f"{prefix:02d}_{base_name}")
                prefix += 1

        with open(img_name, 'wb') as img_file:
            img_file.write(img_content)
            print(f"Downloaded {img_name}")
        image_info[img_url] = {'hash': img_hash, 'filename': img_name}

    except Exception as e:
        print(f"Failed to download image at URL: {img_url}, error: {e}")

def calculate_image_hash(img_bytes):
    return hashlib.md5(img_bytes).hexdigest()

def calculate_file_hash(conn, service_name, file_path):
    file_obj = BytesIO()
    conn.retrieveFile(service_name, file_path, file_obj)
    file_obj.seek(0)
    return hashlib.md5(file_obj.read()).hexdigest()

def list_and_copy_files_to_nas_photos_library(nas_ip, nas_username, nas_password, local_folder, nas_folder_name, delete_small_images, move_files=False):

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

async def download_images_async(url, folder_name='downloaded_images', max_depth=DEFAULT_MAX_DEPTH, max_workers=DEFAULT_NUMBER_OF_WORKERS):
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)
    else:
        create_new_folder = input(f"Folder '{folder_name}' already exists. Create a new folder? (yes/no): ")
        if create_new_folder.lower() == 'yes':
            suffix = 1
            new_folder_name = f"{folder_name}_{suffix:02d}"
            while os.path.exists(new_folder_name):
                suffix += 1
                new_folder_name = f"{folder_name}_{suffix:02d}"
            folder_name = new_folder_name
            os.makedirs(folder_name)

    image_info = load_image_info()

    async with aiohttp.ClientSession() as session:
        tasks = [process_url(session, url, 0, max_depth, image_info)]
        img_download_tasks = []

        while tasks:
            new_tasks = []
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    print(f"An error occurred: {result}")
                    continue

                new_img_urls, new_urls = result
                img_download_tasks.extend([download_image(session, img_url, folder_name, image_info) for img_url in new_img_urls])
                new_tasks.extend([process_url(session, new_url, new_depth, max_depth, image_info) for new_url, new_depth in new_urls if new_depth <= max_depth])
            tasks = new_tasks[:max_workers]  # Limit concurrent tasks

            # Process image downloads
            while img_download_tasks:
                batch = img_download_tasks[:max_workers]
                img_download_tasks = img_download_tasks[max_workers:]
                await asyncio.gather(*batch)

        # Ensure any remaining image download tasks are completed
        if img_download_tasks:
            await asyncio.gather(*img_download_tasks)

    save_image_info(image_info)
    print("All images have been downloaded.")

def load_url_list():
    if os.path.exists(URL_LIST_FILE):
        with open(URL_LIST_FILE, 'r') as f:
            reader = csv.reader(f, delimiter=';')
            next(reader)  # Skip the header
            return [(row[0], row[1], int(row[2])) for row in reader if row]
    return []

async def download_images_from_file(urls):
    async with aiohttp.ClientSession() as session:
        for url, folder_name, depth in urls:
            print(f"Starting download for {url} into folder {folder_name} with depth {depth}")
            await download_images_async(url, folder_name=folder_name, max_depth=depth)

def is_valid_folder_name(folder_name):
    # Placeholder for actual folder name validation
    return bool(folder_name and folder_name.strip())

def get_user_input():
    choice = 'new'
    urls = load_url_list()

    if urls:
        print("Available URLs and corresponding folders:")
        for idx, (url, folder, depth) in enumerate(urls, start=1):
            print(f"{idx}. URL: {url}, Folder: {folder}, Depth: {depth}")

        while True:
            choice = input("Do you want to fetch images from the URLs in the file or type a new URL? (file/new): ").strip().lower()
            if choice in ['file', 'new', '']:
                if choice == '':
                    choice = 'new'
                break
            print("Invalid input. Please enter 'file' or 'new'.")

        print(f"Source: {choice}.")

    if choice == 'new':
        while True:
            website_url = input("Enter the website URL: ").strip()
            if validators.url(website_url):
                break
            print("Invalid URL. Please enter a valid website URL.")

        print(f"URL: {website_url}.")

        while True:
            folder_name = input("Enter the folder name to download the images to: ").strip()
            if is_valid_folder_name(folder_name):
                break
            print("Invalid folder name. Please enter a valid folder name.")

        print(f"Folder: {folder_name}.")

        try:
            max_depth = int(input("Enter the depth to follow: ").strip())
        except ValueError:
            max_depth = 0

        print(f"Depth: {max_depth}.")

        urls = [[website_url, folder_name, max_depth]]

    while True:
        delete_small_images_input = input("Do you want to delete images under 10k bytes before copying? (yes/no): ").strip().lower()
        if delete_small_images_input in ['yes', 'no', 'y', 'n', '']:
            if delete_small_images_input == '' or delete_small_images_input == 'n':
                delete_small_images = False
            else:
                delete_small_images = delete_small_images_input in ['yes', 'y']
            break
        print("Invalid input. Please answer with yes, no, y, or n.")

    print(f"Delete small images: {delete_small_images}.")

    move_files = False

    while True:
        move_files_input = input("Do you want to move images or copy? (move/copy): ").strip().lower()
        if move_files_input in ['copy', '']:
            move_files = False
            break
        elif move_files_input == 'move':
            move_files = True
            break

        print("Invalid input. Please answer with move or copy.")

    print(f"Move images: {move_files}.")

    return urls, delete_small_images, move_files

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
        with open('nas_images.json', 'r') as f:
            image_data = json.load(f)
        print("Loaded image data from nas_images.json.")
    else:
        print("Recalculating hashes...")
        traverse_nas_folder(nas_folder_path)

        with open('nas_images.json', 'w') as f:
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

def main():

    choice = input("Do you want to download images or clean up the NAS? (download/cleanup): ").strip().lower()
    if choice in ['download', '']:
        urls, delete_small_images, move_files = get_user_input()

        if urls:
            asyncio.run(download_images_from_file(urls))

            # copy files to the NAS
            for url, folder_name, depth in urls:
                list_and_copy_files_to_nas_photos_library(NAS_IP, NAS_USERNAME, NAS_PASSWORD, folder_name, folder_name, delete_small_images, move_files)
    elif choice == 'cleanup':
        cleanup_nas_images(NAS_IP, NAS_USERNAME, NAS_PASSWORD)
    else:
        print("Invalid choice. Please enter 'download' or 'cleanup'.")

if __name__ == "__main__":
    main()
