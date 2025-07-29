import unittest
import os
import asyncio
import aiohttp
from v2ray2proxy import V2RayProxy

# Get a test V2Ray link from environment or use default for testing
TEST_LINK = os.environ.get("TEST_V2RAY_LINK")


class TestAsyncV2RayProxy(unittest.IsolatedAsyncioTestCase):
    """Test V2RayProxy with async HTTP requests."""

    async def test_aiohttp_request(self):
        """Test making an async HTTP request through the proxy."""
        proxy = V2RayProxy(TEST_LINK)
        try:
            # Create a session with the proxy
            async with aiohttp.ClientSession() as session:
                # Make a request through the proxy
                async with session.get("https://api.ipify.org?format=json", proxy=proxy.http_proxy_url) as response:
                    self.assertEqual(response.status, 200)
                    data = await response.json()
                    self.assertIn("ip", data)
        finally:
            proxy.stop()

    async def test_multiple_concurrent_requests(self):
        """Test making multiple concurrent requests through the proxy."""
        proxy = V2RayProxy(TEST_LINK)
        try:
            # List of URLs to fetch
            urls = ["https://api.ipify.org?format=json", "https://api.ipify.org?format=json", "https://api.ipify.org?format=json"]

            # Create a session with the proxy
            async with aiohttp.ClientSession() as session:
                # Create tasks for all requests
                tasks = []
                for url in urls:
                    tasks.append(session.get(url, proxy=proxy.http_proxy_url))

                # Wait for all requests to complete
                responses = await asyncio.gather(*tasks)

                # Check all responses
                for response in responses:
                    async with response:
                        self.assertEqual(response.status, 200)
                        data = await response.json()
                        self.assertTrue(data)  # Ensure we got some data
        finally:
            proxy.stop()

    async def test_error_handling(self):
        """Test handling errors in async requests."""
        proxy = V2RayProxy(TEST_LINK)
        try:
            # Create a session with the proxy
            async with aiohttp.ClientSession() as session:
                # Try to connect to a non-existent server
                with self.assertRaises(aiohttp.ClientError):
                    async with session.get(
                        "https://this-domain-does-not-exist-123456789.com",
                        proxy=proxy.http_proxy_url,
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as response:
                        pass
        finally:
            proxy.stop()

    async def test_socks5_proxy(self):
        """Test using SOCKS5 proxy with aiohttp."""
        proxy = V2RayProxy(TEST_LINK)
        try:
            # Create a session with the SOCKS5 proxy
            # Note: aiohttp needs aiohttp-socks package for SOCKS support
            connector = aiohttp.TCPConnector()
            async with aiohttp.ClientSession(connector=connector) as session:
                try:
                    # Use HTTP proxy URL since aiohttp-socks isn't included by default
                    async with session.get("https://api.ipify.org?format=json", proxy=proxy.http_proxy_url, timeout=10) as response:
                        self.assertEqual(response.status, 200)
                        data = await response.json()
                        self.assertIn("ip", data)
                except ImportError:
                    self.skipTest("aiohttp-socks not installed")
        finally:
            proxy.stop()

    async def test_proxy_pool_async(self):
        """Test using V2RayPool with async requests."""
        from v2ray2proxy import V2RayPool

        # Create a pool with two proxies
        pool = V2RayPool(v2ray_links=[TEST_LINK, TEST_LINK])
        try:
            # Get a proxy from the pool
            proxy = pool.get_proxy()

            # Create a session and make a request
            async with aiohttp.ClientSession() as session:
                async with session.get("https://api.ipify.org?format=json", proxy=proxy.http_proxy_url) as response:
                    self.assertEqual(response.status, 200)
                    data = await response.json()
                    self.assertIn("ip", data)
        finally:
            pool.stop()


if __name__ == "__main__":
    asyncio.run(unittest.main())
