import unittest
import os
import requests
from v2ray2proxy import V2RayPool

# Get a test V2Ray link from environment or skip the test
TEST_LINK = os.environ.get("TEST_V2RAY_LINK")


@unittest.skipIf(not TEST_LINK, "TEST_V2RAY_LINK environment variable not set")
class TestV2RayPool(unittest.TestCase):
    def test_pool_creation(self):
        """Test creating a V2RayPool with multiple proxies."""
        pool = V2RayPool(v2ray_links=[TEST_LINK, TEST_LINK])
        try:
            status = pool.get_status()
            self.assertEqual(len(status), 2)
            for proxy_id, proxy_status in status.items():
                self.assertTrue(proxy_status["active"])
        finally:
            pool.stop()

    def test_pool_proxy_selection(self):
        """Test different proxy selection strategies."""
        pool = V2RayPool(v2ray_links=[TEST_LINK, TEST_LINK])
        try:
            # Round-robin selection
            proxy1 = pool.get_proxy(strategy="round-robin")
            proxy2 = pool.get_proxy(strategy="round-robin")
            self.assertNotEqual(proxy1.http_port, proxy2.http_port)

            # Random selection
            proxy = pool.get_proxy(strategy="random")
            self.assertIsNotNone(proxy)
        finally:
            pool.stop()

    def test_health_check(self):
        """Test health check functionality."""
        pool = V2RayPool(v2ray_links=[TEST_LINK])
        try:
            health = pool.check_health(timeout=10)
            self.assertTrue(1 in health)  # First proxy has ID 1
            self.assertTrue(health[1])  # Should be healthy
        finally:
            pool.stop()

    def test_fastest_proxy(self):
        """Test getting the fastest proxy."""
        pool = V2RayPool(v2ray_links=[TEST_LINK, TEST_LINK])
        try:
            proxy = pool.get_fastest_proxy(count=1)
            self.assertIsNotNone(proxy)

            # Test making a request with the fastest proxy
            proxies = {"http": proxy.http_proxy_url, "https": proxy.http_proxy_url}
            response = requests.get("https://api.ipify.org?format=json", proxies=proxies, timeout=10)
            self.assertEqual(response.status_code, 200)
        finally:
            pool.stop()

    def test_proxy_urls(self):
        """Test getting proxy URLs from the pool."""
        pool = V2RayPool(v2ray_links=[TEST_LINK])
        try:
            http_url = pool.http_proxy_url()
            socks_url = pool.socks5_proxy_url()

            self.assertTrue(http_url.startswith("http://127.0.0.1:"))
            self.assertTrue(socks_url.startswith("socks5://127.0.0.1:"))
        finally:
            pool.stop()


if __name__ == "__main__":
    unittest.main()
