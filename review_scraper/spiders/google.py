import binascii
import csv
import json
import os
import re
import shutil

#######
# SELENIUM IMPORTS
import time

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

#######
# TASK LISTS

# - To Load everything one after the other without quitting the browser - Second thoughts, might not be very practical.. might save whatever we can procure in a csv.
# - Function that loads listing image

progress_file = "./logs/scraping_log.json"
restaurant_details_file = "./data/restaurant_details.json"
restaurant_names_file = "./data/restaurant_names.json"


class GoogleSpider(scrapy.Spider):

    name = "google"

    HEADERS = {
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36 Edg/87.0.664.66",
        "referer": None,
    }

    def __init__(self, *args, **kwargs):
        super(GoogleSpider, self).__init__(*args, **kwargs)
        self.progress_file = progress_file
        self.progress = self.load_progress(self.progress_file)
        self.restaurant_details_file = restaurant_details_file
        self.restaurant_details = self.load_progress(self.restaurant_details_file)
        self.restaurant_names_file = restaurant_names_file
        self.restaurant_names = self.load_progress(self.restaurant_names_file)

    def get_review_page_fid_fast(self, name):
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

        search_url = f"https://www.google.com/search?q={name}+Abu+Dhabi+reviews"

        response = requests.get(search_url, headers=headers)
        soup = BeautifulSoup(response.text, "html.parser")

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

    def generate_points_in_quadrilateral(self, num_points=4):
        # Extract the four corner points
        (x1, y1) = (24.451583, 54.283702)
        (x2, y2) = (24.182576, 54.667959)
        (x3, y3) = (24.365645, 54.930711)
        (x4, y4) = (24.597685, 54.472527)

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

    def scrape_restaurant_names(self, timeout=300, num_points=400):
        pts = self.generate_points_in_quadrilateral(num_points=num_points)

        for pt in pts:
            # print(pt[0], "PT")
            current_dict = self.scrape_restaurant_names_at_gps(
                lat=pt[0], lon=pt[1], timeout=timeout
            )
            self.restaurant_names.update(current_dict)

        print("\n\nTotal restaurants: ", len(self.restaurant_names.keys()), "\n\n")
        self.save_progress(self.restaurant_names_file, self.restaurant_names)

    def scrape_restaurant_names_at_gps(
        self, lat=24.5264811, lon=54.4092652, timeout=300
    ):
        url = f"https://www.google.com/maps/search/Restaurants/@{lat},{lon},12z"

        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--headless")  # Run in headless mode (optional)

        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), options=chrome_options
        )

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
                    WebDriverWait(driver, 5).until(
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
                        By.CSS_SELECTOR, "div.UaQhfb.fontBodyMedium"
                    )

                    for entry in restaurant_entries:
                        try:
                            # Find name and address within each entry
                            name_element = entry.find_element(
                                By.CSS_SELECTOR, ".qBF1Pd.fontHeadlineSmall"
                            )
                            address_element = entry.find_element(
                                By.XPATH, "./div[@class='W4Efsd'][2]/div/span[last()]"
                            )

                            name, address = None, None
                            if name_element:
                                name = name_element.text.strip()
                            if address_element:
                                address = address_element.text.strip()

                            if name and name not in restaurants:
                                restaurants[name] = address
                                print("UPDATED")
                        except Exception:
                            # print(Exception, "Meeh don't worry ;)")
                            continue
                        # except NoSuchElementException:
                        #     print(
                        #         f"Could not find name or address for a restaurant entry"
                        #     )
                        #     continue
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

    def get_review_page_fid(self, name):
        """OBSOLETE FOR NOW
        Searches for the restaurant name, one at a time and returns the feature_id, gps_coordinates of the reviews page NOTE: Uses selenium!
        Returns
        ------
        fid, gps_coordinate : feature_id of the reviews page, gps_coordinate: a str of format "lat,lon"
        """
        service = Service(executable_path="C:\chromedriver-win64\chromedriver.exe")
        driver = webdriver.Chrome(service=service)

        driver.get("https://www.google.com/")

        WebDriverWait(driver, 0.5).until
        (EC.presence_of_element_located((By.CLASS_NAME, "gLFyf")))

        input_element = driver.find_element(By.CLASS_NAME, "gLFyf")
        input_element.clear()
        input_element.send_keys(name + " Abu Dhabi reviews" + Keys.ENTER)

        WebDriverWait(driver, 0.5).until
        (
            EC.presence_of_element_located(
                (By.XPATH, "//a[@data-async-trigger='reviewDialog']")
            )
        )

        element = driver.find_element(
            By.XPATH, "//a[@data-async-trigger='reviewDialog']"
        )
        fid = element.get_attribute("data-fid")

        element = driver.find_element(By.CSS_SELECTOR, "div.SwlyWb.rhsmap4col a")
        url = element.get_attribute("data-url")

        pattern = r"@([\d\.\-]+),([\d\.\-]+)"

        # Search for the pattern in the URL
        match = re.search(pattern, url)

        if match:
            latitude = match.group(1)
            longitude = match.group(2)

        gps_coordinate = f"{latitude},{longitude}"
        driver.quit()

        return fid, gps_coordinate

    def get_fid_gps_from_names(self, restaurant_names):
        """Helper method to get feature_ids and gps_coordinates from restaurant_names. Takes a list of restaurant names.
        Returns the lists feature_id,gps_coordinates
        -- NOTE: This makes use of Selenium, so captcha might be an issue
        -- NOTE: Might need to implement a log system for getting the fid,gps since captcha and other stuff might be a hurdle
        """

        for restaurant_name in restaurant_names:
            if not self.restaurant_details.get(restaurant_name, {}).get(
                "feature_id", None
            ):
                fid, gps_coordinate = self.get_review_page_fid_fast(restaurant_name)
                if fid:
                    if self.restaurant_details.get(restaurant_name, None):
                        self.restaurant_details[restaurant_name]["feature_id"] = fid
                        self.restaurant_details[restaurant_name][
                            "gps_coordinates"
                        ] = gps_coordinate
                    else:
                        restaurant_detail = {
                            "feature_id": fid,
                            "gps_coordinates": gps_coordinate,
                        }
                        self.restaurant_details[restaurant_name] = restaurant_detail

                elif self.restaurant_details.get(restaurant_name, None):
                    del self.restaurant_details[restaurant_name]

                self.save_progress(
                    self.restaurant_details_file, self.restaurant_details
                )

    def save_restaurant_details(self):
        """This is a method designed to be used only to get a comprehensive list of names and their details once."""
        # NOTE: CALL THE NAME SCRAPING FUNCTION HERE
        # restaurant_names = [
        #     # # RESTAURANT NAMES, SHOULD GET IT FROM GOOGLE MAPS API
        #     "B Laban Abu Dhabi",
        #     "Sushi Counter NYUAD",
        #     "Happy Yemen Restaurant",
        #     "Bait El Khetyar -Najdah",
        #     "The Marketplace",
        #     "Al Baik - Al Wahda Mall",
        # ]

        restaurant_names_addresses = []
        for key, value in self.restaurant_names.items():
            restaurant_names_addresses.append(f"{key}: {value}")
        self.get_fid_gps_from_names(restaurant_names_addresses)

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

        for restaurant_name in self.restaurant_details:
            restaurant_detail = self.restaurant_details[restaurant_name]

            feature_id = restaurant_detail["feature_id"]
            if feature_id not in self.progress:
                self.progress[feature_id] = {
                    "restaurant_name": restaurant_name,
                    "status": "not_started",
                    "next_page_token": "",
                }

            if self.progress[feature_id]["status"] != "completed":

                gps_coordinate = restaurant_detail["gps_coordinates"]

                next_page_token = self.progress[feature_id]["next_page_token"]
                url = (
                    "https://www.google.com/async/reviewDialog?async=feature_id:"
                    + str(feature_id)
                    + f",next_page_token:{next_page_token}"
                    + ",_fmt:pc"
                )

                yield Request(
                    url=url,  # THE URL CONTAINS THE NEXT PAGE TOKEN, NO NEED TO SEND IT VIA META
                    headers=self.HEADERS,
                    callback=self.parse_reviews,
                    meta={
                        "restaurant_name": restaurant_name,
                        "feature_id": feature_id,
                        "gps_coordinate": gps_coordinate,
                    },
                )

    def save_to_csv(self, row):
        file_exists = os.path.isfile("reviews.csv")
        with open("reviews.csv", "a", newline="", encoding="utf-8") as csvfile:
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
                self.save_to_csv(data_row)

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
        self.progress[feature_id]["next_page_token"] = next_page_token
        if next_page_token == "":
            self.progress[feature_id]["status"] = "completed"
        else:
            self.progress[feature_id]["status"] = "in_progress"

        self.save_progress(self.progress_file, self.progress)

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
spider.scrape_restaurant_names()
spider.save_restaurant_details()
