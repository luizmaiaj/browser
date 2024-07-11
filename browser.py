import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import deque
from PIL import Image, ImageFile
from io import BytesIO
import hashlib

# Ensure truncated images are handled properly
ImageFile.LOAD_TRUNCATED_IMAGES = True

def download_images(url, folder_name='downloaded_images', max_depth=1):
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

    visited_urls = set()
    image_hashes = set()
    url_queue = deque([(url.rstrip('/'), 0)])

    while url_queue:
        current_url, depth = url_queue.popleft()
        if current_url in visited_urls or depth > max_depth:
            continue

        print(f"Processing page: {current_url} at depth {depth}")
        response = requests.get(current_url)
        soup = BeautifulSoup(response.content, 'html.parser')
        visited_urls.add(current_url)

        img_tags = soup.find_all('img')
        for img in img_tags:
            img_url = img.get('src')
            img_url = urljoin(current_url, img_url)
            if not is_image_downloaded(img_url, folder_name, image_hashes):
                download_image(img_url, folder_name, image_hashes)

            # Get page links from image tags if available
            link_tag = img.parent if img.parent.name == 'a' else None
            if link_tag:
                next_page_url = link_tag.get('href').rstrip('/')
                next_page_url = urljoin(current_url, next_page_url)
                if next_page_url not in visited_urls:
                    url_queue.append((next_page_url, depth + 1))

    print("All images have been downloaded.")

def is_image_downloaded(img_url, folder_name, image_hashes):
    # Download initial bytes to inspect the image
    try:
        img_response = requests.get(img_url, headers={'Range': 'bytes=0-10240'}, stream=True)
        img_response.raise_for_status()
        img = Image.open(BytesIO(img_response.content))
        img_hash = calculate_image_hash(img_response.content)

        if img_hash in image_hashes:
            print(f"Image already downloaded (hash match): {img_url}")
            return True
        return False
    except (requests.HTTPError, IOError, Image.UnidentifiedImageError) as e:
        print(f"Failed to identify image at URL: {img_url}, error: {e}")
        return True

def download_image(img_url, folder_name, image_hashes):
    try:
        img_response = requests.get(img_url)
        img_response.raise_for_status()
        img = Image.open(BytesIO(img_response.content))
        img_hash = calculate_image_hash(img_response.content)
        
        img_name = os.path.join(folder_name, f"{img_hash}.jpg")

        if os.path.exists(img_name):
            print(f"Already downloaded: {img_name}")
            return

        with open(img_name, 'wb') as img_file:
            img_file.write(img_response.content)
            print(f"Downloaded {img_name}")
        image_hashes.add(img_hash)
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