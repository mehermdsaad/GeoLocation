"""
Dumping useful code for later use
"""

"""################################################################################################################################################"""
"""### <THESE HAVE BEEN COPIED FROM google.py FILE> ###"""
"""################################################################################################################################################"""

"""Method that takes a random set of users and samples restaurants(or places in general) from them"""
def scrape_restaurant_details_from_random_users(self, num_users=50,random_seed=None):
    """Method to get restaurant details by checking randomly chosen {num_users} number of users (based on a p-distribution which gives priority to users with the most reviews).
    Maintains users_log.json to not repeat checking the same user for the second time. Surprisingly effective at discovering new restaurant names"""

    if random_seed is not None:
        np.random.seed(random_seed)

    # Read the CSV file
    df = pd.read_csv(self.scrape_data_file)
    columns = ["Reviewer","Reviewer ID","Num Reviews"]
    df= df[columns]
    
    # Remove duplicate rows
    df.drop_duplicates(inplace=True)

    # Remove previously seen users
    self.load_progress(self.users_log_file)
    df = df[~df['Reviewer ID'].isin(self.users_log.keys())]

    
    # Ensure num_reviews is numeric
    df['Num Reviews'] = pd.to_numeric(df['Num Reviews'], errors='coerce')
    df.dropna(subset=['Num Reviews'], inplace=True)
    
    # Calculate weights based on num_reviews
    weights = df['Num Reviews'] / df['Num Reviews'].sum()
    
    # Perform weighted random sampling without replacement
    sampled_indices = np.random.choice(
        df.index, 
        size=min(num_users, len(df)), 
        replace=False, 
        p=weights
    )
    
    # Get the sampled users
    sampled_users = df.loc[sampled_indices]
    sampled_users_list = sampled_users.to_dict('records')
    
    prev_restaurant_count = len(self.restaurant_details.keys())
    # Process each selected user
    for i, user in enumerate(sampled_users_list):
        restaurant_count_before_user = len(self.restaurant_details.keys())

        username = user["Reviewer"]
        user_id = user["Reviewer ID"]
        print(f"\n{i+1:<3}: Looking at {username}, {user_id}:")

        self.scrape_restaurant_details_per_user(user_id, username=username)

        self.save_progress(self.restaurant_details_file, self.restaurant_details)

        print(
            f"\nUser {i+1}: {user['Reviewer'][:20]:<20}\tUnique Restaurants from user: {(len(self.restaurant_details.keys())-restaurant_count_before_user):>4}. Total Restaurants: {len(self.restaurant_details.keys()):>6}"
        )

        self.users_log[user_id]=username
        self.save_progress(self.users_log_file,self.users_log)

    print(
        "\nRestaurant names collection completed. New restaurants found: ",
        len(self.restaurant_details.keys()) - prev_restaurant_count,
        ". Total Restaurants: ",
        len(self.restaurant_details.keys()),
    )

"""Method that takes one user and gets restaurants(or places in general) reviewed by him/her"""
def scrape_restaurant_details_per_user(self, user_id, username="USER", timeout=300):
    """Gets the restaurant detail for each user. Currently only gets the ones based on Abu Dhabi"""

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

"""This version checks if the place is restaurant or not"""
def get_review_page_fid_gps_from_name(self, name, address=""):
    """
    Searches for the restaurant name and returns the feature_id and gps_coordinates of the reviews page. 
    Additionally check if the place is a restaurant or not by keyword checks


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
        "coffee",
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


"""################################################################################################################################################"""
"""### </THESE HAVE BEEN COPIED FROM google.py FILE> ###"""
"""################################################################################################################################################"""
