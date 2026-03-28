import os
import re
import requests
from bs4 import BeautifulSoup
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

def scrape_syndicate_mods():

    def normalize_name(name: str) -> str:
        return name.lower().replace(" ", "_").replace("'", "").replace("\u2019", "")

    def super_normalize(name: str) -> str:
        """Strip every non-alphanumeric character; used as a last-resort match."""
        return re.sub(r'[^a-z0-9_]', '', name.lower().replace(' ', '_'))

    def scrape_augment_mods(url: str = "https://wiki.warframe.com/w/Warframe_Augment_Mods"):
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        mods_by_syndicate = {}

        table = soup.find("table", {"class": "wikitable"})
        if not table:
            raise ValueError("No wikitable found on the page")

        for row in table.find_all("tr")[1:]: 
            cols = row.find_all("td")
            if len(cols) < 3:
                continue

            mods_col = cols[1]
            synd_col = cols[2]

            mod_spans = mods_col.find_all("span", {"data-param-source": "Mods"})
            mod_names = [span["data-param-name"].strip() for span in mod_spans]

            synd_spans = synd_col.find_all("span", {"data-param-source": "Factions"})
            synd_names = [span["data-param-name"].strip() for span in synd_spans]

            for synd in synd_names:
                if synd not in mods_by_syndicate:
                    mods_by_syndicate[synd] = []

                for mod in mod_names:
                    mod_entry = {
                        "Name": mod,
                        "URL_Name": normalize_name(mod)
                    }
                    if mod_entry not in mods_by_syndicate[synd]:
                        mods_by_syndicate[synd].append(mod_entry)

        return mods_by_syndicate

    with open(os.path.join(DATA_DIR, 'items.json'), 'r', encoding='utf-8') as f:
        items_data = json.load(f)["data"]

    # Primary lookup: WFM slug
    slug_to_id = {item["slug"]: item["id"] for item in items_data}

    # Secondary lookup: normalize the WFM item's own display name.
    # Handles cases where the wiki name differs slightly from the WFM slug.
    name_to_id: dict[str, str] = {}
    for item in items_data:
        en = item.get("i18n", {}).get("en", {})
        raw = en.get("item_name") or en.get("name") or ""
        if raw:
            name_to_id[normalize_name(raw)] = item["id"]
            name_to_id[super_normalize(raw)] = item["id"]

    mods_data = scrape_augment_mods()

    for syndicate, mods in mods_data.items():
        for mod in mods:
            key = mod["URL_Name"]
            mod_id = (
                slug_to_id.get(key)
                or name_to_id.get(key)
                or name_to_id.get(super_normalize(key))
            )
            if mod_id:
                mod["id"] = mod_id

    with open(os.path.join(DATA_DIR, 'augment_mods_by_syndicate.json'), 'w', encoding='utf-8') as f:
        json.dump(mods_data, f, indent=4, ensure_ascii=False)

    print(f"Scraped {sum(len(v) for v in mods_data.values())} mods from {len(mods_data)} syndicates")
