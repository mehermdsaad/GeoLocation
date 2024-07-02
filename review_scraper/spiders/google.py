import binascii
import csv
import json
import os
import re
import shutil

#######
# SELENIUM IMPORTS
import time

import requests
import scrapy
from bs4 import BeautifulSoup
from scrapy.http.request import Request
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

#######
# TASK LISTS

# - To Load everything one after the other without quitting the browser - Second thoughts, might not be very practical.. might save whatever we can procure in a csv.
# - Function that loads listing image

progress_file = "./logs/scraping_log.json"
restaurant_details_file = "./data/restaurant_details.json"


class GoogleSpider(scrapy.Spider):

    name = "google"

    HEADERS = {
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36 Edg/87.0.664.66",
        "referer": None,
    }

    def __init__(self, *args, **kwargs):
        super(GoogleSpider, self).__init__(*args, **kwargs)
        self.progress_file = progress_file
        self.progress = self.load_progress()
        self.restaurant_details_file = restaurant_details_file
        self.restaurant_details = self.load_progress_restaurant_details()

    def get_review_page_fid(self, name):
        """Searches for the restaurant name, one at a time and returns the feature_id, gps_coordinates of the reviews page NOTE: Uses selenium!
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

        # self.load_progress_restaurant_details()

        for restaurant_name in restaurant_names:
            if not self.restaurant_details.get(restaurant_name, {}).get(
                "feature_id", None
            ):
                fid, gps_coordinate = self.get_review_page_fid(restaurant_name)
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

                self.save_progress_restaurant_details()

    def save_restaurant_details(self):
        """This is a method designed to be used only to get a comprehensive list of names and their details once."""
        # NOTE: CALL THE NAME SCRAPING FUNCTION HERE
        restaurant_names = [
            # # RESTAURANT NAMES, SHOULD GET IT FROM GOOGLE MAPS API
            "B Laban Abu Dhabi",
            "Sushi Counter NYUAD",
            "Happy Yemen Restaurant",
            "Bait El Khetyar -Najdah",
            "The Marketplace",
        ]

        self.get_fid_gps_from_names(restaurant_names)

    def load_progress(self):
        try:
            if os.path.getsize(self.progress_file) == 0:
                return {}
            with open(self.progress_file, "r") as file:
                return json.load(file)
        except FileNotFoundError:
            return {}

    def load_progress_restaurant_details(self):
        try:
            if os.path.getsize(self.restaurant_details_file) == 0:
                return {}
            with open(self.restaurant_details_file, "r") as file:
                print("\n\n\nFILE LOADED!!!!!!!!!!!!!!!!!!!!!!!!\n\n\n\n")
                return json.load(file)
        except FileNotFoundError:
            return {}

    def save_progress(self):
        with open(self.progress_file, "w") as file:
            json.dump(self.progress, file)

    def save_progress_restaurant_details(self):
        with open(self.restaurant_details_file, "w") as file:
            json.dump(self.restaurant_details, file)

    def start_requests(self):

        # self.load_restaurant_details()

        for restaurant_name in self.restaurant_details:
            restaurant_detail = self.restaurant_details[restaurant_name]
            if restaurant_name not in self.progress:
                self.progress[restaurant_name] = {
                    "status": "not_started",
                    "next_page_token": "",
                }

            if self.progress[restaurant_name]["status"] != "completed":

                feature_id, gps_coordinate = (
                    restaurant_detail["feature_id"],
                    restaurant_detail["gps_coordinates"],
                )
                next_page_token = self.progress[restaurant_name]["next_page_token"]
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

    def download_image(self, name, url):
        response = requests.get(url, stream=True)
        with open(f"./images/{name}.png", "wb") as out_file:
            shutil.copyfileobj(response.raw, out_file)

    def parse_reviews(self, response):
        """Parses the response object from a previous request, loads first 10 reviews, saves the data for the ones that have images with them in a csv. Finally it detects the next_page_token and then recursively calls itself for the next 10 entries.
        - When loading for the first call(when response.meta["iter"]==0) it detects the total reviews in the page and accounts for pagination.
        - Note: Currently for debugging purposes it doesn't keep loading the next pages. Delete line 131 for auto total review scrapes.
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
                url += "=s2000-p-k-no"  # THIS MAKES THE IMAGE 2000x2000

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
        self.progress[restaurant_name]["next_page_token"] = next_page_token
        if next_page_token == "":
            self.progress[restaurant_name]["status"] = "completed"
        else:
            self.progress[restaurant_name]["status"] = "in_progress"

        self.save_progress()

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
spider.save_restaurant_details()
