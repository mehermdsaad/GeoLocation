# GeoLocation for Indoor Images 

In this project, we aimed to improve the image-to-location capabilities of machine learning models with regard to geolocating indoor images. Current existing models perform well in case outdoor images but have subpar performance when it comes to indoor images. We focused on the results of the GeoCLIP model in particular, due to this model having SOTA results all the while being open-source. The original GeoCLIP results can be found [here](https://arxiv.org/abs/2103.00020).

# Idea

Due to the training data of the GeoCLIP model comprising only outdoor images, our first approach will be to retrain the model on mostly indoor images using a dataset of a number of images taken from Middle Eastern and European countries. We are yet to do so, and we will update our results once we have them. But before training a new model, we would like to test it on the pre-trained GeoCLIP model to see how well it performs in different image classes.

# Directories

<h2>review_scraper</h2> 

Employs a Python script using selenium and scrapy to at first scrape city names and details from the site [Restaurant Guru](https://restaurantguru.com/) and then uses this list of cities to get the restaurant_details (feature_id, gps_coordinate, restaurant_name, city_name, country_name) of a certain number of restaurants from each city. Then using scrapy, the reviews can be scraped with their images, review_description, reviewer_id, rating, etc. 
<br><br>
The total number of restaurants per country is set before running the script. The number of restaurants per city is adjusted based on the number of restaurant entries present on the restaurant guru website. This is done to ensure an even distribution of restaurants all over the country. The restaurant_details are collected in the following way: The script gets the restaurant_name, city_name, and country_name and searches on Google via a combination of search texts (for example, XYZ Restaurant Paris France Reviews). Once it locates the reviews box in the search results it gets the feature_id, gps_coordinates from there.
<br><br>
<b>To run the script</b>, navigate to <code>./spiders/google.py</code> file where all key methods are located. 
<br><br>><b>To get the restaurant_details</b>, uncomment the lines 
<code>spider.scrape_city_names_from_countries(COUNTRIES)</code> and <code>spider.scrape_restaurant_names_from_countries(COUNTRIES)</code> and run it using <code>python google.py</code> command.
<br><b>NOTE:</b> Might run into captchas from the restaurant guru site, till now manually resolving one of them solves the issue temporarily.
<br><br>><b>To scrape images and review entries</b>, run <code>scrapy crawl google</code> after commenting out the previously uncommented lines.
<br><br><b>NOTE:</b> You might need to change some constants on top of the <code>./spiders/google.py</code> file. For example <code>NUM_RESTAURANTS_PER_COUNTRY = 400</code> limits the number of restaurants per country to 400, while <code>NUM_IMGS_TO_DOWNLOAD = 25</code> means it downloads 25 images per restaurant.
<br><br><b>Saved data is stored in the following: </b>(filenames might change based on use-case) 
- <code>./spiders/data/restaurant_details.json</code> contains the country list, city names, and list of restaurant details 
- <code>./spiders/logs/scraping_log.json</code> contains the log file that is used to start the script from where it left off.
- <code>./spiders/reviews.csv</code> contains the csv file with the reviews data.
- <code>./spiders/images</code> directory with all the downloaded images.


<h2>eval_geoclip</h2> 
Contains script to evaluate images based on pre-trained geoclip model. <code>./eval_geoclip/eval_geoclip.py</code> takes an input csv file, locates the image using image_path value, and then processes it using the pretrained geoclip model. The predicted latitude and longitude are then appended to an output file, along with the spherical distance from the original latitude and longitude of the image. Our aim is to later label the image categories and measure the performance of GeoCLIP on different image classes.  
<br><br>
<b>NOTE:</b> The script can be interrupted and once run again it will pick up from where it left off. The User might need to fix the image_path for different cases.

<h2>image_clustering</h2>
Contains a notebook that runs a basic clustering algorithm to try to distinguish between food vs non-food images. Might be helpful in the future for image labeling. 
