import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import deque
from PIL import Image
from io import BytesIO

def download_images(url, folder_name='downloaded_images', max_depth=1):
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

    visited_urls = set()
    image_urls = set()
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
            if img_url not in image_urls:
                download_image(img_url, folder_name)
                image_urls.add(img_url)

            # Get page links from image tags if available
            link_tag = img.parent if img.parent.name == 'a' else None
            if link_tag:
                next_page_url = link_tag.get('href').rstrip('/')
                next_page_url = urljoin(current_url, next_page_url)
                if next_page_url not in visited_urls:
                    url_queue.append((next_page_url, depth + 1))

    print("All images have been downloaded.")

def download_image(img_url, folder_name):
    img_name = os.path.join(folder_name, os.path.basename(urlparse(img_url).path))
    hd_img_name = append_hd_to_filename(img_name)

    if os.path.exists(hd_img_name):
        print(f"Already downloaded: {hd_img_name}")
        return

    img_response = requests.get(img_url)
    try:
        img = Image.open(BytesIO(img_response.content))
        img_size = img.size
    except (IOError, Image.UnidentifiedImageError):
        print(f"Failed to identify image at URL: {img_url}")
        return

    if os.path.exists(img_name):
        existing_img = Image.open(img_name)
        existing_img_size = existing_img.size
        if img_size > existing_img_size:
            img_name = hd_img_name
        else:
            print(f"Already downloaded: {img_name}")
            return

    img.save(img_name)
    print(f"Downloaded {img_name}")

def append_hd_to_filename(file_path):
    file_name, file_ext = os.path.splitext(file_path)
    return f"{file_name}_hd{file_ext}"

# Usage
if __name__ == "__main__":
    website_url = input("Enter the website URL: ")
    max_depth = int(input("Enter the number of levels to follow: "))
    download_images(website_url, max_depth=max_depth)