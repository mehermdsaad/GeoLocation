import csv
import json
import os
import re
import shutil
import time

from urllib.parse import quote_plus

import numpy as np
from PIL import Image

import requests
import scrapy
from scrapy.http.request import Request

from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

# LOGS AND OUTPUT FILES
scraping_progress_file = "./logs/scraping_log_eu.json" # REPLACE THE _eu WITH _ar TO SAVE TO THE ARAB COUNTRIES' LOG
restaurant_details_file = "./data/restaurant_details_eu.json"
scrape_data_file = "./reviews_eu.csv"

# CONSTRAINTS
# COUNTRIES = ["Saudi Arabia","United Arab Emirates","Lebanon","Egypt","Qatar"] # THE ARAB COUNTRIES
COUNTRIES = ["Germany","United Kingdom","Italy","Spain","France"] # THE EU COUNTRIES

NUM_RESTAURANTS_PER_COUNTRY = 400 # GET 400 RESTAURANTS PER COUNTRY
NUM_REVIEWS_THRESHHOLD = 350 # RESTAURANTS ARE PICKED ONLY IF THEIR TOTAL NUMBER OF REVIEWS EXCEED 350
NUM_IMGS_TO_DOWNLOAD = 25 # PER RESTAURANT 25 IMAGES ARE DOWNLOADED
MAX_NUM_IMGS_PER_USER = 5 # MAX NUMBER OF IMAGES SCRAPED FROM A SINGLE USER PER RESTAURANT

