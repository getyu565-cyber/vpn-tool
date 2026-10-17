#!/usr/bin/env python3
import os
import sys
import hashlib
import getpass
import json
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import httpx
import orjson

VERSION = "1.0.0"
API_BASE = "https://vpn-gateway-manager--jjajajjajahsh.replit.app"
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8765

def get_config_dir() -> Path:
    return Path.home() / ".vpn-tool"

def get_auth_file() -> Path:
    return get_config_dir() / "auth.json"

def get_session_file() -> Path:
    return get_config_dir() / "session"

def get_server_pid_file() -> Path:
    return get_config_dir() / "server.pid"

def get_server_host_file() -> Path:
    return get_config_dir() / "server.host"

def get_server_port_file() -> Path:
    return get_config_dir() / "server.port"

def ensure_config():
    try:
        get_config_dir().mkdir(parents=True, exist_ok=True, mode=0o700)
    except Exception as e:
        print(f"Error creating config directory: {e}", file=sys.stderr)
        sys.exit(1)

def hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()

def load_store() -> dict | None:
    file = get_auth_file()
    if not file.exists():
        return None
    try:
        data = file.read_bytes()
        return orjson.loads(data)
    except Exception:
        return None

def save_store(store: dict):
    ensure_config()
    try:
        data = orjson.dumps(store, option=orjson.OPT_INDENT_2)
        auth_file = get_auth_file()
        auth_file.write_bytes(data)
        os.chmod(auth_file, 0o600)
    except Exception as e:
        print(f"Error saving auth store: {e}", file=sys.stderr)
        sys.exit(1)

def registered() -> bool:
    store = load_store()
    return store is not None and len(store.get("profiles", [])) > 0

def logged_in() -> bool:
    file = get_session_file()
    if not file.exists():
        return False
    try:
        return file.read_text(encoding="utf-8").strip() == "logged_in"
    except Exception:
        return False

def set_logged_in(status: bool):
    ensure_config()
    val = "logged_in" if status else "logged_out"
    session_file = get_session_file()
    try:
        session_file.write_text(val, encoding="utf-8")
        os.chmod(session_file, 0o600)
    except Exception:
        pass

def prompt(prompt_str: str, secure: bool = False) -> str:
    if secure:
        try:
            return getpass.getpass(prompt_str).strip()
        except Exception:
            return ""
    try:
        return input(prompt_str).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""

def require_login():
    if not registered():
        print("Not registered. Run: vpn-tool auth register", file=sys.stderr)
        sys.exit(1)
    if not logged_in():
        print("Not logged in. Run: vpn-tool auth login", file=sys.stderr)
        sys.exit(1)

def get_server_endpoint() -> tuple[str, int]:
    host = DEFAULT_HOST
    port = DEFAULT_PORT
    host_file = get_server_host_file()
    port_file = get_server_port_file()
    if host_file.exists():
        try:
            host = host_file.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    if port_file.exists():
        try:
            port = int(port_file.read_text(encoding="utf-8").strip())
        except Exception:
            pass
    return host, port

def check_server() -> bool:
    host, port = get_server_endpoint()
    try:
        with httpx.Client(timeout=2.0) as client:
            client.get(f"http://{host}:{port}/api/")
            return True
    except Exception:
        print("Error: could not connect to vpn-tool server, run 'vpn-tool serve' to start it", file=sys.stderr)
        sys.exit(1)

def api_request(method: str, endpoint: str):
    check_server()
    host, port = get_server_endpoint()
    proxy_base = f"http://{host}:{port}"
    
    try:
        with httpx.Client() as client:
            response = client.request(
                method,
                proxy_base + endpoint,
                headers={"Accept": "application/json"},
                timeout=30.0
            )
            try:
                body_json = response.json()
            except Exception:
                body_json = response.text

            output = {
                "status": response.status_code,
                "body": body_json
            }
            print(orjson.dumps(output, option=orjson.OPT_INDENT_2).decode("utf-8"))
            
            if response.status_code < 200 or response.status_code >= 300:
                sys.exit(1)
    except httpx.RequestError:
        print("Error: could not connect to vpn-tool server, run 'vpn-tool serve' to start it", file=sys.stderr)
        sys.exit(1)

def print_error(status: int, msg: str):
    output = {
        "status": status,
        "body": {"error": msg}
    }
    print(orjson.dumps(output, option=orjson.OPT_INDENT_2).decode("utf-8"))
    sys.exit(1)

