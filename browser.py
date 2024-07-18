import asyncio
import hashlib
import json
import os
from urllib.parse import urljoin, urlparse

import aiohttp
from aiohttp import ClientError, ServerDisconnectedError
from bs4 import BeautifulSoup
from dotenv import find_dotenv, load_dotenv
from PIL import ImageFile

from user_input import get_user_input
from nas import Nas

# from search import extract_links_to_csv

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
        with open(IMAGE_INFO_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_image_info(image_info):
    with open(IMAGE_INFO_FILE, 'w', encoding='utf-8') as f:
        json.dump(image_info, f)

async def fetch_url(session, url):
    async with session.get(url) as response:
        return await response.text()

async def process_url(session, url, depth, max_depth, image_info):
    """
    Process a given URL to extract new image URLs and new URLs for further processing.

    Parameters:
        session (aiohttp.ClientSession): The HTTP client session used for fetching the URL.
        url (str): The URL of the webpage to process.
        depth (int): The current depth in the recursive search.
        max_depth (int): The maximum depth to which the recursive search should go.
        image_info (dict): A dictionary containing information about images already processed.

    Returns:
        tuple: A tuple containing two lists - new image URLs and new URLs for further processing.
    """

    # Prevent concurrent modification of visited_urls set
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
    except ValueError as e:
        print(f"Failed to fetch URL: {url}, error: {e}")
        return [], []

async def download_image(session, img_url, folder_name, image_info, max_retries=3):
    retry_count = 0
    while retry_count < max_retries:
        try:
            async with session.get(img_url) as response:
                img_content = await response.read()
                # Skip files smaller than 15 KB
                if len(img_content) < 15 * 1024:
                    print(f"Skipping {img_url} because it is smaller than 15 KB")
                    return

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
                return  # Successfully downloaded, exit the function

        except (ClientError, ServerDisconnectedError, asyncio.TimeoutError) as e:
            retry_count += 1
            if retry_count < max_retries:
                wait_time = 2 ** retry_count  # Exponential backoff
                print(f"Error downloading {img_url}: {e}. Retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
            else:
                print(f"Failed to download image at URL: {img_url} after {max_retries} attempts. Error: {e}")
        except Exception as e:
            print(f"Unexpected error downloading image at URL: {img_url}. Error: {e}")
        
    # If we've exhausted all retries or encountered an unexpected error, we still return
    print(f"Skipping {img_url} due to persistent errors")
    return

def calculate_image_hash(img_bytes):
    return hashlib.md5(img_bytes).hexdigest()

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
                # Filter out SVG URLs and URLs without an extension
                valid_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp')
                new_img_urls = [img_url for img_url in new_img_urls if img_url.lower().endswith(valid_extensions)]

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

async def download_images_from_file(urls):
    async with aiohttp.ClientSession() as session:
        for url, folder_name, depth in urls:
            print(f"Starting download for {url} into folder {folder_name} with depth {depth}")
            await download_images_async(url, folder_name=folder_name, max_depth=depth)

def main():

    b3_nas = Nas(NAS_USERNAME, NAS_IP, NAS_PASSWORD)

    choice = input("Do you want to download images or clean up the NAS? (download/cleanup): ").strip().lower()
    if choice in ['download', '']:
        urls, delete_small_images, move_files = get_user_input(URL_LIST_FILE)

        if urls:
            asyncio.run(download_images_from_file(urls))

            # copy files to the NAS
            for url, folder_name, depth in urls:
                b3_nas.copy_files_to_nas_photos_library(folder_name, 'home', '/Photos/PhotoLibrary/', folder_name, delete_small_images, move_files)
    elif choice == 'cleanup':
        b3_nas.cleanup_nas_images('home', '/Photos/PhotoLibrary/', True, 'newer', 20000)
    else:
        print("Invalid choice. Please enter 'download' or 'cleanup'.")

import requests
from bs4 import BeautifulSoup
import csv
from urllib.parse import urljoin, urlparse
from validator_collection import validators, checkers, errors

def validate_url(url):
    try:
        # Validate the URL
        validators.url(url)
        print(f"The URL '{url}' is valid.")
        return True
    except errors.InvalidURLError:
        print(f"The URL '{url}' is invalid.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    return False

def extract_links_to_csv(url, output_file='links.csv', recursive=False):
    def get_links(page_url):
        try:
            response = requests.get(page_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            return [link.get('href') for link in soup.find_all('a') if link.get('href')]
        except requests.RequestException as e:
            print(f"Error fetching the URL {page_url}: {e}")
            return []

    def process_links(link, sub_links):
        unique_data = set()
        for href in sub_links:
            if href != link and href.startswith(link.strip('/')):
                full_url = href
                folder = urlparse(link).path.strip('/')
                if folder:
                    unique_data.add((full_url, folder, 1))  # Depth is always 1
        return unique_data

    # Process the initial page
    initial_links = get_links(url)
    
    all_data = set()

    if not recursive:
        # If not recursive, just process the initial page links
        for href in initial_links:
            if href:
                # Make sure the URL is absolute
                full_url = urljoin(url, href)
                # Extract the folder (path) from the URL
                folder = urlparse(full_url).path.strip('/')

                if folder:
                    # Set depth to 1 as per requirement
                    depth = 1
                    all_data.add((full_url, folder, depth))
    else:
        # If recursive, visit each link from the initial page
        for link in initial_links:

            if validate_url(link):
                sub_links = get_links(link)
                all_data.update(process_links(link, sub_links))

    all_data = list(all_data)

    # Write data to CSV file
    try:
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile, delimiter=';')
            writer.writerow(['URL', 'Folder', 'Depth'])
            writer.writerows(all_data)
        print(f"CSV file '{output_file}' has been created successfully with {len(all_data)} unique entries.")
    except IOError as e:
        print(f"Error writing to CSV file: {e}")

# Example usage:
# extract_links_to_csv('https://example.com', recursive=True)

def search_test():
    extract_links_to_csv('https://thefappening.pro/all-actresses-list/','url_list.csv', True)

if __name__ == "__main__":
    search_test()
    # main()
