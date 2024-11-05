import json
import os
from typing import Optional
from better_proxy import Proxy

class ProxyManager:
    def __init__(self):
        self.bindings_file = 'bot/config/proxy_bindings.json'
        self.bindings = self._load_bindings()

    def _load_bindings(self) -> dict:
        if os.path.exists(self.bindings_file):
            try:
                with open(self.bindings_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_bindings(self):
        with open(self.bindings_file, 'w') as f:
            json.dump(self.bindings, f, indent=4)

    def get_proxy(self, session_name: str) -> Optional[str]:
        return self.bindings.get(session_name)

    def set_proxy(self, session_name: str, proxy: str):
        self.bindings[session_name] = proxy
        self._save_bindings()

    def remove_proxy(self, session_name: str):
        if session_name in self.bindings:
            del self.bindings[session_name]
            self._save_bindings() 