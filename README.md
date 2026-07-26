# 🖥️ Malicious System Monitor
**Created by Malicious : @M4lic1ous**
<div align="center">

![Python](https://img.shields.io/badge/Python-3.6+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Status](https://img.shields.io/badge/Status-Stable-brightgreen.svg)

**A powerful System Information viewer**

</div>
(https://raw.githubusercontent.com/M4lic1ous/Sys_Info/refs/heads/main/IMG_20260726_215937_346.jpg)
---
## 📋 Features

### 🖥️ System Information
- Operating System & Kernel version
- Hostname & Current User
- System Uptime
- Running Processes count
- SSH status & version

### ⚡ CPU Monitoring
- Real-time overall usage percentage
- Per-core usage visualization
- CPU Model & Architecture
- Physical & Logical core count
- Current frequency
- Temperature monitoring
- Load average (1, 5, 15 minutes)

### 🧠 Memory Management
- Total, Used, Available memory
- Cached & Buffered memory
- Swap usage monitoring
- Visual progress bars with percentages

### 💾 Disk Usage
- Multiple mount points support
- Used/Total space display
- Visual usage bars with color coding:
  - 🟢 Green (0-70%)
  - 🟡 Yellow (70-85%)
  - 🔴 Red (85-100%)

### 🌐 Network Monitoring
- **Public IP with Geolocation:**
  - Country, Region, City, District
  - ZIP Code, Coordinates
  - Timezone, ISP, Organization
- **Interface details:**
  - IPv4 & IPv6 addresses
  - MAC address
  - Real-time RX/TX rates
- Gateway & DNS servers

### 🎮 GPU Support
- NVIDIA GPU detection (via nvidia-smi)
- AMD GPU detection (via rocm-smi)
- Utilization, Memory usage, Temperature
- Vendor detection

### 🔌 Open Ports
- TCP & UDP port listing
- Process information (PID & name)
- Connection states (LISTEN, ESTABLISHED, etc.)
- Local address binding details

---

## 🚀 Installation

### Prerequisites
- Python 3.6 or higher
- Linux-based OS (Ubuntu/Debian/CentOS/Arch)
- Root privileges (for port 80 or firewall operations)
- Internet connection (for geolocation API)

### Quick Install

```bash
# Clone the repository
git clone https://github.com/M4lic1ous/Sys_Info.git
cd Sys_Info

# Make script executable
chmod +x monitor.py

# Run directly
python3 monitor.py
