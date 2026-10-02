import os
import time
import requests
import certifi

class SECClient:
    def __init__(self, user_agent=None, delay_seconds=0.25):
        self.user_agent = user_agent or os.getenv("SEC_USER_AGENT")
        if not self.user_agent:
            raise RuntimeError("SEC_USER_AGENT is required.")
        self.delay_seconds = delay_seconds
        self.session = requests.Session()
        self.session.verify = certifi.where()
        self.session.headers.update({
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
        })

    def get(self, url):
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        time.sleep(self.delay_seconds)
        return response

    def get_json(self, url):
        return self.get(url).json()
