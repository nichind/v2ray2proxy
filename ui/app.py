from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for
from flask_socketio import SocketIO, emit, join_room
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
import psutil
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

# Session cleanup timer (24 hours)
SESSION_TIMEOUT = 24 * 60 * 60

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

        # Performance tracking
        self.test_times = []
        self.last_update_time = time.time()
        self.last_eta_update = time.time()
        self.cached_eta = 0

        # File paths for real-time saving
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.results_filename = f"proxy_test_results_{timestamp}_{session_id[:8]}.json"
        self.results_filepath = RESULTS_DIR / self.results_filename

        # Resource usage tracking
        self.resource_usage_data = {"process_count": 0, "v2ray_processes": 0, "memory_mb": 0, "cpu_percent": 0}
        self.resource_update_thread = None
        self.resource_update_running = False

        # Thread management
        self.executor = None
        self.active_v2ray_instances = set()
        self.cleanup_lock = threading.Lock()
        self.results_lock = threading.Lock()

        # Initialize results file
        self._save_current_results()

    def get_status(self):
        elapsed = time.time() - self.start_time

        with self.results_lock:
            tested = self.tested_proxies
            working = len(self.working_proxies)
            failed = len(self.failed_proxies)
            progress = (tested / self.total_proxies * 100) if self.total_proxies > 0 else 0

        # Calculate ETA only every 5 seconds to reduce flickering
        current_time = time.time()
        if (current_time - self.last_eta_update) >= 5.0 and tested > 0:
            if tested < self.total_proxies and len(self.test_times) >= 5:
                # Use average of last 20 tests for more stable ETA
                recent_times = self.test_times[-20:] if len(self.test_times) > 20 else self.test_times
                avg_time_per_proxy = sum(recent_times) / len(recent_times)
                remaining_proxies = self.total_proxies - tested
                self.cached_eta = avg_time_per_proxy * remaining_proxies
            else:
                self.cached_eta = 0
            self.last_eta_update = current_time

        return {
            "session_id": self.session_id,
            "total_proxies": self.total_proxies,
            "tested_proxies": tested,
            "working_proxies": working,
            "failed_proxies": failed,
            "progress": round(progress, 2),
            "elapsed_time": round(elapsed, 2),
            "eta": round(self.cached_eta, 0),
            "is_running": not self.stop_requested,
            "working_proxy_list": self.working_proxies.copy() if len(self.working_proxies) < 1000 else self.working_proxies[-1000:],
            "resource_usage": self.resource_usage_data,
            "results_filename": self.results_filename,
        }

    def _save_current_results(self):
        """Save current results to file in real-time"""
        try:
            with self.results_lock:
                results = {
                    "session_id": self.session_id,
                    "test_url": self.test_url,
                    "timeout": self.timeout,
                    "retries": self.retries,
                    "max_threads": self.max_threads,
                    "start_time": self.start_time,
                    "end_time": time.time(),
                    "total_proxies": self.total_proxies,
                    "tested_proxies": self.tested_proxies,
                    "working_proxies": self.working_proxies.copy(),
                    "failed_proxies": self.failed_proxies.copy(),
                    "summary": {
                        "total_proxies": self.total_proxies,
                        "tested_proxies": self.tested_proxies,
                        "working_count": len(self.working_proxies),
                        "failed_count": len(self.failed_proxies),
                        "success_rate": round((len(self.working_proxies) / max(self.tested_proxies, 1)) * 100, 2),
                    },
                }

            with open(self.results_filepath, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)

        except Exception as e:
            logging.error(f"Error saving results to file: {e}")

    def update_resource_usage(self):
        """Continuously monitor and update resource usage in a separate thread"""
        self.resource_update_running = True

        while self.resource_update_running and not self.stop_requested:
            try:
                # Count active instances
                with self.cleanup_lock:
                    process_count = len(self.active_v2ray_instances)

                # Get all v2ray processes
                v2ray_processes = []
                total_memory_mb = 0
                total_cpu_percent = 0

                for proc in psutil.process_iter(["pid", "name", "memory_info"]):
                    try:
                        if proc.info["name"] and "v2ray" in proc.info["name"].lower():
                            v2ray_processes.append(proc)
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        pass

                # First CPU measurement to initialize
                for proc in v2ray_processes:
                    try:
                        proc.cpu_percent(interval=None)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

                # Wait for a moment to get accurate CPU readings
                time.sleep(0.5)

                # Get actual measurements
                for proc in v2ray_processes:
                    try:
                        cpu_percent = proc.cpu_percent(interval=None)
                        memory_mb = proc.memory_info().rss / (1024 * 1024)

                        total_cpu_percent += cpu_percent
                        total_memory_mb += memory_mb
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

                # Update the resource usage data
                self.resource_usage_data = {
                    "process_count": process_count,
                    "v2ray_processes": len(v2ray_processes),
                    "memory_mb": round(total_memory_mb, 2),
                    "cpu_percent": round(total_cpu_percent, 2),
                }

                # Sleep before next update
                time.sleep(1.0)

            except Exception as e:
                logging.error(f"Error updating resource usage: {e}")
                time.sleep(2.0)  # Longer delay if error

        logging.info("Resource usage monitoring stopped")

    def stop(self):
        self.stop_requested = True
        self.resource_update_running = False

        if self.executor:
            self.executor.shutdown(wait=False)

        # Stop resource monitoring thread
        if self.resource_update_thread and self.resource_update_thread.is_alive():
            self.resource_update_thread.join(timeout=2.0)

        self.cleanup_all_instances()

    def cleanup_all_instances(self):
        """Clean up all active V2Ray instances"""
        with self.cleanup_lock:
            instances_to_cleanup = list(self.active_v2ray_instances)
            self.active_v2ray_instances.clear()

        for proxy_instance in instances_to_cleanup:
            try:
                proxy_instance.stop()
                proxy_instance.cleanup()
            except Exception as e:
                logging.warning(f"Error cleaning up V2Ray instance: {e}")

    def test_single_proxy(self, proxy_link):
        """Test a single proxy and return result"""
        if self.stop_requested:
            return None

        proxy_instance = None
        start_time = time.time()

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
                        result = {
                            "proxy_link": proxy_link,
                            "status": "working",
                            "response_text": response.text[:500],
                            "response_code": response.status_code,
                            "attempt": attempt + 1,
                            "test_url": self.test_url,
                            "test_time": time.time() - start_time,
                        }

                        with self.results_lock:
                            self.working_proxies.append(result)
                            self.tested_proxies += 1
                            self.test_times.append(time.time() - start_time)

                        # Save results in real-time every 10 working proxies
                        if len(self.working_proxies) % 10 == 0:
                            self._save_current_results()

                        return result

                except Exception as e:
                    if attempt == self.retries - 1:  # Last attempt
                        result = {
                            "proxy_link": proxy_link,
                            "status": "failed",
                            "error": str(e),
                            "attempt": attempt + 1,
                            "test_url": self.test_url,
                            "test_time": time.time() - start_time,
                        }

                        with self.results_lock:
                            self.failed_proxies.append(result)
                            self.tested_proxies += 1
                            self.test_times.append(time.time() - start_time)

                        return result

                    # Wait before retry
                    time.sleep(0.5)

            # If we get here, all retries failed without a specific exception
            result = {
                "proxy_link": proxy_link,
                "status": "failed",
                "error": "All retries failed",
                "test_url": self.test_url,
                "test_time": time.time() - start_time,
            }

            with self.results_lock:
                self.failed_proxies.append(result)
                self.tested_proxies += 1
                self.test_times.append(time.time() - start_time)

            return result

        except Exception as e:
            logging.error(f"Error testing proxy: {e}")
            result = {
                "proxy_link": proxy_link,
                "status": "failed",
                "error": str(e),
                "test_url": self.test_url,
                "test_time": time.time() - start_time,
            }

            with self.results_lock:
                self.failed_proxies.append(result)
                self.tested_proxies += 1
                self.test_times.append(time.time() - start_time)

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
            # Start resource usage monitoring thread
            self.resource_update_thread = threading.Thread(target=self.update_resource_usage)
            self.resource_update_thread.daemon = True
            self.resource_update_thread.start()

            # Create a proxy counter for batch updates
            completed_count = 0
            last_update_time = time.time()
            last_save_time = time.time()

            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_threads) as executor:
                self.executor = executor

                # Submit all proxy tests
                future_to_proxy = {executor.submit(self.test_single_proxy, proxy): proxy for proxy in self.proxies}

                # Process results as they complete
                for future in concurrent.futures.as_completed(future_to_proxy):
                    if self.stop_requested:
                        break

                    try:
                        future.result()  # Result already handled in test_single_proxy

                        # Update UI periodically to avoid excessive updates
                        completed_count += 1
                        current_time = time.time()

                        # Save results every 30 seconds or every 100 proxies
                        if (current_time - last_save_time) > 30.0 or completed_count % 100 == 0:
                            last_save_time = current_time
                            self._save_current_results()

                        # Only update UI every 5 proxies or every 3 seconds
                        if completed_count % 5 == 0 or (current_time - last_update_time) > 3.0:
                            last_update_time = current_time
                            status = self.get_status()
                            socketio.emit("progress_update", status, room=self.session_id)

                            # Log updates periodically
                            if completed_count % 50 == 0:
                                logging.info(f"Progress: {status['progress']}% - {status['tested_proxies']}/{status['total_proxies']}")

                    except Exception as e:
                        logging.error(f"Error processing proxy result: {e}")

            # Stop resource usage monitoring
            self.resource_update_running = False
            if self.resource_update_thread.is_alive():
                self.resource_update_thread.join(timeout=2.0)

            # Save final results
            self._save_current_results()

            # Final status update and completion notification
            final_status = self.get_status()
            socketio.emit("progress_update", final_status, room=self.session_id)
            socketio.emit("test_complete", final_status, room=self.session_id)
            logging.info(
                f"Test complete: {final_status['tested_proxies']}/{final_status['total_proxies']} proxies tested, {len(self.working_proxies)} working"
            )

        except Exception as e:
            logging.error(f"Error in run_test: {e}")
            socketio.emit("test_error", {"error": str(e), "session_id": self.session_id}, room=self.session_id)
        finally:
            # Final cleanup and save
            self._save_current_results()
            self.cleanup_all_instances()

    def save_results(self):
        """Legacy method - now just calls _save_current_results for compatibility"""
        self._save_current_results()


