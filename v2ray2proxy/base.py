import json
import tempfile
import os
import time
import subprocess
import random
import atexit
import logging
import base64
import urllib.parse
import socket
import signal
import threading


class V2RayCore:
    """Represents executable of V2Ray core."""

    def __init__(self):
        self.release_tag_url = os.environ.get("V2RAY_RELASE_TAG_URL") or "https://github.com/v2fly/v2ray-core/releases/download/v4.31.0"
        if os.environ.get("V2RAY_EXECUTABLE_DIR"):
            self.executable_dir = os.environ["V2RAY_EXECUTABLE_DIR"]
            self.executable = os.path.join(self.executable_dir, "v2ray.exe" if os.name == "nt" else "v2ray")
        if not os.environ.get("V2RAY_EXECUTABLE_DIR") or not os.path.isdir(self.executable_dir):
            logging.info("V2Ray executable directory not found in environment variable, using default...")
            self.executable_dir = self._download_executables()
            self.executable = os.path.join(self.executable_dir, "v2ray.exe" if os.name == "nt" else "v2ray")
        if not os.path.isfile(self.executable):
            raise RuntimeError(f"V2Ray executable not found at {self.executable}")
        logging.info(f"V2Ray executable found at {self.executable}")

    def _download_executables(self):
        """Download and set up V2Ray executables for the current platform."""
        import platform
        import zipfile
        import urllib.request
        import stat
        from pathlib import Path

        # Create a directory to store V2Ray
        home_dir = Path.home()
        v2ray_dir = home_dir / ".v2ray"
        v2ray_dir.mkdir(exist_ok=True)

        # Determine the executable name based on OS
        system = platform.system().lower()
        if system == "windows":
            executable_name = "v2ray.exe"
            ctl_name = "v2ctl.exe"
        else:
            executable_name = "v2ray"
            ctl_name = "v2ctl"

        # Check if the executable and v2ctl already exist
        v2ray_executable = v2ray_dir / executable_name
        v2ctl_executable = v2ray_dir / ctl_name

        if v2ray_executable.exists() and v2ctl_executable.exists():
            logging.info(f"V2Ray executables already exist at {v2ray_dir}")
            return str(v2ray_dir)

        # Determine the current OS and architecture
        machine = platform.machine().lower()

        # Map the OS and architecture to the appropriate download file
        download_file = None

        # Windows mapping
        if system == "windows":
            if machine == "amd64" or machine == "x86_64":
                download_file = "v2ray-windows-64.zip"
            elif machine == "x86" or machine == "i386":
                download_file = "v2ray-windows-32.zip"
            elif "arm" in machine:
                download_file = "v2ray-windows-arm32-v7a.zip"

        # Linux mapping
        elif system == "linux":
            if machine == "x86_64" or machine == "amd64":
                download_file = "v2ray-linux-64.zip"
            elif machine == "i386" or machine == "x86":
                download_file = "v2ray-linux-32.zip"
            elif "arm" in machine:
                if "64" in machine or "v8" in machine:
                    download_file = "v2ray-linux-arm64-v8a.zip"
                elif "v7" in machine:
                    download_file = "v2ray-linux-arm32-v7a.zip"
                elif "v6" in machine:
                    download_file = "v2ray-linux-arm32-v6.zip"
                else:
                    download_file = "v2ray-linux-arm32-v5.zip"
            elif "mips" in machine:
                if "64" in machine:
                    if "le" in machine:
                        download_file = "v2ray-linux-mips64le.zip"
                    else:
                        download_file = "v2ray-linux-mips64.zip"
                else:
                    if "le" in machine:
                        download_file = "v2ray-linux-mips32le.zip"
                    else:
                        download_file = "v2ray-linux-mips32.zip"
            elif "ppc64" in machine:
                if "le" in machine:
                    download_file = "v2ray-linux-ppc64le.zip"
                else:
                    download_file = "v2ray-linux-ppc64.zip"
            elif "s390x" in machine:
                download_file = "v2ray-linux-s390x.zip"
            elif "riscv64" in machine:
                download_file = "v2ray-linux-riscv64.zip"

        # macOS mapping
        elif system == "darwin":
            download_file = "v2ray-macos-64.zip"

        # FreeBSD mapping
        elif system == "freebsd":
            if machine == "amd64" or machine == "x86_64":
                download_file = "v2ray-freebsd-64.zip"
            elif machine == "i386" or machine == "x86":
                download_file = "v2ray-freebsd-32.zip"

        # OpenBSD mapping
        elif system == "openbsd":
            if machine == "amd64" or machine == "x86_64":
                download_file = "v2ray-openbsd-64.zip"
            elif machine == "i386" or machine == "x86":
                download_file = "v2ray-openbsd-32.zip"

        # Dragonfly mapping
        elif system == "dragonfly":
            download_file = "v2ray-dragonfly-64.zip"

        if not download_file:
            raise RuntimeError(f"Unsupported platform: {system} {machine}")

        # Download the file
        release_url = f"{self.release_tag_url}/{download_file}"
        logging.info(f"Downloading V2Ray from {release_url}")

        # Create a temporary directory for the download
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            zip_path = temp_dir_path / download_file

            # Download the file
            try:
                urllib.request.urlretrieve(release_url, zip_path)
            except Exception as e:
                raise RuntimeError(f"Failed to download V2Ray: {str(e)}")

            # Extract the zip file to the v2ray directory
            try:
                logging.info(f"Extracting V2Ray package to {v2ray_dir}")
                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    # Extract all files directly to the v2ray directory
                    zip_ref.extractall(v2ray_dir)
            except Exception as e:
                raise RuntimeError(f"Failed to extract V2Ray: {str(e)}")

            # Verify main executables exist
            if not v2ray_executable.exists():
                raise RuntimeError(f"Could not find {executable_name} in the extracted files")

            if not v2ctl_executable.exists():
                logging.warning(f"Could not find {ctl_name} in the extracted files, V2Ray may not function correctly")

            # Make the files executable on Unix systems
            if system != "windows":
                for exe in [v2ray_executable, v2ctl_executable]:
                    if exe.exists():
                        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)

        logging.info(f"V2Ray installed at {v2ray_dir}")
        return str(v2ray_dir)


