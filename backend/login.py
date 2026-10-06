from wfm_client import api_request
import json

def login(
    user_email: str, user_password: str, WFM_API: str, platform: str = "pc", language: str = "en"
):
    """
    Used for logging into warframe.market via the API.
    Returns (User_Name, JWT_Token) on success,
    or returns (None, None) if unsuccessful.
    """
    headers = {
        "Content-Type": "application/json; utf-8",
        "Accept": "application/json",
        "Authorization": "JWT",
        "platform": platform,
        "language": language,
    }
    content = {"email": user_email, "password": user_password, "auth_type": "header"}
    response = api_request('POST', f"{WFM_API}/v1/auth/signin", data=json.dumps(content), headers=headers)
    return (response.json()["payload"]["user"]["ingame_name"], response.headers["Authorization"])
