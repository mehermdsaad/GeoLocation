# GeoLocation for Indoor Images 

In this project, we aimed to improve the image-to-location capabilities of large language models in regard to datasets consisting of indoor images. Other existing models perform 
well with regard to outdoor images but have subpar performance when it comes to indoor images. We focused on the results of the GEOCLIP model in particular. The exact results can 
be found [here](https://arxiv.org/abs/2103.00020).

# Approach

Due to the training data of the GEOCLIP model comprising only outdoor images, our first approach was to retrain the model on mostly indoor images using a dataset of "number" images
taken from Middle Eastern and European countries. 


# Scraping Script(For future reference) 

Employs a Python script using the Selenium library to scrape only restaurant names from the site [Restaurant Guru](https://restaurantguru.com/) and then uses this list of restaurant
names to iteratively search each one on Google Maps. Libraries like BeautifulSoup and Requests were employed to scrape both images and text from reviews left on said restaurant. 
The functionalities mentioned above are included in the google.py file, along with other Python files for helper functions/logging functions. 
