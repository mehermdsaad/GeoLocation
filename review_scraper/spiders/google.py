import binascii
import csv
import json
import os
import random
import re
import shutil
import time
from urllib.parse import quote_plus

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
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

scraping_progress_file = "./logs/scraping_log.json"
restaurant_details_file = "./data/restaurant_details.json"
restaurant_names_file = "./data/restaurant_names.json"
scrape_data_file = "./reviews.csv"


class GoogleSpider(scrapy.Spider):

    name = "google"

    HEADERS = {
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36 Edg/87.0.664.66",
        "referer": None,
    }

    def __init__(self, *args, **kwargs):
        super(GoogleSpider, self).__init__(*args, **kwargs)
        self.scraping_progress_file = scraping_progress_file
        self.scraping_progress = self.load_progress(self.scraping_progress_file)
        self.restaurant_details_file = restaurant_details_file
        self.restaurant_details = self.load_progress(self.restaurant_details_file)
        self.restaurant_names_file = restaurant_names_file
        self.restaurant_names = self.load_progress(self.restaurant_names_file)

        self.scrape_data_file = scrape_data_file

    def scrape_restaurant_details_from_random_users(self, num_users=50):
        with open(self.scrape_data_file, "r", newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            all_users = list(reader)

        # Randomly select N users
        # NOTE: NEEDS IMPROVEMENTS
        # - Select only one user only once - maybe use dicts?
        # - Once you go thur one user, make sure you don't hit upon the same user again
        # random.seed(42)
        selected_users = random.sample(all_users, num_users)

        prev_restaurant_count = len(self.restaurant_details.keys())
        # Process each selected user
        for i, user in enumerate(selected_users):
            restaurant_count_before_user = len(self.restaurant_details.keys())

            username = user["Reviewer"]
            user_id = user["Reviewer ID"]
            print(f"\n{i+1:<3}: Looking at {username}, {user_id}:")

            self.scrape_restaurant_details_per_user(user_id, username=username)

            self.save_progress(self.restaurant_details_file, self.restaurant_details)

            print(
                f"\nUser {i+1}: {user['Reviewer'][:20]:<20}\tUnique Restaurants from user: {(len(self.restaurant_details.keys())-restaurant_count_before_user):>4}. Total Restaurants: {len(self.restaurant_details.keys()):>6}"
            )

        print(
            "\nRestaurant names collection completed. New restaurants found: ",
            len(self.restaurant_details.keys()) - prev_restaurant_count,
            ". Total Restaurants: ",
            len(self.restaurant_details.keys()),
        )

    def scrape_restaurant_details_per_user(self, user_id, username="USER", timeout=300):
        url = f"https://www.google.com/maps/contrib/{user_id}/reviews?entry=ttu"

        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--headless")  # Run in headless mode (optional)

        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), options=chrome_options
        )

        try:
            driver.get(url)

            scrollable_div = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (
                        By.CSS_SELECTOR,
                        'div.m6QErb.DxyBCb.kA9KIf.dS8AEf.XiKgde[aria-label="Reviews"]',
                    )
                )
            )

            last_item_count = 0
            extracted_data = []

            def extract_data_from_item(item):
                # Extract name and address from the item
                # You'll need to adjust these XPaths based on the actual structure of your page
                name_element = item.find_element(By.CSS_SELECTOR, ".d4r55.YJxk2d")
                address_element = item.find_element(By.CSS_SELECTOR, "div.RfnDt.xJVozb")

                name, address = None, None
                if name_element:
                    name = name_element.text.strip()
                if address_element:
                    address = address_element.text.strip()

                return name, address

            start_time = time.time()

            n_restaurants_before_user = len(self.restaurant_details.keys())
            while True:
                # Scroll the reviews div
                driver.execute_script(
                    "arguments[0].scrollTop = arguments[0].scrollHeight", scrollable_div
                )

                try:
                    # Wait for new items to load
                    WebDriverWait(driver, 10).until(
                        lambda d: len(
                            d.find_elements(
                                By.CSS_SELECTOR,
                                "div.jftiEf.fontBodyMedium.t2Acle.FwTFEc.azD0p",
                            )
                        )
                        > last_item_count
                    )

                    # Get all items
                    items = scrollable_div.find_elements(
                        By.CSS_SELECTOR, "div.jftiEf.fontBodyMedium.t2Acle.FwTFEc.azD0p"
                    )
                    # Process only the new items
                    for item in items[last_item_count:]:
                        try:
                            name, address = extract_data_from_item(item)
                        except Exception:
                            # Sometimes there're no addresses. Ignore for now
                            continue
                        # CHECK IF ABU DHABI OR NOT
                        check_address = address.lower()

                        # List of abu dhabi-related keywords
                        address_keywords = ["abu dhabi"]

                        if not any(
                            keyword in check_address for keyword in address_keywords
                        ):
                            print(f"[NOT AD] Place name: {name} {address}")
                            continue

                        # GET FID, GPS NOTE: FIX THE ISSUES HERE
                        fid, gps_coordinate = self.get_review_page_fid_gps_from_name(
                            name, address
                        )

                        if not fid or not gps_coordinate:
                            continue

                        # CHECK IF UNIQUE OR NOT
                        if self.restaurant_details.get(fid, None):
                            continue  # THIS WE HAVE SEEN BEFORE

                        # CHECK IF INSIDE BOX OR NOT
                        gps_list = gps_coordinate.split(",")

                        # Convert to floating-point numbers
                        lat = float(gps_list[0])
                        lon = float(gps_list[1])

                        if not self.is_point_in_quadrilateral(lat, lon):
                            continue  # OUTSIDE OUR BOX

                        # CHECKS SUCCESSFUL, UNIQUE RESTAURANT FOUND:
                        self.restaurant_details[fid] = {
                            "name": name,
                            "address": address,
                            "gps_coordinates": gps_coordinate,
                        }

                        print(
                            f"[FOUND]\t Name: {name}\t: {address:<30}\tTotal Unique Restaurants:{len(self.restaurant_details.keys())-n_restaurants_before_user:>4}"
                        )
                    # Update the count
                    new_item_count = len(items)
                    print(f"Processed {new_item_count - last_item_count} new items")
                    last_item_count = new_item_count

                    # Check if we've reached the bottom
                    if driver.execute_script(
                        "return arguments[0].scrollHeight - arguments[0].scrollTop === arguments[0].clientHeight;",
                        scrollable_div,
                    ):
                        break

                except TimeoutException:
                    print("No new items loaded, probably reached the end")
                    break

            print(
                f"Finished processing all items. Total extracted: {len(extracted_data)}"
            )

            # return restaurants

        finally:
            driver.quit()

    def get_review_page_fid_gps_from_name(self, name, address=""):
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
        address = address.split("Abu Dhabi - United Arab Emirates")[0]
        search_text = name + " " + address
        # search_text = search_text.replace(" ", "+")

        search_text = quote_plus(search_text)
        search_url = f"https://www.google.com/search?q={search_text}+Abu+Dhabi+reviews"

        response = requests.get(search_url, headers=headers)
        soup = BeautifulSoup(response.text, "html.parser")

        # Check if restaurant or not:
        place_type_element = soup.find(
            "div", {"data-attrid": "kc:/local:one line summary"}
        )
        if place_type_element:
            place_type = place_type_element.get_text()
        else:
            place_type_element = soup.find("div", {"data-attrid": "subtitle"})
            if not place_type_element:
                print(f"[DESCRIPTION NOT FOUND],URL: {search_url}")

                # box = soup.find("div", {"data-attrid": "title"})
                # if box:
                #     print(f"BOX LOCATED - {name} {address}")
                # else:
                #     print(f"NO BOX :) - {name} {address}")
                return None, None
            place_type = place_type_element.get_text()

        place_type = place_type.lower()

        # List of food-related keywords
        food_keywords = [
            "restaurant",
            "cafe",
            "cafeteria",
            "bakery",
            "bistro",
            "diner",
            "eatery",
            "grill",
            "pizzeria",
            "steakhouse",
            "tavern",
            "trattoria",
            "fast food",
            "food court",
            "buffet",
            "coffee shop",
            "ice cream parlor",
            "sandwich shop",
            "sushi bar",
            "tea house",
            "pub",
            "bar & grill",
            "food truck",
            "delicatessen",
            "patisserie",
            "creperie",
            "brasserie",
            "dessert",
            "pastry",
            "sweets",
            "confectionary",
            "deli",
        ]

        # Check if the place_type contains any food-related keyword
        if not any(keyword in place_type for keyword in food_keywords):
            print(
                f"[NOT RESTAURANT] Place name: {name[:20]:<20} Address: {address[:20]:<20}"
            )
            return None, None
        # Else this is a place to eat

        # Find the review link
        review_link = soup.find("a", {"data-async-trigger": "reviewDialog"})
        if not review_link:
            return None, None

        fid = review_link.get("data-fid")

        # Find the map link
        map_link = soup.find("a", {"data-url": re.compile(r"@[-\d\.]+,[-\d\.]+")})
        if not map_link:
            return fid, None

        url = map_link.get("data-url")
        match = re.search(r"@([-\d\.]+),([-\d\.]+)", url)
        if match:
            gps_coordinate = f"{match.group(1)},{match.group(2)}"
        else:
            gps_coordinate = None

        return fid, gps_coordinate

    def save_restaurant_details_from_names(self):
        """Helper method to get feature_ids and gps_coordinates from restaurant_names. Takes a list of restaurant names.
        Returns the lists feature_id,gps_coordinates
        -- NOTE: This makes use of Selenium, so captcha might be an issue
        -- NOTE: Might need to implement a log system for getting the fid,gps since captcha and other stuff might be a hurdle
        """

        for name, address in self.restaurant_names.items():
            fid, gps_coordinate = self.get_review_page_fid_gps_from_name(name, address)
            if fid:
                self.restaurant_details[fid] = {
                    "name": name,
                    "address": address,
                    "gps_coordinates": gps_coordinate,
                }

            del self.restaurant_names[name]
        self.save_progress(self.restaurant_names_file, self.restaurant_names)
        self.save_progress(self.restaurant_details_file, self.restaurant_details)

    def is_point_in_quadrilateral(self, lat, lon):
        vertices = [
            (24.441665, 54.257385),
            (24.061811, 54.665366),
            (24.540004, 55.056711),
            (24.899426, 54.506009),
        ]  # A GENEROUS BOUNDARY OF ABU DHABI

        def is_left(p0, p1, p2):
            return (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p2[0] - p0[0]) * (p1[1] - p0[1])

        wn = 0  # winding number

        for i in range(4):
            if vertices[i][1] <= lon:
                if vertices[(i + 1) % 4][1] > lon:
                    if is_left(vertices[i], vertices[(i + 1) % 4], (lat, lon)) > 0:
                        wn += 1
            else:
                if vertices[(i + 1) % 4][1] <= lon:
                    if is_left(vertices[i], vertices[(i + 1) % 4], (lat, lon)) < 0:
                        wn -= 1

        return wn != 0

    def generate_points_in_quadrilateral(self, vertices, num_points=4):
        (x1, y1) = vertices[0]
        (x2, y2) = vertices[1]
        (x3, y3) = vertices[2]
        (x4, y4) = vertices[3]

        # Calculate the number of points along each dimension
        n = int(np.sqrt(num_points))

        # Generate a grid of points in the unit square
        u, v = np.meshgrid(np.linspace(0, 1, n), np.linspace(0, 1, n))
        u, v = u.flatten(), v.flatten()

        # Perform bilinear interpolation
        x = (1 - u) * (1 - v) * x1 + u * (1 - v) * x2 + u * v * x3 + (1 - u) * v * x4
        y = (1 - u) * (1 - v) * y1 + u * (1 - v) * y2 + u * v * y3 + (1 - u) * v * y4

        # Combine x and y into a list of tuples
        return list(zip(x, y))

    def scrape_restaurant_details(self, timeout=300, num_points=400):
        # COMPLETE
        vertices = [
            (24.459788, 54.314777),
            (24.393291, 54.523680),
            (24.484544, 54.643805),
            (24.564686, 54.458536),
        ]
        pts = self.generate_points_in_quadrilateral(vertices, num_points=num_points)

        for i, pt in enumerate(pts):
            print(
                "\nChecking ",
                i + 1,
                "th Point, Total Unique Restaurants So Far:",
                len(self.restaurant_details.keys()),
            )
            current_dict = self.scrape_restaurant_details_at_gps(
                lat=pt[0], lon=pt[1], timeout=timeout
            )
            self.restaurant_details.update(current_dict)

            self.save_progress(self.restaurant_details_file, self.restaurant_details)
        print(
            "\nRestaurant name collection completed. Total restaurants found: ",
            len(self.restaurant_details.keys()),
        )

    def scrape_restaurant_details_at_gps(
        self, lat=24.5264811, lon=54.4092652, timeout=300
    ):
        url = (
            f"https://www.google.com/maps/search/Restaurants/@{lat},{lon},15z?entry=ttu"
        )

        print(f"\nLooking at {lat},{lon}:")
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--headless")  # Run in headless mode (optional)

        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), options=chrome_options
        )

        def extract_info_from_url(input_str):
            # Extract fid
            data_index = input_str.find("data=")
            data_str = input_str[data_index + len("data=") :]

            end_index = data_str.find("!", 12)
            fid = data_str[11:end_index]

            # Extract coordinates
            lat_start_index = data_str.find("!3d") + 3
            lat_end_index = data_str.find("!", lat_start_index)
            lat = data_str[lat_start_index:lat_end_index]

            lon_start_index = data_str.find("!4d") + 3
            lon_end_index = data_str.find("!", lon_start_index)
            lon = data_str[lon_start_index:lon_end_index]

            gps_coordinate = lat + "," + lon

            return fid, gps_coordinate

        try:
            driver.get(url)

            scrollable_div = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'div[aria-label="Results for Restaurants"]')
                )
            )

            restaurants = {}
            last_height = driver.execute_script(
                "return arguments[0].scrollHeight", scrollable_div
            )
            start_time = time.time()

            while True:

                if time.time() - start_time > timeout:
                    print(
                        f"Timeout of {timeout} seconds reached. Returning current results."
                    )
                    break

                # Scroll down to bottom
                driver.execute_script(
                    "arguments[0].scrollTo(0, arguments[0].scrollHeight);",
                    scrollable_div,
                )

                # Wait to load page
                try:
                    WebDriverWait(driver, 10).until(
                        lambda d: d.execute_script(
                            "return arguments[0].scrollHeight", scrollable_div
                        )
                        > last_height
                    )
                except TimeoutException:
                    print("No new content loaded. Assuming end of results.")
                    break

                # Calculate new scroll height and compare with last scroll height
                new_height = driver.execute_script(
                    "return arguments[0].scrollHeight", scrollable_div
                )

                # Get current restaurant entries
                try:
                    # Locate all parent divs that contain restaurant information
                    restaurant_entries = scrollable_div.find_elements(
                        By.CSS_SELECTOR, "div.Nv2PK.THOPZb.CpccDe"
                    )

                    for entry in restaurant_entries:
                        try:
                            # Find name and address within each entry
                            name_element = entry.find_element(
                                By.CSS_SELECTOR, ".qBF1Pd.fontHeadlineSmall"
                            )
                            address_container = entry.find_element(
                                By.CSS_SELECTOR, "div.UaQhfb.fontBodyMedium"
                            )
                            address_element = address_container.find_element(
                                By.XPATH, "./div[@class='W4Efsd'][2]/div/span[last()]"
                            )

                            url_str = entry.find_element(
                                By.XPATH, "./a[@class='hfpxzc']"
                            ).get_attribute("href")

                            fid, gps_coordinate = extract_info_from_url(url_str)

                            gps_list = gps_coordinate.split(",")

                            # Convert to floating-point numbers
                            lat = float(gps_list[0])
                            lon = float(gps_list[1])

                            if not self.is_point_in_quadrilateral(lat, lon):
                                continue  # OUTSIDE OUR BOX

                            name, address = None, None
                            if name_element:
                                name = name_element.text.strip()
                            if address_element:
                                address = address_element.text.strip()

                            if fid not in restaurants:
                                restaurants[fid] = {
                                    "name": name,
                                    "address": address,
                                    "gps_coordinates": gps_coordinate,
                                }

                                print(
                                    f"Update: Time {round(time.time() - start_time,2)}s. \tRestaurant Name: {name[:20]:<20}\tAddress: {address[:10]:<10}\tFID: {fid:<20}\tTotal Restaurants:{len(restaurants):>4}"
                                )

                        except Exception as e:
                            # print(type(e).__name__, "Meeh don't worry ;)")
                            continue
                except StaleElementReferenceException:
                    scrollable_div = driver.find_element(
                        By.CSS_SELECTOR, 'div[aria-label="Results for Restaurants"]'
                    )
                    continue

                # Check if "End of Results" message is visible
                try:
                    end_of_results = WebDriverWait(driver, 3).until(
                        EC.presence_of_element_located(
                            (By.XPATH, "//*[contains(text(), 'End of Results')]")
                        )
                    )
                    if end_of_results.is_displayed():
                        print("Reached end of results.")
                        break
                except TimeoutException:
                    pass  # "End of Results" not found, continue scrolling

                if new_height == last_height:
                    print("Reached end of scroll.")
                    break
                last_height = new_height

            return restaurants

        finally:
            driver.quit()

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

    def start_requests(self):

        return

        for fid in self.restaurant_details:
            restaurant_detail = self.restaurant_details[fid]

            restaurant_name = restaurant_detail["name"]
            if fid not in self.scraping_progress:
                self.scraping_progress[fid] = {
                    "restaurant_name": restaurant_name,
                    "status": "not_started",
                    "next_page_token": "",
                }

            if self.scraping_progress[fid]["status"] != "completed":

                gps_coordinate = restaurant_detail["gps_coordinates"]

                next_page_token = self.scraping_progress[fid]["next_page_token"]
                url = (
                    "https://www.google.com/async/reviewDialog?async=feature_id:"
                    + str(fid)
                    + f",next_page_token:{next_page_token}"
                    + ",_fmt:pc"
                )

                yield Request(
                    url=url,  # THE URL CONTAINS THE NEXT PAGE TOKEN, NO NEED TO SEND IT VIA META
                    headers=self.HEADERS,
                    callback=self.parse_reviews,
                    meta={
                        "restaurant_name": restaurant_name,
                        "feature_id": fid,
                        "gps_coordinate": gps_coordinate,
                    },
                )

    def save_to_csv(self, file, row):
        file_exists = os.path.isfile(file)
        with open(file, "a", newline="", encoding="utf-8") as csvfile:
            fieldnames = [
                "Restaurant Name",
                "GPS Coordinates",
                "Reviewer",
                "Reviewer ID",
                "Description",
                "Rating",
                "Review Date",
                "Image Filename",
            ]
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
        with open(f"./images/{name}.png", "wb") as out_file:
            shutil.copyfileobj(response.raw, out_file)

        self.convert_png_to_webp(f"./images/{name}.png", f"./images/{name}.webp")

    def parse_reviews(self, response):
        """Parses the response object from a previous request, loads first 10 reviews, saves the data for the ones that have images with them in a csv. Finally it detects the next_page_token and then recursively calls itself for the next 10 entries.
        Args
        --------
        response - the Response object from a Request


        """

        restaurant_name = response.meta["restaurant_name"]
        gps_coordinate = response.meta["gps_coordinate"]
        feature_id = response.meta["feature_id"]

        all_reviews = response.xpath('//*[@id="reviewSort"]/div/div[2]/div')

        # WRITE CSV OF 10 REVIEWS
        review_i = 0
        for review in all_reviews:
            # REVIEWER NAME
            reviewer = review.css("div.TSUbDb a::text").extract_first()

            reviewer_id = review.xpath(
                "substring-before(substring-after(.//div[@class='TSUbDb']/a[contains(@href, '/maps/contrib/')]/@href, '/contrib/'), '?')"
            ).extract_first()

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
                        br.replace_with("\n")  # CHANGE <br> TAGS TO "\n"

                description = soupDescription.get_text(separator="")

                if description is None:  # JUST IN CASE
                    description = ""
            else:
                soup = BeautifulSoup(description, "html.parser")
                description = soup.get_text(separator="\n")  # CHANGE <br> TAGS TO "\n"

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
            image_names_str = ""
            for review_img_div in review_imgs_div:
                image_i += 1
                style_str = review_img_div.xpath("@style").extract_first()

                # FIND THE URL
                url = url_pattern.search(style_str).group(1)
                url = re.sub(r"=w100-h100-p-n-k-no", "", url)
                url += "=s2000-no"  # THIS MAKES THE IMAGE 2000x2000

                image_name = self.generate_unique_filename()
                image_names_str += "," + image_name

                """DOWNLOAD"""
                # self.download_image(image_name, url)

            image_names_str = image_names_str[1:]  # DROP THE COMMA

            if image_i > 0:
                # A SEPERATE LINE FOR EACH REVIEWER

                data_row = {
                    "Restaurant Name": restaurant_name,
                    "GPS Coordinates": gps_coordinate,
                    "Reviewer": reviewer,
                    "Reviewer ID": reviewer_id,
                    "Description": description,
                    "Rating": review_rating,
                    "Review Date": review_date,
                    "Image Filename": image_names_str,
                }
                self.save_to_csv(self.scrape_data_file, data_row)

            review_i += 1

        # FIND NEXT PAGE TOKEN
        next_page_token_div = response.xpath('//*[@id="reviewSort"]/div/div[2]')
        next_page_token = next_page_token_div.xpath(
            "@data-next-page-token"
        ).extract_first()

        next_url = (
            response.request.url.split(",next_page_token:")[0]
            + f",next_page_token:{next_page_token},_fmt:pc"
        )
        print("NEXT URL!\n\n\n", next_url, "NEXT URL!\n\n\n")

        ##########################
        # LOG YOUR CURRENT PROGRESS SO THAT YOU CAN PICK UP FROM HERE LATER
        self.scraping_progress[feature_id]["next_page_token"] = next_page_token
        if next_page_token == "":
            self.scraping_progress[feature_id]["status"] = "completed"
        else:
            self.scraping_progress[feature_id]["status"] = "in_progress"

        self.save_progress(self.scraping_progress_file, self.scraping_progress)

        if next_page_token != "":
            # SEND REQUEST TO LOAD THE NEXT 10 REVIEWS
            yield Request(
                url=next_url,
                headers=self.HEADERS,
                callback=self.parse_reviews,
                dont_filter=True,
                meta={
                    "restaurant_name": restaurant_name,
                    "feature_id": feature_id,
                    "gps_coordinate": gps_coordinate,
                },
            )


spider = GoogleSpider()
spider.scrape_restaurant_details_from_random_users(num_users=500)
# spider.scrape_restaurant_details()
# spider.save_restaurant_details_from_names()
