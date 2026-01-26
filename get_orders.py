import requests

def get_orders(JWT: str, WFM_API: str, platform: str = "pc", language: str = "en"):
    """
    Returns the user's profile information.
    """
    headers = {
        "Content-Type": "application/json; utf-8",
        "Accept": "application/json",
        "Authorization": JWT.replace("JWT", "Bearer"),
        "platform": platform,
        "language": language,
    }
    response = requests.get(f"{WFM_API}/v2/orders/my", headers=headers)
    #print(response)
    if response.status_code != 200:
        return None, None
    return (response.json())