# Session cleanup background task
def cleanup_old_sessions():
    """Periodically clean up old sessions"""
    while True:
        try:
            current_time = time.time()
            sessions_to_remove = []

            with test_lock:
                for session_id, session in test_sessions.items():
                    # Check if session is old (24 hours)
                    if current_time - session.start_time > SESSION_TIMEOUT:
                        sessions_to_remove.append(session_id)
                        if not session.stop_requested:
                            session.stop()

                # Remove old sessions
                for session_id in sessions_to_remove:
                    del test_sessions[session_id]
                    logging.info(f"Cleaned up old session: {session_id}")

        except Exception as e:
            logging.error(f"Error in cleanup task: {e}")

        # Sleep for 1 hour before next cleanup
        time.sleep(3600)


# Start the cleanup thread
cleanup_thread = threading.Thread(target=cleanup_old_sessions, daemon=True)
cleanup_thread.start()


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
        max_threads = min(int(request.form.get("max_threads", 50)), 1000)

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
        thread = threading.Thread(target=test_session.run_test)
        thread.daemon = True
        thread.start()

        return jsonify({"success": True, "session_id": session_id, "total_proxies": len(proxies)})

    except Exception as e:
        logging.error(f"Error starting test: {e}", exc_info=True)
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


@app.route("/download_results/<session_id>/<format_type>")
def download_results(session_id, format_type):
    try:
        with test_lock:
            if session_id not in test_sessions:
                return jsonify({"error": "Session not found"}), 404

            session = test_sessions[session_id]

            if format_type == "json":
                # Return the JSON file directly
                if session.results_filepath.exists():
                    return send_file(
                        session.results_filepath,
                        as_attachment=True,
                        download_name=f"proxy_results_{session_id[:8]}.json",
                        mimetype="application/json",
                    )
                else:
                    return jsonify({"error": "Results file not found"}), 404

            elif format_type == "txt":
                # Create text file with working proxies only
                with session.results_lock:
                    working_proxies = session.working_proxies.copy()

                content = f"# V2Ray Proxy Test Results - Working Proxies Only\n"
                content += f"# Test URL: {session.test_url}\n"
                content += f"# Total Proxies Tested: {session.tested_proxies}\n"
                content += f"# Working Proxies: {len(working_proxies)}\n"
                content += f"# Success Rate: {round((len(working_proxies) / max(session.tested_proxies, 1)) * 100, 2)}%\n"
                content += f"# Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

                for proxy in working_proxies:
                    content += f"{proxy['proxy_link']}\n"

                # Save to temporary file
                temp_filename = f"working_proxies_{session_id[:8]}.txt"
                temp_filepath = RESULTS_DIR / temp_filename

                with open(temp_filepath, "w", encoding="utf-8") as f:
                    f.write(content)

                return send_file(temp_filepath, as_attachment=True, download_name=temp_filename, mimetype="text/plain")
            else:
                return jsonify({"error": "Invalid format type. Use 'json' or 'txt'"}), 400

    except Exception as e:
        logging.error(f"Error downloading results: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/download_previous/<filename>")