CITY_RESTAURANT_CNT_THRESHHOLD = 200 # DONT INCLUDE THE CITIES WHICH HAVE LESS THAN 200 RESTUARANTS LISTED ON THE WEBSITE

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

        self.scrape_data_file = scrape_data_file

    def scrape_restaurant_names_from_countries(self,countries):
        """
        Method to collect {NUM_RESTAURANTS_PER_COUNTRY} number of restaurants per country. We already have cities and number of restaurants that are listed in those cities. We use it as weights to get the proportionate number of restaurants per city. This tries to ensure an even distribution across the country.

        Further criterias include the fact that the restaurant must have atleast 350 reviews.

        Saves the restaurant names and details (feature_id, county_name, city_name, coordinates) in the self.restaurant_details_file in a json format. Used in the future for scraping from these restaurants' reviews
        """

        self.restaurant_details = self.load_progress(self.restaurant_details_file)

        # IF NO RESTAURANT RECORDS ARE ADDED, CREATE AN EMPTY CONTAINER
        if not self.restaurant_details.get('restaurants',None):
            self.restaurant_details['restaurants'] = {}

        for country_name in countries:

            print(country_name,"\n")
            cities_dict = self.restaurant_details['countries'][country_name]['cities']

            country_restaurant_count = self.restaurant_details['countries'][country_name]['country_restaurant_count']
            sampled_restaurant_count_country = self.restaurant_details['countries'][country_name].get("sampled_restaurant_count_country",0)

            # THIS IS TO BE USED WHEN YOU ARE DONE SCRAPING AND STILL CANNOT GET 400 RESTAURANTS THROUGHOUT THE COUNTRY THAT MEET YOUR CRITERIA: AS IN QATAR, LEBANON
            remaining_restaurant_count_country = NUM_RESTAURANTS_PER_COUNTRY - sampled_restaurant_count_country
            # OTHERWISE THIS IS THE DEFAULT CODE
            remaining_restaurant_count_country = NUM_RESTAURANTS_PER_COUNTRY

            #IF WE ALREADY HAVE ENOUGH RESTAURANTS, MOVE ON TO THE NEXT COUNTRY
            if sampled_restaurant_count_country >= NUM_RESTAURANTS_PER_COUNTRY:
                continue

            
            for city_name, city_detail in cities_dict.items():
                url = city_detail['url']+"#restaurant-list"

                chrome_options = webdriver.ChromeOptions()
                chrome_options.add_argument("--headless")  # Run in headless mode (optional)

                driver = webdriver.Chrome(
                    service=Service(ChromeDriverManager().install()), options=chrome_options
                )

                load_last_item_count = city_detail.get("last_item_count",0) # START WHERE WE LEFT OFF IN THE CITY PAGE IN RESTAURANT GURU

                # city_detail["sampled_restaurant_count_city"] = 0 # IF WE WANT TO START OVER
                sampled_restaurant_count_city = city_detail.get("sampled_restaurant_count_city",0)
                city_restaurant_count = city_detail["city_restaurant_count"]

                remaining_restaurant_count_city = int(np.ceil(remaining_restaurant_count_country * city_restaurant_count / country_restaurant_count)) - sampled_restaurant_count_city
                # CALCULATE HOW MANY RESTAURANTS NEED TO BE SCRAPED PER CITY BASED ON HOW MANY RESTAURANTS IT HAS COMPARED TO THE COUNTRY_TOTAL

                print(f"City: {city_name} Target Number of Restaurants:{int(np.ceil(remaining_restaurant_count_country * city_restaurant_count / country_restaurant_count))}. Remaining Restaurants: {remaining_restaurant_count_city}")
                
                # MORE CHECKS FOR COMPLETION OF COLLECTION
                if self.restaurant_details['countries'][country_name].get("sampled_restaurant_count_country",0) >= NUM_RESTAURANTS_PER_COUNTRY:
                    continue
                elif remaining_restaurant_count_city <=0:
                    continue

                try:
                    # FETCH THE CITY PAGE
                    driver.get(url)

                    last_item_count = 0
                    city_restaurant_cnt = 0

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

                            # GET ALL ITEMS
                            items = driver.find_elements(
                                By.CSS_SELECTOR, "div.wrapper_info"
                            )
                            # PROCESS ONLY THE NEW ONES
                            if len(items)<load_last_item_count:
                                last_item_count = len(items)
                                print("Previously checked items, please wait ",last_item_count)
                                continue
                            
                            for item in items[last_item_count:]:
                                try:
                                    if city_restaurant_cnt>=remaining_restaurant_count_city:
                                        break

                                    name_element = item.find_element(
                                        By.CSS_SELECTOR, "a.notranslate.title_url"
                                    )
                                    restaurant_name = name_element.text
                                    restaurant_name = restaurant_name.replace(",","-")
                                    restaurant_url = name_element.get_attribute('href')
                                    
                                    try:
                                        closed_or_not = item.find_element(
                                            By.CSS_SELECTOR, "div.closed_info_block"
                                        )
                                        if closed_or_not:
                                            closed_or_not = closed_or_not.text
                                            if "permanently closed" in closed_or_not.lower():
                                                continue
                                    except Exception as e:
                                        pass
                                    

                                    
                                        
                                    fid,gps_coordinate,city_name_google,search_url = self.get_review_page_fid_gps_from_name(restaurant_name,city_name=city_name,country_name=country_name)

                                    if not fid or not gps_coordinate or not city_name:
                                        continue
                                    

                                    if not self.restaurant_details['restaurants'].get(fid,None):
                                        self.restaurant_details['restaurants'][fid] = {"restaurant_name":restaurant_name,"city_name":city_name,"country_name":country_name,"url":search_url,"gps_coordinates":gps_coordinate}
                                        city_detail['sampled_restaurant_count_city'] = city_detail.get('sampled_restaurant_count_city',0) + 1
                                        self.restaurant_details['countries'][country_name]["sampled_restaurant_count_country"] = self.restaurant_details['countries'][country_name].get("sampled_restaurant_count_country",0) + 1
                                        if self.restaurant_details['countries'][country_name]["sampled_restaurant_count_country"] >= NUM_RESTAURANTS_PER_COUNTRY:
                                            break

                                        print(f"[FOUND] CNT:{city_detail['sampled_restaurant_count_city']}/{remaining_restaurant_count_city+sampled_restaurant_count_city} - {country_name} - {self.restaurant_details['countries'][country_name]['sampled_restaurant_count_country']}/400 --- {city_name} --- {restaurant_name}")
                                    else:
                                        continue

                                    city_restaurant_cnt+=1
                                    if city_restaurant_cnt>=remaining_restaurant_count_city:
                                        break
                                    
                                except Exception as e:
                                    print("EXCEPTION OCCURED: ",e)

                            new_item_count = len(items)

                            if city_restaurant_cnt>=remaining_restaurant_count_city:
                                new_item_count = 0
                            
                            city_detail["last_item_count"] = new_item_count
                            
                            self.save_progress(self.restaurant_details_file,self.restaurant_details)
                            
                            print(f"Processed {new_item_count - last_item_count} new items.\tCity: {city_name}, CNT: {city_restaurant_cnt}/{remaining_restaurant_count_city}")
                            last_item_count = new_item_count

                            if city_restaurant_cnt >= remaining_restaurant_count_city:
                                break

                            if self.restaurant_details['countries'][country_name]["sampled_restaurant_count_country"] >= NUM_RESTAURANTS_PER_COUNTRY:
                                break

                            # CHECK IF WE'VE REACHED THE BOTTOM
                            if driver.execute_script("return document.documentElement.scrollHeight - document.documentElement.scrollTop <= document.documentElement.clientHeight + 1;"):
                                break
                            
                        except TimeoutException:
                            print("No new items loaded, probably reached the end: URL" , url)
                            break

                    print(
                        f"Finished processing all items. Total extracted: {city_restaurant_cnt}/{remaining_restaurant_count_city}"
                    )


                finally:
                    driver.quit()

    def scrape_city_names_from_countries(self,countries):
        """Searches in restaurantguru.com for city names. Only gets the city if it has more than {CITY_RESTAURANT_CNT_THRESHHOLD} number of restaurants (200) listed on the website.
        """

        self.restaurant_details = self.load_progress(self.restaurant_details_file)

        self.restaurant_details['countries'] = {}

        for country_name in countries:
            country_dict={}

            country_search = country_name.replace(" ", "-")

            url = f"https://t.restaurantguru.com/cities-{country_search}-c/"

            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_argument("--headless")  # Run in headless mode (optional)

            driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()), options=chrome_options
            )


            try:
                driver.get(url)

                city_elements = driver.find_elements(By.CSS_SELECTOR, "ul.cities_link li")
                
                cities_dict = {}

                country_restaurant_count = 0
                for city_element in city_elements:
                    try:
                        city_link = city_element.find_element(By.CSS_SELECTOR,"a").get_attribute('href')
                        city_name = city_element.find_element(By.CSS_SELECTOR,"a").text.split("/")[0].strip()
                        city_restaurant_cnt = int(city_element.find_element(By.CSS_SELECTOR,"span.grey").text.split()[-1])

                        if city_restaurant_cnt<CITY_RESTAURANT_CNT_THRESHHOLD:
                            continue
                        
                        cities_dict[city_name]={'url':city_link,'city_restaurant_count':city_restaurant_cnt}
                        country_restaurant_count += city_restaurant_cnt

                        print(f"FOUND {len(cities_dict.keys())}: ",cities_dict[city_name])
                    except Exception as e:
                        print(f"Exception found: {e}")

                country_dict['cities'] = cities_dict
                country_dict['cities_count'] = len(cities_dict.keys())
                country_dict['country_restaurant_count'] = country_restaurant_count

            finally:
                driver.quit()
            
            self.restaurant_details['countries'][country_name] = country_dict

            
        self.save_progress(self.restaurant_details_file,self.restaurant_details)

    def get_review_page_fid_gps_from_name(self, restaurant_name, city_name="", country_name=""):
        """
        Searches for the restaurant name along with a combination of city_name, country_name and if the google reviews box exists, returns the feature_id and gps_coordinates of the reviews page.

        Args
        ------
        city_name is optional, when not present, it will pick up the city name from the address in the google reviews box.
        country_name: also optional, but encouraged to pass here.

        Returns
        ------
        fid, gps_coordinate, city_name, search_url : feature_id of the reviews page, gps_coordinate: a str of format "lat,lon", city_name: returns the name of the city to cross check, search_url: the search url that was successful in locating the google reviews box
        """

        if city_name:
            search_texts = [f"{restaurant_name} {city_name} {country_name}",f"{restaurant_name} restaurant {city_name} {country_name}",f"{restaurant_name} {country_name}",f"{restaurant_name} restaurant {country_name}",f"{restaurant_name} {city_name}",f"{restaurant_name} {city_name} restaurant"]
        else:
            search_texts = [f"{restaurant_name} {city_name} {country_name}",f"{restaurant_name} restaurant {city_name} {country_name}",f"{restaurant_name} {country_name}",f"{restaurant_name} restaurant {country_name}"]

        for search_text in search_texts:
            search_text = quote_plus(search_text)
            search_url = f"https://www.google.com/search?q={search_text}+reviews"

            response = requests.get(search_url, headers=self.HEADERS)

            # SOMETIMES THE RATE OF REQUESTS EXCEED THE LIMIT. WAITING IS BETTER IN THAT SCENARIO
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 200))
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
        """Helper method to read a dict from a json file. Currently used for ./data/restaurant_details.json and ./logs/scraping_logs.json."""
        try:
            if os.path.getsize(save_file) == 0:
                return {}
            with open(save_file, "r", encoding="utf-8") as file:
                return json.load(file)
        except FileNotFoundError:
            return {}

    def save_progress(self, save_file, save_data):
        """Helper method to save logs for saving progress. Dumps a dictionary holding logging information to a json file. Currently used for ./data/restaurant_details.json and ./logs/scraping_logs.json."""
        with open(save_file, "w", encoding="utf-8") as file:
            json.dump(save_data, file, ensure_ascii=False)

    def save_to_csv(self, file, row):
        """Helper method to append a row into the output csv. By default it is "./reviews.csv".
        Args:
        --------
        save_file: file path, str
        row: dict containing header, value
        """
        file_exists = os.path.isfile(file)
        with open(file, "a", newline="", encoding="utf-8") as csvfile:
            fieldnames = row.keys()
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

    def download_image(self, name, url):
        """Helper method to download images from a url
        """
        response = requests.get(url, stream=True)

        if not os.path.exists("./images"):
            os.makedirs("./images")
        with open(f"./images/{name}.png", "wb") as out_file:
            shutil.copyfileobj(response.raw, out_file)

    def start_requests(self):
        """Default method called by scrapy. Use 'scrapy crawl google' command to start scraping. Loads the restaurant details form restaurant_details.json file and starts scraping for 
        reviews with images. Scraping is currently subject to constraints. At most NUM_IMAGES_PER_USER number of images (by default 3) are gathered and then it moves on to the next user. 
        Gathers NUM_IMGS_TO_DOWNLOAD number of images for each restaurant (by default 30)"""
    

        for fid in self.restaurant_details['restaurants']:
            restaurant_detail = self.restaurant_details['restaurants'][fid]

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
        """Parses the response object from a previous request, loads first 10 reviews, saves the data for the ones that have images with them in a csv. Finally it detects the 
        next_page_token and then recursively calls itself for the next 10 entries. Currently it keeps going until it gathers all NUM_IMGS_TO_DOWNLOAD number of images per restaurant.

        Args
        --------
        response - the Response object from a Request

        Calls
        --------
        save_to_csv method for each image

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
            reviewer = reviewer.replace(",","")

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
                    "reviewer": reviewer,
                    "reviewer_id": reviewer_id,
                    "num_reviews": num_reviews,
                    "description": description,
                    "review_rating": review_rating,
                    "review_date": review_date,
                    "image_name": image_name,
                    "lat": lat,
                    "lon": lon,
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



spider = GoogleSpider()

'''Method to get city names from restaurantguru.com from country name'''
# spider.scrape_city_names_from_countries(COUNTRIES) # WARNING: THIS MIGHT TRIGGER CPATCHAS

'''Method to get restaurant names from the city names we collected previously'''
# spider.scrape_restaurant_names_from_countries(COUNTRIES)

'''Scrapy calls start_requests on it's own when "scrapy crawl google" command is passed'''
'''But if you only want to get the restaurant names or city names, use "python google.py" and it should be enough'''