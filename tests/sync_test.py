import unittest
import os
import requests
from v2ray2proxy import V2RayProxy

# Get a test V2Ray link from environment or skip the test
TEST_LINK = os.environ.get("TEST_V2RAY_LINK")


@unittest.skipIf(not TEST_LINK, "TEST_V2RAY_LINK environment variable not set")
class TestV2RayProxy(unittest.TestCase):
    def test_proxy_creation(self):
        proxy = V2RayProxy(TEST_LINK)
        self.assertIsNotNone(proxy.socks_port)
        self.assertIsNotNone(proxy.http_port)
        proxy.stop()

    def test_requests_with_proxy(self):
        proxy = V2RayProxy(TEST_LINK)
        try:
            proxies = {"http": proxy.http_proxy_url, "https": proxy.http_proxy_url}
            response = requests.get("https://api.ipify.org?format=json", proxies=proxies, timeout=10)
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertIn("ip", data)
        finally:
            proxy.stop()

    def test_proxy_urls(self):
        proxy = V2RayProxy(TEST_LINK)
        try:
            self.assertTrue(proxy.http_proxy_url.startswith("http://127.0.0.1:"))
            self.assertTrue(proxy.socks5_proxy_url.startswith("socks5://127.0.0.1:"))
        finally:
            proxy.stop()


if __name__ == "__main__":
    unittest.main()
