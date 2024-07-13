import os
from PIL import Image
import requests
from io import BytesIO
from googleapiclient.discovery import build
from duckduckgo_search import DDGS

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

def main():
    query = input("Enter the search query: ").strip()
    search_images = input("Do you want to search for images? (yes/no, default is no): ").strip().lower()
    search_images = search_images == 'yes'

    if search_images:
        google_results = search_image_google(query, API_KEY_GOOGLE, CX_GOOGLE)
        duckduckgo_results = search_image_duckduckgo(query)

        google_urls = [result['link'] for result in google_results]
        duckduckgo_urls = [result['image'] for result in duckduckgo_results]

        print("\nGoogle Image URLs:")
        for url in google_urls:
            print(url)

        print("\nDuckDuckGo Image URLs:")
        for url in duckduckgo_urls:
            print(url)
    else:
        google_results = search_text_google(query, API_KEY_GOOGLE, CX_GOOGLE)
        duckduckgo_results = search_text_duckduckgo(query)

        google_urls = [result['link'] for result in google_results]
        duckduckgo_urls = [result['href'] for result in duckduckgo_results]

        print("\nGoogle Search URLs:")
        for url in google_urls:
            print(url)

        print("\nDuckDuckGo Search URLs:")
        for url in duckduckgo_urls:
            print(url)

if __name__ == "__main__":
    main()
