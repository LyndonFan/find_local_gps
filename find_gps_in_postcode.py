import json
import sys
import time
import requests
import re
from datetime import datetime
import polars as pl
from pathlib import Path

from bs4 import BeautifulSoup
from typing import Any

WAIT_TIME = 0.5

def mock_headers() -> dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

def catch_and_wrap_errors(default_response: Any):
    def wrapper(func):
        def inner(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except requests.exceptions.RequestException as e:
                print(f"Error fetching data: {e}")
                return []
            except Exception as e:
                print(f"Error parsing data: {e}")
                return []
            except Exception as e:
                return default_response
         
        inner.__name__ = func.__name__
        return inner

    return wrapper

def parse_and_get_surgery_information(item) -> dict:
    surgery_info = {}

    # Extract ID (from visually hidden p element)
    id_element = item.find("p", id=lambda x: x and "item_id_" in x)
    if id_element:
        surgery_info["id"] = id_element.get_text(strip=True)

    # Extract name and NHS URL
    name_element = item.find("h2", class_="results__name")
    if name_element:
        link_element = name_element.find("a", class_="nhsapp-open-in-webview")
        if link_element:
            # Get name (excluding visually hidden text)
            name_text = ""
            for text in link_element.stripped_strings:
                if not text.strip().startswith("navigates to more detail for"):
                    name_text = text
                    break
            surgery_info["name"] = name_text
            surgery_info["nhs_url"] = link_element.get("href", "")

    # Extract address (excluding visually hidden text)
    address_element = item.find("p", id=lambda x: x and "address_" in x)
    if address_element:
        address_text = ""
        for text in address_element.stripped_strings:
            if not text.strip().startswith("Address for this organisation is"):
                address_text = text
                break
        surgery_info["address"] = address_text

    # Extract phone number (excluding visually hidden text)
    phone_element = item.find("p", id=lambda x: x and "phone_" in x)
    if phone_element:
        phone_text = ""
        for text in phone_element.stripped_strings:
            if not text.strip().startswith("Phone number for this organisation is"):
                phone_text = text
                break
        surgery_info["phone_number"] = phone_text

    # Extract distance (excluding visually hidden text)
    distance_element = item.find("p", id=lambda x: x and "distance_" in x)
    if distance_element:
        distance_text = ""
        for text in distance_element.stripped_strings:
            if not text.strip().startswith("This organisation is"):
                distance_text = text
                break
        # Extract just the number from "0.4 miles away"
        if "miles away" in distance_text:
            miles_part = distance_text.replace("miles away", "").strip()
            surgery_info["distance_miles"] = miles_part

    return surgery_info

@catch_and_wrap_errors([])
def find_gp_surgeries(postcode: str) -> list[dict]:
    """
    Find GP surgery URLs for a given UK postcode from NHS website.

    Args:
        postcode (str): UK postcode (e.g., 'XM15HQ')

    Returns:
        List[str]: List of GP surgery URLs
    """
    # Construct the URL
    postcode = postcode.replace(" ", "")
    url = f"https://www.nhs.uk/service-search/find-a-gp/results/{postcode}"

    # Set up headers to mimic a real browser
    headers = mock_headers()

    # Make the request
    print(f"Fetching GP surgeries for postcode: {postcode}")
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()

    # Parse the HTML
    soup = BeautifulSoup(response.content, "html.parser")

    # Find result elements
    catchments_tuples = [
        ("catchment_gps_list", True),
        ("non_catchment_gps_list", False),
    ]
    gp_surgeries = []
    for ol_id, is_in_catchment in catchments_tuples:
        catchment_gps_list = soup.find("ol", id=ol_id)
        search_results = catchment_gps_list.find_all("li", class_="results__item")

        for item in search_results:
            surgery_info = parse_and_get_surgery_information(item)
            if surgery_info.get("name") and surgery_info.get("nhs_url"):
                gp_surgeries.append({**surgery_info, "is_in_catchment": is_in_catchment})

    print(f"Found {len(gp_surgeries)} GP surgery links")
    return gp_surgeries

@catch_and_wrap_errors({})
def get_surgery_details(surgery_url: str) -> dict:
    """
    Extract contact details and opening times from a GP surgery's NHS page.

    Args:
        surgery_url (str): URL of the GP surgery (e.g., 'https://www.nhs.uk/services/gp-surgery/ruston-street-clinic/F84030')

    Returns:
        dict: Dictionary containing surgery details including name, address, website, and opening times
    """
    # Construct the contact details URL
    contact_url = f"{surgery_url}/contact-details-and-opening-times"

    # Set up headers to mimic a real browser
    headers = mock_headers()

    print(f"Fetching details from: {contact_url}")
    response = requests.get(contact_url, headers=headers, timeout=10)
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")

    # Extract surgery name
    name = ""
    name_element = soup.find("h2", class_="nhsuk-caption-xl")
    if name_element:
        name = name_element.get_text(strip=True)

    # Extract address
    address = ""
    address_element = soup.find("address", id="address_panel_address")
    if address_element:
        # Get text and clean up line breaks
        address_lines = []
        for line in address_element.stripped_strings:
            address_lines.append(line)
        address = ", ".join(address_lines)

    # Extract website
    website = ""
    website_element = soup.find("a", id="contact_info_panel_website_link")
    if website_element:
        website = website_element.get("href", "")

    # Extract opening times
    opening_times = {}
    opening_table = soup.find("table", id="table_0")
    if opening_table:
        rows = opening_table.find("tbody").find_all("tr")
        for row in rows:
            day_cell = row.find("th")
            time_cell = row.find("td")

            if day_cell and time_cell:
                day = day_cell.get_text(strip=True).lower()
                # Get all text from time cell and clean up
                time_text = time_cell.get_text(separator=" ", strip=True)
                # Clean up extra spaces and normalize
                time_text = " ".join(time_text.split())
                opening_times[day] = time_text

    surgery_details = {
        "name": name,
        "address": address,
        "website": website,
        "opening_times": opening_times,
    }

    print(f"Successfully extracted details for: {name}")
    return surgery_details

def process_review_html(html_element):
    """
    Process HTML snippet to extract review information.

    Args:
        html_snippet (str): HTML string containing review data

    Returns:
        dict: Dictionary containing extracted review data with keys:
              - rating: int (1-5)
              - review_date: str (dd/mm/yyyy format)
              - review_title: str
              - review_content: str
              - review_response: str or None
    """
    review_data = {}

    # Extract rating
    rating_text = html_element.find("p", id=re.compile(r"star-rating-\d+"))
    if rating_text:
        rating_match = re.search(r"Rated (\d+) star", rating_text.get_text())
        review_data["rating"] = int(rating_match.group(1)) if rating_match else None
    else:
        review_data["rating"] = None

    # Extract review title
    title_element = html_element.find("h3", class_="nhsuk-body-l")
    if title_element:
        # Remove the visually hidden text and get clean title
        title_text = title_element.get_text().strip()
        title_text = re.sub(r"Review titled\s*", "", title_text).strip()
        review_data["review_title"] = title_text
    else:
        review_data["review_title"] = None

    # Extract review date
    date_element = html_element.find("p", string=re.compile(r"by .* - Posted on"))
    if date_element:
        date_match = re.search(
            r"Posted on (\d{1,2} \w+ \d{4})", date_element.get_text()
        )
        if date_match:
            date_str = date_match.group(1)
            try:
                # Parse the date and convert to dd/mm/yyyy format
                parsed_date = datetime.strptime(date_str, "%d %B %Y")
                review_data["review_date"] = parsed_date.strftime("%d/%m/%Y")
            except ValueError:
                review_data["review_date"] = None
        else:
            review_data["review_date"] = None
    else:
        review_data["review_date"] = None

    # Extract review content
    comment_element = html_element.find("p", class_="comment-text")
    if comment_element:
        review_data["review_content"] = comment_element.get_text().strip()
    else:
        review_data["review_content"] = None

    # Extract review response
    response_div = html_element.find("div", {"aria-label": "Organisation review response"})
    if response_div:
        response_text = response_div.get_text().strip()
        # Check if it's a "has not yet replied" message
        if re.search(r"has not yet replied\.$", response_text, re.IGNORECASE):
            review_data["review_response"] = None
        else:
            review_data["review_response"] = response_text
    else:
        review_data["review_response"] = None

    return review_data

@catch_and_wrap_errors([])
def get_reviews(nhs_url: str) -> list[dict]:
    url = f"{nhs_url}/ratings-and-reviews"
    headers = mock_headers()
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")

    review_list = soup.find("ol", class_="nhsuk-list")
    review_elements = review_list.find_all("li")
    reviews = []
    for review_element in review_elements:
        review_data = process_review_html(review_element)
        reviews.append(review_data)

    return reviews

def main(postcode):
    """
    Example usage of the GP surgery finder.
    """
    # Example postcode
    postcode = postcode.replace(" ", "")

    gp_surgeries_location = f"raw/{postcode}_gp_surgeries.csv"
    if Path(gp_surgeries_location).exists():
        gp_surgeries = pl.read_csv(gp_surgeries_location).to_dicts()
    else:
        # Find GP surgeries
        gp_surgeries = find_gp_surgeries(postcode)

        # Display results
        if gp_surgeries:
            print(f"\nGP Surgeries found for {postcode}:")
            for i, surgery in enumerate(gp_surgeries, 1):
                print(f"{i}. {surgery['name']} {surgery['nhs_url']}")
        else:
            print(f"No GP surgeries found for {postcode}")
            return []
        
        pl.DataFrame(gp_surgeries).write_csv(gp_surgeries_location)

    all_surgery_details = []
    all_reviews = []
    for surgery in gp_surgeries:
        nhs_url = surgery["nhs_url"]
        time.sleep(WAIT_TIME)
        details = get_surgery_details(nhs_url)
        all_surgery_details.append({**details, "id": surgery["id"]})
        time.sleep(WAIT_TIME)
        reviews = get_reviews(nhs_url)
        for i, r in enumerate(reviews):
            reviews[i] = {**r, "id": surgery["id"]}
        all_reviews.extend(reviews)
    
    pl.DataFrame(all_surgery_details).write_json(f"raw/{postcode}_surgery_details.json")
    pl.DataFrame(all_reviews).write_json(f"raw/{postcode}_surgery_reviews.json")

if __name__ == "__main__":
    postcode = sys.argv[1]
    result = main(postcode)
