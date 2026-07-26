#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import re
import json
import time
import socket
import threading
import http.server
import urllib.request
import urllib.error
import glob
from collections import deque

prev_net = {'rx': {}, 'tx': {}, 'time': 0}
prev_cpu = {}
first_cpu_read = True

def read_proc_file(path):
    try:
        with open(path, 'r') as f:
            return f.readlines()
    except:
        return []

def read_sys_file(path):
    try:
        with open(path, 'r') as f:
            return f.read().strip()
    except:
        return None

def get_cpu_info():
    cpuinfo = read_proc_file('/proc/cpuinfo')
    model = 'Unknown'
    physical_cores = 0
    logical_cores = 0
    freq_mhz = 0

    for line in cpuinfo:
        if 'model name' in line:
            model = line.split(':')[1].strip()
        if 'processor' in line:
            logical_cores += 1
        if 'cpu cores' in line:
            try:
                physical_cores = int(line.split(':')[1].strip())
            except:
                pass
        if 'cpu MHz' in line:
            try:
                freq_mhz = float(line.split(':')[1].strip())
            except:
                pass

    if physical_cores == 0:
        physical_cores = logical_cores
    return model, physical_cores, logical_cores, freq_mhz

def get_cpu_temperature():
    zones = glob.glob('/sys/class/thermal/thermal_zone*/temp')
    if zones:
        temp_raw = read_sys_file(zones[0])
        if temp_raw:
            try:
                return round(int(temp_raw) / 1000.0, 1)
            except:
                pass
    return None

def get_cpu_usage():
    global prev_cpu, first_cpu_read
    stat = read_proc_file('/proc/stat')
    if not stat:
        return 0.0, []

    cpu_lines = [line for line in stat if line.startswith('cpu')]
    now = {}
    for line in cpu_lines:
        parts = line.split()
        if parts[0] == 'cpu':
            name = 'total'
        else:
            name = parts[0]
        values = list(map(int, parts[1:]))
        idle = values[3] + values[4]
        total = sum(values)
        now[name] = (total, idle)

    overall = 0.0
    per_core = []

    if prev_cpu and not first_cpu_read:
        for name, (total, idle) in now.items():
            if name in prev_cpu:
                prev_total, prev_idle = prev_cpu[name]
                delta_total = total - prev_total
                delta_idle = idle - prev_idle
                if delta_total > 0:
                    usage = (1.0 - delta_idle / delta_total) * 100.0
                else:
                    usage = 0.0
                if name == 'total':
                    overall = usage
                else:
                    per_core.append(usage)
    else:
        first_cpu_read = False

    prev_cpu = now
    
    if not per_core and not first_cpu_read:
        return 0.0, []
    
    return overall, per_core

def get_load_avg():
    load = read_proc_file('/proc/loadavg')
    if load:
        parts = load[0].split()
        if len(parts) >= 3:
            try:
                return float(parts[0]), float(parts[1]), float(parts[2])
            except:
                pass
    return 0.0, 0.0, 0.0

def get_memory_info():
    mem = {}
    lines = read_proc_file('/proc/meminfo')
    for line in lines:
        if ':' in line:
            key, val = line.split(':', 1)
            val = val.strip().split()[0]
            try:
                mem[key] = int(val) * 1024
            except:
                pass
    
    total = mem.get('MemTotal', 0)
    free = mem.get('MemFree', 0)
    available = mem.get('MemAvailable', 0)
    buffers = mem.get('Buffers', 0)
    cached = mem.get('Cached', 0)
    sreclaimable = mem.get('SReclaimable', 0)
    
    if available == 0:
        available = free + buffers + cached + sreclaimable
    
    used = total - available
    cached_total = cached + sreclaimable
    
    return {
        'total': total,
        'used': used if used > 0 else 0,
        'free': free,
        'available': available,
        'buffers': buffers,
        'cached': cached_total,
        'percent': (used / total * 100) if total > 0 else 0
    }

def get_swap_info():
    mem = {}
    lines = read_proc_file('/proc/meminfo')
    for line in lines:
        if ':' in line:
            key, val = line.split(':', 1)
            val = val.strip().split()[0]
            try:
                mem[key] = int(val) * 1024
            except:
                pass
    
    total = mem.get('SwapTotal', 0)
    free = mem.get('SwapFree', 0)
    used = total - free
    
    if total > 0:
        percent = (used / total * 100)
    else:
        percent = 0
    
    return {
        'total': total,
        'used': used if used > 0 else 0,
        'free': free,
        'percent': percent
    }

def get_disk_usage():
    try:
        output = subprocess.check_output(['df', '-P', '-B1'], universal_newlines=True)
        lines = output.strip().split('\n')[1:]
        disks = []
        
        important_mounts = ['/', '/home', '/boot', '/var', '/tmp', '/opt', '/usr', '/srv']
        
        for line in lines:
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 6:
                fs, size, used, avail, pct, mount = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]
                
                if mount in important_mounts:
                    try:
                        if mount == '/':
                            mount_display = 'Total Storage'
                        else:
                            mount_display = mount
                        disks.append({
                            'filesystem': fs,
                            'total': int(size),
                            'used': int(used),
                            'free': int(avail),
                            'percent': float(pct.replace('%', '')),
                            'mount': mount_display
                        })
                    except:
                        pass
        
        if not disks:
            for line in lines:
                if not line.strip():
                    continue
                parts = line.split()
                if len(parts) >= 6:
                    fs, size, used, avail, pct, mount = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]
                    if mount == '/':
                        try:
                            disks.append({
                                'filesystem': fs,
                                'total': int(size),
                                'used': int(used),
                                'free': int(avail),
                                'percent': float(pct.replace('%', '')),
                                'mount': 'Total Storage'
                            })
                        except:
                            pass
                    elif mount == '/home':
                        try:
                            disks.append({
                                'filesystem': fs,
                                'total': int(size),
                                'used': int(used),
                                'free': int(avail),
                                'percent': float(pct.replace('%', '')),
                                'mount': mount
                            })
                        except:
                            pass
        
        return disks
    except:
        return []

def get_network_interfaces():
    interfaces = []
    net_path = '/sys/class/net'
    if os.path.isdir(net_path):
        for iface in os.listdir(net_path):
            if iface.startswith('lo') or iface.startswith('docker') or iface.startswith('veth') or iface.startswith('br-') or iface.startswith('virbr'):
                continue
                
            mac_path = os.path.join(net_path, iface, 'address')
            mac = read_sys_file(mac_path) if os.path.exists(mac_path) else 'N/A'
            
            try:
                output = subprocess.check_output(['ip', '-4', 'addr', 'show', iface], universal_newlines=True, stderr=subprocess.DEVNULL)
                ipv4 = re.findall(r'inet (\d+\.\d+\.\d+\.\d+)/\d+', output)
            except:
                ipv4 = []
            
            try:
                output = subprocess.check_output(['ip', '-6', 'addr', 'show', iface], universal_newlines=True, stderr=subprocess.DEVNULL)
                ipv6 = re.findall(r'inet6 ([0-9a-fA-F:]+)/\d+', output)
                ipv6 = [ip for ip in ipv6 if not ip.startswith('fe80')]
            except:
                ipv6 = []
            
            if ipv4 or ipv6:
                interfaces.append({
                    'name': iface,
                    'mac': mac,
                    'ipv4': ipv4,
                    'ipv6': ipv6
                })
    return interfaces

