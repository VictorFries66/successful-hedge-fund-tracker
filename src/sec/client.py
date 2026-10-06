"""Small SEC HTTP client with conservative retries for transient outages."""

import os
import ssl
import time
import requests


class SECClient:
    def __init__(self, user_agent=None, delay_seconds=0.25, max_retries=5):
        self.user_agent = user_agent or os.getenv("SEC_USER_AGENT")
        if not self.user_agent:
            raise RuntimeError("SEC_USER_AGENT is required.")
        self.delay_seconds = delay_seconds
        self.max_retries = max_retries
        self.session = requests.Session()

        # Prefer an explicitly configured CA bundle, otherwise use the CA file
        # selected by the Python/OpenSSL installation.
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
        """GET a SEC URL, retrying temporary server/network failures."""
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.get(url, timeout=30)
                if response.status_code == 429 or response.status_code in (500, 502, 503, 504):
                    if attempt < self.max_retries:
                        retry_after = response.headers.get("Retry-After")
                        try:
                            wait = max(float(retry_after), 1.0) if retry_after else min(2 ** attempt, 30)
                        except ValueError:
                            wait = min(2 ** attempt, 30)
                        response.close()
                        time.sleep(wait)
                        continue
                response.raise_for_status()
                time.sleep(self.delay_seconds)
                return response
            except (requests.ConnectionError, requests.Timeout):
                if attempt >= self.max_retries:
                    raise
                time.sleep(min(2 ** attempt, 30))

        raise RuntimeError(f"SEC request failed after retries: {url}")

    def get_json(self, url):
        return self.get(url).json()
