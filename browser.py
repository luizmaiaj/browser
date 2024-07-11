import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import deque
from PIL import Image, ImageFile
from io import BytesIO
import hashlib
import json
import numpy as np
import concurrent.futures
import threading

# Ensure truncated images are handled properly
ImageFile.LOAD_TRUNCATED_IMAGES = True

IMAGE_INFO_FILE = 'image_info.json'
url_queue = deque()
visited_urls = set()
img_urls = set()
lock = threading.Lock()

def load_image_info():
    if os.path.exists(IMAGE_INFO_FILE):
        with open(IMAGE_INFO_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_image_info(image_info):
    with open(IMAGE_INFO_FILE, 'w') as f:
        json.dump(image_info, f)

def download_images(url, folder_name='downloaded_images', max_depth=1, max_workers=20):
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

    image_info = load_image_info()
    url_queue.append((url.rstrip('/'), 0))

    def fetch_and_parse_url(current_url, depth):
        if current_url in visited_urls or depth > max_depth:
            return

        print(f"Processing page: {current_url} at depth {depth}")
        try:
            response = requests.get(current_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            with lock:
                visited_urls.add(current_url)

            img_tags = soup.find_all('img')
            for img in img_tags:
                img_url = img.get('src')
                img_url = urljoin(current_url, img_url)
                with lock:
                    if img_url not in image_info and img_url not in img_urls:
                        img_urls.add(img_url)

            link_tags = soup.find_all('a')
            new_urls = []
            for link in link_tags:
                next_page_url = link.get('href')
                if next_page_url:
                    next_page_url = urljoin(current_url, next_page_url).rstrip('/')
                    with lock:
                        if next_page_url not in visited_urls:
                            new_urls.append((next_page_url, depth + 1))
            
            return new_urls
        except requests.RequestException as e:
            print(f"Failed to fetch URL: {current_url}, error: {e}")
            return []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(fetch_and_parse_url, url_queue[0][0], url_queue[0][1]): url_queue[0]}
        
        while future_to_url:
            done, _ = concurrent.futures.wait(future_to_url, return_when=concurrent.futures.FIRST_COMPLETED)
            
            for future in done:
                url, depth = future_to_url.pop(future)
                try:
                    new_urls = future.result()
                    if new_urls:
                        for new_url, new_depth in new_urls:
                            if new_depth <= max_depth:
                                future_to_url[executor.submit(fetch_and_parse_url, new_url, new_depth)] = (new_url, new_depth)
                except Exception as exc:
                    print(f"{url} generated an exception: {exc}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as download_executor:
        download_futures = {download_executor.submit(download_image, img_url, folder_name, image_info): img_url for img_url in img_urls}
        for future in concurrent.futures.as_completed(download_futures):
            img_url = download_futures[future]
            try:
                future.result()
            except Exception as exc:
                print(f"{img_url} generated an exception: {exc}")

    save_image_info(image_info)
    print("All images have been downloaded.")

def download_image(img_url, folder_name, image_info):
    try:
        img_response = requests.get(img_url)
        img_response.raise_for_status()
        img = Image.open(BytesIO(img_response.content))
        img_hash = calculate_image_hash(img_response.content)
        
        base_name = os.path.basename(urlparse(img_url).path)
        img_name = os.path.join(folder_name, base_name)

        # Check for existing files and prepend numbers if necessary
        if os.path.exists(img_name):
            prefix = 1
            while os.path.exists(img_name):
                img_name = os.path.join(folder_name, f"{prefix:02d}_{base_name}")
                prefix += 1

        with open(img_name, 'wb') as img_file:
            img_file.write(img_response.content)
            print(f"Downloaded {img_name}")
        image_info[img_url] = {'hash': img_hash, 'filename': img_name}
    except (requests.HTTPError, IOError, Image.UnidentifiedImageError) as e:
        print(f"Failed to download image at URL: {img_url}, error: {e}")

def calculate_image_hash(img_bytes):
    hash_md5 = hashlib.md5()
    hash_md5.update(img_bytes)
    return hash_md5.hexdigest()

# Usage
if __name__ == "__main__":
    website_url = input("Enter the website URL: ")
    max_depth = int(input("Enter the number of levels to follow: "))
    download_images(website_url, max_depth=max_depth)