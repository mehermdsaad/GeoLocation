import binascii
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

# - Get total reviews automatically - NOTE: DONE
# - To Load everything one after the other without quitting the browser - Second thoughts, might not be very practical.. might save whatever we can procure in a csv.
# - Explore the API, Find Names, Locations
# - Function that loads listing image
# - PLEAAAASE MAKE IT MORE READABLE FOR YOUR FUTURE SELF'S SAKE - NOTE: DONE
# - TRY GIT FOR BETTER SYNCHRONIZATION


class GoogleSpider(scrapy.Spider):

    name = "google"
    next_page_token = None

    # Log file path
    log_file = "scraping_log.json"

    HEADERS = {
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36 Edg/87.0.664.66",
        "referer": None,
    }

    def get_review_page_fid(self, name):
        """Searches for the restaurant name and returns the link of the reviews page
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

    def start_requests(self):
        restaurant_names = [
            # # RESTAURANT NAMES, SHOULD GET IT FROM GOOGLE MAPS API
            # "Torch Club",
            "B Laban Abu Dhabi",
            # "Sushi Counter NYUAD",
        ]

        gps_coordinates = []
        feature_ids = []
        for restaurant_name in restaurant_names:
            fid, gps_coordinate = self.get_review_page_fid(restaurant_name)
            feature_ids.append(fid)
            gps_coordinates.append(gps_coordinate)

        it = 0
        for restaurant_name, feature_id, gps_coordinate in zip(
            restaurant_names, feature_ids, gps_coordinates
        ):
            it += 1
            # FOR EACH RESTAURANT (Feature Id), FIND THE LINK TO THE REVIEWS PAGE
            url = (
                "https://www.google.com/async/reviewDialog?async=feature_id:"
                + str(feature_id)
                + ",_fmt:pc"
            )

            yield Request(
                url=url,
                headers=self.HEADERS,
                callback=self.parse_reviews,
                meta={
                    "iter": 0,
                    "restaurant_name": restaurant_name,
                    "gps_coordinate": gps_coordinate,
                    "total_pages_to_load": 1,  # DUMMY VALUE, IT UPDATES AUTOMATICALLY IN THE FIRST CALLBACK
                },
            )

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

        iter = response.meta["iter"]
        total_pages_to_load = response.meta["total_pages_to_load"]
        if iter == 0:
            total_reviews_text = response.css("span.z5jxId::text").extract_first()
            if total_reviews_text:
                # Filter out non-digit characters and convert to integer
                total_reviews = int(re.sub(r"[^\d]", "", total_reviews_text))

            total_pages_to_load = total_reviews / 10  # since

            if total_pages_to_load > int(total_pages_to_load):
                total_pages_to_load += 1

            """AS OF NOW WE LIMIT THE TOTAL PAGES TO SCRAPE"""
            total_pages_to_load = 1

        restaurant_name = response.meta["restaurant_name"]
        gps_coordinate = response.meta["gps_coordinate"]

        ##########################
        # LOG YOUR CURRENT STATE SO THAT YOU CAN PICK UP FROM HERE LATER

        if iter < total_pages_to_load:
            iter += 1

            all_reviews = response.xpath('//*[@id="reviewSort"]/div/div[2]/div')

            # WRITE CSV OF 10 REVIEWS
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
                    description = soup.get_text(
                        separator="\n"
                    )  # CHANGE <br> TAGS TO "\n"

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
                review_imgs_div = review.xpath(
                    './/div[@class="EDblX GpHuwc"]/div/a/div'
                )

                # WE GET THE IMAGE URL BY EXTRACTING FROM background-image:url()
                url_pattern = re.compile(r"url\((.*?)\)")

                image_i = 0
                names_str = ""
                for review_img_div in review_imgs_div:
                    image_i += 1
                    style_str = review_img_div.xpath("@style").extract_first()

                    # FIND THE URL
                    url = url_pattern.search(style_str).group(1)
                    url = re.sub(r"=w100-h100-p-n-k-no", "", url)
                    url += "=s2000-p-k-no"  # THIS MAKES THE IMAGE 2000x2000

                    name = self.generate_unique_filename()
                    names_str += "," + name

                    """DOWNLOAD"""
                    # self.download_image(name, url)
                names_str = names_str[1:]  # DROP THE COMMA

                if image_i > 0:
                    # A SEPERATE LINE FOR EACH REVIEWER
                    yield {
                        "RESTAURANT_NAME": restaurant_name,
                        "GPS": gps_coordinate,
                        "REVIEWER": reviewer,
                        "DESCRIPTION": description,
                        "rating": review_rating,
                        "review_date": review_date,
                        "IMAGE URL": names_str,
                    }

            # FIND NEXT PAGE TOKEN
            next_page_token_div = response.xpath('//*[@id="reviewSort"]/div/div[2]')
            next_page_token = next_page_token_div.xpath(
                "@data-next-page-token"
            ).extract_first()

            next_url = (
                response.request.url.split("next_page_token:")[0]
                + f",next_page_token:{next_page_token}"
            )
            # SEND REQUEST TO LOAD THE NEXT 10 REVIEWS
            yield Request(
                url=next_url,
                headers=self.HEADERS,
                callback=self.parse_reviews,
                dont_filter=True,
                meta={
                    "iter": iter,
                    "restaurant_name": restaurant_name,
                    "gps_coordinate": gps_coordinate,
                    "total_pages_to_load": total_pages_to_load,
                },
            )
