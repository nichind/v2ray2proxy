#!/usr/bin/env python3
import sys
import argparse
import json
import time
import logging
from .base import V2RayProxy, V2RayPool

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def main():
    parser = argparse.ArgumentParser(description="Start a V2Ray proxy from a configuration link")
    parser.add_argument("link", help="V2Ray configuration link (vmess://, vless://, ss://, trojan://)")
    parser.add_argument("--http-port", type=int, help="Port for HTTP protocol (random if not specified)")
    parser.add_argument("--socks-port", type=int, help="Port for SOCKS protocol (random if not specified)")
    parser.add_argument("--test", action="store_true", help="Test the proxy after starting")
    parser.add_argument("--test-url", default="https://api.ipify.org?format=json", help="URL to use for testing")
    parser.add_argument("--timeout", type=int, default=10, help="Timeout for test requests in seconds")
    parser.add_argument("--pool", action="store_true", help="Start a proxy pool with the provided link")
    parser.add_argument("--pool-size", type=int, default=1, help="Number of proxies in the pool (when using --pool)")

    args = parser.parse_args()

    try:
        if args.pool:
            pool_main(args)
        else:
            proxy_main(args)
    except KeyboardInterrupt:
        print("\nProxy stopped by user")
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)


def proxy_main(args):
    try:
        proxy = V2RayProxy(args.link, http_port=args.http_port, socks_port=args.socks_port)

        print(f"V2Ray proxy started:")
        print(f"  SOCKS5 proxy: {proxy.socks5_proxy_url}")
        print(f"  HTTP proxy: {proxy.http_proxy_url}")

        if args.test:
            test_proxy(proxy, args.test_url, args.timeout)

        if not args.test:
            try:
                print("\nPress Ctrl+C to stop the proxy...")
                while True:
                    time.sleep(1)
            finally:
                proxy.stop()
    except Exception as e:
        logging.error(f"Error starting proxy: {str(e)}")
        raise


def pool_main(args):
    try:
        # Create a pool with the link repeated pool_size times
        links = [args.link] * args.pool_size
        pool = V2RayPool(v2ray_links=links, http_port=args.http_port, socks_port=args.socks_port)

        print(f"V2Ray proxy pool started with {args.pool_size} proxies:")

        # Display status of all proxies in the pool
        status = pool.get_status()
        for proxy_id, proxy_status in status.items():
            print(f"  Proxy #{proxy_id}:")
            print(f"    Active: {proxy_status['active']}")
            print(f"    HTTP proxy: {proxy_status['http_proxy_url']}")
            print(f"    SOCKS5 proxy: {proxy_status['socks5_proxy_url']}")

        if args.test:
            # Test the fastest proxy in the pool
            print("\nTesting the fastest proxy in the pool...")
            proxy = pool.get_fastest_proxy()
            if proxy:
                test_proxy(proxy, args.test_url, args.timeout)

        if not args.test:
            try:
                print("\nPress Ctrl+C to stop the proxy pool...")
                while True:
                    time.sleep(1)
            finally:
                pool.stop()
    except Exception as e:
        logging.error(f"Error starting proxy pool: {str(e)}")
        raise


def test_proxy(proxy, test_url, timeout):
    import requests

    print(f"\nTesting proxy with {test_url}...")

    try:
        proxies = {"http": proxy.http_proxy_url, "https": proxy.http_proxy_url}

        response = requests.get(test_url, proxies=proxies, timeout=timeout)

        if response.status_code == 200:
            print(f"✅ Proxy test successful!")
            try:
                json_data = response.json()
                print(f"Response: {json.dumps(json_data, indent=2)}")
            except:
                print(f"Response: {response.text[:100]}")
        else:
            print(f"❌ Proxy test failed with status code: {response.status_code}")
    except Exception as e:
        print(f"❌ Proxy test failed: {str(e)}")


if __name__ == "__main__":
    main()
