from wfm_client import api_request

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
    response = api_request('GET', f"{WFM_API}/v2/items", headers=headers)
    return response.json()
