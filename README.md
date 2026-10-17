# VPN Tool CLI (`vpn-tool`)

A robust command-line interface (CLI) tool and local proxy server to manage and connect to your VPN Gateway manager securely using PIN authentication.

---

## Features

- **Secure PIN Authentication**: Register, login, switch, and manage multiple secure PIN profiles stored locally in `~/.vpn-tool/auth.json`.
- **Local Proxy Server**: Built-in background server (`vpn-tool serve`) that acts as a secure proxy to the remote VPN gateway API.
- **Full CLI Command Suite**: Easily check API health, list countries, create VPN tunnels, connect, disconnect, test latency, and query IP addresses.
- **High Performance**: Powered by Python, utilizing `httpx` for reliable requests and `orjson` for fast, formatted JSON outputs.

---

## Installation

### Prerequisites
Make sure you have Python 3.8+ installed.

### Install from Source / Repository
1. Clone the repository:
   ```bash
   git clone [https://github.com/getyu565-cyber/vpn-tool.git](https://github.com/getyu565-cyber/vpn-tool.git)
   cd vpn-tool
