from contextlib import contextmanager
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .base_proxy import BaseV2RayProxy

class V2RayProxy(BaseV2RayProxy):
    """
    Synchronous V2Ray proxy for use with requests.
    """
    
    @property
    def requests_proxies(self):
        """Get a dictionary of proxies for use with requests."""
        return {
            "http": self.socks5_proxy_url,
            "https": self.socks5_proxy_url
        }
    
    @contextmanager
    def session(self, retries=3, backoff_factor=0.3):
        """
        Create a requests Session that uses this proxy.
        
        Args:
            retries (int): Number of retries for failed requests
            backoff_factor (float): Backoff factor for retries
            
        Yields:
            requests.Session: A configured requests session
        """
        session = requests.Session()
        retry = Retry(
            total=retries,
            backoff_factor=backoff_factor,
            status_forcelist=[500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.proxies.update(self.requests_proxies)
        
        try:
            yield session
        finally:
            session.close()
    
    def test(self, url="https://api.ipify.org?format=json", timeout=10):
        """
        Test the proxy by making a request through it.
        
        Args:
            url (str): URL to test with
            timeout (int): Request timeout in seconds
            
        Returns:
            dict: Response data or error information
        """
        try:
            with self.session() as session:
                response = session.get(url, timeout=timeout)
                if response.status_code == 200:
                    return {
                        "success": True,
                        "status_code": response.status_code,
                        "data": response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
                    }
                else:
                    return {
                        "success": False,
                        "status_code": response.status_code,
                        "error": f"Request failed with status code {response.status_code}"
                    }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
