# v2ray2proxy

A Python library to convert V2Ray configuration links (vmess://, vless://, ss://, trojan://) to usable proxies for Python HTTP clients.

## Features

- Convert V2Ray links to proxy instances
- Support for synchronous (requests) and asynchronous (aiohttp) HTTP clients
- Support for multiple V2Ray protocols:
  - VMess
  - VLESS
  - Shadowsocks
  - Trojan
- No external Python dependencies besides requests/aiohttp
- Automatically manages V2Ray processes

## Requirements

- Python 3.9+
- V2Ray installed on your system and available in your PATH

## Installation

```bash
pip install v2ray2proxy
```

## Usage

### Synchronous (with requests)

```python
from v2ray2proxy import V2RayProxy

# Create a proxy from a V2Ray link
proxy = V2RayProxy("vmess://...")

# Use it with requests
with proxy.session() as session:
    response = session.get("https://api.ipify.org?format=json")
    print(response.json())

# Test the proxy
result = proxy.test()
if result["success"]:
    print(f"Proxy working! IP: {result['data']['ip']}")
else:
    print(f"Proxy failed: {result['error']}")

# Close the proxy when done
proxy.stop()
```

### Asynchronous (with aiohttp)

```python
import asyncio
from v2ray2proxy import AsyncV2RayProxy

async def main():
    # Create a proxy from a V2Ray link
    proxy = await AsyncV2RayProxy.create("vmess://...")
    
    # Use it with aiohttp
    async with proxy.aiohttp_session() as session:
        async with session.get(
            "https://api.ipify.org?format=json",
            proxy=proxy.aiohttp_proxy_url
        ) as response:
            data = await response.json()
            print(data)
    
    # Test the proxy
    result = await proxy.test()
    if result["success"]:
        print(f"Proxy working! IP: {result['data']['ip']}")
    else:
        print(f"Proxy failed: {result['error']}")
    
    # Close the proxy when done
    proxy.stop()

asyncio.run(main())
```

### Command Line Usage

```bash
# Test a V2Ray link
python -m v2ray2proxy "vmess://..." --test

# Specify custom ports
python -m v2ray2proxy "vmess://..." --socks-port 1080 --http-port 8080
```
