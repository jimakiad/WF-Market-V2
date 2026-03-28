import os
import requests
import json
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

def delete_matching_orders(JWT: str, API_URL: str, platform: str = "pc", language: str = "en"):
    
    with open(os.path.join(DATA_DIR, 'augment_mods_by_syndicate.json'), 'r', encoding='utf-8') as f:
        augment_data = json.load(f)

    with open(os.path.join(DATA_DIR, 'orders.json'), 'r', encoding='utf-8') as f:
        orders_data = json.load(f)

    headers = {
    "Accept": "application/json",
    "Authorization": JWT.replace("JWT", "Bearer"),
    "platform": platform,
    "language": language,
    }

    augment_item_ids = set()
    for syndicate, mods in augment_data.items():
        for mod in mods:
            if "id" in mod:
                augment_item_ids.add(mod["id"])

    print(f"Loaded {len(augment_item_ids)} augment item IDs")

    orders = orders_data.get("data", [])

    deleted = 0
    skipped = 0

    for order in orders:
        order_id = order.get("id")
        order_item_id = order.get("itemId")

        if not order_id or not order_item_id:
            continue

        if order_item_id in augment_item_ids:
            try:
                url = f"{API_URL}/v2/order/{order_id}"
                response = requests.delete(url, headers=headers)
                response.raise_for_status()

                print(f"Deleted order {order_id} (itemId: {order_item_id})")
                deleted += 1

                time.sleep(0.1)

            except Exception as e:
                print(f"Failed to delete order {order_id}: {e}")
        else:
            skipped += 1

    print("\n=== Cleanup Summary ===")
    print(f"Deleted orders: {deleted}")
    print(f"Skipped orders: {skipped}")
    print("Done")
