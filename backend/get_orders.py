from wfm_client import api_request

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
    response = api_request('GET', f"{WFM_API}/v2/orders/my", headers=headers)
    return (response.json())
