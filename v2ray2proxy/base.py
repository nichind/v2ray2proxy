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
import urllib.request
import urllib.error
import socket
import signal
import threading
import weakref
import psutil


# Global registry to track all active processes
_active_processes = weakref.WeakSet()
_cleanup_lock = threading.RLock()
_signal_handlers_registered = False


def _register_signal_handlers():
    """Register signal handlers for process cleanup."""
    global _signal_handlers_registered
    if _signal_handlers_registered:
        return

    def cleanup_handler(signum, frame):
        logging.info(f"Received signal {signum}, cleaning up V2Ray processes...")
        _cleanup_all_processes()
        # Re-raise the signal for default handling
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)

    # Register handlers for common termination signals
    if os.name != "nt":  # Unix-like systems
        signal.signal(signal.SIGTERM, cleanup_handler)
        signal.signal(signal.SIGINT, cleanup_handler)
        signal.signal(signal.SIGHUP, cleanup_handler)
    else:  # Windows
        signal.signal(signal.SIGTERM, cleanup_handler)
        signal.signal(signal.SIGINT, cleanup_handler)

    _signal_handlers_registered = True


def _cleanup_all_processes():
    """Emergency cleanup of all tracked processes."""
    with _cleanup_lock:
        processes_to_cleanup = list(_active_processes)
        for process_ref in processes_to_cleanup:
            try:
                if hasattr(process_ref, "_emergency_cleanup"):
                    process_ref._emergency_cleanup()
            except Exception as e:
                logging.error(f"Error in emergency cleanup: {e}")


# Register signal handlers and atexit cleanup
_register_signal_handlers()
atexit.register(_cleanup_all_processes)


