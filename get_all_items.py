import requests

def get_all_items(JWT: str, WFM_API: str, platform: str = "pc", language: str = "en"):
        
    """
    Returns all items from the Warframe Market.
    """
    headers = {
        "Content-Type": "application/json; utf-8",
        "Accept": "application/json",
        "Authorization": JWT.replace("JWT", "Bearer"),
        "platform": platform,
        "language": language,
    }
    response = requests.get(f"{WFM_API}/v2/items", headers=headers)
    if response.status_code != 200:
        print(f"Failed to get items. Status code: {response.status_code}, Status Error: {response.json()}")
        return None
    return response.json()