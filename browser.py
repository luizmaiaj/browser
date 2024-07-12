import os
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from PIL import Image, ImageFile
from io import BytesIO
import hashlib
import json
import aiohttp
import asyncio
from smb.SMBConnection import SMBConnection

# Ensure truncated images are handled properly
ImageFile.LOAD_TRUNCATED_IMAGES = True

IMAGE_INFO_FILE = 'image_info.json'
visited_urls = set()
img_urls = set()
lock = asyncio.Lock()

def load_image_info():
    if os.path.exists(IMAGE_INFO_FILE):
        with open(IMAGE_INFO_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_image_info(image_info):
    with open(IMAGE_INFO_FILE, 'w') as f:
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
        
        img = Image.open(BytesIO(img_content))
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

def list_and_copy_files_to_nas_photos_library(nas_ip, nas_username, nas_password, local_folder):
    conn = SMBConnection(nas_username, nas_password, 'local_machine', 'remote_machine', use_ntlm_v2=True)
    assert conn.connect(nas_ip, 139)
    
    # List shared folders
    # shared_folders = conn.listShares()
    # print("Shared Folders:")
    # for share in shared_folders:
    #     if not share.isSpecial and share.name not in ['NETLOGON', 'SYSVOL']:
    #         print(f"- {share.name}")
    
    # List folders in the Photos library
    print("\nFolders in Photos Library:")
    photos_folders = conn.listPath('home', '/Photos/PhotoLibrary')
    folder_names = []
    for folder in photos_folders:
        if folder.isDirectory and folder.filename not in ['.', '..']:
            print(f"- {folder.filename}")
            folder_names.append(folder.filename)
    
    # Ask the user to select an existing folder or create a new one
    new_folder_name = ""
    new_folder_path = ""
    use_existing = input("Do you want to use an existing folder? (yes/no): ").strip().lower()
    if use_existing == 'yes':
        selected_folder = input("Enter the name of the existing folder: ").strip()
        if selected_folder not in folder_names:
            print("Folder not found. Exiting.")
            return
        new_folder_name = selected_folder
        new_folder_path = f"/Photos/PhotoLibrary/{selected_folder}"
    else:
        new_folder_name = input("Enter the name of the new folder to create in the Photos Library: ").strip()
        new_folder_path = f"/Photos/PhotoLibrary/{new_folder_name}"
        conn.createDirectory('home', new_folder_path)
    
    # Copy files to the selected or new folder, skipping existing files
    for filename in os.listdir(local_folder):
        local_file_path = os.path.join(local_folder, filename)
        if os.path.isfile(local_file_path):
            remote_file_path = f"{new_folder_path}/{filename}"
            try:
                existing_files = conn.listPath('home', new_folder_path)
                existing_filenames = [file.filename for file in existing_files]
                if filename in existing_filenames:
                    print(f"File {filename} already exists in {new_folder_name}. Skipping.")
                    continue
            except Exception as e:
                print(f"Error checking existing files: {e}")
                continue
            
            with open(local_file_path, 'rb') as file_obj:
                file_bytes = file_obj.read()
                conn.storeFile('home', remote_file_path, BytesIO(file_bytes))
                print(f"Copied {filename} to {new_folder_name}")
    
    conn.close()

async def download_images_async(url, folder_name='downloaded_images', max_depth=1, max_workers=50):
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

# Usage
if __name__ == "__main__":
    website_url = input("Enter the website URL: ")
    max_depth = int(input("Enter the number of levels to follow: "))
    asyncio.run(download_images_async(website_url, max_depth=max_depth))
    
    # List files in the NAS photos library
    # nas_ip = input("Enter the NAS IP address: ")
    nas_ip = "192.168.1.56"
    # nas_username = input("Enter the NAS username: ")
    nas_username = "luizmaiaj"
    # nas_password = input("Enter the NAS password: ")
    nas_password = "nacpy3-pyqbaG-dovkax"
    list_and_copy_files_to_nas_photos_library(nas_ip, nas_username, nas_password, 'downloaded_images')