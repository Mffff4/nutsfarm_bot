from typing import Dict, Optional

def _get_language(country: Optional[str] = None) -> str:
    return 'EN' if country and country != 'RU' else 'RU'

def get_headers(user_agent: str, with_auth: bool = False, token: Optional[str] = None, country: Optional[str] = None) -> Dict[str, str]:
    lang = _get_language(country)
    headers = {
        'accept': '*/*',
        'accept-language': lang.lower(),
        'content-type': 'application/json',
        'origin': 'https://nutsfarm.crypton.xyz',
        'referer': 'https://nutsfarm.crypton.xyz/',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'user-agent': user_agent
    }
    
    if with_auth and token:
        headers['authorization'] = f'Bearer {token}'
        
    return headers

def get_task_headers(country: Optional[str] = None) -> Dict[str, str]:
    lang = _get_language(country)
    return {
        'accept': '*/*',
        'accept-language': lang.lower(),
        'content-type': 'application/json',
        'origin': 'https://nutsfarm.crypton.xyz',
        'referer': 'https://nutsfarm.crypton.xyz/',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site'
    }

def get_farming_headers(country: Optional[str] = None) -> Dict[str, str]:
    lang = _get_language(country)
    return {
        'accept': '*/*',
        'accept-language': lang.lower(),
        'content-type': 'application/json',
        'origin': 'https://nutsfarm.crypton.xyz',
        'referer': 'https://nutsfarm.crypton.xyz/farming',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site'
    }

def get_auth_headers(country: Optional[str] = None) -> Dict[str, str]:
    lang = _get_language(country)
    return {
        'accept': '*/*',
        'accept-language': lang.lower(),
        'content-type': 'application/json',
        'origin': 'https://nutsfarm.crypton.xyz',
        'referer': 'https://nutsfarm.crypton.xyz/auth',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site'
    }

def get_proxy_check_headers(country: Optional[str] = None) -> Dict[str, str]:
    lang = _get_language(country)
    return {
        'accept': '*/*',
        'accept-language': lang.lower(),
        'content-type': 'application/json',
        'origin': 'https://nutsfarm.crypton.xyz',
        'referer': 'https://nutsfarm.crypton.xyz/proxy-check',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site'
    }

def get_referral_headers(proxy_country: str = None) -> dict:
    """Возвращает заголовки для запросов к реферальному API"""
    return {
        'accept': '*/*',
        'accept-language': 'ru,en-US;q=0.9,en;q=0.8' if not proxy_country or proxy_country == 'RU' else 'en-US,en;q=0.9',
        'cache-control': 'no-cache',
        'origin': 'https://nutsfarm.crypton.xyz',
        'pragma': 'no-cache',
        'referer': 'https://nutsfarm.crypton.xyz/',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site'
    }