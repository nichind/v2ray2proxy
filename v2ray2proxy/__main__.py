#!/usr/bin/env python3
import sys
import argparse
import json
import asyncio
from .sync_proxy import V2RayProxy
from .async_proxy import AsyncV2RayProxy

def main():
    parser = argparse.ArgumentParser(description="Start a V2Ray proxy from a configuration link")
    parser.add_argument("link", help="V2Ray configuration link (vmess://, vless://, etc.)")
    parser.add_argument("--port", type=int, help="Port for V2Ray to listen on (random if not specified)")
    parser.add_argument("--socks-port", type=int, help="Port for SOCKS protocol (same as port if not specified)")
    parser.add_argument("--http-port", type=int, help="Port for HTTP protocol (same as port if not specified)")
    parser.add_argument("--test", action="store_true", help="Test the proxy after starting")
    parser.add_argument("--test-url", default="https://api.ipify.org?format=json", help="URL to use for testing")
    parser.add_argument("--timeout", type=int, default=10, help="Timeout for test requests in seconds")
    parser.add_argument("--async", action="store_true", dest="use_async", help="Use async API for testing")
    
    args = parser.parse_args()
    
    try:
        if args.use_async:
            asyncio.run(async_main(args))
        else:
            sync_main(args)
    except KeyboardInterrupt:
        print("\nProxy stopped by user")
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)

def sync_main(args):
    proxy = V2RayProxy(
        args.link,
        port=args.port,
        socks_port=args.socks_port,
        http_port=args.http_port
    )
    
    print(f"V2Ray proxy started:")
    print(f"  SOCKS5 proxy: {proxy.socks5_proxy_url}")
    print(f"  HTTP proxy: {proxy.http_proxy_url}")
    print(f"  Requests config: {json.dumps(proxy.requests_proxies)}")
    
    if args.test:
        print(f"\nTesting proxy with {args.test_url}...")
        result = proxy.test(args.test_url, args.timeout)
        if result["success"]:
            print(f"✅ Proxy test successful!")
            print(f"Response: {json.dumps(result['data'], indent=2)}")
        else:
            print(f"❌ Proxy test failed: {result.get('error', 'Unknown error')}")
    
    if not args.test:
        try:
            print("\nPress Ctrl+C to stop the proxy...")
            while True:
                import time
                time.sleep(1)
        finally:
            proxy.stop()

async def async_main(args):
    proxy = await AsyncV2RayProxy.create(
        args.link,
        port=args.port,
        socks_port=args.socks_port,
        http_port=args.http_port
    )
    
    print(f"V2Ray proxy started:")
    print(f"  SOCKS5 proxy: {proxy.socks5_proxy_url}")
    print(f"  HTTP proxy: {proxy.http_proxy_url}")
    print(f"  aiohttp proxy: {proxy.aiohttp_proxy_url}")
    
    if args.test:
        print(f"\nTesting proxy with {args.test_url}...")
        result = await proxy.test(args.test_url, args.timeout)
        if result["success"]:
            print(f"✅ Proxy test successful!")
            print(f"Response: {json.dumps(result['data'], indent=2)}")
        else:
            print(f"❌ Proxy test failed: {result.get('error', 'Unknown error')}")
    
    if not args.test:
        try:
            print("\nPress Ctrl+C to stop the proxy...")
            while True:
                await asyncio.sleep(1)
        finally:
            proxy.stop()

if __name__ == "__main__":
    main()
