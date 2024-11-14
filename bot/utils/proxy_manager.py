import json
import os
from typing import Optional
from better_proxy import Proxy

class ProxyManager:
    def __init__(self):
        self.bindings_file = 'sessions/accounts.json'
        self.bindings = self._load_bindings()
        if isinstance(self.bindings, list):
            self.bindings = {
                item['session_name']: item['proxy']
                for item in self.bindings
                if isinstance(item, dict) and 'session_name' in item and 'proxy' in item
            }

    def _load_bindings(self) -> dict:
        try:
            if os.path.exists(self.bindings_file):
                with open(self.bindings_file, 'r') as f:
                    data = json.load(f)
                    
                    if isinstance(data, list):
                        result = {
                            item['session_name']: item['proxy']
                            for item in data
                            if isinstance(item, dict) and 'session_name' in item and 'proxy' in item
                        }
                        return result
                    elif isinstance(data, dict):
                        return data
                    else:
                        return {}
        except Exception as e:
            print(f"DEBUG: Error in _load_bindings: {str(e)}")
            return {}
        return {}

    def _save_bindings(self):
        data_to_save = [
            {
                'session_name': session_name,
                'proxy': proxy
            }
            for session_name, proxy in self.bindings.items()
        ]
        with open(self.bindings_file, 'w') as f:
            json.dump(data_to_save, f, indent=4)

    def get_proxy(self, session_name: str) -> Optional[str]:
        if isinstance(self.bindings, list):
            self.bindings = {
                item['session_name']: item['proxy']
                for item in self.bindings
                if isinstance(item, dict) and 'session_name' in item and 'proxy' in item
            }
        return self.bindings.get(session_name) if isinstance(self.bindings, dict) else None

    def set_proxy(self, session_name: str, proxy: str):
        self.bindings[session_name] = proxy
        self._save_bindings()

    def remove_proxy(self, session_name: str):
        if session_name in self.bindings:
            del self.bindings[session_name]
            self._save_bindings() 