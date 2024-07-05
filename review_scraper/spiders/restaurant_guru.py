import requests
from bs4 import BeautifulSoup
import time 


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

def scrape(batchsize=10):
    base_url = "https://restaurantguru.com/restaurant-Abu-Dhabi-t1"
    header = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1'}

    response = requests.get(base_url, headers=header)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find all restaurant links, skip the first one (advertisement)
    restaurant_links = soup.find_all(attrs={"class":["notranslate title_url"]})[:batchsize]
    restaurant_guru_list = {}
    for link in restaurant_links:
        restaurant_url = link['href']
        name, address = get_restaurant_info(restaurant_url, header)
        if name and address:
            print(f"Restaurant: {name}")
            print(f"Address: {address}")
            print("-" * 50)
            name = name.strip()
            address = address.strip()
            restaurant_guru_list[name] = address
        else: 
             continue
        
        time.sleep(2)
    return restaurant_guru_list

############################################################################################################
#NOTE: Update so that when the website turns into a captcha, break the loop without exiting the program 
#####  and then save progress(restaurant name and number in list) to a json file and then continue from there
#####  when the program is run again. Save restaurant name and number separate file and then in the json file 
#####  should be progress up to that point, i.e the dictionary of the restaurant name and address. 
############################################################################################################
# list = scrape(5)
# print(list)
scrape(5)

