import asyncio
import aiohttp
from contextlib import asynccontextmanager

from .base_proxy import BaseV2RayProxy

class AsyncV2RayProxy(BaseV2RayProxy):
    """
    Asynchronous V2Ray proxy for use with aiohttp.
    """
    
    @staticmethod
    async def create(v2ray_link, port=None, socks_port=None, http_port=None,
                     initialization_timeout=2, config_only=False):
        """
        Create an AsyncV2RayProxy instance asynchronously.
        
        Args:
            Same as BaseV2RayProxy.__init__
            
        Returns:
            AsyncV2RayProxy: Initialized proxy instance
        """
        proxy = AsyncV2RayProxy(
            v2ray_link, port, socks_port, http_port,
            initialization_timeout, config_only=True
        )
        
        # Run start in the event loop
        if not config_only:
            # Create config file (synchronous operation)
            proxy.create_config_file()
            
            # Start V2Ray process
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, proxy._start_process)
        
        return proxy
    
    def _start_process(self):
        """Internal method to start the V2Ray process (for use with run_in_executor)."""
        super().start()
    
    @property
    def aiohttp_proxy_url(self):
        """Get the proxy URL for aiohttp."""
        return self.socks5_proxy_url
    
    @asynccontextmanager
    async def aiohttp_session(self, **kwargs):
        """
        Create an aiohttp ClientSession that uses this proxy.
        
        Args:
            **kwargs: Additional arguments for aiohttp.ClientSession
            
        Yields:
            aiohttp.ClientSession: A configured aiohttp session
        """
        conn = aiohttp.TCPConnector(ssl=False)
        session = aiohttp.ClientSession(
            connector=conn,
            **kwargs
        )
        
        try:
            yield session
        finally:
            await session.close()
    
    async def test(self, url="https://api.ipify.org?format=json", timeout=10):
        """
        Test the proxy by making a request through it.
        
        Args:
            url (str): URL to test with
            timeout (int): Request timeout in seconds
            
        Returns:
            dict: Response data or error information
        """
        try:
            async with self.aiohttp_session() as session:
                async with session.get(
                    url, 
                    timeout=timeout,
                    proxy=self.aiohttp_proxy_url
                ) as response:
                    if response.status == 200:
                        content_type = response.headers.get('Content-Type', '')
                        if 'application/json' in content_type:
                            data = await response.json()
                        else:
                            data = await response.text()
                            
                        return {
                            "success": True,
                            "status_code": response.status,
                            "data": data
                        }
                    else:
                        return {
                            "success": False,
                            "status_code": response.status,
                            "error": f"Request failed with status code {response.status}"
                        }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
