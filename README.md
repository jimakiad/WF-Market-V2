# WF Market V2

This is a Python script to automate the creation of multiple augment mods for Warframe Market.

## Requirements

- Python 3.6 or higher
- Required Python packages: requests, python-dotenv, beautifulsoup4

## Installation

1. Clone the repository.
2. Install the required packages using pip:

   ```
   pip install requests python-dotenv beautifulsoup4
   ```

## Setup

1. Create a `.env` file in the root directory of the project.
2. Add the following environment variables to the `.env` file:

   ```
   WFM_API=https://api.warframe.market
   WFM_USER_EMAIL=your_email@example.com
   WFM_USER_PASSWORD=your_password
   ```

   Replace `your_email@example.com` and `your_password` with your actual Warframe Market login credentials.

## Usage

Run the main script:

```
python main.py
```

The script will:
- Log in to Warframe Market using the provided credentials.
- Retrieve all items and save them to `items.json`.
- Retrieve all user orders and save them to `orders.json`.
- Scrape syndicate mods from the Warframe Wiki and update `augment_mods_by_syndicate.json`.
- Delete matching orders.
- Create new orders for augment mods.

## Files

- `main.py`: The main script that orchestrates the process.
- `login.py`: Handles login to Warframe Market API.
- `get_all_items.py`: Retrieves all items from the API.
- `get_orders.py`: Retrieves user orders from the API.
- `scrape_syndicate_mods.py`: Scrapes augment mods from the Warframe Wiki.
- `create_orders.py`: Creates new orders for augment mods.
- `delete_orders.py`: Deletes matching orders.
- `items.json`: Stores retrieved items data.
- `orders.json`: Stores retrieved orders data.
- `augment_mods_by_syndicate.json`: Stores scraped syndicate mods data.