@app.route("/download_previous/<filename>/<format_type>")
def download_previous(filename, format_type=None):
    """Download previous results in JSON or TXT format"""
    try:
        filepath = RESULTS_DIR / filename
        if not filepath.exists():
            return jsonify({"error": "File not found"}), 404

        # If no format specified or format is json, return the original file
        if format_type is None or format_type == "json":
            return send_file(filepath, as_attachment=True)

        elif format_type == "txt":
            # Load the JSON file and extract working proxies
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)

                working_proxies = data.get("working_proxies", [])
                test_url = data.get("test_url", "N/A")
                total_proxies = data.get("total_proxies", 0)
                tested_proxies = data.get("tested_proxies", 0)
                start_time = data.get("start_time", time.time())

                # Create TXT content with working proxies only
                content = f"# V2Ray Proxy Test Results - Working Proxies Only\n"
                content += f"# Test URL: {test_url}\n"
                content += f"# Total Proxies: {total_proxies}\n"
                content += f"# Tested Proxies: {tested_proxies}\n"
                content += f"# Working Proxies: {len(working_proxies)}\n"
                content += f"# Success Rate: {round((len(working_proxies) / max(tested_proxies, 1)) * 100, 2)}%\n"
                content += f"# Test Date: {datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')}\n\n"

                for proxy in working_proxies:
                    if isinstance(proxy, dict):
                        content += f"{proxy.get('proxy_link', '')}\n"
                    else:
                        content += f"{proxy}\n"

                # Create temporary TXT file
                base_name = filepath.stem  # filename without extension
                temp_filename = f"{base_name}_working_proxies.txt"
                temp_filepath = RESULTS_DIR / temp_filename

                with open(temp_filepath, "w", encoding="utf-8") as f:
                    f.write(content)

                return send_file(temp_filepath, as_attachment=True, download_name=temp_filename, mimetype="text/plain")

            except json.JSONDecodeError:
                return jsonify({"error": "Invalid JSON file"}), 400
            except Exception as e:
                logging.error(f"Error processing JSON file {filename}: {e}")
                return jsonify({"error": f"Error processing file: {str(e)}"}), 500

        else:
            return jsonify({"error": "Invalid format type. Use 'json' or 'txt'"}), 400

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


@socketio.on("join")
def on_join(data):
    """Join a specific room based on session ID"""
    session_id = data.get("session_id")
    if session_id:
        join_room(session_id)
        logging.info(f"Client joined room: {session_id}")

        # Send current status if session exists
        with test_lock:
            if session_id in test_sessions:
                status = test_sessions[session_id].get_status()
                emit("progress_update", status)
                # Log room join for debugging
                logging.info(f"Sent status update to client in room {session_id}: {status['progress']}%")
    else:
        logging.warning("Client attempted to join room without session_id")


@socketio.on("disconnect")
def handle_disconnect():
    logging.info("Client disconnected")


if __name__ == "__main__":
    socketio.run(app, debug=True, host="0.0.0.0", port=5000)
