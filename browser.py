import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import deque

def download_images(url, folder_name='downloaded_images', num_pages=1):
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

    visited_urls = set()
    image_urls = set()
    url_queue = deque([url])

    while url_queue and num_pages > 0:
        current_url = url_queue.popleft()
        if current_url in visited_urls:
            continue

        print(f"Processing page: {current_url}")
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
                next_page_url = link_tag.get('href')
                next_page_url = urljoin(current_url, next_page_url)
                if next_page_url not in visited_urls:
                    url_queue.append(next_page_url)

        num_pages -= 1

    print("All images have been downloaded.")

def download_image(img_url, folder_name):
    img_name = os.path.join(folder_name, os.path.basename(urlparse(img_url).path))
    if os.path.exists(img_name):
        print(f"Already downloaded: {img_name}")
        return

    img_response = requests.get(img_url)
    with open(img_name, 'wb') as img_file:
        img_file.write(img_response.content)
        print(f"Downloaded {img_name}")

# Usage
if __name__ == "__main__":
    # website_url = input("Enter the website URL: ")
    website_url = "https://www.amourhub.com"
    num_pages = int(input("Enter the number of pages to follow: "))
    download_images(website_url, num_pages=num_pages)