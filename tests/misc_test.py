import unittest
import os
import json
from v2ray2proxy import V2RayProxy, V2RayPool

# Get a test V2Ray link from environment or skip the test
TEST_LINK = os.environ.get("TEST_V2RAY_LINK")


class TestMiscFunctionality(unittest.TestCase):
    """Test miscellaneous functionality that users might need."""

    def test_export_config_as_json(self):
        """Test exporting proxy configuration as JSON."""
        proxy = V2RayProxy(TEST_LINK, config_only=True)
        config = proxy.generate_config()

        # Test that the config can be exported as JSON
        config_json = json.dumps(config, indent=2)
        self.assertIsInstance(config_json, str)

        # Test that the JSON can be loaded back
        loaded_config = json.loads(config_json)
        self.assertEqual(loaded_config["inbounds"][0]["protocol"], "socks")
        self.assertEqual(loaded_config["inbounds"][1]["protocol"], "http")

    def test_parse_vmess_link(self):
        """Test parsing a VMess link."""
        # A sample VMess link - no need for a real one
        vmess_link = "vmess://eyJhZGQiOiJleGFtcGxlLmNvbSIsImFpZCI6IjAiLCJpZCI6IjExMTExMTExLTIyMjItMzMzMy00NDQ0LTU1NTU1NTU1NTU1NSIsIm5ldCI6IndzIiwicG9ydCI6IjQ0MyIsInBzIjoiVGVzdCBWTWVzcyIsInNjeSI6ImF1dG8iLCJ0bHMiOiJ0bHMiLCJ0eXBlIjoibm9uZSIsInYiOiIyIn0="

        proxy = V2RayProxy(vmess_link, config_only=True)
        outbound = proxy._parse_vmess_link(vmess_link)

        self.assertEqual(outbound["protocol"], "vmess")
        self.assertEqual(outbound["settings"]["vnext"][0]["address"], "example.com")
        self.assertEqual(outbound["settings"]["vnext"][0]["users"][0]["id"], "11111111-2222-3333-4444-555555555555")

    def test_parse_vless_link(self):
        """Test parsing a VLESS link."""
        vless_link = (
            "vless://11111111-2222-3333-4444-555555555555@example.com:443?type=ws&security=tls&path=%2Fpath&host=example.com#Test+VLESS"
        )

        proxy = V2RayProxy(vless_link, config_only=True)
        outbound = proxy._parse_vless_link(vless_link)

        self.assertEqual(outbound["protocol"], "vless")
        self.assertEqual(outbound["settings"]["vnext"][0]["address"], "example.com")
        self.assertEqual(outbound["settings"]["vnext"][0]["users"][0]["id"], "11111111-2222-3333-4444-555555555555")

    def test_custom_ports(self):
        """Test setting custom ports."""
        # Create a proxy with custom ports
        socks_port = 10080
        http_port = 10081

        # Use a sample link
        vmess_link = "vmess://eyJhZGQiOiJleGFtcGxlLmNvbSIsImFpZCI6IjAiLCJpZCI6IjExMTExMTExLTIyMjItMzMzMy00NDQ0LTU1NTU1NTU1NTU1NSIsIm5ldCI6IndzIiwicG9ydCI6IjQ0MyIsInBzIjoiVGVzdCBWTWVzcyIsInNjeSI6ImF1dG8iLCJ0bHMiOiJ0bHMiLCJ0eXBlIjoibm9uZSIsInYiOiIyIn0="

        proxy = V2RayProxy(vmess_link, socks_port=socks_port, http_port=http_port, config_only=True)
        config = proxy.generate_config()

        # Check if the custom ports are used
        socks_inbound = next(i for i in config["inbounds"] if i["protocol"] == "socks")
        http_inbound = next(i for i in config["inbounds"] if i["protocol"] == "http")

        self.assertEqual(socks_inbound["port"], socks_port)
        self.assertEqual(http_inbound["port"], http_port)

    def test_config_file_creation_and_cleanup(self):
        """Test that config files are created and cleaned up properly."""
        # Use a sample link
        vmess_link = "vmess://eyJhZGQiOiJleGFtcGxlLmNvbSIsImFpZCI6IjAiLCJpZCI6IjExMTExMTExLTIyMjItMzMzMy00NDQ0LTU1NTU1NTU1NTU1NSIsIm5ldCI6IndzIiwicG9ydCI6IjQ0MyIsInBzIjoiVGVzdCBWTWVzcyIsInNjeSI6ImF1dG8iLCJ0bHMiOiJ0bHMiLCJ0eXBlIjoibm9uZSIsInYiOiIyIn0="

        proxy = V2RayProxy(vmess_link, config_only=True)
        config_path = proxy.create_config_file()

        # Check if the file exists
        self.assertTrue(os.path.exists(config_path))

        # Check if the file is cleaned up after stop
        proxy.cleanup()
        self.assertFalse(os.path.exists(config_path))

    @unittest.skipIf(not TEST_LINK, "TEST_V2RAY_LINK environment variable not set")
    def test_multiple_proxies(self):
        """Test running multiple proxies simultaneously."""
        proxy1 = V2RayProxy(TEST_LINK)
        proxy2 = V2RayProxy(TEST_LINK)

        try:
            # Check that they have different ports
            self.assertNotEqual(proxy1.socks_port, proxy2.socks_port)
            self.assertNotEqual(proxy1.http_port, proxy2.http_port)
        finally:
            proxy1.stop()
            proxy2.stop()

    def test_proxy_url_formats(self):
        """Test proxy URL formats."""
        # Use a sample link
        vmess_link = "vmess://eyJhZGQiOiJleGFtcGxlLmNvbSIsImFpZCI6IjAiLCJpZCI6IjExMTExMTExLTIyMjItMzMzMy00NDQ0LTU1NTU1NTU1NTU1NSIsIm5ldCI6IndzIiwicG9ydCI6IjQ0MyIsInBzIjoiVGVzdCBWTWVzcyIsInNjeSI6ImF1dG8iLCJ0bHMiOiJ0bHMiLCJ0eXBlIjoibm9uZSIsInYiOiIyIn0="

        proxy = V2RayProxy(vmess_link, socks_port=1080, http_port=8080, config_only=True)

        # Check URL formats
        self.assertEqual(proxy.socks5_proxy_url, "socks5://127.0.0.1:1080")
        self.assertEqual(proxy.http_proxy_url, "http://127.0.0.1:8080")

    def test_module_exports(self):
        """Test that the module exports the correct classes and constants."""
        # Import directly from the package
        import v2ray2proxy

        self.assertTrue(hasattr(v2ray2proxy, "V2RayProxy"))
        self.assertTrue(hasattr(v2ray2proxy, "V2RayPool"))
        self.assertTrue(hasattr(v2ray2proxy, "VERSION"))

        # Check types
        self.assertEqual(type(v2ray2proxy.VERSION), str)

    @unittest.skipIf(not TEST_LINK, "TEST_V2RAY_LINK environment variable not set")
    def test_pool_functionality(self):
        """Test V2RayPool functionality."""
        # Create a pool with two proxies
        pool = V2RayPool(v2ray_links=[TEST_LINK, TEST_LINK])

        try:
            # Test pool status
            status = pool.get_status()
            self.assertEqual(len(status), 2)

            # Test proxy selection
            proxy = pool.get_proxy()
            self.assertIsNotNone(proxy)
            self.assertTrue(hasattr(proxy, "http_proxy_url"))

            # Test get_fastest_proxy
            fast_proxy = pool.get_fastest_proxy(count=1)
            self.assertIsNotNone(fast_proxy)
        finally:
            pool.stop()


if __name__ == "__main__":
    unittest.main()