class V2RayCore:
    """Represents executable of V2Ray core."""

    def __init__(self):
        self.release_tag_url = os.environ.get("V2RAY_RELASE_TAG_URL") or "https://github.com/XTLS/Xray-core/releases/download/v25.8.3"
        if os.environ.get("V2RAY_EXECUTABLE_DIR"):
            self.executable_dir = os.environ["V2RAY_EXECUTABLE_DIR"]
            self.executable = os.path.join(self.executable_dir, "xray.exe" if os.name == "nt" else "xray")
        if not os.environ.get("V2RAY_EXECUTABLE_DIR") or not os.path.isdir(self.executable_dir):
            logging.info("V2Ray executable directory not found in environment variable, using default...")
            self.executable_dir = self._download_executables()
            self.executable = os.path.join(self.executable_dir, "xray.exe" if os.name == "nt" else "xray")
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
        executable_name = "xray"

        # Check if the executable already exist
        v2ray_executable = v2ray_dir / (executable_name + (".exe" if system == "windows" else ""))

        if v2ray_executable.exists():
            logging.info(f"V2Ray executables found at {v2ray_dir}")
            return str(v2ray_dir)

        # Determine the current OS and architecture
        machine = platform.machine().lower()

        # Map the OS and architecture to the appropriate download file
        download_file = None

        # Windows mapping
        if system == "windows":
            if machine == "amd64" or machine == "x86_64":
                download_file = "Xray-windows-64.zip"
            elif machine == "x86" or machine == "i386":
                download_file = "Xray-windows-32.zip"
            elif "arm" in machine:
                if "64" in machine or "v8" in machine:
                    download_file = "Xray-windows-arm64-v8a.zip"
                else:
                    download_file = "Xray-windows-arm32-v7a.zip"

        # Linux mapping
        elif system == "linux":
            if machine == "x86_64" or machine == "amd64":
                download_file = "Xray-linux-64.zip"
            elif machine == "i386" or machine == "x86":
                download_file = "Xray-linux-32.zip"
            elif "arm" in machine:
                if "64" in machine or "v8" in machine:
                    download_file = "Xray-linux-arm64-v8a.zip"
                elif "v7" in machine:
                    download_file = "Xray-linux-arm32-v7a.zip"
                elif "v6" in machine:
                    download_file = "Xray-linux-arm32-v6.zip"
                else:
                    download_file = "Xray-linux-arm32-v5.zip"
            elif "mips" in machine:
                if "64" in machine:
                    if "le" in machine:
                        download_file = "Xray-linux-mips64le.zip"
                    else:
                        download_file = "Xray-linux-mips64.zip"
                else:
                    if "le" in machine:
                        download_file = "Xray-linux-mips32le.zip"
                    else:
                        download_file = "Xray-linux-mips32.zip"
            elif "ppc64" in machine:
                if "le" in machine:
                    download_file = "Xray-linux-ppc64le.zip"
                else:
                    download_file = "Xray-linux-ppc64.zip"
            elif "s390x" in machine:
                download_file = "Xray-linux-s390x.zip"
            elif "riscv64" in machine:
                download_file = "Xray-linux-riscv64.zip"
            elif "loong64" in machine:
                download_file = "Xray-linux-loong64.zip"

        # macOS mapping
        elif system == "darwin":
            if "arm" in machine or "aarch64" in machine:
                download_file = "Xray-macos-arm64-v8a.zip"
            else:
                download_file = "Xray-macos-64.zip"

        # FreeBSD mapping
        elif system == "freebsd":
            if machine == "amd64" or machine == "x86_64":
                download_file = "Xray-freebsd-64.zip"
            elif machine == "i386" or machine == "x86":
                download_file = "Xray-freebsd-32.zip"
            elif "arm" in machine:
                if "64" in machine or "v8" in machine:
                    download_file = "Xray-freebsd-arm64-v8a.zip"
                elif "v7" in machine:
                    download_file = "Xray-freebsd-arm32-v7a.zip"

        # OpenBSD mapping
        elif system == "openbsd":
            if machine == "amd64" or machine == "x86_64":
                download_file = "Xray-openbsd-64.zip"
            elif machine == "i386" or machine == "x86":
                download_file = "Xray-openbsd-32.zip"
            elif "arm" in machine:
                if "64" in machine or "v8" in machine:
                    download_file = "Xray-openbsd-arm64-v8a.zip"
                elif "v7" in machine:
                    download_file = "Xray-openbsd-arm32-v7a.zip"

        # Dragonfly mapping
        elif system == "dragonfly":
            download_file = "Xray-dragonfly-64.zip"

        # Android mapping
        elif system == "android":
            if machine == "x86_64" or machine == "amd64":
                download_file = "Xray-android-amd64.zip"
            elif "arm" in machine:
                if "64" in machine or "v8" in machine:
                    download_file = "Xray-android-arm64-v8a.zip"

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

            # Make the files executable on Unix systems
            if system != "windows":
                for exe in [v2ray_executable]:
                    if exe.exists():
                        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)

        logging.info(f"Using V2Ray executable at {v2ray_dir}")
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
        self._cleanup_lock = threading.RLock()
        self._process_terminated = threading.Event()

        # Register this instance for global cleanup
        _active_processes.add(self)

        # Start V2Ray if not in config_only mode
        if not config_only:
            self.start()

    def _is_port_in_use(self, port: int) -> bool:
        """Check if a port is currently in use by trying to bind to it."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("localhost", port))
                return False
        except (socket.error, OSError):
            return True

    def _pick_unused_port(self, exclude_port: int | list = None) -> int:
        # Try to get a system-assigned port first
        if not exclude_port:
            exclude_port = []
        elif isinstance(exclude_port, int):
            exclude_port = [exclude_port]
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("localhost", 0))  # Let OS choose a free port
                _, port = s.getsockname()
                if port not in exclude_port:
                    return port
        except Exception as e:
            logging.warning(f"Failed to get system-assigned port: {str(e)}")

        # If that fails, try a few random ports
        for _ in range(100):
            port = random.randint(10000, 65000)
            if port not in exclude_port and not self._is_port_in_use(port):
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
            core = V2RayCore()
            v2ray_exe = core.executable
            if not os.path.isfile(v2ray_exe):
                raise FileNotFoundError(f"V2Ray executable not found at {v2ray_exe}")

            if os.name == "posix" and not os.access(v2ray_exe, os.X_OK):
                raise PermissionError(f"V2Ray executable {v2ray_exe} is not executable")

            # Prepare command and environment
            cmd = [v2ray_exe, "-config", config_path]

            # Perform a quick check to find out the version of v2ray core
            files = os.listdir(core.executable_dir)
            if "v2ctl" in files or "v2ctl.exe" in files:
                logging.info(f"Detected v2ctl in {core.executable_dir}, assuming v2ray core is <v5.0")
            else:
                # If v2ctl is not found, assume v2ray core is >=v5.0
                # Insert "run" command for compatibility
                cmd.insert(1, "run")

            logging.info(f"Starting V2Ray with command: {' '.join(cmd)}")

            # Set up process creation flags for better process management
            kwargs = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "universal_newlines": True,
            }

            if os.name == "nt":  # Windows
                kwargs["shell"] = True
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:  # Unix-like systems
                kwargs["preexec_fn"] = os.setsid  # Create new process group

            # Start v2ray process
            self.v2ray_process = subprocess.Popen(cmd, **kwargs)
            self._process_terminated.clear()

            # Quick check if process started successfully
            time.sleep(0.05)
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
                self._terminate_process(timeout=1)
                try:
                    stdout, stderr = self.v2ray_process.communicate(timeout=2)
                    logging.error(f"V2Ray output after failed start: Stdout: {stdout}, Stderr: {stderr}")
                except Exception:
                    pass
                raise

        except Exception as e:
            logging.error(f"Error starting V2Ray: {str(e)}")
            self._safe_cleanup()  # Use _safe_cleanup instead of cleanup to avoid recursion
            raise

    def stop(self):
        """Stop the V2Ray process and clean up resources."""
        with self._cleanup_lock:
            if not self.running and self.v2ray_process is None:
                return

            try:
                # Terminate the process with short timeout for speed
                if self.v2ray_process is not None:
                    success = self._terminate_process(timeout=1)
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

    def _terminate_process(self, timeout=2) -> bool:
        """
        Fast and reliable process termination with cross-platform support.

        Args:
            timeout (int): Maximum time to wait for graceful termination

        Returns:
            bool: True if process was terminated successfully
        """
        if self.v2ray_process is None:
            return True

        try:
            # Check if process is already terminated
            if self.v2ray_process.poll() is not None:
                self._process_terminated.set()
                return True

            pid = self.v2ray_process.pid
            logging.debug(f"Terminating V2Ray process (PID: {pid})")

            if os.name == "nt":  # Windows
                return self._terminate_windows_process(pid, timeout)
            else:  # Unix-like systems
                return self._terminate_unix_process(pid, timeout)

        except Exception as e:
            logging.error(f"Error terminating V2Ray process: {e}")
            return False

    def _terminate_windows_process(self, pid, timeout):
        """Terminate process on Windows."""
        try:
            # Use psutil for more reliable process management
            try:
                parent = psutil.Process(pid)
                children = parent.children(recursive=True)

                # Terminate children first
                for child in children:
                    try:
                        child.terminate()
                    except psutil.NoSuchProcess:
                        pass

                # Terminate parent
                parent.terminate()

                # Wait for termination
                try:
                    parent.wait(timeout=timeout)
                    self._process_terminated.set()
                    return True
                except psutil.TimeoutExpired:
                    # Force kill if timeout
                    logging.warning("Process didn't terminate gracefully, force killing")
                    for child in children:
                        try:
                            child.kill()
                        except psutil.NoSuchProcess:
                            pass
                    parent.kill()
                    parent.wait(timeout=1)
                    self._process_terminated.set()
                    return True

            except psutil.NoSuchProcess:
                # Process already terminated
                self._process_terminated.set()
                return True

        except ImportError:
            # Fallback to subprocess if psutil not available
            try:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], check=False, capture_output=True, timeout=timeout)
                time.sleep(0.1)
                if self.v2ray_process.poll() is not None:
                    self._process_terminated.set()
                    return True
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

            # Final fallback
            try:
                self.v2ray_process.terminate()
                self.v2ray_process.wait(timeout=timeout)
                self._process_terminated.set()
                return True
            except subprocess.TimeoutExpired:
                self.v2ray_process.kill()
                self.v2ray_process.wait(timeout=1)
                self._process_terminated.set()
                return True

    def _terminate_unix_process(self, pid, timeout):
        """Terminate process on Unix-like systems."""
        try:
            # Use psutil for better process management
            try:
                parent = psutil.Process(pid)
                children = parent.children(recursive=True)

                # Send SIGTERM to all processes
                for child in children:
                    try:
                        child.terminate()
                    except psutil.NoSuchProcess:
                        pass
                parent.terminate()

                # Wait for graceful termination
                try:
                    parent.wait(timeout=timeout)
                    self._process_terminated.set()
                    return True
                except psutil.TimeoutExpired:
                    # Force kill if timeout
                    logging.warning("Process didn't terminate gracefully, sending SIGKILL")
                    for child in children:
                        try:
                            child.kill()
                        except psutil.NoSuchProcess:
                            pass
                    parent.kill()
                    parent.wait(timeout=1)
                    self._process_terminated.set()
                    return True

            except psutil.NoSuchProcess:
                # Process already terminated
                self._process_terminated.set()
                return True

        except ImportError:
            # Fallback without psutil
            try:
                # Create process group to manage child processes
                if hasattr(os, "killpg"):
                    try:
                        # Try to kill the entire process group
                        os.killpg(os.getpgid(pid), signal.SIGTERM)

                        # Wait for termination
                        start_time = time.time()
                        while time.time() - start_time < timeout:
                            if self.v2ray_process.poll() is not None:
                                self._process_terminated.set()
                                return True
                            time.sleep(0.05)

                        # Force kill if timeout
                        os.killpg(os.getpgid(pid), signal.SIGKILL)
                        self.v2ray_process.wait(timeout=1)
                        self._process_terminated.set()
                        return True

                    except (ProcessLookupError, OSError):
                        # Process group doesn't exist, try individual process
                        pass

                # Fallback to individual process termination
                self.v2ray_process.terminate()
                try:
                    self.v2ray_process.wait(timeout=timeout)
                    self._process_terminated.set()
                    return True
                except subprocess.TimeoutExpired:
                    self.v2ray_process.kill()
                    self.v2ray_process.wait(timeout=1)
                    self._process_terminated.set()
                    return True

            except (ProcessLookupError, OSError):
                # Process already terminated
                self._process_terminated.set()
                return True

    def _emergency_cleanup(self):
        """Emergency cleanup called by signal handler."""
        try:
            if self.v2ray_process and self.v2ray_process.poll() is None:
                if os.name == "nt":
                    # Windows - force kill immediately
                    try:
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(self.v2ray_process.pid)], check=False, capture_output=True, timeout=1
                        )
                    except Exception:
                        try:
                            self.v2ray_process.kill()
                        except Exception:
                            pass
                else:
                    # Unix - force kill process group
                    try:
                        os.killpg(os.getpgid(self.v2ray_process.pid), signal.SIGKILL)
                    except Exception:
                        try:
                            self.v2ray_process.kill()
                        except Exception:
                            pass
        except Exception:
            pass  # Suppress all exceptions in emergency cleanup

    @property
    def socks5_proxy_url(self):
        """Get the SOCKS5 proxy URL."""
        return f"socks5://127.0.0.1:{self.socks_port}"

    @property
    def http_proxy_url(self):
        """Get the HTTP proxy URL."""
        return f"http://127.0.0.1:{self.http_port}"

    @property
    def usage_memory(self):
        """Get the memory usage of the V2Ray process."""
        if self.v2ray_process and self.v2ray_process.pid:
            try:
                process = psutil.Process(self.v2ray_process.pid)
                return process.memory_info().rss
            except Exception as exc:
                logging.error(f"Error getting memory usage: {exc}")
        return 0

    @property
    def usage_memory_mb(self):
        """Get the memory usage of the V2Ray process in MB."""
        return self.memory_usage / (1024 * 1024)

    @property
    def usage_cpu(self):
        """Get the CPU usage of the V2Ray process."""
        if self.v2ray_process and self.v2ray_process.pid:
            try:
                process = psutil.Process(self.v2ray_process.pid)
                return process.cpu_percent(interval=1)
            except Exception as exc:
                logging.error(f"Error getting CPU usage: {exc}")
        return 0

    def __del__(self):
        """Ensure resources are cleaned up when the object is garbage collected."""
        try:
            # Emergency cleanup - don't wait
            if self.v2ray_process and self.v2ray_process.poll() is None:
                self._emergency_cleanup()
            self._safe_cleanup()
        except Exception:
            # Suppress all exceptions in __del__
            pass


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

        # Register this pool for global cleanup
        _active_processes.add(self)

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

        # Use threading to stop proxies in parallel for speed
        def stop_proxy_thread(proxy_id):
            try:
                self.proxies[proxy_id].stop()
            except Exception as e:
                error_msg = f"Error stopping proxy {proxy_id}: {str(e)}"
                logging.error(error_msg)
                errors.append(error_msg)

        # Start threads for each proxy
        threads = []
        for proxy_id in list(self.active_proxies):
            thread = threading.Thread(target=stop_proxy_thread, args=(proxy_id,))
            thread.start()
            threads.append(thread)

        # Wait for all threads to complete with timeout
        for thread in threads:
            thread.join(timeout=2)  # Don't wait too long

        self.active_proxies.clear()

        if errors:
            logging.warning(f"Encountered {len(errors)} errors while stopping proxies")

    def _emergency_cleanup(self):
        """Emergency cleanup for the entire pool."""
        try:
            for proxy in self.proxies.values():
                try:
                    proxy._emergency_cleanup()
                except Exception:
                    pass
        except Exception:
            pass

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
        latencies = {}

        for proxy_id in self.active_proxies:
            proxy = self.proxies[proxy_id]

            # Set up proxy handler
            proxy_handler = urllib.request.ProxyHandler({"http": proxy.http_proxy_url, "https": proxy.http_proxy_url})
            opener = urllib.request.build_opener(proxy_handler)

            try:
                start_time = time.time()
                with opener.open(target, timeout=timeout) as response:
                    # Read a small amount of data to ensure connection works
                    response.read(1024)
                end_time = time.time()

                latency = end_time - start_time
                latencies[proxy_id] = latency
                # Update proxy's last known latency
                proxy.last_latency = latency
                proxy.last_check_time = end_time
            except (urllib.error.URLError, urllib.error.HTTPError, socket.timeout) as e:
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
        health = {}

        for proxy_id in self.active_proxies:
            proxy = self.proxies[proxy_id]

            # Set up proxy handler
            proxy_handler = urllib.request.ProxyHandler({"http": proxy.http_proxy_url, "https": proxy.http_proxy_url})
            opener = urllib.request.build_opener(proxy_handler)

            try:
                with opener.open(target, timeout=timeout) as response:
                    health[proxy_id] = response.code == 200

                # Clear any previous error state if successful
                if health[proxy_id]:
                    proxy.last_error = None
                    proxy.last_error_time = None
                    proxy.last_check_time = time.time()
            except (urllib.error.URLError, urllib.error.HTTPError, socket.timeout) as e:
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

            # Set up proxy handler
            proxy_handler = urllib.request.ProxyHandler({"http": proxy.http_proxy_url, "https": proxy.http_proxy_url})
            opener = urllib.request.build_opener(proxy_handler)

            try:
                start_time = time.time()
                with opener.open("https://www.google.com", timeout=timeout) as response:
                    # Read a small amount of data to ensure connection works
                    response.read(1024)
                end_time = time.time()

                latency = end_time - start_time
                latencies[proxy_id] = latency
                # Update proxy's last known latency
                proxy.last_latency = latency
                proxy.last_check_time = end_time
            except (urllib.error.URLError, urllib.error.HTTPError, socket.timeout) as e:
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
            self._emergency_cleanup()
        except Exception:
            # Suppress all exceptions in __del__
            pass
