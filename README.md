# v2ray2proxy

A Python library to convert V2Ray configuration links (vmess://, vless://, ss://, trojan://) to usable HTTP and SOCKS5 proxies for Python HTTP clients.

## Features

- Convert V2Ray links to local proxy instances
- **Automatic V2Ray core download** - no external installation needed
- Support for all major V2Ray protocols:
  - VMess
  - VLESS
  - Shadowsocks
  - Trojan
- Proxy pool for load balancing and failover
- Works with both synchronous and asynchronous HTTP clients
- Clean, Pythonic API

## Installation

```bash
pip install v2ray2proxy
```

## Usage

### Basic Usage

```python
from v2ray2proxy import V2RayProxy
import requests

# Create a proxy from a V2Ray link
proxy = V2RayProxy("vmess://...")

try:
    # Use with requests
    proxies = {
        "http": proxy.http_proxy_url,
        "https": proxy.http_proxy_url
    }
    
    response = requests.get("https://api.ipify.org?format=json", proxies=proxies)
    print(response.json())
finally:
    # Always stop the proxy when done
    proxy.stop()
```

### Using with aiohttp (Async)

```python
import asyncio
import aiohttp
from v2ray2proxy import V2RayProxy

async def main():
    # Create a proxy from a V2Ray link
    proxy = V2RayProxy("vmess://...")
    
    try:
        # Use with aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.ipify.org?format=json",
                proxy=proxy.http_proxy_url
            ) as response:
                data = await response.json()
                print(data)
    finally:
        # Always stop the proxy when done
        proxy.stop()

asyncio.run(main())
```

### Proxy Pool for Load Balancing

```python
from v2ray2proxy import V2RayPool
import requests

# Create a pool with multiple proxies
links = [
    "vmess://...",
    "vless://...",
    "trojan://..."
]

pool = V2RayPool(v2ray_links=links)

try:
    # Get the fastest proxy from the pool
    proxy = pool.get_fastest_proxy()
    
    # Use the proxy
    proxies = {
        "http": proxy.http_proxy_url,
        "https": proxy.http_proxy_url
    }
    
    response = requests.get("https://api.ipify.org?format=json", proxies=proxies)
    print(response.json())
    
    # You can also get a proxy using different strategies
    # Round-robin
    proxy = pool.get_proxy(strategy="round-robin")
    # Random
    proxy = pool.get_proxy(strategy="random")
    
    # Get proxy URLs directly from the pool
    http_url = pool.http_proxy_url()
    socks5_url = pool.socks5_proxy_url()
finally:
    # Always stop the pool when done
    pool.stop()
```

### Command Line Usage

```bash
# Start a proxy and print the details
python -m v2ray2proxy "vmess://..."

# Test the proxy after starting
python -m v2ray2proxy "vmess://..." --test

# Specify custom ports
python -m v2ray2proxy "vmess://..." --http-port 8080 --socks-port 1080

# Start a proxy pool with multiple instances of the same link
python -m v2ray2proxy "vmess://..." --pool --pool-size 3
```

## Supported Link Types

- **VMess**: `vmess://...` - V2Ray's VMess protocol
- **VLESS**: `vless://...` - V2Ray's VLESS protocol
- **Shadowsocks**: `ss://...` - Shadowsocks protocol
- **Trojan**: `trojan://...` - Trojan protocol

## Requirements

- Python 3.9+
- No external V2Ray installation needed (automatically downloaded)

## Advanced Usage

### Custom Ports

```python
from v2ray2proxy import V2RayProxy

# Specify custom ports
proxy = V2RayProxy(
    "vmess://...",
    http_port=8080,
    socks_port=1080
)
```

### Checking Proxy Health

```python
from v2ray2proxy import V2RayPool

pool = V2RayPool(v2ray_links=["vmess://...", "vmess://..."])

# Check health of all proxies
health_status = pool.check_health()
print(health_status)

# Automatically restart unhealthy proxies
pool.auto_failover()
```

### Configuration Only Mode

If you only want to generate the configuration without starting the proxy:

```python
from v2ray2proxy import V2RayProxy
import json

proxy = V2RayProxy("vmess://...", config_only=True)

# Get the V2Ray configuration
config = proxy.generate_config()
print(json.dumps(config, indent=2))

# Create the config file
config_path = proxy.create_config_file()
print(f"Config file created at: {config_path}")
```

## Some thoughts

Each v2ray instance eats about ~17MB of RAM on Linux, under 10MB on W11

## License

MIT
