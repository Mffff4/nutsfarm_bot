def get_headers(user_agent: str, with_auth: bool = False, token: str = None) -> dict:
    headers = {
        'Host': 'nutsfarm.crypton.xyz',
        'Sec-Fetch-Site': 'same-origin',
        'Accept-Language': 'ru',
        'Connection': 'keep-alive',
        'Sec-Fetch-Mode': 'cors', 
        'Accept': '*/*',
        'User-Agent': user_agent,
        'Sec-Fetch-Dest': 'empty',
        'Referer': 'https://nutsfarm.crypton.xyz/'
    }
    
    if with_auth and token:
        headers['Authorization'] = f'Bearer {token}'
        
    return headers