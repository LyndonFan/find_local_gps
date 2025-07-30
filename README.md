# Find Local GPs

Find and view details about GPs in your area in a file.

## Quickstart

Set up the virtual environment with uv
```bash
uv venv .venv
source .venv/bin/activate
# or appropriate command to activate the venv
uv pip install -r pyproject.toml
```
Or if you don't have uv,
```bash
python -m venv .venv
source .venv/bin/activate
# or appropriate command to activate the venv
pip install -r requirements.txt
```

Once the environment is set up, start by getting the data from NHS
```bash
mkdir raw
python find_gps_in_postcode.py POSTCODENOSPACES
```
Where the raw data is in the "raw" folder. Then process and data
```bash
mkdir processed
python compare_gps POSTCODENOSPACES
```
The final results will then be in "processed/${POSTCODENOSPACES}_surgery_summaries.csv"

The result intentionally does not include any ranking mechanism -- make your own judgement 🙃

## Output Format

The resulting CSV file has the following columns:

- id: NHS id for the GP
- name: Name of the GP
- nhs_url: URL of the GP's page on the NHS website
- address
- phone_number
- distance_miles: Distance from the specified postcode to the GP (in miles)
- is_in_catchment: Whether the GP is within the catchment area of the specified postcode
- website: The GP's own website
- opening_times_monday to opening_times_sunday: Opening times of the GP for each day of the week, or empty/null if it's not open.
- num_reviews: Number of reviews for the GP
- avg_rating, min_rating, max_rating: Average, minimum and maximum ratings of the GP on the NHS website. If there aren't any reviews on the website, it will be 0 here.

## Disclaimer

All data is found on public pages on [NHS](https://www.nhs.uk/service-search/).

I did use AI (Claude) to help write some code. I've reviewed it and tested it to check the results make sense. It gave wrong information -- especially about polars at times -- but I knew enough to fix it. On the other hand, it helped massively with web scraping by generating the boilerplate and finding which fields to extract from.
