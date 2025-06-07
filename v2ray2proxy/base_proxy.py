import json
import tempfile
import os
import time
import subprocess
import random
import atexit
import logging
import base64
import uuid
import re
import urllib.parse
from contextlib import contextmanager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("v2ray2proxy")

class BaseV2RayProxy:
    """Base class for managing V2Ray processes."""
    
    def __init__(self, v2ray_link, port=None, socks_port=None, http_port=None, 
                 initialization_timeout=2, config_only=False):
        """
        Initialize a V2Ray proxy instance.
        
        Args:
            v2ray_link (str): V2Ray configuration link (vmess://, vless://, ss://, etc.)
            port (int, optional): Port for V2Ray to listen on. Random if not specified.
            socks_port (int, optional): Separate port for SOCKS protocol. Same as port if not specified.
            http_port (int, optional): Separate port for HTTP protocol. Same as port if not specified.
            initialization_timeout (int, optional): Time to wait for V2Ray to initialize in seconds.
            config_only (bool, optional): If True, only generate config but don't start V2Ray.
        """
        self.v2ray_link = v2ray_link
        self.port = port or random.randint(10000, 60000)
        self.socks_port = socks_port or self.port
        self.http_port = http_port or self.port
        self.initialization_timeout = initialization_timeout
        self.config_only = config_only
        
        self.v2ray_process = None
        self.config_file_path = None
        self.running = False
        
        # Register cleanup on exit
        atexit.register(self.stop)
        
        # Start V2Ray if not in config_only mode
        if not config_only:
            self.start()
    
    def _parse_vmess_link(self, link):
        """Parse a VMess link into a V2Ray configuration."""
        if not link.startswith("vmess://"):
            raise ValueError("Not a valid VMess link")
        
        try:
            # Remove "vmess://" and decode the base64 content
            b64_content = link[8:]
            decoded_content = base64.b64decode(b64_content).decode('utf-8')
            vmess_info = json.loads(decoded_content)
            
            # Create outbound configuration
            outbound = {
                "protocol": "vmess",
                "settings": {
                    "vnext": [{
                        "address": vmess_info.get("add", ""),
                        "port": int(vmess_info.get("port", 0)),
                        "users": [{
                            "id": vmess_info.get("id", ""),
                            "alterId": int(vmess_info.get("aid", 0)),
                            "security": vmess_info.get("scy", "auto"),
                            "level": 0
                        }]
                    }]
                },
                "streamSettings": {
                    "network": vmess_info.get("net", "tcp"),
                    "security": vmess_info.get("tls", "none")
                }
            }
            
            # Handle TLS settings
            if vmess_info.get("tls") == "tls":
                outbound["streamSettings"]["tlsSettings"] = {
                    "serverName": vmess_info.get("host", vmess_info.get("sni", ""))
                }
            
            # Handle WebSocket settings
            if vmess_info.get("net") == "ws":
                outbound["streamSettings"]["wsSettings"] = {
                    "path": vmess_info.get("path", "/"),
                    "headers": {
                        "Host": vmess_info.get("host", "")
                    }
                }
            
            return outbound
        except Exception as e:
            logger.error(f"Failed to parse VMess link: {str(e)}")
            raise ValueError(f"Invalid VMess format: {str(e)}")
    
    def _parse_vless_link(self, link):
        """Parse a VLESS link into a V2Ray configuration."""
        if not link.startswith("vless://"):
            raise ValueError("Not a valid VLESS link")
        
        try:
            # Format: vless://uuid@host:port?param=value&param2=value2#remark
            parsed_url = urllib.parse.urlparse(link)
            
            # Extract user info (uuid)
            user_info = parsed_url.netloc.split('@')[0]
            
            # Extract host and port
            host_port = parsed_url.netloc.split('@')[1]
            host, port = host_port.split(':')
            
            # Parse query parameters
            params = dict(urllib.parse.parse_qsl(parsed_url.query))
            
            # Create outbound configuration
            outbound = {
                "protocol": "vless",
                "settings": {
                    "vnext": [{
                        "address": host,
                        "port": int(port),
                        "users": [{
                            "id": user_info,
                            "encryption": "none",
                            "level": 0
                        }]
                    }]
                },
                "streamSettings": {
                    "network": params.get("type", "tcp"),
                    "security": params.get("security", "none")
                }
            }
            
            # Handle TLS settings
            if params.get("security") == "tls":
                outbound["streamSettings"]["tlsSettings"] = {
                    "serverName": params.get("sni", "")
                }
            
            # Handle WebSocket settings
            if params.get("type") == "ws":
                outbound["streamSettings"]["wsSettings"] = {
                    "path": params.get("path", "/"),
                    "headers": {
                        "Host": params.get("host", "")
                    }
                }
            
            return outbound
        except Exception as e:
            logger.error(f"Failed to parse VLESS link: {str(e)}")
            raise ValueError(f"Invalid VLESS format: {str(e)}")
    
    def _parse_shadowsocks_link(self, link):
        """Parse a Shadowsocks link into a V2Ray configuration."""
        if not link.startswith("ss://"):
            raise ValueError("Not a valid Shadowsocks link")
        
        try:
            # Two possible formats:
            # 1. ss://base64(method:password@host:port)#remark
            # 2. ss://base64(method:password)@host:port#remark
            
            parsed_url = urllib.parse.urlparse(link)
            
            if '@' in parsed_url.netloc:
                # Format 2
                user_info_b64, host_port = parsed_url.netloc.split('@', 1)
                user_info = base64.b64decode(user_info_b64).decode('utf-8')
                method, password = user_info.split(':', 1)
                host, port = host_port.split(':', 1)
            else:
                # Format 1
                decoded = base64.b64decode(parsed_url.netloc).decode('utf-8')
                method_pass, host_port = decoded.split('@', 1)
                method, password = method_pass.split(':', 1)
                host, port = host_port.split(':', 1)
            
            # Create outbound configuration
            outbound = {
                "protocol": "shadowsocks",
                "settings": {
                    "servers": [{
                        "address": host,
                        "port": int(port),
                        "method": method,
                        "password": password
                    }]
                }
            }
            
            return outbound
        except Exception as e:
            logger.error(f"Failed to parse Shadowsocks link: {str(e)}")
            raise ValueError(f"Invalid Shadowsocks format: {str(e)}")
    
    def _parse_trojan_link(self, link):
        """Parse a Trojan link into a V2Ray configuration."""
        if not link.startswith("trojan://"):
            raise ValueError("Not a valid Trojan link")
        
        try:
            # Format: trojan://password@host:port?param=value&param2=value2#remark
            parsed_url = urllib.parse.urlparse(link)
            
            # Extract password
            password = parsed_url.netloc.split('@')[0]
            
            # Extract host and port
            host_port = parsed_url.netloc.split('@')[1]
            host, port = host_port.split(':')
            
            # Parse query parameters
            params = dict(urllib.parse.parse_qsl(parsed_url.query))
            
            # Create outbound configuration
            outbound = {
                "protocol": "trojan",
                "settings": {
                    "servers": [{
                        "address": host,
                        "port": int(port),
                        "password": password
                    }]
                },
                "streamSettings": {
                    "network": params.get("type", "tcp"),
                    "security": "tls",
                    "tlsSettings": {
                        "serverName": params.get("sni", host)
                    }
                }
            }
            
            return outbound
        except Exception as e:
            logger.error(f"Failed to parse Trojan link: {str(e)}")
            raise ValueError(f"Invalid Trojan format: {str(e)}")
    
    def generate_config(self):
        """Generate V2Ray configuration from link."""
        try:
            # Determine the type of link and parse accordingly
            if self.v2ray_link.startswith("vmess://"):
                outbound = self._parse_vmess_link(self.v2ray_link)
            elif self.v2ray_link.startswith("vless://"):
                outbound = self._parse_vless_link(self.v2ray_link)
            elif self.v2ray_link.startswith("ss://"):
                outbound = self._parse_shadowsocks_link(self.v2ray_link)
            elif self.v2ray_link.startswith("trojan://"):
                outbound = self._parse_trojan_link(self.v2ray_link)
            else:
                raise ValueError(f"Unsupported link type: {self.v2ray_link[:10]}...")
            
            # Create a basic V2Ray configuration with SOCKS and HTTP inbounds
            config = {
                "inbounds": [
                    {
                        "port": self.socks_port,
                        "protocol": "socks",
                        "settings": {
                            "udp": True
                        }
                    },
                    {
                        "port": self.http_port,
                        "protocol": "http"
                    }
                ],
                "outbounds": [outbound]
            }
            
            return config
        except Exception as e:
            logger.error(f"Error generating config: {str(e)}")
            raise
    
    def create_config_file(self):
        """Create a temporary file with the V2Ray configuration."""
        config = self.generate_config()
        
        # Create a temporary file for the configuration
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as temp_file:
            temp_file_path = temp_file.name
            temp_file.write(json.dumps(config).encode('utf-8'))
        
        self.config_file_path = temp_file_path
        return temp_file_path
    
    def start(self):
        """Start the V2Ray process with the generated configuration."""
        if self.running:
            logger.warning("V2Ray process is already running")
            return
        
        try:
            # Create config file
            config_path = self.create_config_file()
            
            # Start v2ray with this configuration
            self.v2ray_process = subprocess.Popen(
                ['v2ray', '-config', config_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Wait for v2ray to initialize
            time.sleep(self.initialization_timeout)
            
            # Check if v2ray is still running
            if self.v2ray_process.poll() is not None:
                stdout, stderr = self.v2ray_process.communicate()
                logger.error(f"Error starting V2Ray: {stderr.decode('utf-8')}")
                raise RuntimeError(f"Failed to start V2Ray. Exit code: {self.v2ray_process.returncode}")
            
            self.running = True
            logger.info(f"V2Ray started on SOCKS port {self.socks_port}, HTTP port {self.http_port}")
            
        except Exception as e:
            logger.error(f"Error starting V2Ray: {str(e)}")
            self.cleanup()
            raise
    
    def stop(self):
        """Stop the V2Ray process and clean up resources."""
        if not self.running or self.v2ray_process is None:
            return
        
        try:
            self.v2ray_process.terminate()
            try:
                self.v2ray_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.v2ray_process.kill()
            
            self.running = False
            logger.info("V2Ray process stopped")
        except Exception as e:
            logger.error(f"Error stopping V2Ray: {str(e)}")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Clean up temporary files."""
        if self.config_file_path and os.path.exists(self.config_file_path):
            try:
                os.unlink(self.config_file_path)
                self.config_file_path = None
            except Exception as e:
                logger.error(f"Error removing config file: {str(e)}")
    
    @property
    def socks5_proxy_url(self):
        """Get the SOCKS5 proxy URL."""
        return f"socks5://127.0.0.1:{self.socks_port}"
    
    @property
    def http_proxy_url(self):
        """Get the HTTP proxy URL."""
        return f"http://127.0.0.1:{self.http_port}"
    
    def __del__(self):
        """Ensure resources are cleaned up when the object is garbage collected."""
        self.stop()
