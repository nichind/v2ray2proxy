import unittest
import os
import json
from v2ray2proxy import V2RayProxy


class TestLinkParsing(unittest.TestCase):
    def test_vmess_parsing(self):
        # A sample VMess link
        vmess_link = "vmess://eyJhZGQiOiJleGFtcGxlLmNvbSIsImFpZCI6IjAiLCJpZCI6IjExMTExMTExLTIyMjItMzMzMy00NDQ0LTU1NTU1NTU1NTU1NSIsIm5ldCI6IndzIiwicG9ydCI6IjQ0MyIsInBzIjoiVGVzdCBWTWVzcyIsInNjeSI6ImF1dG8iLCJ0bHMiOiJ0bHMiLCJ0eXBlIjoibm9uZSIsInYiOiIyIn0="

        proxy = V2RayProxy(vmess_link, config_only=True)
        config = proxy.generate_config()

        # Check if the parsed config has the correct structure
        self.assertEqual(config["outbounds"][0]["protocol"], "vmess")
        self.assertEqual(config["outbounds"][0]["settings"]["vnext"][0]["address"], "example.com")
        self.assertEqual(config["outbounds"][0]["settings"]["vnext"][0]["port"], 443)
        self.assertEqual(config["outbounds"][0]["streamSettings"]["network"], "ws")
        self.assertEqual(config["outbounds"][0]["streamSettings"]["security"], "tls")

    def test_vless_parsing(self):
        # A sample VLESS link
        vless_link = (
            "vless://11111111-2222-3333-4444-555555555555@example.com:443?type=ws&security=tls&path=%2Fpath&host=example.com#Test+VLESS"
        )

        proxy = V2RayProxy(vless_link, config_only=True)
        config = proxy.generate_config()

        # Check if the parsed config has the correct structure
        self.assertEqual(config["outbounds"][0]["protocol"], "vless")
        self.assertEqual(config["outbounds"][0]["settings"]["vnext"][0]["address"], "example.com")
        self.assertEqual(config["outbounds"][0]["settings"]["vnext"][0]["port"], 443)
        self.assertEqual(config["outbounds"][0]["streamSettings"]["network"], "ws")
        self.assertEqual(config["outbounds"][0]["streamSettings"]["security"], "tls")

    def test_ss_parsing(self):
        # A sample Shadowsocks link
        ss_link = "ss://YWVzLTI1Ni1nY206cGFzc3dvcmQ=@example.com:8388#Test+SS"

        proxy = V2RayProxy(ss_link, config_only=True)
        config = proxy.generate_config()

        # Check if the parsed config has the correct structure
        self.assertEqual(config["outbounds"][0]["protocol"], "shadowsocks")
        self.assertEqual(config["outbounds"][0]["settings"]["servers"][0]["address"], "example.com")
        self.assertEqual(config["outbounds"][0]["settings"]["servers"][0]["port"], 8388)

    def test_trojan_parsing(self):
        # A sample Trojan link
        trojan_link = "trojan://password@example.com:443?sni=example.org#Test+Trojan"

        proxy = V2RayProxy(trojan_link, config_only=True)
        config = proxy.generate_config()

        # Check if the parsed config has the correct structure
        self.assertEqual(config["outbounds"][0]["protocol"], "trojan")
        self.assertEqual(config["outbounds"][0]["settings"]["servers"][0]["address"], "example.com")
        self.assertEqual(config["outbounds"][0]["settings"]["servers"][0]["port"], 443)
        self.assertEqual(config["outbounds"][0]["settings"]["servers"][0]["password"], "password")
        self.assertEqual(config["outbounds"][0]["streamSettings"]["tlsSettings"]["serverName"], "example.org")

    def test_config_file_creation(self):
        # Test that the config file is created correctly
        vmess_link = "vmess://eyJhZGQiOiJleGFtcGxlLmNvbSIsImFpZCI6IjAiLCJpZCI6IjExMTExMTExLTIyMjItMzMzMy00NDQ0LTU1NTU1NTU1NTU1NSIsIm5ldCI6IndzIiwicG9ydCI6IjQ0MyIsInBzIjoiVGVzdCBWTWVzcyIsInNjeSI6ImF1dG8iLCJ0bHMiOiJ0bHMiLCJ0eXBlIjoibm9uZSIsInYiOiIyIn0="

        proxy = V2RayProxy(vmess_link, config_only=True)
        config_path = proxy.create_config_file()

        try:
            # Check if file exists
            self.assertTrue(os.path.exists(config_path))

            # Check file content
            with open(config_path, "r") as f:
                config_json = json.load(f)

            self.assertEqual(config_json["outbounds"][0]["protocol"], "vmess")
            self.assertEqual(len(config_json["inbounds"]), 2)  # SOCKS and HTTP inbounds
        finally:
            # Clean up
            if os.path.exists(config_path):
                os.unlink(config_path)


if __name__ == "__main__":
    unittest.main()
    unittest.main()