def get_public_ip():
    try:
        with urllib.request.urlopen('https://api.ipify.org?format=json', timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return data.get('ip', 'Unknown')
    except:
        return None

def get_geo_info(ip):
    if not ip or ip == 'Unknown':
        return {'country': 'N/A', 'region': 'N/A', 'city': 'N/A', 'district': 'N/A', 'zip': 'N/A', 'lat': 'N/A', 'lon': 'N/A', 'timezone': 'N/A', 'isp': 'N/A', 'org': 'N/A'}
    try:
        url = f'http://ip-api.com/json/{ip}?fields=status,country,city,isp,regionName,district,zip,lat,lon,timezone,org'
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            if data.get('status') == 'success':
                return {
                    'country': data.get('country', 'N/A'),
                    'region': data.get('regionName', 'N/A'),
                    'city': data.get('city', 'N/A'),
                    'district': data.get('district', 'N/A'),
                    'zip': data.get('zip', 'N/A'),
                    'lat': data.get('lat', 'N/A'),
                    'lon': data.get('lon', 'N/A'),
                    'timezone': data.get('timezone', 'N/A'),
                    'isp': data.get('isp', 'N/A'),
                    'org': data.get('org', 'N/A')
                }
    except:
        pass
    return {'country': 'N/A', 'region': 'N/A', 'city': 'N/A', 'district': 'N/A', 'zip': 'N/A', 'lat': 'N/A', 'lon': 'N/A', 'timezone': 'N/A', 'isp': 'N/A', 'org': 'N/A'}

def get_network_rates():
    global prev_net
    net_dev = read_proc_file('/proc/net/dev')
    if not net_dev:
        return {}
    
    now_time = time.time()
    rates = {}
    for line in net_dev[2:]:
        parts = line.split()
        if len(parts) >= 10:
            iface = parts[0].rstrip(':')
            try:
                rx_bytes = int(parts[1])
                tx_bytes = int(parts[9])
                rates[iface] = {'rx': rx_bytes, 'tx': tx_bytes}
            except:
                pass
    
    result = {}
    if prev_net['time'] > 0:
        delta_time = now_time - prev_net['time']
        if delta_time > 0:
            for iface, cur in rates.items():
                if iface in prev_net['rx'] and iface in prev_net['tx']:
                    rx_delta = cur['rx'] - prev_net['rx'][iface]
                    tx_delta = cur['tx'] - prev_net['tx'][iface]
                    result[iface] = {
                        'rx_rate': max(0, rx_delta / delta_time),
                        'tx_rate': max(0, tx_delta / delta_time)
                    }
    
    prev_net['rx'] = {iface: data['rx'] for iface, data in rates.items()}
    prev_net['tx'] = {iface: data['tx'] for iface, data in rates.items()}
    prev_net['time'] = now_time
    return result

def get_gpu_info():
    gpu = {'exists': False}
    
    try:
        subprocess.check_call(['which', 'nvidia-smi'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            output = subprocess.check_output(
                ['nvidia-smi', '--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu',
                 '--format=csv,noheader,nounits'],
                universal_newlines=True,
                stderr=subprocess.DEVNULL
            )
            lines = output.strip().split('\n')
            if lines and lines[0]:
                parts = lines[0].split(', ')
                if len(parts) >= 5:
                    name = parts[0]
                    util = float(parts[1])
                    mem_used = float(parts[2]) * 1024 * 1024
                    mem_total = float(parts[3]) * 1024 * 1024
                    temp = float(parts[4])
                    gpu = {
                        'exists': True,
                        'model': name,
                        'utilization': util,
                        'memory_used': mem_used,
                        'memory_total': mem_total,
                        'memory_percent': (mem_used / mem_total * 100) if mem_total > 0 else 0,
                        'temperature': temp,
                        'vendor': 'NVIDIA'
                    }
                    return gpu
        except:
            pass
    except:
        pass
    
    try:
        subprocess.check_call(['which', 'rocm-smi'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            output = subprocess.check_output(['rocm-smi', '--showuse', '--showtemp', '--showmeminfo', 'vram'], 
                                           universal_newlines=True, stderr=subprocess.DEVNULL)
            gpu = {'exists': True, 'model': 'AMD GPU', 'utilization': 0, 
                   'memory_used': 0, 'memory_total': 0, 'temperature': 0, 'vendor': 'AMD'}
            return gpu
        except:
            pass
    except:
        pass
    
    return gpu

def get_open_ports():
    tcp_ports_dict = {}
    udp_ports_dict = {}

    try:
        output = subprocess.check_output(['ss', '-tulnp'], universal_newlines=True, stderr=subprocess.DEVNULL)
        lines = output.strip().split('\n')[1:]

        for line in lines:
            if not line.strip():
                continue

            parts = line.split()
            if len(parts) < 6:
                continue

            proto = parts[0]
            state = parts[1]
            local = parts[4]
            process = ' '.join(parts[6:]) if len(parts) > 6 else ''

            addr = ''
            port = 0

            match = re.match(r'^([^:]+):(\d+)$', local)
            if match:
                addr = match.group(1)
                port = int(match.group(2))
            else:
                match = re.match(r'^\[([^\]]+)\]:(\d+)$', local)
                if match:
                    addr = match.group(1)
                    port = int(match.group(2))
                else:
                    parts_local = local.split(':')
                    if len(parts_local) >= 2:
                        port_str = parts_local[-1]
                        if port_str.isdigit():
                            port = int(port_str)
                            addr = ':'.join(parts_local[:-1])
                        else:
                            continue
                    else:
                        continue

            proc_name = ''
            pid = ''
            if process:
                proc_match = re.search(r'users:\(\("([^"]+)",pid=(\d+),fd=\d+\)', process)
                if proc_match:
                    proc_name = proc_match.group(1)
                    pid = proc_match.group(2)
                    process_str = f"{proc_name} (PID: {pid})"
                else:
                    process_str = process
            else:
                process_str = ''

            if proto.startswith('tcp'):
                key = ('tcp', port)
                if key not in tcp_ports_dict:
                    tcp_ports_dict[key] = {'addresses': set(), 'process': process_str, 'state': state}
                tcp_ports_dict[key]['addresses'].add(addr)
            elif proto.startswith('udp'):
                key = ('udp', port)
                if key not in udp_ports_dict:
                    udp_ports_dict[key] = {'addresses': set(), 'process': process_str}
                udp_ports_dict[key]['addresses'].add(addr)

    except Exception:
        pass

    tcp_ports = []
    for (_, port), info in tcp_ports_dict.items():
        addr_str = ', '.join(sorted(info['addresses']))
        tcp_ports.append({
            'port': port,
            'address': addr_str,
            'process': info['process'],
            'state': info['state']
        })

    udp_ports = []
    for (_, port), info in udp_ports_dict.items():
        addr_str = ', '.join(sorted(info['addresses']))
        udp_ports.append({
            'port': port,
            'address': addr_str,
            'process': info['process']
        })

    tcp_ports.sort(key=lambda x: x['port'])
    udp_ports.sort(key=lambda x: x['port'])

    return tcp_ports, udp_ports

def get_system_info():
    os_release = {}
    if os.path.exists('/etc/os-release'):
        try:
            with open('/etc/os-release', 'r') as f:
                for line in f:
                    if '=' in line:
                        k, v = line.strip().split('=', 1)
                        os_release[k] = v.strip('"')
        except:
            pass
    
    distro = os_release.get('PRETTY_NAME', 'Unknown')
    try:
        kernel = subprocess.check_output(['uname', '-r'], universal_newlines=True).strip()
    except:
        kernel = 'Unknown'
    
    uptime_sec = 0
    uptime_file = read_sys_file('/proc/uptime')
    if uptime_file:
        try:
            uptime_sec = float(uptime_file.split()[0])
        except:
            pass
    
    hostname = socket.gethostname()
    user = os.environ.get('USER', os.environ.get('LOGNAME', 'unknown'))
    
    proc_count = 0
    try:
        proc_count = int(subprocess.check_output(['ps', 'aux', '--no-headers', '|', 'wc', '-l'], 
                                                shell=True, universal_newlines=True).strip())
    except:
        try:
            proc_count = int(subprocess.check_output(['ps', 'aux', '|', 'wc', '-l'], 
                                                    shell=True, universal_newlines=True).strip()) - 1
        except:
            proc_count = 0
    
    cpu_model, phys_cores, log_cores, _ = get_cpu_info()
    
    return {
        'distro': distro,
        'kernel': kernel,
        'uptime': uptime_sec,
        'hostname': hostname,
        'user': user,
        'processes': proc_count,
        'cpu_model': cpu_model,
        'cpu_physical': phys_cores,
        'cpu_logical': log_cores
    }

def get_ssh_info():
    ssh_info = {'running': False, 'port': None, 'version': None}
    tcp_ports, _ = get_open_ports()
    for p in tcp_ports:
        if p['port'] == 22:
            ssh_info['running'] = True
            ssh_info['port'] = 22
            break
    try:
        output = subprocess.check_output(['sshd', '-V'], stderr=subprocess.STDOUT, universal_newlines=True)
        match = re.search(r'OpenSSH_([\d.]+p?\d*)', output)
        if match:
            ssh_info['version'] = match.group(1)
    except:
        try:
            output = subprocess.check_output(['ssh', '-V'], stderr=subprocess.STDOUT, universal_newlines=True)
            match = re.search(r'OpenSSH_([\d.]+p?\d*)', output)
            if match:
                ssh_info['version'] = match.group(1)
        except:
            pass
    return ssh_info

def get_network_gateway():
    try:
        output = subprocess.check_output(['ip', 'route', 'show', 'default'], universal_newlines=True, stderr=subprocess.DEVNULL)
        lines = output.strip().split('\n')
        for line in lines:
            if 'default via' in line:
                parts = line.split()
                if len(parts) > 2:
                    return parts[2]
    except:
        pass
    return None

def get_dns_servers():
    servers = []
    try:
        with open('/etc/resolv.conf', 'r') as f:
            for line in f:
                if line.strip().startswith('nameserver'):
                    parts = line.split()
                    if len(parts) >= 2:
                        servers.append(parts[1])
    except:
        pass
    return servers

def get_all_stats():
    try:
        cpu_model, phys_cores, log_cores, freq = get_cpu_info()
        cpu_temp = get_cpu_temperature()
        cpu_overall, cpu_per_core = get_cpu_usage()
        load1, load5, load15 = get_load_avg()
        mem = get_memory_info()
        swap = get_swap_info()
        disks = get_disk_usage()
        interfaces = get_network_interfaces()
        pub_ip = get_public_ip()
        geo = get_geo_info(pub_ip) if pub_ip else {'country': 'N/A', 'region': 'N/A', 'city': 'N/A', 'district': 'N/A', 'zip': 'N/A', 'lat': 'N/A', 'lon': 'N/A', 'timezone': 'N/A', 'isp': 'N/A', 'org': 'N/A'}
        net_rates = get_network_rates()
        gpu = get_gpu_info()
        sys_info = get_system_info()
        tcp_ports, udp_ports = get_open_ports()
        ssh_info = get_ssh_info()
        gateway = get_network_gateway()
        dns = get_dns_servers()

        return {
            'cpu': {
                'model': cpu_model,
                'physical_cores': phys_cores,
                'logical_cores': log_cores,
                'frequency_mhz': freq,
                'temperature': cpu_temp,
                'overall_usage': cpu_overall,
                'per_core': cpu_per_core,
                'load_avg': [load1, load5, load15]
            },
            'memory': mem,
            'swap': swap,
            'disk': disks,
            'network': {
                'interfaces': interfaces,
                'public_ip': pub_ip,
                'geo': geo,
                'rates': net_rates,
                'gateway': gateway,
                'dns': dns
            },
            'gpu': gpu,
            'system': sys_info,
            'ports': {
                'tcp': tcp_ports,
                'udp': udp_ports
            },
            'ssh': ssh_info,
            'timestamp': time.time()
        }
    except Exception as e:
        return {
            'cpu': {'model': 'Error', 'physical_cores': 0, 'logical_cores': 0, 
                    'frequency_mhz': 0, 'temperature': None, 'overall_usage': 0, 
                    'per_core': [], 'load_avg': [0,0,0]},
            'memory': {'total': 0, 'used': 0, 'free': 0, 'available': 0, 
                      'buffers': 0, 'cached': 0, 'percent': 0},
            'swap': {'total': 0, 'used': 0, 'free': 0, 'percent': 0},
            'disk': [],
            'network': {'interfaces': [], 'public_ip': None, 'geo': {}, 'rates': {}, 'gateway': None, 'dns': []},
            'gpu': {'exists': False},
            'system': {'distro': 'Error', 'kernel': 'Error', 'uptime': 0, 
                      'hostname': 'Error', 'user': 'Error', 'processes': 0,
                      'cpu_model': 'Error', 'cpu_physical': 0, 'cpu_logical': 0},
            'ports': {'tcp': [], 'udp': []},
            'ssh': {'running': False, 'port': None, 'version': None},
            'timestamp': time.time()
        }

class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(INDEX_HTML.encode('utf-8'))
        elif self.path == '/api/stats':
            try:
                data = get_all_stats()
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(data).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass

INDEX_HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Malicious · System Monitor</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,300;14..32,400;14..32,500;14..32,600;14..32,700;14..32,800&display=swap" rel="stylesheet" />
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        :root {
            --bg-primary: #060a13;
            --bg-secondary: #0b111f;
            --bg-card: rgba(255,255,255,0.03);
            --bg-card-hover: rgba(255,255,255,0.07);
            --border-color: rgba(255,255,255,0.06);
            --text-primary: #eef3fc;
            --text-secondary: #8a9bb5;
            --text-muted: #5a6a84;

            --neon-blue: #4f8cff;
            --neon-cyan: #4fc9ff;
            --neon-green: #4ade80;
            --neon-yellow: #facc15;
            --neon-orange: #fb923c;
            --neon-red: #f87171;
            --neon-purple: #8b7cf7;
            --neon-pink: #f472b6;
            --neon-teal: #2dd4bf;

            --shadow-card: 0 8px 32px rgba(0,0,0,0.6);
            --radius-lg: 20px;
            --radius-md: 14px;
            --radius-sm: 10px;
            --transition: 0.3s cubic-bezier(0.4,0,0.2,1);
        }

        html { font-size: 15px; }
        body {
            font-family: 'Inter', -apple-system, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            padding: 20px;
            -webkit-font-smoothing: antialiased;
        }

        ::-webkit-scrollbar { width: 4px; height: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--neon-blue); border-radius: 20px; }

        .app { max-width: 1440px; margin: 0 auto; }

        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 16px 24px;
            margin-bottom: 24px;
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-lg);
            backdrop-filter: blur(20px);
            flex-wrap: wrap;
            gap: 12px;
        }

        .logo {
            display: flex;
            align-items: center;
            gap: 10px;
            font-weight: 800;
            font-size: 1.3rem;
            letter-spacing: -0.02em;
            background: linear-gradient(135deg, var(--neon-blue), var(--neon-purple));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .logo svg { width: 28px; height: 28px; flex-shrink: 0; }

        .health-badge {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px 16px;
            background: rgba(74,222,128,0.1);
            border: 1px solid rgba(74,222,128,0.2);
            border-radius: 40px;
            font-size: 0.75rem;
            font-weight: 600;
            color: var(--neon-green);
        }
        .health-badge .dot {
            width: 8px; height: 8px;
            border-radius: 50%;
            background: var(--neon-green);
            animation: pulse-dot 2s ease-in-out infinite;
        }
        @keyframes pulse-dot {
            0%,100% { opacity:1; transform:scale(1); }
            50% { opacity:0.4; transform:scale(0.8); }
        }

        .clock {
            font-size: 0.8rem;
            color: var(--text-secondary);
            font-weight: 500;
            padding: 6px 14px;
            background: rgba(255,255,255,0.04);
            border-radius: 40px;
            border: 1px solid var(--border-color);
        }

        .refresh-btn {
            background: rgba(255,255,255,0.05);
            border: 1px solid var(--border-color);
            color: var(--text-secondary);
            padding: 6px 12px;
            border-radius: 40px;
            cursor: pointer;
            font-size: 0.75rem;
            font-weight: 500;
            transition: var(--transition);
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .refresh-btn:hover {
            background: rgba(255,255,255,0.1);
            color: var(--text-primary);
        }
        .refresh-btn svg { width: 14px; height: 14px; }
        .refresh-btn .spinning { animation: spin 1s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }

        .main-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 18px;
            margin-bottom: 18px;
        }

        .card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-lg);
            padding: 18px 20px;
            transition: var(--transition);
            position: relative;
            overflow: hidden;
        }
        .card:hover {
            border-color: var(--border-glow, var(--neon-blue));
            box-shadow: 0 0 30px rgba(79,140,255,0.05);
        }

        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }
        .card-title {
            display: flex;
            align-items: center;
            gap: 10px;
            font-weight: 600;
            font-size: 0.9rem;
            color: var(--text-primary);
            letter-spacing: -0.01em;
        }
        .card-title svg { width: 22px; height: 22px; flex-shrink: 0; }

        .card-badge {
            font-size: 0.6rem;
            font-weight: 600;
            padding: 3px 12px;
            border-radius: 40px;
            background: rgba(255,255,255,0.05);
            color: var(--text-secondary);
            border: 1px solid var(--border-color);
        }

        .full-width { grid-column: 1 / -1; }
        .half-width { grid-column: span 1; }

        .card-system { --border-glow: var(--neon-blue); }
        .card-system .card-title svg { stroke: var(--neon-blue); }
        .card-system .card-badge { border-color: rgba(79,140,255,0.3); color: var(--neon-blue); }

        .card-cpu { --border-glow: var(--neon-cyan); }
        .card-cpu .card-title svg { stroke: var(--neon-cyan); }
        .card-cpu .card-badge { border-color: rgba(79,201,255,0.3); color: var(--neon-cyan); }

        .card-memory { --border-glow: var(--neon-green); }
        .card-memory .card-title svg { stroke: var(--neon-green); }
        .card-memory .card-badge { border-color: rgba(74,222,128,0.3); color: var(--neon-green); }

        .card-disk { --border-glow: var(--neon-yellow); }
        .card-disk .card-title svg { stroke: var(--neon-yellow); }
        .card-disk .card-badge { border-color: rgba(250,204,21,0.3); color: var(--neon-yellow); }

        .card-gpu { --border-glow: var(--neon-pink); }
        .card-gpu .card-title svg { stroke: var(--neon-pink); }
        .card-gpu .card-badge { border-color: rgba(244,114,182,0.3); color: var(--neon-pink); }

        .card-network { --border-glow: var(--neon-purple); }
        .card-network .card-title svg { stroke: var(--neon-purple); }
        .card-network .card-badge { border-color: rgba(139,124,247,0.3); color: var(--neon-purple); }

        .card-ports { --border-glow: var(--neon-teal); }
        .card-ports .card-title svg { stroke: var(--neon-teal); }
        .card-ports .card-badge { border-color: rgba(45,212,191,0.3); color: var(--neon-teal); }

        .cpu-visual { display: flex; flex-direction: column; gap: 10px; }
        .cpu-metrics {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 4px 16px;
        }
        .cpu-metrics .item {
            display: flex;
            justify-content: space-between;
            padding: 3px 0;
            font-size: 0.78rem;
            border-bottom: 1px solid rgba(255,255,255,0.03);
        }
        .cpu-metrics .item .label { color: var(--text-secondary); }
        .cpu-metrics .item .value { font-weight: 600; }

        .cpu-bars { margin-top: 6px; }
        .cpu-bar-row {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 3px;
        }
        .cpu-bar-row .core-label {
            font-size: 0.6rem;
            color: var(--text-muted);
            width: 28px;
            font-weight: 600;
            text-align: right;
        }
        .cpu-bar-row .track {
            flex: 1;
            height: 6px;
            background: rgba(255,255,255,0.05);
            border-radius: 20px;
            overflow: hidden;
        }
        .cpu-bar-row .track .fill {
            height: 100%;
            border-radius: 20px;
            transition: width 0.6s ease;
            background: linear-gradient(90deg, var(--neon-cyan), var(--neon-blue));
        }
        .cpu-bar-row .pct {
            font-size: 0.6rem;
            color: var(--text-secondary);
            width: 36px;
            text-align: right;
            font-weight: 500;
        }

        .mem-visual { display: flex; flex-direction: column; gap: 8px; }
        .mem-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 3px 0;
            font-size: 0.78rem;
            border-bottom: 1px solid rgba(255,255,255,0.03);
        }
        .mem-row .label { color: var(--text-secondary); }
        .mem-row .value { font-weight: 500; }

        .mem-bar-wrap {
            margin-top: 4px;
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .mem-bar-wrap .track {
            flex: 1;
            height: 8px;
            background: rgba(255,255,255,0.05);
            border-radius: 20px;
            overflow: hidden;
        }
        .mem-bar-wrap .track .fill {
            height: 100%;
            border-radius: 20px;
            transition: width 0.6s ease;
            background: linear-gradient(90deg, var(--neon-green), var(--neon-cyan));
        }
        .mem-bar-wrap .track .fill.high { background: linear-gradient(90deg, var(--neon-orange), var(--neon-red)); }
        .mem-bar-wrap .track .fill.warning { background: linear-gradient(90deg, var(--neon-yellow), var(--neon-orange)); }
        .mem-bar-wrap .pct-text {
            font-size: 0.75rem;
            font-weight: 600;
            color: var(--text-secondary);
            min-width: 40px;
            text-align: right;
        }

        .swap-row { margin-top: 6px; padding-top: 6px; border-top: 1px solid var(--border-color); }
        .swap-bar {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .swap-bar .track {
            flex: 1;
            height: 5px;
            background: rgba(255,255,255,0.05);
            border-radius: 20px;
            overflow: hidden;
            margin-top: 3px;
        }
        .swap-bar .track .fill {
            height: 100%;
            border-radius: 20px;
            transition: width 0.6s ease;
            background: linear-gradient(90deg, var(--neon-purple), var(--neon-pink));
        }
        .swap-bar .pct-text {
            font-size: 0.7rem;
            font-weight: 600;
            color: var(--text-secondary);
            min-width: 36px;
            text-align: right;
        }

        .disk-list { display: flex; flex-direction: column; gap: 8px; }
        .disk-item {
            background: rgba(255,255,255,0.02);
            border-radius: var(--radius-sm);
            padding: 8px 12px;
            border: 1px solid rgba(255,255,255,0.04);
        }
        .disk-item .top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.78rem;
        }
        .disk-item .top .mount { font-weight: 600; }
        .disk-item .top .size { color: var(--text-secondary); }
        .disk-item .track {
            height: 5px;
            background: rgba(255,255,255,0.05);
            border-radius: 20px;
            overflow: hidden;
            margin-top: 3px;
        }
        .disk-item .track .fill { height: 100%; border-radius: 20px; transition: width 0.6s ease; }
        .disk-item .track .fill.green { background: var(--neon-green); }
        .disk-item .track .fill.yellow { background: var(--neon-yellow); }
        .disk-item .track .fill.red { background: var(--neon-red); }

        .gpu-info { display: flex; flex-direction: column; gap: 4px; }
        .gpu-info .row {
            display: flex;
            justify-content: space-between;
            padding: 3px 0;
            font-size: 0.78rem;
            border-bottom: 1px solid rgba(255,255,255,0.03);
        }
        .gpu-info .row .label { color: var(--text-secondary); }
        .gpu-info .row .value { font-weight: 500; }
        .gpu-bar .track {
            height: 5px;
            background: rgba(255,255,255,0.05);
            border-radius: 20px;
            overflow: hidden;
            margin-top: 4px;
        }
        .gpu-bar .track .fill {
            height: 100%;
            border-radius: 20px;
            transition: width 0.6s ease;
            background: linear-gradient(90deg, var(--neon-pink), var(--neon-purple));
        }

        .network-section { display: flex; flex-direction: column; gap: 10px; }
        .net-public {
            background: rgba(79,140,255,0.06);
            border: 1px solid rgba(79,140,255,0.12);
            border-radius: var(--radius-sm);
            padding: 10px 14px;
        }
        .net-public .ip-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.85rem;
            font-weight: 600;
        }
        .net-public .ip-row .ip { color: var(--neon-blue); }
        .net-public .geo-row {
            display: flex;
            flex-direction: column;
            gap: 3px;
            margin-top: 8px;
        }
        .net-public .geo-row .geo-item {
            font-size: 0.75rem;
            color: var(--text-secondary);
            padding: 3px 0;
            border-bottom: 1px solid rgba(255,255,255,0.03);
            display: flex;
            justify-content: space-between;
        }
        .net-public .geo-row .geo-item .geo-label {
            color: var(--text-muted);
            font-weight: 500;
        }
        .net-public .geo-row .geo-item .geo-value {
            color: var(--text-primary);
            font-weight: 500;
        }
        .net-iface {
            background: rgba(255,255,255,0.02);
            border-radius: var(--radius-sm);
            padding: 10px 14px;
            border: 1px solid rgba(255,255,255,0.04);
        }
        .net-iface .top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 4px;
            font-size: 0.78rem;
        }
        .net-iface .top .name { font-weight: 600; }
        .net-iface .top .mac { color: var(--text-muted); font-family: monospace; font-size: 0.65rem; }
        .net-iface .ips { 
            font-size: 0.7rem; 
            color: var(--neon-cyan); 
            font-family: monospace;
            display: flex;
            flex-direction: column;
            gap: 2px;
            margin-top: 2px;
        }
        .net-iface .ips .ip-label {
            color: var(--text-muted);
            font-weight: 600;
            font-size: 0.6rem;
        }
        .net-iface .rates {
            display: flex;
            gap: 20px;
            font-size: 0.7rem;
            margin-top: 4px;
        }
        .net-iface .rates .rx { color: var(--neon-green); }
        .net-iface .rates .tx { color: var(--neon-red); }

        .system-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 6px 20px;
        }
        .system-grid .item {
            display: flex;
            justify-content: space-between;
            padding: 3px 0;
            font-size: 0.78rem;
            border-bottom: 1px solid rgba(255,255,255,0.03);
        }
        .system-grid .item .label { color: var(--text-secondary); }
        .system-grid .item .value { font-weight: 500; }

        .ports-container { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
        .port-table-wrap { max-height: 260px; overflow-y: auto; }
        .port-table-wrap table {
            width: 100%;
            font-size: 0.7rem;
            border-collapse: collapse;
        }
        .port-table-wrap th {
            text-align: left;
            color: var(--text-muted);
            font-weight: 600;
            font-size: 0.6rem;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            padding: 5px 8px;
            border-bottom: 1px solid var(--border-color);
            position: sticky;
            top: 0;
            background: var(--bg-primary);
            z-index: 2;
        }
        .port-table-wrap td {
            padding: 4px 8px;
            border-bottom: 1px solid rgba(255,255,255,0.03);
            color: var(--text-secondary);
        }
        .port-table-wrap .port-num { font-weight: 600; color: var(--neon-blue); font-family: monospace; }
        .port-table-wrap .port-addr { font-family: monospace; font-size: 0.65rem; color: var(--neon-cyan); }
        .port-table-wrap .port-proc { font-size: 0.65rem; color: var(--text-secondary); }
        .port-state {
            display: inline-block;
            padding: 1px 10px;
            border-radius: 20px;
            font-size: 0.55rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }
        .port-state.listen { background: rgba(74,222,128,0.12); color: var(--neon-green); }
        .port-state.established { background: rgba(79,140,255,0.12); color: var(--neon-blue); }
        .port-state.time_wait { background: rgba(250,204,21,0.12); color: var(--neon-yellow); }
        .port-state.close_wait { background: rgba(248,113,113,0.12); color: var(--neon-red); }
        .port-state.unknown { background: rgba(255,255,255,0.04); color: var(--text-muted); }

        .port-count {
            font-size: 0.6rem;
            color: var(--text-muted);
            background: rgba(255,255,255,0.04);
            padding: 0 10px;
            border-radius: 20px;
            font-weight: 500;
        }

        .footer {
            margin-top: 24px;
            padding: 14px 24px;
            text-align: center;
            color: var(--text-muted);
            font-size: 0.7rem;
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-lg);
        }
        .footer .created {
            color: var(--neon-purple);
            font-weight: 600;
            letter-spacing: 0.04em;
        }
        .footer .highlight {
            color: var(--neon-pink);
            font-weight: 700;
        }

        @media (max-width: 1024px) {
            .main-grid { grid-template-columns: 1fr; }
            .half-width { grid-column: 1 / -1; }
            .ports-container { grid-template-columns: 1fr; }
        }
        @media (max-width: 768px) {
            body { padding: 12px; }
            html { font-size: 14px; }
            .header { padding: 12px 16px; }
            .card { padding: 14px; }
        }
        @media (max-width: 480px) {
            .cpu-metrics { grid-template-columns: 1fr; }
            .system-grid { grid-template-columns: 1fr; }
        }
        @media (prefers-reduced-motion: reduce) {
            * { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
        }
    </style>
</head>
<body>
<div class="app">
    <header class="header">
        <div class="logo">
            <svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M16 2L4 9v14l12 7 12-7V9L16 2z" stroke="url(#logo-grad)"/>
                <path d="M16 2v28" stroke="url(#logo-grad)" opacity="0.3"/>
                <path d="M4 9l12 7 12-7" stroke="url(#logo-grad)" opacity="0.5"/>
                <defs><linearGradient id="logo-grad" x1="0" y1="0" x2="32" y2="32">
                    <stop offset="0%" stop-color="#4f8cff"/>
                    <stop offset="100%" stop-color="#8b7cf7"/>
                </linearGradient></defs>
            </svg>
            Malicious Monitor
        </div>
        <div class="health-badge">
            <span class="dot"></span>
            <span id="health-status">Operational</span>
        </div>
        <span class="clock" id="clock">--:--:--</span>
        <button class="refresh-btn" id="refresh-btn">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M23 4v6h-6"/>
                <path d="M1 20v-6h6"/>
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10"/>
                <path d="M20.49 15a9 9 0 0 1-14.85 3.36L1 14"/>
            </svg>
            Refresh
        </button>
    </header>

    <div class="main-grid">
        <div class="card full-width card-system">
            <div class="card-header">
                <div class="card-title">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 6V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v2"/><path d="M6 18v2a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-2"/><path d="M10 10h4" opacity="0.5"/><path d="M10 14h4" opacity="0.5"/></svg>
                    System Information
                </div>
                <span class="card-badge" id="system-badge">Info</span>
            </div>
            <div class="system-grid" id="system-info"></div>
        </div>

        <div class="card half-width card-cpu">
            <div class="card-header">
                <div class="card-title">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 6V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v2"/><path d="M6 18v2a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-2"/><path d="M10 10h4" opacity="0.5"/></svg>
                    CPU
                </div>
                <span class="card-badge" id="cpu-badge">Idle</span>
            </div>
            <div class="cpu-visual">
                <div class="cpu-metrics">
                    <div class="item"><span class="label">Model</span><span class="value" id="cpu-model">--</span></div>
                    <div class="item"><span class="label">Cores</span><span class="value" id="cpu-cores">--</span></div>
                    <div class="item"><span class="label">Frequency</span><span class="value" id="cpu-freq">--</span></div>
                    <div class="item"><span class="label">Temperature</span><span class="value" id="cpu-temp">--</span></div>
                    <div class="item"><span class="label">Load</span><span class="value" id="cpu-load">--</span></div>
                </div>
                <div class="cpu-bars" id="cpu-bars"></div>
            </div>
        </div>

        <div class="card half-width card-memory">
            <div class="card-header">
                <div class="card-title">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 6V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v2"/><path d="M6 18v2a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-2"/><path d="M8 10v4" opacity="0.4"/><path d="M12 10v4" opacity="0.4"/><path d="M16 10v4" opacity="0.4"/></svg>
                    Memory
                </div>
                <span class="card-badge" id="mem-badge">Normal</span>
            </div>
            <div class="mem-visual">
                <div class="mem-row"><span class="label">Total</span><span class="value" id="mem-total">--</span></div>
                <div class="mem-row"><span class="label">Used</span><span class="value" id="mem-used">--</span></div>
                <div class="mem-row"><span class="label">Available</span><span class="value" id="mem-avail">--</span></div>
                <div class="mem-row"><span class="label">Cached</span><span class="value" id="mem-cached">--</span></div>
                <div class="mem-bar-wrap">
                    <div class="track"><div class="fill" id="mem-bar" style="width:0%"></div></div>
                    <span class="pct-text" id="mem-pct">0%</span>
                </div>
                <div class="swap-row">
                    <div class="mem-row"><span class="label">Swap</span><span class="value" id="swap-info">--</span></div>
                    <div class="swap-bar">
                        <div class="track"><div class="fill" id="swap-bar" style="width:0%"></div></div>
                        <span class="pct-text" id="swap-pct">0%</span>
                    </div>
                </div>
            </div>
        </div>

        <div class="card half-width card-disk">
            <div class="card-header">
                <div class="card-title">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 6V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v2"/><path d="M6 18v2a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-2"/><circle cx="8" cy="12" r="1.5"/><circle cx="16" cy="12" r="1.5"/></svg>
                    Disk
                </div>
                <span class="card-badge" id="disk-count">0 devices</span>
            </div>
            <div class="disk-list" id="disk-list"></div>
        </div>

        <div class="card half-width card-gpu" id="gpu-card" style="display:none;">
            <div class="card-header">
                <div class="card-title">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 6V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v2"/><path d="M6 18v2a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-2"/><circle cx="12" cy="12" r="3"/><path d="M9 9l-2-2M15 9l2-2M9 15l-2 2M15 15l2 2"/></svg>
                    GPU
                </div>
                <span class="card-badge" id="gpu-badge">Active</span>
            </div>
            <div class="gpu-info" id="gpu-info"></div>
        </div>

        <div class="card full-width card-network">
            <div class="card-header">
                <div class="card-title">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
                    Network
                </div>
                <span class="card-badge" id="net-badge">Connected</span>
            </div>
            <div class="network-section" id="network-info"></div>
        </div>

        <div class="card full-width card-ports">
            <div class="card-header">
                <div class="card-title">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 6V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v2"/><path d="M6 18v2a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-2"/><path d="M8 10h8M8 14h6"/></svg>
                    Open Ports
                </div>
                <span class="card-badge" id="port-count">0 total</span>
            </div>
            <div class="ports-container">
                <div>
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
                        <span style="font-size:0.7rem;font-weight:600;color:var(--text-secondary);letter-spacing:0.04em;">TCP</span>
                        <span class="port-count" id="tcp-count">0</span>
                    </div>
                    <div class="port-table-wrap"><table><thead><tr><th>Port</th><th>Address</th><th>Process</th><th>State</th></tr></thead><tbody id="tcp-ports-body"></tbody></table></div>
                </div>
                <div>
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
                        <span style="font-size:0.7rem;font-weight:600;color:var(--text-secondary);letter-spacing:0.04em;">UDP</span>
                        <span class="port-count" id="udp-count">0</span>
                    </div>
                    <div class="port-table-wrap"><table><thead><tr><th>Port</th><th>Address</th><th>Process</th></tr></thead><tbody id="udp-ports-body"></tbody></table></div>
                </div>
            </div>
        </div>
    </div>

    <footer class="footer">
        <span class="created">✦ Created by <span class="highlight">Malicious</span> : @<span class="highlight">M4lic1ous</span> ✦</span>
    </footer>
</div>

<script>
    const API = '/api/stats';
    let startTime = Date.now();
    let firstRun = true;
    let refreshInterval = 2200;
    let refreshTimer = null;

    function fmtBytes(b) {
        if (!b || b === 0) return '0 B';
        const k = 1024;
        const u = ['B','KB','MB','GB','TB'];
        const i = Math.floor(Math.log(b) / Math.log(k));
        return parseFloat((b / Math.pow(k, i)).toFixed(1)) + ' ' + u[i];
    }

    function fmtBytesRate(b) {
        if (!b || b === 0) return '0 B/s';
        const k = 1024;
        const u = ['B/s','KB/s','MB/s','GB/s'];
        const i = Math.floor(Math.log(b) / Math.log(k));
        return parseFloat((b / Math.pow(k, i)).toFixed(1)) + ' ' + u[i];
    }

    function fmtDuration(s) {
        if (!s) return '0s';
        const d = Math.floor(s / 86400);
        const h = Math.floor((s % 86400) / 3600);
        const m = Math.floor((s % 3600) / 60);
        const sec = Math.floor(s % 60);
        let parts = [];
        if (d) parts.push(d+'d');
        if (h) parts.push(h+'h');
        if (m) parts.push(m+'m');
        if (sec) parts.push(sec+'s');
        return parts.join(' ') || '0s';
    }

    function getStateClass(state) {
        const s = (state || '').toLowerCase();
        if (s.includes('listen')) return 'listen';
        if (s.includes('established')) return 'established';
        if (s.includes('time_wait') || s.includes('time-wait')) return 'time_wait';
        if (s.includes('close_wait') || s.includes('close-wait')) return 'close_wait';
        return 'unknown';
    }

    function updateClock() {
        const el = document.getElementById('clock');
        if (el) el.textContent = new Date().toLocaleTimeString();
    }
    setInterval(updateClock, 1000);
    updateClock();

    function renderCPU(data) {
        const cpu = data.cpu || {};
        document.getElementById('cpu-model').textContent = cpu.model || '--';
        document.getElementById('cpu-cores').textContent = (cpu.physical_cores||0) + 'P / ' + (cpu.logical_cores||0) + 'L';
        document.getElementById('cpu-freq').textContent = (cpu.frequency_mhz||0).toFixed(0) + ' MHz';
        document.getElementById('cpu-temp').textContent = cpu.temperature ? cpu.temperature + '°C' : '--';
        const load = cpu.load_avg || [0,0,0];
        document.getElementById('cpu-load').textContent = load.map(v => v.toFixed(2)).join(' / ');

        const pct = Math.round(cpu.overall_usage || 0);
        const badge = document.getElementById('cpu-badge');
        if (pct < 30) badge.textContent = 'Idle';
        else if (pct < 60) badge.textContent = 'Moderate';
        else if (pct < 85) badge.textContent = 'Busy';
        else badge.textContent = 'Critical';

        const perCore = cpu.per_core || [];
        const bars = document.getElementById('cpu-bars');
        if (perCore.length) {
            bars.innerHTML = perCore.map((v, i) => `
                <div class="cpu-bar-row">
                    <span class="core-label">C${i}</span>
                    <div class="track"><div class="fill" style="width:${Math.round(v)}%"></div></div>
                    <span class="pct">${Math.round(v)}%</span>
                </div>
            `).join('');
        } else {
            bars.innerHTML = '<div style="color:var(--text-muted);font-size:0.7rem;text-align:center;padding:6px 0;">No per-core data</div>';
        }
    }

    function renderMemory(data) {
        const mem = data.memory || {};
        const swap = data.swap || {};

        document.getElementById('mem-total').textContent = fmtBytes(mem.total);
        document.getElementById('mem-used').textContent = fmtBytes(mem.used);
        document.getElementById('mem-avail').textContent = fmtBytes(mem.available);
        document.getElementById('mem-cached').textContent = fmtBytes(mem.cached);

        const pct = Math.round(mem.percent || 0);
        const bar = document.getElementById('mem-bar');
        bar.style.width = pct + '%';
        bar.className = 'fill';
        if (pct > 85) bar.classList.add('high');
        else if (pct > 70) bar.classList.add('warning');
        document.getElementById('mem-pct').textContent = pct + '%';

        const badge = document.getElementById('mem-badge');
        if (pct < 60) badge.textContent = 'Normal';
        else if (pct < 80) badge.textContent = 'Elevated';
        else if (pct < 90) badge.textContent = 'High';
        else badge.textContent = 'Critical';

        const swapTotal = swap.total || 0;
        const swapUsed = swap.used || 0;
        const swapPct = Math.round(swap.percent || 0);
        document.getElementById('swap-info').textContent = swapTotal > 0 ?
            fmtBytes(swapUsed) + ' / ' + fmtBytes(swapTotal) + ' (' + swapPct + '%)' :
            'Disabled';
        document.getElementById('swap-bar').style.width = swapPct + '%';
        document.getElementById('swap-pct').textContent = swapTotal > 0 ? swapPct + '%' : '0%';
    }

    function renderGPU(data) {
        const gpu = data.gpu || {};
        const card = document.getElementById('gpu-card');
        const info = document.getElementById('gpu-info');

        if (gpu && gpu.exists) {
            card.style.display = 'block';
            const util = Math.round(gpu.utilization || 0);
            const memPct = Math.round(gpu.memory_percent || 0);
            info.innerHTML = `
                <div class="row"><span class="label">Model</span><span class="value">${gpu.model || 'Unknown'}</span></div>
                <div class="row"><span class="label">Vendor</span><span class="value">${gpu.vendor || '--'}</span></div>
                <div class="row"><span class="label">Utilization</span><span class="value">${util}%</span></div>
                <div class="row"><span class="label">Memory</span><span class="value">${fmtBytes(gpu.memory_used||0)} / ${fmtBytes(gpu.memory_total||0)}</span></div>
                <div class="row"><span class="label">Temperature</span><span class="value">${gpu.temperature ? gpu.temperature+'°C' : '--'}</span></div>
                <div class="gpu-bar"><div class="track"><div class="fill" style="width:${memPct}%"></div></div></div>
            `;
            const badge = document.getElementById('gpu-badge');
            if (util < 20) badge.textContent = 'Idle';
            else if (util < 60) badge.textContent = 'Active';
            else badge.textContent = 'Busy';
        } else {
            card.style.display = 'none';
        }
    }

    function renderDisk(data) {
        const disks = data.disk || [];
        const list = document.getElementById('disk-list');
        document.getElementById('disk-count').textContent = disks.length + ' devices';

        if (!disks.length) {
            list.innerHTML = '<div style="color:var(--text-muted);text-align:center;padding:12px;font-size:0.8rem;">No disk data</div>';
            return;
        }

        list.innerHTML = disks.map(d => {
            const pct = Math.round(d.percent || 0);
            let cls = 'green';
            if (pct > 85) cls = 'red';
            else if (pct > 70) cls = 'yellow';
            return `
                <div class="disk-item">
                    <div class="top">
                        <span class="mount">${d.mount || '--'}</span>
                        <span class="size">${fmtBytes(d.used||0)} / ${fmtBytes(d.total||0)}</span>
                        <span style="font-weight:600;font-size:0.7rem;color:${pct > 85 ? 'var(--neon-red)' : pct > 70 ? 'var(--neon-yellow)' : 'var(--neon-green)'}">${pct}%</span>
                    </div>
                    <div class="track"><div class="fill ${cls}" style="width:${pct}%"></div></div>
                </div>
            `;
        }).join('');
    }

    function renderNetwork(data) {
        const net = data.network || {};
        const ifaces = net.interfaces || [];
        const rates = net.rates || {};
        const info = document.getElementById('network-info');

        let html = '';

        if (net.public_ip) {
            html += `
                <div class="net-public">
                    <div class="ip-row">
                        <span>🌐 Public IP</span>
                        <span class="ip">${net.public_ip}</span>
                    </div>
                    <div class="geo-row">
                        ${net.geo && net.geo.country && net.geo.country !== 'N/A' ? `<div class="geo-item"><span class="geo-label">🌍 Country</span><span class="geo-value">${net.geo.country}</span></div>` : ''}
                        ${net.geo && net.geo.region && net.geo.region !== 'N/A' ? `<div class="geo-item"><span class="geo-label">📍 Region</span><span class="geo-value">${net.geo.region}</span></div>` : ''}
                        ${net.geo && net.geo.city && net.geo.city !== 'N/A' ? `<div class="geo-item"><span class="geo-label">🏙️ City</span><span class="geo-value">${net.geo.city}</span></div>` : ''}
                        ${net.geo && net.geo.district && net.geo.district !== 'N/A' ? `<div class="geo-item"><span class="geo-label">🏘️ District</span><span class="geo-value">${net.geo.district}</span></div>` : ''}
                        ${net.geo && net.geo.zip && net.geo.zip !== 'N/A' ? `<div class="geo-item"><span class="geo-label">📮 ZIP Code</span><span class="geo-value">${net.geo.zip}</span></div>` : ''}
                        ${net.geo && net.geo.lat && net.geo.lat !== 'N/A' && net.geo.lon && net.geo.lon !== 'N/A' ? `<div class="geo-item"><span class="geo-label">📍 Coordinates</span><span class="geo-value">${net.geo.lat}, ${net.geo.lon}</span></div>` : ''}
                        ${net.geo && net.geo.timezone && net.geo.timezone !== 'N/A' ? `<div class="geo-item"><span class="geo-label">🕐 Timezone</span><span class="geo-value">${net.geo.timezone}</span></div>` : ''}
                        ${net.geo && net.geo.isp && net.geo.isp !== 'N/A' ? `<div class="geo-item"><span class="geo-label">🔌 ISP</span><span class="geo-value">${net.geo.isp}</span></div>` : ''}
                        ${net.geo && net.geo.org && net.geo.org !== 'N/A' ? `<div class="geo-item"><span class="geo-label">🏢 Organization</span><span class="geo-value">${net.geo.org}</span></div>` : ''}
                        ${net.gateway ? `<div class="geo-item"><span class="geo-label">💠 Gateway</span><span class="geo-value">${net.gateway}</span></div>` : ''}
                        ${net.dns && net.dns.length ? `<div class="geo-item"><span class="geo-label">📡 DNS</span><span class="geo-value">${net.dns.join(', ')}</span></div>` : ''}
                    </div>
                </div>
            `;
        }

        if (ifaces.length) {
            ifaces.forEach(iface => {
                const r = rates[iface.name] || {rx_rate:0, tx_rate:0};
                const rxMB = r.rx_rate / (1024*1024);
                const txMB = r.tx_rate / (1024*1024);
                let ipsHtml = '';
                if (iface.ipv4 && iface.ipv4.length) {
                    ipsHtml += `<div><span class="ip-label">IPv4:</span> ${iface.ipv4.join(', ')}</div>`;
                }
                if (iface.ipv6 && iface.ipv6.length) {
                    ipsHtml += `<div><span class="ip-label">IPv6:</span> ${iface.ipv6.join(', ')}</div>`;
                }
                html += `
                    <div class="net-iface">
                        <div class="top">
                            <span class="name">${iface.name}</span>
                            <span class="mac">${iface.mac}</span>
                        </div>
                        ${ipsHtml ? `<div class="ips">${ipsHtml}</div>` : '<div style="color:var(--text-muted);font-size:0.65rem;">No IP addresses</div>'}
                        <div class="rates">
                            <span class="rx">⬇ ${fmtBytesRate(r.rx_rate)} (${rxMB.toFixed(2)} MB/s)</span>
                            <span class="tx">⬆ ${fmtBytesRate(r.tx_rate)} (${txMB.toFixed(2)} MB/s)</span>
                        </div>
                    </div>
                `;
            });
        } else {
            html += '<div style="color:var(--text-muted);text-align:center;padding:12px;font-size:0.8rem;">No active interfaces</div>';
        }

        info.innerHTML = html;
        document.getElementById('net-badge').textContent = ifaces.length ? 'Connected' : 'No link';
    }

    function renderSystem(data) {
        const sys = data.system || {};
        const ssh = data.ssh || {};
        const grid = document.getElementById('system-info');
        grid.innerHTML = `
            <div class="item"><span class="label">Distro</span><span class="value">${sys.distro || '--'}</span></div>
            <div class="item"><span class="label">Kernel</span><span class="value">${sys.kernel || '--'}</span></div>
            <div class="item"><span class="label">Hostname</span><span class="value">${sys.hostname || '--'}</span></div>
            <div class="item"><span class="label">User</span><span class="value">${sys.user || '--'}</span></div>
            <div class="item"><span class="label">Uptime</span><span class="value">${fmtDuration(sys.uptime)}</span></div>
            <div class="item"><span class="label">Processes</span><span class="value">${sys.processes || 0}</span></div>
            <div class="item"><span class="label">CPU Model</span><span class="value">${sys.cpu_model || '--'}</span></div>
            <div class="item"><span class="label">CPU Cores</span><span class="value">${sys.cpu_physical || 0}P / ${sys.cpu_logical || 0}L</span></div>
            <div class="item"><span class="label">SSH</span><span class="value">${ssh.running ? '🛜 Port '+(ssh.port||22)+' (v'+(ssh.version||'?')+')' : '❌ Not running'}</span></div>
        `;
    }

    function renderPorts(data) {
        const ports = data.ports || { tcp: [], udp: [] };
        const tcp = ports.tcp || [];
        const udp = ports.udp || [];

        document.getElementById('tcp-count').textContent = tcp.length;
        document.getElementById('udp-count').textContent = udp.length;
        document.getElementById('port-count').textContent = (tcp.length + udp.length) + ' total';

        const tcpBody = document.getElementById('tcp-ports-body');
        tcpBody.innerHTML = '';
        if (tcp.length === 0) {
            tcpBody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--text-muted);padding:12px;">No open TCP ports</td></tr>';
        } else {
            tcp.forEach(p => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><span class="port-num">${p.port}</span></td>
                    <td><span class="port-addr">${p.address || '0.0.0.0'}</span></td>
                    <td><span class="port-proc">${p.process || '—'}</span></td>
                    <td><span class="port-state ${getStateClass(p.state)}">${p.state || 'UNKNOWN'}</span></td>
                `;
                tcpBody.appendChild(tr);
            });
        }

        const udpBody = document.getElementById('udp-ports-body');
        udpBody.innerHTML = '';
        if (udp.length === 0) {
            udpBody.innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--text-muted);padding:12px;">No open UDP ports</td></tr>';
        } else {
            udp.forEach(p => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><span class="port-num">${p.port}</span></td>
                    <td><span class="port-addr">${p.address || '0.0.0.0'}</span></td>
                    <td><span class="port-proc">${p.process || '—'}</span></td>
                `;
                udpBody.appendChild(tr);
            });
        }
    }

    function renderAll(data) {
        renderCPU(data);
        renderMemory(data);
        renderGPU(data);
        renderDisk(data);
        renderNetwork(data);
        renderSystem(data);
        renderPorts(data);
        document.getElementById('health-status').textContent = 'Operational';
    }

    function fetchStats() {
        fetch(API)
            .then(r => r.json())
            .then(data => {
                if (firstRun) {
                    if (data.system && data.system.uptime) {
                        startTime = Date.now() - (data.system.uptime * 1000);
                    }
                    firstRun = false;
                }
                renderAll(data);
            })
            .catch(() => {
                document.getElementById('health-status').textContent = 'Error';
            });
    }

    document.getElementById('refresh-btn').addEventListener('click', function() {
        const svg = this.querySelector('svg');
        svg.classList.add('spinning');
        fetchStats();
        setTimeout(() => svg.classList.remove('spinning'), 1000);
    });

    fetchStats();
    refreshTimer = setInterval(fetchStats, refreshInterval);