# HTTP Proxy Server Implementation
class ProxyHandler(BaseHTTPRequestHandler):
    def do_request(self, method):
        if not self.path.startswith("/api/"):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")
            return

        target_url = API_BASE + self.path
        headers = {key: val for key, val in self.headers.items() if key.lower() != 'host'}
        
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else None

        try:
            with httpx.Client() as client:
                resp = client.request(
                    method=method,
                    url=target_url,
                    headers=headers,
                    content=body,
                    timeout=30.0,
                    follow_redirects=True
                )
                self.send_response(resp.status_code)
                for key, val in resp.headers.items():
                    if key.lower() in ['content-encoding', 'transfer-encoding', 'content-length']:
                        continue
                    self.send_header(key, val)
                self.send_header('Content-Length', str(len(resp.content)))
                self.end_headers()
                self.wfile.write(resp.content)
        except Exception as e:
            self.send_response(502)
            self.end_headers()
            err_body = orjson.dumps({"error": str(e)})
            self.wfile.write(err_body)

    def do_GET(self):
        self.do_request("GET")

    def do_POST(self):
        self.do_request("POST")

    def do_PUT(self):
        self.do_request("PUT")

    def do_DELETE(self):
        self.do_request("DELETE")

    def log_message(self, format, *args):
        pass

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="VPN Gateway Manager CLI",
        prog="vpn-tool"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"vpn-tool version {VERSION}"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Auth Command
    auth_parser = subparsers.add_parser("auth", help="Authentication commands")
    auth_subparsers = auth_parser.add_subparsers(dest="auth_command", required=True)

    def handle_register(args):
        store = load_store()
        if store is None:
            store = {"version": 1, "active_profile": "", "profiles": []}
        
        pin = prompt("Enter new PIN: ", secure=True)
        if not pin:
            print("PIN cannot be empty.", file=sys.stderr)
            sys.exit(1)
        
        confirm = prompt("Confirm new PIN: ", secure=True)
        if pin != confirm:
            print("PINs do not match.", file=sys.stderr)
            sys.exit(1)
            
        label = prompt("Enter profile label (optional): ", secure=False)
        if not label:
            label = f"profile-{len(store['profiles']) + 1}"
            
        profile_id = f"id-{len(store['profiles']) + 1}"
        new_profile = {
            "id": profile_id,
            "label": label,
            "pin_hash": hash_pin(pin),
            "created_at": str(os.getpid())
        }
        store["profiles"].append(new_profile)
        store["active_profile"] = profile_id
        save_store(store)
        set_logged_in(False)
        print(f"PIN registered successfully with profile '{label}' ({profile_id}).")
        print("Run: vpn-tool auth login")

    reg_cmd = auth_subparsers.add_parser("register", help="Register a new PIN profile")
    reg_cmd.set_defaults(func=handle_register)

    def handle_login(args):
        store = load_store()
        if store is None or not store.get("profiles"):
            print("No PIN registered. Run: vpn-tool auth register", file=sys.stderr)
            sys.exit(1)
            
        pin = prompt("Enter PIN: ", secure=True)
        hashed = hash_pin(pin)
        matched = None
        for p in store["profiles"]:
            if p["pin_hash"] == hashed:
                matched = p
                break
                
        if not matched:
            print("Invalid PIN.", file=sys.stderr)
            sys.exit(1)
            
        store["active_profile"] = matched["id"]
        save_store(store)
        set_logged_in(True)
        print(f"Login successful as profile '{matched['label']}'.")

    login_cmd = auth_subparsers.add_parser("login", help="Login with PIN")
    login_cmd.set_defaults(func=handle_login)

    def handle_logout(args):
        if not registered():
            print("No PIN registered.", file=sys.stderr)
            sys.exit(1)
        store = load_store()
        pin = prompt("Enter PIN: ", secure=True)
        hashed = hash_pin(pin)
        matched = False
        for p in store.get("profiles", []):
            if p["id"] == store.get("active_profile") and p["pin_hash"] == hashed:
                matched = True
                break
        if not matched:
            print("Invalid PIN or active profile mismatch.", file=sys.stderr)
            sys.exit(1)
        set_logged_in(False)
        print("Logout successful.")

    logout_cmd = auth_subparsers.add_parser("logout", help="Logout")
    logout_cmd.set_defaults(func=handle_logout)

    def handle_auth_status(args):
        reg_str = "yes" if registered() else "no"
        log_str = "yes" if logged_in() else "no"
        print(f"Registered: {reg_str}")
        print(f"Logged in: {log_str}")

    astatus_cmd = auth_subparsers.add_parser("status", help="Show authentication status")
    astatus_cmd.set_defaults(func=handle_auth_status)

    def handle_auth_list(args):
        store = load_store()
        if store is None or not store.get("profiles"):
            print("No profiles registered.")
            return
        print("Registered Auth Profiles:")
        for p in store["profiles"]:
            active_marker = "*" if p["id"] == store.get("active_profile") else " "
            print(f"{active_marker} [{p['id']}] Label: {p['label']}")

    alist_cmd = auth_subparsers.add_parser("list", help="List all registered auth profiles")
    alist_cmd.set_defaults(func=handle_auth_list)

    def handle_whoami(args):
        store = load_store()
        active_id = store.get("active_profile") if store else None
        if not store or not active_id:
            print("No active profile.")
            return
        for p in store.get("profiles", []):
            if p["id"] == active_id:
                print(orjson.dumps(p, option=orjson.OPT_INDENT_2).decode("utf-8"))
                return
        print("Active profile not found in store.")

    whoami_cmd = auth_subparsers.add_parser("whoami", help="Show current active auth profile metadata")
    whoami_cmd.set_defaults(func=handle_whoami)

    def handle_switch(args):
        target_id = args.profile_id
        store = load_store()
        if not store:
            print("No profiles registered.", file=sys.stderr)
            sys.exit(1)
        found = False
        for p in store.get("profiles", []):
            if p["id"] == target_id or p["label"] == target_id:
                store["active_profile"] = p["id"]
                found = True
                break
        if not found:
            print(f"Profile '{target_id}' not found.", file=sys.stderr)
            sys.exit(1)
        save_store(store)
        set_logged_in(False)
        print(f"Switched active profile to {target_id}. Please login.")

    switch_cmd = auth_subparsers.add_parser("switch", help="Switch active auth profile")
    switch_cmd.add_argument("profile_id")
    switch_cmd.set_defaults(func=handle_switch)

    def handle_reset(args):
        store = load_store()
        if not store or not store.get("profiles"):
            print("No PIN registered.", file=sys.stderr)
            sys.exit(1)
        current = prompt("Enter current PIN: ", secure=True)
        hashed = hash_pin(current)
        index = -1
        for i, p in enumerate(store["profiles"]):
            if p["id"] == store.get("active_profile") and p["pin_hash"] == hashed:
                index = i
                break
        if index == -1:
            print("Invalid current PIN.", file=sys.stderr)
            sys.exit(1)
        new_pin = prompt("Enter new PIN: ", secure=True)
        if not new_pin:
            print("New PIN cannot be empty.", file=sys.stderr)
            sys.exit(1)
        confirm = prompt("Confirm new PIN: ", secure=True)
        if new_pin != confirm:
            print("PINs do not match.", file=sys.stderr)
            sys.exit(1)
        store["profiles"][index]["pin_hash"] = hash_pin(new_pin)
        save_store(store)
        set_logged_in(False)
        print("PIN reset successfully.")

    reset_cmd = auth_subparsers.add_parser("reset", help="Reset PIN for active profile")
    reset_cmd.set_defaults(func=handle_reset)

    def handle_remove(args):
        if not registered():
            print("No PIN registered.", file=sys.stderr)
            sys.exit(1)
        try:
            get_auth_file().unlink(missing_ok=True)
            get_session_file().unlink(missing_ok=True)
        except Exception:
            pass
        print("Authentication removed.")

    remove_cmd = auth_subparsers.add_parser("remove", help="Remove authentication configuration")
    remove_cmd.set_defaults(func=handle_remove)

    # Server Subcommands
    def handle_serve(args):
        ensure_config()
        host = args.address
        port = int(args.port)
        server_address = (host, port)
        try:
            httpd = HTTPServer(server_address, ProxyHandler)
        except Exception as e:
            print(f"Error starting server on {host}:{port}: {e}", file=sys.stderr)
            sys.exit(1)

        get_server_pid_file().write_text(str(os.getpid()), encoding="utf-8")
        get_server_host_file().write_text(host, encoding="utf-8")
        get_server_port_file().write_text(str(port), encoding="utf-8")
        print(f"vpn-tool server started on http://{host}:{port} ( proxying {API_BASE} )")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            get_server_pid_file().unlink(missing_ok=True)
            get_server_host_file().unlink(missing_ok=True)
            get_server_port_file().unlink(missing_ok=True)
            httpd.server_close()

    serve_cmd = subparsers.add_parser("serve", help="Start VPN tool HTTP proxy server")
    serve_cmd.add_argument("--address", default=DEFAULT_HOST, help="Address to bind the server to (default: localhost)")
    serve_cmd.add_argument("--port", default=str(DEFAULT_PORT), help="Port to run the server on (default: 8765)")
    serve_cmd.set_defaults(func=handle_serve)

    def handle_server_status(args):
        pid_file = get_server_pid_file()
        if not pid_file.exists():
            print("vpn-tool server is NOT running.")
            sys.exit(1)
        
        pid = pid_file.read_text(encoding="utf-8").strip()
        host, port = get_server_endpoint()
        
        try:
            os.kill(int(pid), 0)
            print(f"vpn-tool server is running (PID: {pid}, Address: {host}:{port})")
        except OSError:
            print("vpn-tool server PID file exists, but the process is dead.")
            sys.exit(1)

    server_status_cmd = subparsers.add_parser("server-status", help="Check VPN tool server status")
    server_status_cmd.set_defaults(func=handle_server_status)

    def handle_server_stop(args):
        pid_file = get_server_pid_file()
        if not pid_file.exists():
            print("vpn-tool server is not running.")
            return
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            os.kill(pid, 15)
            print(f"Stopped vpn-tool server (PID: {pid})")
        except Exception as e:
            print(f"Error stopping server: {e}", file=sys.stderr)
        finally:
            get_server_pid_file().unlink(missing_ok=True)
            get_server_host_file().unlink(missing_ok=True)
            get_server_port_file().unlink(missing_ok=True)

    server_stop_cmd = subparsers.add_parser("server-stop", help="Stop VPN tool server")
    server_stop_cmd.set_defaults(func=handle_server_stop)

    # Info Command
    def handle_info(args):
        info_data = {
            "tool": "vpn-tool",
            "version": VERSION,
            "api_base": API_BASE
        }
        print(orjson.dumps({"status": 200, "body": info_data}, option=orjson.OPT_INDENT_2).decode("utf-8"))

    info_cmd = subparsers.add_parser("info", help="Show client version info")
    info_cmd.set_defaults(func=handle_info)

    # API Commands
    healthz_cmd = subparsers.add_parser("healthz", help="Check API health")
    healthz_cmd.set_defaults(func=lambda args: (require_login(), api_request("GET", "/api/healthz")))

    countries_cmd = subparsers.add_parser("countries", help="List VPN countries")
    countries_cmd.set_defaults(func=lambda args: (require_login(), api_request("GET", "/api/vpn/countries")))

    for action in ["create", "connect", "disconnect"]:
        c = subparsers.add_parser(action, help=f"{action.capitalize()} VPN")
        c.add_argument("--country", required=True, help="Country code (required)")
        def make_action_handler(act):
            return lambda args: (require_login(), api_request("POST", f"/api/vpn/{act}?countryCode={args.country}"))
        c.set_defaults(func=make_action_handler(action))

    status_cmd = subparsers.add_parser("status", help="Get VPN status")
    status_cmd.add_argument("--country", required=True, help="Country code (required)")
    status_cmd.set_defaults(func=lambda args: (require_login(), api_request("GET", f"/api/vpn/status?countryCode={args.country}")))

    test_cmd = subparsers.add_parser("test", help="Test API delay")
    test_cmd.add_argument("--ms", default="100", help="Milliseconds")
    test_cmd.set_defaults(func=lambda args: (require_login(), api_request("GET", f"/api/vpn/test/sleep?ms={args.ms}")))

    ip_cmd = subparsers.add_parser("ip", help="Get VPN IP addresses")
    ip_cmd.add_argument("--country", required=True, help="Country code (required)")
    ip_cmd.add_argument("--count", default="10", help="Number of IPs")
    ip_cmd.set_defaults(func=lambda args: (require_login(), api_request("POST", f"/api/vpn/ip?countryCode={args.country}&count={args.count}")))

    parsed_args = parser.parse_args()
    if hasattr(parsed_args, "func"):
        parsed_args.func(parsed_args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
