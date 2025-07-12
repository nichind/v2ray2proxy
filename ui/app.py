from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for
from flask_socketio import SocketIO, emit
import os
import json
import time
import threading
import requests
import base64
import concurrent.futures
from datetime import datetime
import logging
import uuid
from pathlib import Path
import sys

# Add parent directory to path to import v2ray2proxy
sys.path.insert(0, str(Path(__file__).parent.parent))
from v2ray2proxy.base import V2RayProxy, V2RayCore

app = Flask(__name__)
app.config["SECRET_KEY"] = "v2ray-proxy-tester-secret-key"
socketio = SocketIO(app, cors_allowed_origins="*")
core = V2RayCore()

# Global variables for tracking test state
test_sessions = {}
test_lock = threading.Lock()

# Setup directories
BASE_DIR = Path(__file__).parent
RESULTS_DIR = BASE_DIR / "results"
LOGS_DIR = BASE_DIR / "logs"
UPLOADS_DIR = BASE_DIR / "uploads"

for dir_path in [RESULTS_DIR, LOGS_DIR, UPLOADS_DIR]:
    dir_path.mkdir(exist_ok=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOGS_DIR / "app.log"), logging.StreamHandler()],
)


class ProxyTestSession:
    def __init__(self, session_id, proxies, test_url, timeout, retries, max_threads):
        self.session_id = session_id
        self.proxies = proxies
        self.test_url = test_url
        self.timeout = timeout
        self.retries = retries
        self.max_threads = max_threads
        self.start_time = time.time()
        self.stop_requested = False

        # Results tracking
        self.total_proxies = len(proxies)
        self.tested_proxies = 0
        self.working_proxies = []
        self.failed_proxies = []

        # Thread management
        self.executor = None
        self.active_v2ray_instances = set()
        self.cleanup_lock = threading.Lock()

    def get_status(self):
        elapsed = time.time() - self.start_time
        progress = (self.tested_proxies / self.total_proxies * 100) if self.total_proxies > 0 else 0

        return {
            "session_id": self.session_id,
            "total_proxies": self.total_proxies,
            "tested_proxies": self.tested_proxies,
            "working_proxies": len(self.working_proxies),
            "failed_proxies": len(self.failed_proxies),
            "progress": round(progress, 2),
            "elapsed_time": round(elapsed, 2),
            "is_running": not self.stop_requested,
            "working_proxy_list": self.working_proxies.copy(),
        }

    def stop(self):
        self.stop_requested = True
        if self.executor:
            self.executor.shutdown(wait=False)
        self.cleanup_all_instances()

    def cleanup_all_instances(self):
        """Clean up all active V2Ray instances"""
        with self.cleanup_lock:
            for proxy_instance in list(self.active_v2ray_instances):
                try:
                    proxy_instance.stop()
                    proxy_instance.cleanup()
                except Exception as e:
                    logging.warning(f"Error cleaning up V2Ray instance: {e}")
            self.active_v2ray_instances.clear()

    def test_single_proxy(self, proxy_link):
        """Test a single proxy and return result"""
        if self.stop_requested:
            return None

        proxy_instance = None
        try:
            # Create V2Ray instance
            proxy_instance = V2RayProxy(proxy_link, config_only=False)

            # Track the instance for cleanup
            with self.cleanup_lock:
                self.active_v2ray_instances.add(proxy_instance)

            # Test the proxy with retries
            for attempt in range(self.retries):
                if self.stop_requested:
                    break

                try:
                    proxies = {"http": proxy_instance.http_proxy_url, "https": proxy_instance.http_proxy_url}

                    response = requests.get(self.test_url, proxies=proxies, timeout=self.timeout)

                    if response.status_code == 200:
                        # Success!
                        result = {
                            "proxy_link": proxy_link,
                            "status": "working",
                            "response_text": response.text[:500],  # Limit response text
                            "response_code": response.status_code,
                            "attempt": attempt + 1,
                            "test_url": self.test_url,
                        }

                        self.working_proxies.append(result)
                        return result

                except Exception as e:
                    if attempt == self.retries - 1:  # Last attempt
                        result = {
                            "proxy_link": proxy_link,
                            "status": "failed",
                            "error": str(e),
                            "attempt": attempt + 1,
                            "test_url": self.test_url,
                        }
                        self.failed_proxies.append(result)
                        return result

                    # Wait before retry
                    time.sleep(0.5)

            return None

        except Exception as e:
            logging.error(f"Error testing proxy: {e}")
            result = {"proxy_link": proxy_link, "status": "failed", "error": str(e), "test_url": self.test_url}
            self.failed_proxies.append(result)
            return result

        finally:
            # Always clean up the proxy instance
            if proxy_instance:
                try:
                    proxy_instance.stop()
                    proxy_instance.cleanup()
                    with self.cleanup_lock:
                        self.active_v2ray_instances.discard(proxy_instance)
                except Exception as e:
                    logging.warning(f"Error cleaning up proxy instance: {e}")

    def run_test(self):
        """Run the proxy test with threading"""
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_threads) as executor:
                self.executor = executor

                # Submit all proxy tests
                future_to_proxy = {executor.submit(self.test_single_proxy, proxy): proxy for proxy in self.proxies}

                # Process results as they complete
                for future in concurrent.futures.as_completed(future_to_proxy):
                    if self.stop_requested:
                        break

                    proxy = future_to_proxy[future]
                    try:
                        result = future.result()
                        self.tested_proxies += 1

                        # Emit progress update
                        socketio.emit("progress_update", self.get_status())

                    except Exception as e:
                        logging.error(f"Error processing proxy {proxy}: {e}")
                        self.tested_proxies += 1

                        # Add to failed list
                        self.failed_proxies.append({"proxy_link": proxy, "status": "failed", "error": str(e), "test_url": self.test_url})

                        socketio.emit("progress_update", self.get_status())

            # Save results
            self.save_results()

            # Emit completion
            socketio.emit("test_complete", self.get_status())

        except Exception as e:
            logging.error(f"Error in run_test: {e}")
            socketio.emit("test_error", {"error": str(e)})
        finally:
            # Final cleanup
            self.cleanup_all_instances()

    def save_results(self):
        """Save test results to file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"proxy_test_results_{timestamp}.json"
        filepath = RESULTS_DIR / filename

        results = {
            "session_id": self.session_id,
            "test_url": self.test_url,
            "timeout": self.timeout,
            "retries": self.retries,
            "max_threads": self.max_threads,
            "start_time": self.start_time,
            "end_time": time.time(),
            "total_proxies": self.total_proxies,
            "working_proxies": self.working_proxies,
            "failed_proxies": self.failed_proxies,
            "summary": self.get_status(),
        }

        with open(filepath, "w") as f:
            json.dump(results, f, indent=2)

        logging.info(f"Results saved to {filepath}")


@app.route("/")
def index():
    # Get recent results
    recent_results = []
    for result_file in sorted(RESULTS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:10]:
        try:
            with open(result_file, "r") as f:
                data = json.load(f)
                recent_results.append(
                    {
                        "filename": result_file.name,
                        "timestamp": datetime.fromtimestamp(data.get("start_time", 0)).strftime("%Y-%m-%d %H:%M:%S"),
                        "total_proxies": data.get("total_proxies", 0),
                        "working_proxies": len(data.get("working_proxies", [])),
                        "test_url": data.get("test_url", "N/A"),
                    }
                )
        except Exception as e:
            logging.error(f"Error reading result file {result_file}: {e}")

    return render_template("index.html", recent_results=recent_results)


@app.route("/start_test", methods=["POST"])
def start_test():
    try:
        # Get form data
        input_type = request.form.get("input_type")
        test_url = request.form.get("test_url", "https://api.ipify.org?format=json")
        timeout = int(request.form.get("timeout", 10))
        retries = int(request.form.get("retries", 3))
        max_threads = int(request.form.get("max_threads", 50))

        proxies = []

        # Parse input based on type
        if input_type == "file":
            file = request.files.get("subscription_file")
            if file:
                content = file.read().decode("utf-8")
                proxies = parse_proxy_content(content)

        elif input_type == "url":
            subscription_url = request.form.get("subscription_url")
            if subscription_url:
                response = requests.get(subscription_url, timeout=30)
                content = response.text
                proxies = parse_proxy_content(content)

        elif input_type == "manual":
            manual_input = request.form.get("manual_input")
            if manual_input:
                proxies = parse_proxy_content(manual_input)

        if not proxies:
            return jsonify({"error": "No valid proxies found"}), 400

        # Create test session
        session_id = str(uuid.uuid4())
        test_session = ProxyTestSession(
            session_id=session_id, proxies=proxies, test_url=test_url, timeout=timeout, retries=retries, max_threads=max_threads
        )

        # Store session
        with test_lock:
            test_sessions[session_id] = test_session

        # Start test in background
        def run_test_background():
            test_session.run_test()

        thread = threading.Thread(target=run_test_background)
        thread.daemon = True
        thread.start()

        return jsonify({"success": True, "session_id": session_id, "total_proxies": len(proxies)})

    except Exception as e:
        logging.error(f"Error starting test: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/stop_test", methods=["POST"])
def stop_test():
    try:
        session_id = request.json.get("session_id")

        with test_lock:
            if session_id in test_sessions:
                test_sessions[session_id].stop()
                return jsonify({"success": True})
            else:
                return jsonify({"error": "Session not found"}), 404

    except Exception as e:
        logging.error(f"Error stopping test: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/get_status/<session_id>")
def get_status(session_id):
    try:
        with test_lock:
            if session_id in test_sessions:
                return jsonify(test_sessions[session_id].get_status())
            else:
                return jsonify({"error": "Session not found"}), 404

    except Exception as e:
        logging.error(f"Error getting status: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/download_results/<session_id>")
def download_results(session_id):
    try:
        with test_lock:
            if session_id not in test_sessions:
                return jsonify({"error": "Session not found"}), 404

            session = test_sessions[session_id]

            # Create text file with working proxies
            content = f"# V2Ray Proxy Test Results\n"
            content += f"# Test URL: {session.test_url}\n"
            content += f"# Total Proxies: {session.total_proxies}\n"
            content += f"# Working Proxies: {len(session.working_proxies)}\n"
            content += f"# Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

            for proxy in session.working_proxies:
                content += f"{proxy['proxy_link']}\n"

            # Save to file
            filename = f"working_proxies_{session_id[:8]}.txt"
            filepath = RESULTS_DIR / filename

            with open(filepath, "w") as f:
                f.write(content)

            return send_file(filepath, as_attachment=True, download_name=filename)

    except Exception as e:
        logging.error(f"Error downloading results: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/download_previous/<filename>")
def download_previous(filename):
    try:
        filepath = RESULTS_DIR / filename
        if filepath.exists():
            return send_file(filepath, as_attachment=True)
        else:
            return jsonify({"error": "File not found"}), 404

    except Exception as e:
        logging.error(f"Error downloading previous result: {e}")
        return jsonify({"error": str(e)}), 500


def parse_proxy_content(content):
    """Parse proxy content from various formats"""
    proxies = []

    # Try to decode base64 first (subscription format)
    try:
        decoded = base64.b64decode(content).decode("utf-8")
        content = decoded
    except:
        pass

    # Split by lines and filter valid proxy links
    lines = content.strip().split("\n")

    for line in lines:
        line = line.strip()
        if line and not line.startswith("#"):
            # Check if it's a valid proxy link
            if any(line.startswith(prefix) for prefix in ["vmess://", "vless://", "ss://", "trojan://"]):
                proxies.append(line)

    return proxies


@socketio.on("connect")
def handle_connect():
    logging.info("Client connected")
    emit("connected", {"data": "Connected to server"})


@socketio.on("disconnect")
def handle_disconnect():
    logging.info("Client disconnected")


if __name__ == "__main__":
    socketio.run(app, debug=True, host="0.0.0.0", port=5000)
