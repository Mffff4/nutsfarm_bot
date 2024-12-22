from bot.config.config import Settings

def get_headers(user_agent: str, with_auth: bool = False, token: str = None) -> dict:
    base_url = Settings().BASE_URL.replace('https://', '').replace('/', '')
    headers = {
        'Host': base_url,
        'Sec-Fetch-Site': 'same-origin',
        'Accept-Language': 'ru',
        'Connection': 'keep-alive',
        'Sec-Fetch-Mode': 'cors', 
        'Accept': '*/*',
        'User-Agent': user_agent,
        'Sec-Fetch-Dest': 'empty',
        'Referer': Settings().BASE_URL
    }
    
    if with_auth and token:
        headers['Authorization'] = f'Bearer {token}'
        
    return headers