import unittest
import asyncio
import os
from v2ray2proxy import AsyncV2RayProxy

# Get a test V2Ray link from environment or skip the test
TEST_LINK = os.environ.get("TEST_V2RAY_LINK")

@unittest.skipIf(not TEST_LINK, "TEST_V2RAY_LINK environment variable not set")
class TestAsyncV2RayProxy(unittest.IsolatedAsyncioTestCase):
    
    async def test_proxy_creation(self):
        proxy = await AsyncV2RayProxy.create(TEST_LINK)
        self.assertTrue(proxy.running)
        self.assertIsNotNone(proxy.socks_port)
        proxy.stop()
    
    async def test_aiohttp_session(self):
        proxy = await AsyncV2RayProxy.create(TEST_LINK)
        try:
            async with proxy.aiohttp_session() as session:
                async with session.get(
                    "https://api.ipify.org?format=json",
                    proxy=proxy.aiohttp_proxy_url
                ) as response:
                    self.assertEqual(response.status, 200)
                    data = await response.json()
                    self.assertIn('ip', data)
        finally:
            proxy.stop()
    
    async def test_proxy_test_method(self):
        proxy = await AsyncV2RayProxy.create(TEST_LINK)
        try:
            result = await proxy.test()
            self.assertTrue(result["success"])
            self.assertEqual(result["status_code"], 200)
            self.assertIn('ip', result["data"])
        finally:
            proxy.stop()

if __name__ == "__main__":
    asyncio.run(unittest.main())
