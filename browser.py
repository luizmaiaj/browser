import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

def download_images(url, folder_name='downloaded_images'):
    # Create a folder to save the images
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

    # Get the HTML content of the page
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')

    # Find all image tags
    img_tags = soup.find_all('img')

    for img in img_tags:
        img_url = img.get('src')

        # Ensure the image URL is absolute
        img_url = urljoin(url, img_url)

        # Get the image content
        img_response = requests.get(img_url)
        img_data = img_response.content

        # Get the image file name
        img_name = os.path.join(folder_name, img_url.split('/')[-1])

        # Save the image
        with open(img_name, 'wb') as img_file:
            img_file.write(img_data)
            print(f"Downloaded {img_name}")

    print("All images have been downloaded.")

# Usage
website_url = 'https://www.amourhub.com'  # Replace with your website link
download_images(website_url)