from PIL import Image
import requests
from io import BytesIO
from googleapiclient.discovery import build
from duckduckgo_search import DDGS
import hashlib
import re

# API keys and CX values
API_KEY_GOOGLE = 'AIzaSyAutDcATnEePEoOOskYFshBJlxGmlqNidk'
CX_GOOGLE = '3760336eb9d764ed9'
API_KEY_BING = 'YOUR_BING_API_KEY'

def search_image_google(query, api_key, cx, num_results=1):
    try:
        service = build("customsearch", "v1", developerKey=api_key)
        res = service.cse().list(
            q=query,
            cx=cx,
            searchType='image',
            num=num_results
        ).execute()
        return res.get('items', [])
    except ValueError as e:
        print(f"An error occurred: {e}")
        return []

def search_image_duckduckgo(keywords, max_results=1):
    ddgs = DDGS()
    results = ddgs.images(keywords, max_results=max_results)
    return results

def search_text_google(query, api_key, cx, num_results=10):
    try:
        service = build("customsearch", "v1", developerKey=api_key)
        res = service.cse().list(
            q=query,
            cx=cx,
            num=num_results
        ).execute()
        return res.get('items', [])
    except ValueError as e:
        print(f"An error occurred: {e}")
        return []

def search_text_duckduckgo(keywords, max_results=10):
    ddgs = DDGS()
    results = ddgs.text(keywords, max_results=max_results)
    return results

def download_image(url):
    response = requests.get(url)
    img = Image.open(BytesIO(response.content))
    return img

def generate_folder_name(url):
    # Remove query parameters and trailing slash from the URL
    url = re.sub(r'\?.*$', '', url).rstrip('/')

    # Extract the domain name and path from the URL
    match = re.match(r'https://([^/]+)(/.*)', url)
    if match:
        domain, path = match.groups()
    else:
        return None

    # Remove common words that don't contribute to the uniqueness of the folder name
    stop_words = ['pics', 'pictures', 'photos', 'images', 'gallery', 'galleries']
    path = re.sub(r'\b(' + '|'.join(stop_words) + r')\b', '', path)

    # Remove non-alphanumeric characters and replace spaces with hyphens
    folder_name = re.sub(r'[^a-zA-Z0-9]', '-', path).strip('-').lower()

    # Generate a short hash of the URL to ensure uniqueness
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]

    # Combine the domain name, folder name, and hash to create the final folder name
    folder_name = f"{domain}-{folder_name}-{url_hash}"

    return folder_name

def main():
    query = input("Enter the search query: ").strip()
    search_images = input("Do you want to search for images? (yes/no, default is no): ").strip().lower()
    search_images = search_images == 'yes'

    if search_images:
        # google_results = search_image_google(query, API_KEY_GOOGLE, CX_GOOGLE)
        duckduckgo_results = search_image_duckduckgo(query)

        # google_urls = [result['link'] for result in google_results]
        duckduckgo_urls = [result['image'] for result in duckduckgo_results]

        # print("\nGoogle Image URLs:")
        # for url in google_urls:
        #     print(url)

        print("\nDuckDuckGo Image URLs:")
        for url in duckduckgo_urls:
            print(url)
    else:
        # google_results = search_text_google(query, API_KEY_GOOGLE, CX_GOOGLE)
        duckduckgo_results = search_text_duckduckgo(query, 50)

        # google_urls = [result['link'] for result in google_results]
        duckduckgo_urls = [result['href'] for result in duckduckgo_results]

        # print("\nGoogle Search URLs:")
        # for url in google_urls:
        #     print(url)

        print("\nDuckDuckGo Search URLs:")
        for url in duckduckgo_urls:
            print(url)

if __name__ == "__main__":
    main()
