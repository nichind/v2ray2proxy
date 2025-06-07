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
        self.assertTrue(proxy.running)
        self.assertIsNotNone(proxy.socks_port)
        proxy.stop()
    
    def test_requests_session(self):
        proxy = V2RayProxy(TEST_LINK)
        try:
            with proxy.session() as session:
                response = session.get("https://api.ipify.org?format=json")
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertIn('ip', data)
        finally:
            proxy.stop()
    
    def test_proxy_test_method(self):
        proxy = V2RayProxy(TEST_LINK)
        try:
            result = proxy.test()
            self.assertTrue(result["success"])
            self.assertEqual(result["status_code"], 200)
            self.assertIn('ip', result["data"])
        finally:
            proxy.stop()

if __name__ == "__main__":
    unittest.main()
