import os
import csv
import validators

from search import search_text_duckduckgo, generate_folder_name, extract_links_to_csv

def is_valid_folder_name(folder_name):
    """
    Validates if the given folder name is valid or not.
    
    Args:
        folder_name (str): The name of the folder to be validated.
    
    Returns:
        bool: True if the folder name is valid, False otherwise.
    """
    return bool(folder_name and folder_name.strip())

def load_url_list(url_list_file):
    """
    Loads the list of URLs from a file.
    
    Args:
        url_list_file (str): The path to the file containing the list of URLs.
    
    Returns:
        list: A list of URLs loaded from the file.
    """
    if os.path.exists(url_list_file):
        with open(file=url_list_file, mode='r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=';')
            next(reader)  # Skip the header
            return [(row[0], row[1], int(row[2])) for row in reader if row]
    return []

def print_url_list(urls):
    """
    Prints the list of URLs and their corresponding folders.
    
    Args:
        urls (List[tuple]): A list of tuples containing URL, folder name, and depth as int.
    
    Returns:
        None
    """
    print("Available URLs and corresponding folders:")
    for idx, (url, folder, depth) in enumerate(urls, start=1):
        print(f"{idx}. URL: {url}, Folder: {folder}, Depth: {depth}")

def get_user_input(url_list_file):
    """
    This function initializes default values for processing URLs.
    
    Args:
        url_list_file (str): The path to the file containing a list of URLs, folders, and depth values.
    
    Returns:
        tuple: A tuple containing the selected choice ('new') and the list of URLs.
    """
    choice = 'new'
    urls = load_url_list(url_list_file)

    download_choices = ['file', 'new', 'search', 'scrape', '']

    if not urls:
        download_choices.remove('file')
    else:
        print_url_list(urls)

    download_choices_str = '/'.join(download_choices)

    while True:
        choice = input(f"How do you want to download images? ({download_choices_str}): ").strip().lower()
        if choice in download_choices:
            if choice == '':
                choice = 'new'
            break
        print(f"Invalid input. Please enter one of these: {download_choices_str}.")

    print(f"Source: {choice}.")

    if choice in ['new', 'search', 'scrape']:
        try:
            max_depth = int(input("Enter the depth to follow: ").strip())
        except ValueError:
            max_depth = 0

        print(f"Depth: {max_depth}.")

        if choice in ['new', 'scrape']:
            while True:
                website_url = input("Enter the website URL: ").strip()
                if validators.url(website_url):
                    break
                print("Invalid URL. Please enter a valid website URL.")
            
                print(f"URL: {website_url}.")

            if choice == 'new':
                while True:
                    folder_name = input("Enter the folder name to download the images to: ").strip()
                    if is_valid_folder_name(folder_name):
                        break
                    print("Invalid folder name. Please enter a valid folder name.")

                print(f"Folder: {folder_name}.")

                urls = [[website_url, folder_name, max_depth]]
            else:
                extract_links_to_csv(website_url, url_list_file)
                urls = load_url_list(url_list_file)
                print_url_list(urls)

        else:
            query = input("Enter the search query: ").strip()
            duckduckgo_results = search_text_duckduckgo(query, 50)
            duckduckgo_urls = [result['href'] for result in duckduckgo_results]

            urls = []

            print("\nDuckDuckGo Search URLs:")
            for url in duckduckgo_urls:
                folder_name = generate_folder_name(url)
                urls.append([url, folder_name, max_depth])
                print(f"Folder name: {folder_name}, URL: {url}")

    while True:
        delete_small_images_input = input("Do you want to delete images under 10k bytes before copying? (yes/no): ").strip().lower()
        if delete_small_images_input in ['yes', 'no', 'y', 'n', '']:
            if delete_small_images_input == '' or delete_small_images_input == 'n':
                delete_small_images = False
            else:
                delete_small_images = delete_small_images_input in ['yes', 'y']
            break
        print("Invalid input. Please answer with yes, no, y, or n.")

    print(f"Delete small images: {delete_small_images}.")

    move_files = False

    while True:
        move_files_input = input("Do you want to move images or copy? (move/copy): ").strip().lower()
        if move_files_input in ['copy', '']:
            move_files = False
            break
        elif move_files_input == 'move':
            move_files = True
            break

        print("Invalid input. Please answer with move or copy.")

    print(f"Move images: {move_files}.")

    return urls, delete_small_images, move_files