class V2RayProxy:
    def __init__(self, v2ray_link: str, http_port: int = None, socks_port: int = None, config_only: bool = False):
        self.v2ray_link = v2ray_link
        self.http_port = http_port or self._pick_unused_port()
        self.socks_port = socks_port or self._pick_unused_port(self.http_port)
        self.config_only = config_only

        self.v2ray_process = None
        self.config_file_path = None
        self.running = False
        self._cleanup_lock = threading.Lock()
        self._cleanup_registered = False

        # Register cleanup on exit only once
        if not self._cleanup_registered:
            atexit.register(self._safe_cleanup)
            self._cleanup_registered = True

        # Start V2Ray if not in config_only mode
        if not config_only:
            self.start()

    def _is_port_in_use(self, port: int) -> bool:
        """Check if a port is currently in use."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(("localhost", port)) == 0

    def _pick_unused_port(self, exclude_port: int = None) -> int:
        for _ in range(500):
            port = random.randint(10000, 65535)
            if not self._is_port_in_use(port) and port != exclude_port:
                return port
        raise RuntimeError("Could not find an unused port")

    def _parse_vmess_link(self, link: str) -> dict:
        """Parse a VMess link into a V2Ray configuration."""
        if not link.startswith("vmess://"):
            raise ValueError("Not a valid VMess link")

        try:
            # Remove "vmess://" and decode the base64 content
            b64_content = link[8:]
            decoded_content = base64.b64decode(b64_content).decode("utf-8")
            vmess_info = json.loads(decoded_content)

            # Create outbound configuration
            outbound = {
                "protocol": "vmess",
                "settings": {
                    "vnext": [
                        {
                            "address": vmess_info.get("add", ""),
                            "port": int(vmess_info.get("port", 0)),
                            "users": [
                                {
                                    "id": vmess_info.get("id", ""),
                                    "alterId": int(vmess_info.get("aid", 0)),
                                    "security": vmess_info.get("scy", "auto"),
                                    "level": 0,
                                }
                            ],
                        }
                    ]
                },
                "streamSettings": {"network": vmess_info.get("net", "tcp"), "security": vmess_info.get("tls", "none")},
            }

            # Handle TLS settings
            if vmess_info.get("tls") == "tls":
                outbound["streamSettings"]["tlsSettings"] = {"serverName": vmess_info.get("host", vmess_info.get("sni", ""))}

            # Handle WebSocket settings
            if vmess_info.get("net") == "ws":
                outbound["streamSettings"]["wsSettings"] = {
                    "path": vmess_info.get("path", "/"),
                    "headers": {"Host": vmess_info.get("host", "")},
                }

            return outbound
        except Exception as e:
            logging.error(f"Failed to parse VMess link: {str(e)}")
            raise ValueError(f"Invalid VMess format: {str(e)}")

    def _parse_vless_link(self, link: str) -> dict:
        """Parse a VLESS link into a V2Ray configuration."""
        if not link.startswith("vless://"):
            raise ValueError("Not a valid VLESS link")

        try:
            # Format: vless://uuid@host:port?param=value&param2=value2#remark
            parsed_url = urllib.parse.urlparse(link)

            # Extract user info (uuid)
            user_info = parsed_url.netloc.split("@")[0]

            # Extract host and port
            host_port = parsed_url.netloc.split("@")[1]
            host, port = host_port.split(":")

            # Parse query parameters
            params = dict(urllib.parse.parse_qsl(parsed_url.query))

            # Create outbound configuration
            outbound = {
                "protocol": "vless",
                "settings": {
                    "vnext": [{"address": host, "port": int(port), "users": [{"id": user_info, "encryption": "none", "level": 0}]}]
                },
                "streamSettings": {"network": params.get("type", "tcp"), "security": params.get("security", "none")},
            }

            # Handle TLS settings
            if params.get("security") == "tls":
                outbound["streamSettings"]["tlsSettings"] = {"serverName": params.get("sni", "")}

            # Handle WebSocket settings
            if params.get("type") == "ws":
                outbound["streamSettings"]["wsSettings"] = {"path": params.get("path", "/"), "headers": {"Host": params.get("host", "")}}

            return outbound
        except Exception as e:
            logging.error(f"Failed to parse VLESS link: {str(e)}")
            raise ValueError(f"Invalid VLESS format: {str(e)}")

    def _parse_shadowsocks_link(self, link: str) -> dict:
        """Parse a Shadowsocks link into a V2Ray configuration."""
        if not link.startswith("ss://"):
            raise ValueError("Not a valid Shadowsocks link")

        try:
            # Two possible formats:
            # 1. ss://base64(method:password@host:port)#remark
            # 2. ss://base64(method:password)@host:port#remark

            parsed_url = urllib.parse.urlparse(link)

            if "@" in parsed_url.netloc:
                # Format 2
                user_info_b64, host_port = parsed_url.netloc.split("@", 1)
                user_info = base64.b64decode(user_info_b64).decode("utf-8")
                method, password = user_info.split(":", 1)
                host, port = host_port.split(":", 1)
            else:
                # Format 1
                decoded = base64.b64decode(parsed_url.netloc).decode("utf-8")
                method_pass, host_port = decoded.split("@", 1)
                method, password = method_pass.split(":", 1)
                host, port = host_port.split(":", 1)

            # Create outbound configuration
            outbound = {
                "protocol": "shadowsocks",
                "settings": {"servers": [{"address": host, "port": int(port), "method": method, "password": password}]},
            }

            return outbound
        except Exception as e:
            logging.error(f"Failed to parse Shadowsocks link: {str(e)}")
            raise ValueError(f"Invalid Shadowsocks format: {str(e)}")

    def _parse_trojan_link(self, link: str) -> dict:
        """Parse a Trojan link into a V2Ray configuration."""
        if not link.startswith("trojan://"):
            raise ValueError("Not a valid Trojan link")

        try:
            # Format: trojan://password@host:port?param=value&param2=value2#remark
            parsed_url = urllib.parse.urlparse(link)

            # Extract password
            password = parsed_url.netloc.split("@")[0]

            # Extract host and port
            host_port = parsed_url.netloc.split("@")[1]
            host, port = host_port.split(":")

            # Parse query parameters
            params = dict(urllib.parse.parse_qsl(parsed_url.query))

            # Create outbound configuration
            outbound = {
                "protocol": "trojan",
                "settings": {"servers": [{"address": host, "port": int(port), "password": password}]},
                "streamSettings": {
                    "network": params.get("type", "tcp"),
                    "security": "tls",
                    "tlsSettings": {"serverName": params.get("sni", host)},
                },
            }

            return outbound
        except Exception as e:
            logging.error(f"Failed to parse Trojan link: {str(e)}")
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
                    {"port": self.socks_port, "protocol": "socks", "settings": {"udp": True}},
                    {"port": self.http_port, "protocol": "http"},
                ],
                "outbounds": [outbound],
            }

            return config
        except Exception as e:
            logging.error(f"Error generating config: {str(e)}")
            raise

    def create_config_file(self):
        """Create a temporary file with the V2Ray configuration."""
        config = self.generate_config()

        # Log the generated config for debugging
        logging.debug(f"Generated V2Ray config: {json.dumps(config, indent=2)}")

        # Create a temporary file for the configuration
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as temp_file:
            temp_file_path = temp_file.name
            json_config = json.dumps(config, indent=2)
            temp_file.write(json_config.encode("utf-8"))
            logging.debug(f"Wrote config to {temp_file_path}")

        self.config_file_path = temp_file_path
        return temp_file_path

    def _check_proxy_ready(self, timeout=15):
        """Check if the proxy ports are actually accepting connections."""
        start_time = time.time()
        last_error = None

        while time.time() - start_time < timeout:
            # First check if process is still running
            if self.v2ray_process.poll() is not None:
                stdout, stderr = self.v2ray_process.communicate()
                error_msg = (
                    f"V2Ray process terminated early. Exit code: {self.v2ray_process.returncode}\nStdout: {stdout}\nStderr: {stderr}"
                )
                logging.error(error_msg)
                raise RuntimeError(error_msg)

            try:
                # Check if the SOCKS port is accepting connections
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(1)
                    logging.debug(f"Checking SOCKS port {self.socks_port}...")
                    result = s.connect_ex(("127.0.0.1", self.socks_port))
                    if result == 0:
                        # Check if the HTTP port is also accepting connections
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s2:
                            s2.settimeout(1)
                            logging.debug(f"Checking HTTP port {self.http_port}...")
                            result2 = s2.connect_ex(("127.0.0.1", self.http_port))
                            if result2 == 0:
                                logging.info("V2Ray proxy is ready and accepting connections")
                                return True
            except Exception as e:
                last_error = str(e)
                logging.debug(f"Proxy not ready yet: {last_error}")

            time.sleep(1)

        # If we get here, the proxy didn't become ready in time
        if self.v2ray_process.poll() is not None:
            stdout, stderr = self.v2ray_process.communicate()
            error_msg = f"V2Ray process terminated during initialization. Exit code: {self.v2ray_process.returncode}\nStdout: {stdout}\nStderr: {stderr}"
        else:
            error_msg = f"Proxy failed to become ready within {timeout} seconds. Last error: {last_error}"

            # Try to read process output without terminating it
            try:
                # Check if there's any output available
                if self.v2ray_process.stdout.readable():
                    stdout = self.v2ray_process.stdout.read(1024)
                    if stdout:
                        error_msg += f"\nStdout (partial): {stdout}"

                if self.v2ray_process.stderr.readable():
                    stderr = self.v2ray_process.stderr.read(1024)
                    if stderr:
                        error_msg += f"\nStderr (partial): {stderr}"
            except Exception as e:
                error_msg += f"\nCould not read process output: {e}"

        logging.error(error_msg)
        raise TimeoutError(error_msg)

    def start(self):
        """Start the V2Ray process with the generated configuration."""
        if self.running:
            logging.warning("V2Ray process is already running")
            return

        try:
            # Create config file
            config_path = self.create_config_file()

            # Verify executable exists and is accessible
            v2ray_exe = V2RayCore().executable
            if not os.path.isfile(v2ray_exe):
                raise FileNotFoundError(f"V2Ray executable not found at {v2ray_exe}")

            if os.name == "posix" and not os.access(v2ray_exe, os.X_OK):
                raise PermissionError(f"V2Ray executable {v2ray_exe} is not executable")

            # Use shell=True on Windows to avoid path issues
            use_shell = os.name == "nt"

            # Log the exact command being executed
            cmd = [v2ray_exe, "-config", config_path]
            logging.info(f"Starting V2Ray with command: {' '.join(cmd)}")

            # Start v2ray with this configuration
            self.v2ray_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=use_shell,
                universal_newlines=True,  # Use text mode for output
            )

            # Wait a brief moment to see if process terminates immediately
            time.sleep(0.5)

            # Check if v2ray is still running
            if self.v2ray_process.poll() is not None:
                stdout, stderr = self.v2ray_process.communicate()
                error_msg = f"V2Ray exited with code {self.v2ray_process.returncode}.\nStdout: {stdout}\nStderr: {stderr}"
                logging.error(error_msg)

                # Try to read and log the config file
                try:
                    with open(config_path, "r") as f:
                        logging.error(f"Config file content: {f.read()}")
                except Exception as e:
                    logging.error(f"Unable to read config file: {e}")

                raise RuntimeError(f"Failed to start V2Ray: {error_msg}")

            # Wait for the proxy to become ready
            try:
                self._check_proxy_ready(timeout=15)
                self.running = True
                logging.info(f"V2Ray started successfully on SOCKS port {self.socks_port}, HTTP port {self.http_port}")
            except Exception:
                # If checking fails, terminate the process and raise the exception
                self.v2ray_process.terminate()
                try:
                    stdout, stderr = self.v2ray_process.communicate(timeout=5)
                    logging.error(f"V2Ray output after failed start: Stdout: {stdout}, Stderr: {stderr}")
                except Exception:
                    pass
                raise

        except Exception as e:
            logging.error(f"Error starting V2Ray: {str(e)}")
            self.cleanup()
            raise

    def _terminate_process(self, timeout=10):
        """
        Safely terminate the V2Ray process with platform-specific handling.

        Args:
            timeout (int): Maximum time to wait for process to terminate

        Returns:
            bool: True if process was terminated successfully
        """
        if self.v2ray_process is None:
            return True

        try:
            # Check if process is already terminated
            if self.v2ray_process.poll() is not None:
                return True

            logging.info(f"Terminating V2Ray process (PID: {self.v2ray_process.pid})")

            # Platform-specific termination
            if os.name == "nt":  # Windows
                # Use taskkill on Windows for more reliable termination
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(self.v2ray_process.pid)], check=False, capture_output=True, timeout=5
                    )
                    # Wait a bit for process to terminate
                    time.sleep(0.5)
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    # Fall back to terminate if taskkill fails
                    try:
                        self.v2ray_process.terminate()
                        time.sleep(0.5)
                        if self.v2ray_process.poll() is None:
                            self.v2ray_process.kill()
                    except ProcessLookupError:
                        pass  # Process already terminated
            else:  # Unix-like systems
                try:
                    # Send SIGTERM first
                    self.v2ray_process.terminate()

                    # Wait for graceful shutdown
                    try:
                        self.v2ray_process.wait(timeout=timeout // 2)
                        return True
                    except subprocess.TimeoutExpired:
                        logging.warning("V2Ray process did not terminate gracefully, sending SIGKILL")
                        # Force kill if graceful termination fails
                        self.v2ray_process.kill()
                        self.v2ray_process.wait(timeout=2)
                except ProcessLookupError:
                    # Process already terminated
                    return True

            # Final check if process terminated
            start_time = time.time()
            while time.time() - start_time < timeout:
                if self.v2ray_process.poll() is not None:
                    logging.info("V2Ray process terminated successfully")
                    return True
                time.sleep(0.1)

            logging.error(f"Failed to terminate V2Ray process within {timeout} seconds")
            return False

        except Exception as e:
            logging.error(f"Error terminating V2Ray process: {str(e)}")
            return False

    def _safe_cleanup(self):
        """Thread-safe cleanup method."""
        with self._cleanup_lock:
            self._cleanup_internal()

    def _cleanup_internal(self):
        """Internal cleanup method - should only be called while holding the lock."""
        # Clean up temporary files
        if self.config_file_path:
            try:
                if os.path.exists(self.config_file_path):
                    os.unlink(self.config_file_path)
                    logging.debug(f"Removed config file: {self.config_file_path}")
            except Exception as e:
                logging.warning(f"Failed to remove config file {self.config_file_path}: {str(e)}")
            finally:
                self.config_file_path = None

        # Reset process reference
        self.v2ray_process = None
        self.running = False

    def stop(self):
        """Stop the V2Ray process and clean up resources."""
        with self._cleanup_lock:
            if not self.running and self.v2ray_process is None:
                return

            try:
                # Terminate the process
                if self.v2ray_process is not None:
                    success = self._terminate_process(timeout=5)  # Reduced timeout for faster cleanup
                    if not success:
                        logging.warning("V2Ray process may not have terminated cleanly")

                self.running = False
                logging.info("V2Ray process stopped")

            except Exception as e:
                logging.error(f"Error stopping V2Ray: {str(e)}")
            finally:
                # Always clean up resources
                self._cleanup_internal()

    def cleanup(self):
        """Clean up temporary files and resources."""
        self._safe_cleanup()

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
        try:
            self._safe_cleanup()
        except Exception as e:
            # Avoid raising exceptions in __del__
            logging.warning(f"Error during V2RayProxy cleanup: {str(e)}")


class V2RayPool:
    """Manages a pool of V2Ray proxy instances for load balancing and failover."""

    def __init__(self, v2ray_links=None, http_port=None, socks_port=None, max_size=None):
        """
        Initialize a pool of V2Ray proxies.

        Args:
            v2ray_links (list, optional): Initial list of V2Ray links to add to the pool.
            http_port (int, optional): Starting HTTP port. If not provided, random ports will be assigned.
            socks_port (int, optional): Starting SOCKS port. If not provided, random ports will be assigned.
            max_size (int, optional): Maximum number of proxies in the pool. None means unlimited.
        """
        self.proxies = {}  # Map of ID -> V2RayProxy object
        self.active_proxies = set()  # Set of active proxy IDs
        self.current_index = 0  # For round-robin selection
        self.max_size = max_size
        self.http_port = http_port
        self.socks_port = socks_port
        self.next_id = 1  # For generating unique IDs

        # Add initial proxies if provided
        if v2ray_links:
            for link in v2ray_links:
                self.add_proxy(link)

    def add_proxy(self, v2ray_link, start=True):
        """
        Add a new V2Ray proxy to the pool.

        Args:
            v2ray_link (str): V2Ray link to add.
            start (bool): Whether to start the proxy immediately.

        Returns:
            int: ID of the added proxy.
        """
        # Check if we've reached max size
        if self.max_size and len(self.proxies) >= self.max_size:
            raise ValueError(f"Pool has reached maximum size of {self.max_size}")

        proxy_id = self.next_id
        self.next_id += 1

        # Calculate ports if sequential ports are requested
        http_port = None
        socks_port = None
        if self.http_port:
            http_port = self.http_port + (proxy_id - 1) * 2
        if self.socks_port:
            socks_port = self.socks_port + (proxy_id - 1) * 2

        # Create a new proxy
        try:
            proxy = V2RayProxy(v2ray_link, http_port=http_port, socks_port=socks_port, config_only=not start)
            self.proxies[proxy_id] = proxy

            if start:
                self.active_proxies.add(proxy_id)

            return proxy_id
        except Exception as e:
            logging.error(f"Failed to add proxy: {str(e)}")
            raise

    def remove_proxy(self, proxy_id):
        """
        Remove a proxy from the pool.

        Args:
            proxy_id (int): ID of the proxy to remove.
        """
        if proxy_id not in self.proxies:
            raise ValueError(f"Proxy with ID {proxy_id} not found in pool")

        # Stop the proxy if it's running
        try:
            self.proxies[proxy_id].stop()
        except Exception as e:
            logging.error(f"Error stopping proxy {proxy_id} during removal: {str(e)}")

        # Remove from active proxies set
        if proxy_id in self.active_proxies:
            self.active_proxies.remove(proxy_id)

        # Remove from proxies dict
        del self.proxies[proxy_id]

    def start_proxy(self, proxy_id):
        """
        Start a proxy in the pool.

        Args:
            proxy_id (int): ID of the proxy to start.
        """
        if proxy_id not in self.proxies:
            raise ValueError(f"Proxy with ID {proxy_id} not found in pool")

        try:
            self.proxies[proxy_id].start()
            self.active_proxies.add(proxy_id)
        except Exception as e:
            logging.error(f"Failed to start proxy {proxy_id}: {str(e)}")
            raise

    def stop_proxy(self, proxy_id):
        """
        Stop a proxy in the pool.

        Args:
            proxy_id (int): ID of the proxy to stop.
        """
        if proxy_id not in self.proxies:
            raise ValueError(f"Proxy with ID {proxy_id} not found in pool")

        try:
            self.proxies[proxy_id].stop()
        except Exception as e:
            logging.error(f"Error stopping proxy {proxy_id}: {str(e)}")

        if proxy_id in self.active_proxies:
            self.active_proxies.remove(proxy_id)

    def start_all(self):
        """Start all proxies in the pool."""
        for proxy_id, proxy in self.proxies.items():
            if proxy_id not in self.active_proxies:
                try:
                    proxy.start()
                    self.active_proxies.add(proxy_id)
                except Exception as e:
                    logging.error(f"Failed to start proxy {proxy_id}: {str(e)}")

    def stop_all(self):
        """Stop all proxies in the pool."""
        errors = []
        for proxy_id in list(self.active_proxies):
            try:
                self.proxies[proxy_id].stop()
            except Exception as e:
                error_msg = f"Error stopping proxy {proxy_id}: {str(e)}"
                logging.error(error_msg)
                errors.append(error_msg)

        self.active_proxies.clear()

        if errors:
            logging.warning(f"Encountered {len(errors)} errors while stopping proxies")

    def restart_proxy(self, proxy_id):
        """
        Restart a specific proxy.

        Args:
            proxy_id (int): ID of the proxy to restart.
        """
        if proxy_id not in self.proxies:
            raise ValueError(f"Proxy with ID {proxy_id} not found in pool")

        try:
            # Stop the proxy
            self.proxies[proxy_id].stop()

            # Wait a bit to ensure clean shutdown
            time.sleep(1)

            # Start the proxy again
            self.proxies[proxy_id].start()

            if proxy_id not in self.active_proxies:
                self.active_proxies.add(proxy_id)

            return True
        except Exception as e:
            logging.error(f"Failed to restart proxy {proxy_id}: {str(e)}")
            if proxy_id in self.active_proxies:
                self.active_proxies.remove(proxy_id)
            return False

    def get_proxy(self, strategy="round-robin"):
        """
        Get a proxy from the pool using the specified strategy.

        Args:
            strategy (str): Strategy for selecting a proxy:
                            "round-robin": Rotate through proxies in sequence
                            "random": Select a random proxy
                            "least-latency": Select the proxy with the lowest latency

        Returns:
            V2RayProxy: A proxy instance, or None if no proxies are available.
        """
        if not self.active_proxies:
            return None

        active_ids = list(self.active_proxies)

        if strategy == "round-robin":
            # Round-robin selection
            if self.current_index >= len(active_ids):
                self.current_index = 0

            proxy_id = active_ids[self.current_index]
            self.current_index += 1
            return self.proxies[proxy_id]

        elif strategy == "random":
            # Random selection
            proxy_id = random.choice(active_ids)
            return self.proxies[proxy_id]

        elif strategy == "least-latency":
            # Select proxy with lowest latency
            latencies = self.measure_latencies()
            if not latencies:
                return self.get_proxy(strategy="round-robin")

            best_id = min(latencies, key=latencies.get)
            return self.proxies[best_id]

        else:
            raise ValueError(f"Unknown selection strategy: {strategy}")

    def measure_latencies(self, target="https://www.google.com", timeout=5):
        """
        Measure the latency of each active proxy.

        Args:
            target (str): URL to measure latency to.
            timeout (int): Timeout in seconds.

        Returns:
            dict: Map of proxy ID to latency in seconds. Failed proxies are not included.
        """
        import requests
        from requests.exceptions import RequestException

        latencies = {}

        for proxy_id in self.active_proxies:
            proxy = self.proxies[proxy_id]
            proxies = {"http": proxy.http_proxy_url, "https": proxy.http_proxy_url}

            try:
                start_time = time.time()
                response = requests.get(target, proxies=proxies, timeout=timeout)
                end_time = time.time()

                if response.status_code == 200:
                    latency = end_time - start_time
                    latencies[proxy_id] = latency
                    # Update proxy's last known latency
                    proxy.last_latency = latency
                    proxy.last_check_time = end_time
            except RequestException as e:
                logging.warning(f"Failed to measure latency for proxy {proxy_id}: {str(e)}")
                # Mark as failed for monitoring purposes
                proxy.last_error = str(e)
                proxy.last_error_time = time.time()

        return latencies

    def check_health(self, target="https://www.google.com", timeout=5):
        """
        Check the health of all proxies in the pool.

        Args:
            target (str): URL to check connectivity.
            timeout (int): Timeout in seconds.

        Returns:
            dict: Map of proxy ID to health status (True/False).
        """
        import requests
        from requests.exceptions import RequestException

        health = {}

        for proxy_id in self.active_proxies:
            proxy = self.proxies[proxy_id]
            proxies = {"http": proxy.http_proxy_url, "https": proxy.http_proxy_url}

            try:
                response = requests.get(target, proxies=proxies, timeout=timeout)
                health[proxy_id] = response.status_code == 200

                # Clear any previous error state if successful
                if health[proxy_id]:
                    proxy.last_error = None
                    proxy.last_error_time = None
                    proxy.last_check_time = time.time()
            except RequestException as e:
                health[proxy_id] = False
                # Update error state
                proxy.last_error = str(e)
                proxy.last_error_time = time.time()
                logging.warning(f"Health check failed for proxy {proxy_id}: {str(e)}")

        return health

    def get_status(self):
        """
        Get the status of all proxies in the pool.

        Returns:
            dict: Map of proxy ID to status information.
        """
        status = {}

        for proxy_id, proxy in self.proxies.items():
            status[proxy_id] = {
                "active": proxy_id in self.active_proxies,
                "http_port": proxy.http_port,
                "socks_port": proxy.socks_port,
                "http_proxy_url": proxy.http_proxy_url,
                "socks5_proxy_url": proxy.socks5_proxy_url,
                "last_latency": getattr(proxy, "last_latency", None),
                "last_error": getattr(proxy, "last_error", None),
                "last_error_time": getattr(proxy, "last_error_time", None),
                "last_check_time": getattr(proxy, "last_check_time", None),
            }

        return status

    def get_proxy_by_id(self, proxy_id):
        """
        Get a specific proxy by its ID.

        Args:
            proxy_id (int): ID of the proxy to get.

        Returns:
            V2RayProxy: The requested proxy or None if not found.
        """
        return self.proxies.get(proxy_id)

    def get_proxy_count(self):
        """
        Get the count of proxies in the pool.

        Returns:
            tuple: (total_count, active_count)
        """
        return len(self.proxies), len(self.active_proxies)

    def auto_failover(self, target="https://www.google.com", timeout=5):
        """
        Check health of all proxies and restart failed ones.

        Returns:
            dict: Results of health checks and restart attempts.
        """
        results = {}
        health = self.check_health(target=target, timeout=timeout)

        for proxy_id, is_healthy in health.items():
            if not is_healthy:
                logging.info(f"Auto-failover: Restarting unhealthy proxy {proxy_id}")
                restart_success = self.restart_proxy(proxy_id)
                results[proxy_id] = {"was_healthy": False, "restart_attempted": True, "restart_successful": restart_success}
            else:
                results[proxy_id] = {"was_healthy": True, "restart_attempted": False}

        return results

    def http_proxy_url(self, strategy="round-robin"):
        """
        Get the HTTP proxy URL using the specified strategy.

        Args:
            strategy (str): Proxy selection strategy.

        Returns:
            str: HTTP proxy URL or None if no proxy is available.
        """
        proxy = self.get_proxy(strategy=strategy)
        if proxy:
            return proxy.http_proxy_url
        return None

    def socks5_proxy_url(self, strategy="round-robin"):
        """
        Get the SOCKS5 proxy URL using the specified strategy.

        Args:
            strategy (str): Proxy selection strategy.

        Returns:
            str: SOCKS5 proxy URL or None if no proxy is available.
        """
        proxy = self.get_proxy(strategy=strategy)
        if proxy:
            return proxy.socks5_proxy_url
        return None

    def get_fastest_proxy(self, count=None, timeout=5):
        """
        Get the fastest proxy from the pool by measuring latencies.

        Args:
            count (int, optional): Number of proxies to test. If None, test all active proxies.
            timeout (int): Timeout in seconds for latency measurement.

        Returns:
            V2RayProxy: The fastest proxy, or None if no proxies are available or all fail.
        """
        if not self.active_proxies:
            return None

        # Determine which proxies to test
        active_ids = list(self.active_proxies)
        
        if count is not None and count > 0:
            # Test only a subset of proxies (randomly selected)
            test_count = min(count, len(active_ids))
            test_ids = random.sample(active_ids, test_count)
        else:
            # Test all active proxies
            test_ids = active_ids

        # Measure latencies for selected proxies
        latencies = {}
        for proxy_id in test_ids:
            proxy = self.proxies[proxy_id]
            proxies = {"http": proxy.http_proxy_url, "https": proxy.http_proxy_url}

            try:
                import requests
                start_time = time.time()
                response = requests.get("https://www.google.com", proxies=proxies, timeout=timeout)
                end_time = time.time()

                if response.status_code == 200:
                    latency = end_time - start_time
                    latencies[proxy_id] = latency
                    # Update proxy's last known latency
                    proxy.last_latency = latency
                    proxy.last_check_time = end_time
            except Exception as e:
                logging.warning(f"Failed to measure latency for proxy {proxy_id}: {str(e)}")
                # Mark as failed for monitoring purposes
                proxy.last_error = str(e)
                proxy.last_error_time = time.time()

        # Return the fastest proxy
        if latencies:
            fastest_id = min(latencies, key=latencies.get)
            logging.info(f"Fastest proxy is {fastest_id} with latency {latencies[fastest_id]:.3f}s")
            return self.proxies[fastest_id]
        
        return None

    def stop(self):
        """Stop all proxies and clean up resources."""
        self.stop_all()

    def __del__(self):
        """Ensure resources are cleaned up when the object is garbage collected."""
        try:
            self.stop()
        except Exception as e:
            # Avoid raising exceptions in __del__
            logging.warning(f"Error during V2RayPool cleanup: {str(e)}")
