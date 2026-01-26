import requests
import json
import time

PLATINUM_PRICE = 12
QUANTITY = 1

def create_orders(JWT: str, API_URL: str, platform: str = "pc", language: str = "en"):
    with open("augment_mods_by_syndicate.json", "r", encoding="utf-8") as f:
        mods_data = json.load(f)

    syndicates = list(mods_data.keys())
    print("Available syndicates:")
    for synd in syndicates:
        print(f"- {synd}")

    while True:
        selected_synd = input("Enter the syndicate name: ").strip()
        if selected_synd in mods_data:
            break
        else:
            print("Invalid syndicate name. Please enter one exactly as shown above.")

    print(f"\nProcessing orders for syndicate: {selected_synd}\n")

    headers = {
    "Accept": "application/json",
    "Authorization": JWT.replace("JWT", "Bearer"),
    "platform": platform,
    "language": language,
    }


    for mod in mods_data[selected_synd]:
        if "id" in mod and "orderId" not in mod:
            body = {
                "itemId": mod["id"],
                "type": "sell",
                "platinum": PLATINUM_PRICE,
                "quantity": QUANTITY,
                "visible": True,
                "rank": 0
            }

            try:
                response = requests.post(API_URL + "/v2/order", json=body, headers=headers)
                response.raise_for_status()
                data = response.json()

                if data.get("data") and "id" in data["data"]:
                    mod["orderId"] = data["data"]["id"]
                    print(f"Created order for {mod['Name']} -> {mod['orderId']}")
                else:
                    print(f"Warning: No order ID returned for {mod['Name']}")

            except Exception as e:
                print(f"Error creating order for {mod['Name']}: {e}")

            with open("augment_mods_by_syndicate.json", "w", encoding="utf-8") as f:
                json.dump(mods_data, f, indent=4, ensure_ascii=False)

            time.sleep(0.1)

    print("\nAll orders processed for this syndicate.")
