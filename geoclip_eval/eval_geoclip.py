import math
import time

import csv
import os

import torch

# Import GeoCLIP class from GeoCLIP.py (assuming it's in the same folder)
from geoclip.GeoCLIP import GeoCLIP

start_time = time.time()

# Initialize the model
model = GeoCLIP(from_pretrained=True).to("cuda")


print(torch.cuda.is_available())
print(torch.cuda.device_count())


end_time = time.time()
load_time = end_time - start_time

print(f"Model loading took {load_time:.2f} seconds\n")


def geoclipmodel(image_path):

    top_k = 1  # Number of top predictions to return
    top_pred_gps, top_pred_prob = model.predict(image_path, top_k)

    return top_pred_gps.tolist()[0]


def calculate_spherical_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points
    on the Earth (specified in decimal degrees)
    """
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))

    # Radius of Earth in kilometers. Use 3956 for miles
    r = 6371

    # Calculate the result
    return c * r


def append_row_to_csv(file, row):
    """Helper method to append a row into the output csv."""
    file_exists = os.path.isfile(file)
    with open(file, "a", newline="", encoding="utf-8") as csvfile:
        fieldnames = row.keys()
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

def process_csv(input_file, output_file, process_function):
    """Process rows from input CSV, apply function, and append to output CSV."""
    # Get the last processed row
    last_processed_row = 0
    if os.path.exists(output_file):
        with open(output_file, 'r', newline='', encoding='utf-8') as f:
            last_processed_row = sum(1 for _ in f) - 1  # Subtract 1 to account for header

    with open(input_file, 'r', newline='', encoding='utf-8') as infile:
        reader = csv.DictReader(infile)
        
        for i, row in enumerate(reader):
            if i < last_processed_row:
                continue  # Skip already processed rows
            
            # Process the row and get the result
            result = process_function(row)
            
            # Append the result to the output CSV
            append_row_to_csv(output_file, result)

            print(f"Processed row {i + 1}")

# Example usage:
def process_function(row):
    global total_time

    start_time = time.time()

    try:
        image_name = row['image_name']
        image_path = "../review_scraper/spiders/images/"+image_name+".png"

        coordinates = geoclipmodel(image_path)
        lat, lon = coordinates[0], coordinates[1]
        real_lat = float(row['lat'])
        real_lon = float(row['lon'])

        dist = calculate_spherical_distance(
            real_lat, real_lon, lat, lon
        )
        
        row['pred_lat'] = lat
        row['pred_lon'] = lon
        row['spherical_distance'] = dist



    except Exception as e:
        print(f"Exception in processing: {e}")
        dist = -1
        row['pred_lat'] = 0
        row['pred_lon'] = 0
        row['spherical_distance'] = -1


    end_time = time.time()
    iteration_time = end_time - start_time
    total_time += iteration_time

    print(f"Entry: duration {iteration_time:.2f}s - Total time elapsed: {total_time:.2f}s - Error: {dist:.4f}km")

    return row

# Use the function
input_file = 'reviews_48k.csv'
output_file = 'reviews_48k_processed.csv'

total_time = 0
process_csv(input_file, output_file, process_function)


