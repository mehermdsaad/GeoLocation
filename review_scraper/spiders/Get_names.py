import requests
from bs4 import BeautifulSoup
import os
import json
import time

from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

restaurant_names_file = "./data/restaurant_names.json"




def load_progress(save_file):
    try:
        if os.path.getsize(save_file) == 0:
            return {}
        with open(save_file, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return {}

def save_progress(save_file, save_data):
    with open(save_file, "w", encoding="utf-8") as file:
        json.dump(save_data, file, ensure_ascii=False)


restaurant_names = load_progress(restaurant_names_file)

def get_restaurant_info(url, header):
    try:
        response = requests.get(url, headers=header)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find the restaurant name
        restaurant_name = soup.find('h1', {'class': 'notranslate'}).get_text()

        # Find the address
        address = soup.find('div', {'class': 'address'}).find_all('div')[1].get_text()

        return restaurant_name,address
    except Exception as e:
        print(f"Error scraping {url}: {str(e)}")
        return None, None

def scrape_restaurant_guru():
    for page_no  in range(1,501):
        print(f"Looking at page {page_no}... Total restaurants so far: {len(restaurant_names.keys())}")
        get_names_from_page(page_no=page_no)


def get_names_from_page(page_no=1):
    """FUNCTION TO GET JUST RESTAURANT NAMES FROM PAGE NUMBERS. NOTE: MUST SOLVE CAPTCHA ISSUE
    """
    # base_url = "https://restaurantguru.com/restaurant-Abu-Dhabi-t1"
    url = f"https://restaurantguru.com/restaurant-Abu-Dhabi-t1/{page_no}"
    headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')

    # # Find all restaurant links, skip the first one (advertisement)
    restaurant_elements = soup.find_all(attrs={"class":["notranslate title_url"]})

    if page_no==1:
        restaurant_elements=restaurant_elements[1:] # FIRST ONE'S A PROMO

    restaurant_names = load_progress(restaurant_names_file)

    # restaurant_names = {}
    for restaurant_element in restaurant_elements:
        restaurant_name = restaurant_element.get_text()
        # LET'S AT FIRST GET ALL THE NAMES
        # CHECK IF WE HAVE SEEN THE NAME BEFORE
        if restaurant_name in restaurant_names:
            restaurant_names[restaurant_name].append(restaurant_element['href']) # SO IF THERE ARE LINKS WE KNOW WHICH ONES TO LOOK ADDRESSES FOR IN THE FUTRUE
            print("[SEEN BEFORE]",end=" ")
        else:
            restaurant_names[restaurant_name] = []
        print(restaurant_name)


        # if name and address:
        #     name = name.strip()
        #     address = address.strip()
        #     if not restaurant_names.get(name,None):
        #         restaurant_names[name] = address
        #         print(f"[ENTRY] {name} - {address}")
    
    restaurant_names = save_progress(restaurant_names_file,restaurant_names)
    

def get_names_by_scrolling():
    """SELENIUM IS THE WAY"""

    url = "https://restaurantguru.com/restaurant-Abu-Dhabi-t1/"

    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless")  # Run in headless mode (optional)

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=chrome_options
    )

    restaurant_names = load_progress(restaurant_names_file)

    cnt = 0
    try:
        driver.get(url)

        last_item_count = 0
        extracted_data = []

        start_time = time.time()

        while True:
            
            driver.execute_script("window.scrollTo(0,document.body.scrollHeight);")

            try:
                # Wait for new items to load
                WebDriverWait(driver, 50).until(
                    lambda d: len(
                        d.find_elements(
                            By.CSS_SELECTOR,
                            "a.notranslate.title_url",
                        )
                    )
                    > last_item_count
                )

                # Get all items
                items = driver.find_elements(
                    By.CSS_SELECTOR, "a.notranslate.title_url"
                )
                # Process only the new items
                for item in items[last_item_count:]:
                    try:
                        restaurant_name = item.text
                        cnt+=1
                        print(f"[FOUND] CNT:{cnt} - {restaurant_name}")
                        if restaurant_name in restaurant_names.keys():
                            restaurant_names[restaurant_name].append(item.get_attribute('href'))
                        else:
                            restaurant_names[restaurant_name] = [item.get_attribute('href')]

                    except Exception:
                        print("EXCEPTION OCCURED AT ITEM: ",item)

                save_progress(restaurant_names_file,restaurant_names)
                # Update the count
                new_item_count = len(items)
                print(f"Processed {new_item_count - last_item_count} new items")
                last_item_count = new_item_count

                # Check if we've reached the bottom
                if driver.execute_script("return document.documentElement.scrollHeight - document.documentElement.scrollTop <= document.documentElement.clientHeight + 1;"):
                    break
                
                # if driver.execute_script(
                #     "return arguments[0].scrollHeight - arguments[0].scrollTop === arguments[0].clientHeight;",
                #     scrollable_div,
                # ):
                #     break

                
            except TimeoutException:
                print("No new items loaded, probably reached the end")
                break

        print(
            f"Finished processing all items. Total extracted: {len(extracted_data)}"
        )

        # return restaurants

    finally:
        driver.quit()



############################################################################################################
#NOTE: Update so that when the website turns into a captcha, break the loop without exiting the program 
#####  and then save progress(restaurant name and number in list) to a json file and then continue from there
#####  when the program is run again. Save restaurant name and number separate file and then in the json file 
#####  should be progress up to that point, i.e the dictionary of the restaurant name and address. 
############################################################################################################
# list = scrape(5)
# print(list)
# scrape(5)
##NOTE: Code does not include saving of progress to json file, will need to use function from 
##      google.py to save progress to json file.

# scrape_restaurant_guru()
get_names_by_scrolling()