</script>
</body>
</html>
'''

def open_firewall(port):
    cmds = []
    if subprocess.call(['which', 'ufw'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
        cmds.append(['ufw', 'allow', f'{port}/tcp'])
    if subprocess.call(['which', 'firewall-cmd'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
        cmds.append(['firewall-cmd', '--add-port', f'{port}/tcp', '--permanent'])
        cmds.append(['firewall-cmd', '--reload'])
    if subprocess.call(['which', 'iptables'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
        cmds.append(['iptables', '-I', 'INPUT', '-p', 'tcp', '--dport', str(port), '-j', 'ACCEPT'])

    for cmd in cmds:
        try:
            if os.geteuid() != 0:
                cmd = ['sudo'] + cmd
            subprocess.check_call(cmd, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            print(f"Firewall: opened port {port}")
        except:
            pass

def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        port = s.getsockname()[1]
    return port

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return '127.0.0.1'

def main():
    port = find_free_port()
    print(f"Selected port: {port}")

    open_firewall(port)

    local_ip = get_local_ip()
    public_ip = None
    try:
        with urllib.request.urlopen('https://api.ipify.org', timeout=5) as resp:
            public_ip = resp.read().decode()
    except:
        pass

    server_address = ('', port)
    httpd = http.server.HTTPServer(server_address, DashboardHandler)
    print(f"\n✓ Server started at http://{local_ip}:{port}")
    if public_ip:
        print(f"✓ Public access: http://{public_ip}:{port}")
    print("\nPress Ctrl+C to stop.\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        httpd.shutdown()

if __name__ == '__main__':
    main()
