import binascii
import csv
import json
import os
import random
import re
import shutil
import time
from urllib.parse import quote_plus

import pandas as pd
import numpy as np
import requests
import scrapy
from bs4 import BeautifulSoup
from PIL import Image
from scrapy.http.request import Request
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

scraping_progress_file = "./logs/scraping_log.json"
users_log_file = "./logs/users_log.json"
restaurant_details_file = "./data/restaurant_details.json"
restaurant_names_file = "./data/restaurant_names.json"
scrape_data_file = "./reviews.csv"

COUNTRIES = ["Saudi Arabia","United Arab Emirates","Lebanon","Egypt","Qatar"]
NUM_RESTAURANTS_PER_COUNTRY = 50
MAX_NUM_CITIES_PER_COUNTRY = 10
MAX_NUM_RESTAURANTS_PER_CITY = 20
NUM_REVIEWS_THRESHHOLD = 500
NUM_IMGS_TO_DOWNLOAD =30
MAX_NUM_IMGS_PER_USER = 3

class GoogleSpider(scrapy.Spider):

    name = "google"

    HEADERS = {
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36 Edg/87.0.664.66",
        "referer": None,
    }

    def __init__(self, *args, **kwargs):
        super(GoogleSpider, self).__init__(*args, **kwargs)

        self.HEADERS = {
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36 Edg/87.0.664.66",
            "referer": None,
        }
        
        self.scraping_progress_file = scraping_progress_file
        self.scraping_progress = self.load_progress(self.scraping_progress_file)
        self.restaurant_details_file = restaurant_details_file
        self.restaurant_details = self.load_progress(self.restaurant_details_file)
        self.restaurant_names_file = restaurant_names_file
        self.restaurant_names = self.load_progress(self.restaurant_names_file)
        self.users_log_file = users_log_file
        self.users_log = self.load_progress(self.users_log_file)

        self.scrape_data_file = scrape_data_file

    def scrape_restaurant_names_from_country(self,countries):

        for country_name in countries:
            country_search = country_name.replace(" ", "-")

            """SELENIUM IS THE WAY"""


            url = f"https://t.restaurantguru.com/restaurant-{country_search}-t1/"

            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_argument("--headless")  # Run in headless mode (optional)

            driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()), options=chrome_options
            )

            self.restaurant_details = self.load_progress(self.restaurant_details_file)
            load_last_item_count = self.restaurant_details.get("last_item_count",0) # DEFAULT START VALUE SHOULD BE 0 BUT 100 IS CHOSEN FOR KICKSTARTING
            self.restaurant_details.pop("last_item_count",None)

            cities = {}

            cnt = 0
            for item in self.restaurant_details.values():
                if item["country_name"] == country_name:
                    cnt += 1
                    cities[item["city_name"]] = cities.get(item["city_name"],0)+1
            if cnt==50:
                continue
            

            try:
                driver.get(url)

                last_item_count = 0

                while True:
                    
                    driver.execute_script("window.scrollTo(0,document.body.scrollHeight);")

                    try:
                        # Wait for new items to load
                        WebDriverWait(driver, 5).until(
                            lambda d: len(
                                d.find_elements(
                                    By.CSS_SELECTOR,
                                    "div.wrapper_info",
                                )
                            )
                            > last_item_count
                        )

                        # Get all items
                        items = driver.find_elements(
                            By.CSS_SELECTOR, "div.wrapper_info"
                        )
                        # Process only the new items
                        if len(items)<load_last_item_count:
                            last_item_count = len(items)
                            print("Previously checked items, please wait ",last_item_count)
                            continue
                        
                        for item in items[last_item_count:]:
                            try:

                                if cnt>=NUM_RESTAURANTS_PER_COUNTRY:
                                    break

                                name_element = item.find_element(
                                    By.CSS_SELECTOR, "a.notranslate.title_url"
                                )
                                restaurant_name = name_element.text
                                restaurant_url = name_element.get_attribute('href')
                                
                                city_name = ""
                                try:
                                    city_string = item.find_element(
                                        By.CSS_SELECTOR, "div.number"
                                    ).text
                                    marker = "to eat in "
                                    start_index = city_string.find(marker)
                                    city_name = city_string[start_index + len(marker):].strip()

                                    
                                    closed_or_not = item.find_element(
                                        By.CSS_SELECTOR, "div.closed_info_block"
                                    )
                                    if closed_or_not:
                                        closed_or_not = closed_or_not.text
                                        if "permanently closed" in closed_or_not.lower():
                                            continue
                                except Exception as e:
                                    # print(f"[JUST PASSING],{e}")
                                    pass
                                

                                if city_name:
                                    if len(cities.keys())>=MAX_NUM_CITIES_PER_COUNTRY and city_name not in cities.keys():
                                        continue

                                    if cities.get(city_name,0) >= MAX_NUM_RESTAURANTS_PER_CITY:
                                        continue
                                    
                                    fid,gps_coordinate,city_name,search_url = self.get_review_page_fid_gps_from_name(restaurant_name,city_name=city_name,country_name=country_name)

                                    if not fid or not gps_coordinate or not city_name:
                                        continue
                                else:
                                    fid,gps_coordinate,city_name,search_url = self.get_review_page_fid_gps_from_name(restaurant_name,city_name=city_name,country_name=country_name)
                                    
                                    if not fid or not gps_coordinate or not city_name:
                                        continue

                                    if len(cities.keys())>=MAX_NUM_CITIES_PER_COUNTRY and city_name not in cities.keys():
                                        continue

                                    if cities.get(city_name,0) >= MAX_NUM_RESTAURANTS_PER_CITY:
                                        continue


                                

                                if not self.restaurant_details.get(fid,None):
                                    self.restaurant_details[fid] = {"restaurant_name":restaurant_name,"city_name":city_name,"country_name":country_name,"url":search_url,"gps_coordinates":gps_coordinate}
                                    cities[city_name] = cities.get(city_name,0) + 1
                                    print(f"[FOUND] CNT:{cnt+1} - {country_name} --- {city_name} --- {restaurant_name}")
                                else:
                                    continue

                                cnt+=1
                                if cnt>=NUM_RESTAURANTS_PER_COUNTRY:

                                    break
                        
                            except Exception as e:
                                print("EXCEPTION OCCURED: ",e)
                        
                        
                        

                        new_item_count = len(items)
                        
                        self.restaurant_details["last_item_count"] = new_item_count
                        if cnt>=NUM_RESTAURANTS_PER_COUNTRY:
                            self.restaurant_details.pop("last_item_count",None)
                        self.save_progress(self.restaurant_details_file,self.restaurant_details)
                        # Update the count
                        
                        print(f"Processed {new_item_count - last_item_count} new items.\tCity dict: {cities}, CNT: {cnt}")
                        last_item_count = new_item_count


                        if cnt>=NUM_RESTAURANTS_PER_COUNTRY:
                            self.restaurant_details.pop("last_item_count",None)
                            break

                        # Check if we've reached the bottom
                        if driver.execute_script("return document.documentElement.scrollHeight - document.documentElement.scrollTop <= document.documentElement.clientHeight + 1;"):
                            break
                        

                        
                    except TimeoutException:
                        print("No new items loaded, probably reached the end: URL" , url)
                        break

                print(
                    f"Finished processing all items. Total extracted: {cnt}"
                )
                self.restaurant_details.pop("last_item_count",None)


            finally:
                driver.quit()

    def get_review_page_fid_gps_from_name(self, restaurant_name, city_name="", country_name=""):
        """
        Searches for the restaurant name and returns the feature_id and gps_coordinates of the reviews page.
        This method uses requests and BeautifulSoup instead of Selenium for faster performance.

        Returns
        ------
        fid, gps_coordinate : feature_id of the reviews page, gps_coordinate: a str of format "lat,lon"
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        # address = address.split("Abu Dhabi - United Arab Emirates")[0]
        # if city_name:
        #     print("FID: CITY NAME")

        if city_name:
            search_texts = [f"{restaurant_name} {city_name} {country_name}",f"{restaurant_name} restaurant {city_name} {country_name}",f"{restaurant_name} {country_name}",f"{restaurant_name} restaurant {country_name}",f"{restaurant_name} {city_name}",f"{restaurant_name} {city_name} restaurant"]
        else:
            search_texts = [f"{restaurant_name} {city_name} {country_name}",f"{restaurant_name} restaurant {city_name} {country_name}",f"{restaurant_name} {country_name}",f"{restaurant_name} restaurant {country_name}"]

        # search_text = search_text.replace(" ", "+")

        for search_text in search_texts:
            search_text = quote_plus(search_text)
            search_url = f"https://www.google.com/search?q={search_text}+reviews"

            response = requests.get(search_url, headers=self.HEADERS)

            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 60))
                print(f"Rate limit exceeded. Waiting for {retry_after} seconds")
                time.sleep(retry_after)
            
            
            soup = BeautifulSoup(response.text, "html.parser")

            # Find the review link
            review_link = soup.find("a", {"data-async-trigger": "reviewDialog"})
            if review_link:
                break
        if not review_link:
            print("ISSUE FOUND")
            return None, None, None, None

        fid = review_link.get("data-fid")

        num_reviews_string = soup.find("a",{"data-fid":fid}).get_text()

        match = re.search(r'([\d,]+)', num_reviews_string)
        num_reviews = int(match.group(1).replace(',', ''))
        if num_reviews<NUM_REVIEWS_THRESHHOLD:
            return None, None, None, None

        # Find the map link
        map_link = soup.find("a", {"data-url": re.compile(r"@[-\d\.]+,[-\d\.]+")})
        if not map_link:
            return None, None, None, None

        url = map_link.get("data-url")
        match = re.search(r"@([-\d\.]+),([-\d\.]+)", url)
        if match:
            gps_coordinate = f"{match.group(1)},{match.group(2)}"
        else:
            gps_coordinate = None

        # CITY CHECK
        if city_name:
            return fid, gps_coordinate, city_name, search_url
        else:
            # WE GET THE CITY NAME
            address = soup.find("span",class_="LrzXr").get_text()    

            parts = address.split(',')
    
            # Remove the last part (country) and any leading/trailing whitespace
            parts = [part.strip() for part in parts[:-1]]
            
            # Get the second to last part, which should contain the city
            city_part = parts[-1]
            
            # Split this part by spaces
            city_words = city_part.split()
            
            # Filter out any parts that are purely numeric
            city_words = [word for word in city_words if not word.isdigit()]
            
            # Join the remaining words to form the city name
            city_name = ' '.join(city_words)

            return fid, gps_coordinate, city_name, search_url
        
    def load_progress(self, save_file):
        try:
            if os.path.getsize(save_file) == 0:
                return {}
            with open(save_file, "r", encoding="utf-8") as file:
                return json.load(file)
        except FileNotFoundError:
            return {}

    def save_progress(self, save_file, save_data):
        with open(save_file, "w", encoding="utf-8") as file:
            json.dump(save_data, file, ensure_ascii=False)

    def save_to_csv(self, file, row):
        file_exists = os.path.isfile(file)
        with open(file, "a", newline="", encoding="utf-8") as csvfile:
            fieldnames = row.keys()
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

    def generate_unique_filename(self):
        """Helper Method to generate unique filenames
        Returns
        ----
        name: A 15-byte random hexadecimal string"""
        # Generate a random 15-byte hexadecimal string
        name = binascii.b2a_hex(os.urandom(15)).decode("utf-8")
        # Ensure the filename is unique in the given directory
        while os.path.exists(os.path.join("./images/", name)):
            name = binascii.b2a_hex(os.urandom(15)).decode("utf-8")
        return name

    def convert_png_to_webp(self, input_path, output_path, quality=80):
        """
        Convert a PNG image to WebP format.

        :param input_path: Path to the input PNG file
        :param output_path: Path to save the output WebP file
        :param quality: Quality of the output WebP image (0-100, default 80)
        """
        try:
            # Open the PNG image
            with Image.open(input_path) as img:
                # Convert and save as WebP
                img.save(output_path, "WEBP", quality=quality)
            print(f"Converted {input_path} to {output_path}")
            os.remove(input_path)
        except Exception as e:
            print(f"Error converting {input_path}: {str(e)}")

    def download_image(self, name, url):
        response = requests.get(url, stream=True)

        if not os.path.exists("./images"):
            os.makedirs("./images")
        with open(f"./images/{name}.png", "wb") as out_file:
            shutil.copyfileobj(response.raw, out_file)

        # self.convert_png_to_webp(f"./images/{name}.png", f"./images/{name}.webp")

    def start_requests(self):

        # return

        for fid in self.restaurant_details:
            restaurant_detail = self.restaurant_details[fid]

            restaurant_name = restaurant_detail["restaurant_name"]
            if fid not in self.scraping_progress:
                self.scraping_progress[fid] = {
                    "restaurant_name": restaurant_name,
                    "status": "not_started",
                    "next_page_token": "",
                    "images_left_to_download": NUM_IMGS_TO_DOWNLOAD
                }

            if self.scraping_progress[fid]["images_left_to_download"]==0:
                continue
            
            if self.scraping_progress[fid]["status"] != "completed":

                next_page_token = self.scraping_progress[fid]["next_page_token"]
                url = (
                    "https://www.google.com/async/reviewDialog?async=feature_id:"
                    + str(fid)
                    + f",next_page_token:{next_page_token}"
                    + ",_fmt:pc"
                )

                images_left_to_download = self.scraping_progress[fid]["images_left_to_download"]

                yield Request(
                    url=url,  # THE URL CONTAINS THE NEXT PAGE TOKEN, NO NEED TO SEND IT VIA META
                    headers=self.HEADERS,
                    callback=self.parse_reviews,
                    meta={
                        "feature_id":fid,
                        "restaurant_detail": restaurant_detail,
                        "images_left_to_download":images_left_to_download
                    },
                )

    def parse_reviews(self, response):
        """Parses the response object from a previous request, loads first 10 reviews, saves the data for the ones that have images with them in a csv. Finally it detects the next_page_token and then recursively calls itself for the next 10 entries.
        Args
        --------
        response - the Response object from a Request


        """

        restaurant_detail = response.meta["restaurant_detail"]

        restaurant_name = restaurant_detail["restaurant_name"]
        country_name = restaurant_detail["country_name"]
        city_name = restaurant_detail["city_name"]
        gps_coordinate = restaurant_detail["gps_coordinates"]
        
        lat, lon = gps_coordinate.split(',')

        # Convert to float for numerical operations
        lat = float(lat)
        lon = float(lon)

        feature_id = response.meta["feature_id"]
        images_left_to_download = response.meta["images_left_to_download"]

        all_reviews = response.xpath('//*[@id="reviewSort"]/div/div[2]/div')

        if images_left_to_download == 0:
            return

        # WRITE CSV OF 10 REVIEWS
        review_i = 0
        for review in all_reviews:
            # REVIEWER NAME
            reviewer = review.css("div.TSUbDb a::text").extract_first()

            reviewer_id = review.xpath(
                "substring-before(substring-after(.//div[@class='TSUbDb']/a[contains(@href, '/maps/contrib/')]/@href, '/contrib/'), '?')"
            ).extract_first()

            num_reviews = review.css("span.A503be::text").extract_first()

            if isinstance(num_reviews, str):
                num_reviews = re.search(r'(\d+)\s*review', num_reviews)
                if num_reviews:
                    num_reviews=num_reviews.group(1)
                else:
                    num_reviews=0
            else:
                num_reviews = 0

            # GET THE DESCRIPTION
            description = review.xpath(
                './/span[@class="review-full-text"]'
            ).extract_first()

            if description is None:
                # THIS IS WHEN THERE IS NO ...MORE OPTION AFTER THE DESCRIPTION
                description = review.css(".Jtu6Td span").extract_first()

                soupDescription = BeautifulSoup(description, "html.parser")

                if soupDescription:
                    # THERE MIGHT BE OTHRE DIVS/ELEMENTS WHICH WE ARE NOT INTERESTED IN. WE ONLY CARE ABOUT THE DESCRIPTION TEXT
                    nested_div = soupDescription.find(
                        "div", class_="k8MTF"
                    )  # NO UNWANTED DIVS
                    if nested_div:
                        nested_div.decompose()

                    nested_span = soupDescription.find(  # NO UNWANTED SPANS
                        "span", attrs={"data-ellipsis-for-sq": True}
                    )
                    if nested_span:
                        nested_span.decompose()

                    nested_a = soupDescription.find(  # NO UNWANTED LINK TAGS
                        "a", class_="review-more-link"
                    )
                    if nested_a:
                        nested_a.decompose()

                    for br in soupDescription.find_all("br"):
                        br.replace_with(" ")  # CHANGE <br> TAGS TO "\n"

                description = soupDescription.get_text(separator="")

                if description is None:  # JUST IN CASE
                    description = ""
            else:
                soup = BeautifulSoup(description, "html.parser")
                description = soup.get_text(separator=" ")  # CHANGE <br> TAGS TO "\n"
            
            description = description.replace("\n"," ")

            # GET REVIEW RATING
            # NOTE: ACTIVATE NYU VPN PLEASE, THE ARABIC LOCATION ISN'T HELPFUL FOR SCRAPING
            review_rating = float(
                review.xpath('.//span[@class="lTi8oc z3HNkc"]/@aria-label')
                .extract_first()
                .split(" ")[1]
            )

            # GET REVIEW DATE
            review_date = review.xpath(
                './/span[@class="dehysf lTi8oc"]/text()'
            ).extract_first()

            # IMAGE LINKS HERE WE GO!
            review_imgs_div = review.xpath('.//div[@class="EDblX GpHuwc"]/div/a/div')

            # WE GET THE IMAGE URL BY EXTRACTING FROM background-image:url()
            url_pattern = re.compile(r"url\((.*?)\)")

            image_i = 0
            # image_names_str = ""
            for review_img_div in review_imgs_div:
                image_i += 1

                if image_i>MAX_NUM_IMGS_PER_USER:
                    break
                style_str = review_img_div.xpath("@style").extract_first()

                # FIND THE URL
                url = url_pattern.search(style_str).group(1)
                url = re.sub(r"=w100-h100-p-n-k-no", "", url)
                url += "=s1000-no"  # THIS MAKES THE IMAGE MIN_DIM 1000

                feature_id_str = feature_id.replace(":","_")
                image_name = f"{feature_id_str}_{reviewer_id}_{image_i}"
                # image_names_str += "," + image_name

                """DOWNLOAD"""
                self.download_image(image_name, url)

                data_row = {
                    "country_name":country_name,
                    "city_name":city_name,
                    "restaurant_name": restaurant_name,
                    "feature_id":feature_id,
                    "lat": lat,
                    "lon": lon,
                    "reviewer": reviewer,
                    "reviewer_id": reviewer_id,
                    "num_reviews": num_reviews,
                    "description": description,
                    "review_rating": review_rating,
                    "review_date": review_date,
                    "image_name": image_name,
                }
                self.save_to_csv(self.scrape_data_file, data_row)

                images_left_to_download -= 1
                if images_left_to_download == 0:
                    break

            review_i += 1
            if images_left_to_download == 0:
                break

        # FIND NEXT PAGE TOKEN
        next_page_token_div = response.xpath('//*[@id="reviewSort"]/div/div[2]')
        next_page_token = next_page_token_div.xpath(
            "@data-next-page-token"
        ).extract_first()

        next_url = (
            response.request.url.split(",next_page_token:")[0]
            + f",next_page_token:{next_page_token},_fmt:pc"
        )
        # print("NEXT URL!\n\n\n", next_url, "NEXT URL!\n\n\n")

        ##########################
        # LOG YOUR CURRENT PROGRESS SO THAT YOU CAN PICK UP FROM HERE LATER
        self.scraping_progress[feature_id]["next_page_token"] = next_page_token
        if next_page_token == "":
            self.scraping_progress[feature_id]["status"] = "completed"
        else:
            self.scraping_progress[feature_id]["status"] = "in_progress"

        self.scraping_progress[feature_id]["images_left_to_download"] = images_left_to_download

        self.save_progress(self.scraping_progress_file, self.scraping_progress)

        if next_page_token != "":
            if images_left_to_download > 0:

                # SEND REQUEST TO LOAD THE NEXT 10 REVIEWS
                yield Request(
                    url=next_url,
                    headers=self.HEADERS,
                    callback=self.parse_reviews,
                    dont_filter=True,
                    meta={
                        "feature_id":feature_id,
                        "restaurant_detail": restaurant_detail,
                        "images_left_to_download":images_left_to_download
                    },
            )


# spider = GoogleSpider()
# spider.scrape_restaurant_details_from_random_users(num_users=500)
# spider.scrape_restaurant_details()
# spider.save_restaurant_details_from_names()

# spider.scrape_restaurant_names_from_country(COUNTRIES)
