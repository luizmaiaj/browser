import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from PIL import Image, ImageFile
from io import BytesIO
import hashlib
import json
import numpy as np
import concurrent.futures
import threading
import time
from collections import defaultdict
import aiohttp
import asyncio

# Ensure truncated images are handled properly
ImageFile.LOAD_TRUNCATED_IMAGES = True

IMAGE_INFO_FILE = 'image_info.json'
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

async def fetch_url(session, url):
    async with session.get(url) as response:
        return await response.text()

async def process_url(session, url, depth, max_depth):
    if url in visited_urls or depth > max_depth:
        return []

    print(f"Processing page: {url} at depth {depth}")
    try:
        html = await fetch_url(session, url)
        soup = BeautifulSoup(html, 'html.parser')
        with lock:
            visited_urls.add(url)

        new_img_urls = set()
        for img in soup.find_all('img'):
            img_url = urljoin(url, img.get('src'))
            with lock:
                if img_url not in img_urls:
                    new_img_urls.add(img_url)
                    img_urls.add(img_url)

        new_urls = []
        for link in soup.find_all('a'):
            next_page_url = urljoin(url, link.get('href')).rstrip('/')
            with lock:
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

async def download_images_async(url, folder_name='downloaded_images', max_depth=1, max_workers=10):
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

    image_info = load_image_info()
    
    async with aiohttp.ClientSession() as session:
        tasks = [process_url(session, url, 0, max_depth)]
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
                new_tasks.extend([process_url(session, new_url, new_depth, max_depth) for new_url, new_depth in new_urls if new_depth <= max_depth])

            tasks = new_tasks[:max_workers]  # Limit concurrent tasks
            
            if len(img_download_tasks) >= max_workers or (not tasks and img_download_tasks):
                await asyncio.gather(*img_download_tasks[:max_workers])
                img_download_tasks = img_download_tasks[max_workers:]

    save_image_info(image_info)
    print("All images have been downloaded.")

# Usage
if __name__ == "__main__":
    website_url = input("Enter the website URL: ")
    max_depth = int(input("Enter the number of levels to follow: "))
    asyncio.run(download_images_async(website_url, max_depth=max_depth))