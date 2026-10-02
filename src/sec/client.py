import os
import ssl
import time
import requests


class SECClient:
    def __init__(self, user_agent=None, delay_seconds=0.25):
        self.user_agent = user_agent or os.getenv("SEC_USER_AGENT")
        if not self.user_agent:
            raise RuntimeError("SEC_USER_AGENT is required.")
        self.delay_seconds = delay_seconds
        self.session = requests.Session()

        # Prefer an explicitly configured CA bundle, otherwise use the CA file
        # selected by the Python/OpenSSL installation. This avoids forcing
        # Requests to use certifi's bundled CA set, which can differ from the
        # system/Homebrew trust store.
        ca_bundle = os.getenv("SEC_CA_BUNDLE") or ssl.get_default_verify_paths().cafile
        if not ca_bundle:
            raise RuntimeError(
                "No CA bundle is configured. Set SEC_CA_BUNDLE to a trusted CA bundle path."
            )
        self.session.verify = ca_bundle
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
