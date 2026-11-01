#!/usr/bin/env python3
"""
Node Monitor - Servidor Web Simples para Monitoramento Linux
Rotas:
  /          -> Serve o index.html
  /api/stats -> Retorna JSON com métricas de RAM, Disco, Uptime e Hostname
"""

import http.server
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request

PORT = 8080
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(BASE_DIR, "index.html")


def get_hostname():
    """Obtém o nome do host do sistema."""
    try:
        proc = subprocess.run(
            ["hostname"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except Exception:
        pass
    return socket.gethostname()


def get_uptime():
    """Obtém o tempo de atividade (uptime) do sistema."""
    # 1. Tenta uptime formatado amigável (-p)
    try:
        proc = subprocess.run(
            ["uptime", "-p"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except Exception:
        pass

    # 2. Tenta comando uptime padrão
    try:
        proc = subprocess.run(
            ["uptime"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if proc.returncode == 0 and proc.stdout.strip():
            out = proc.stdout.strip()
            match = re.search(r"up\s+(.*?)(?:,\s*\d+\s+user|\s*$)", out)
            if match:
                return f"up {match.group(1).strip()}"
            return out
    except Exception:
        pass

    # 3. Fallback lendo /proc/uptime
    try:
        if os.path.exists("/proc/uptime"):
            with open("/proc/uptime", "r") as f:
                total_seconds = float(f.readline().split()[0])
            days = int(total_seconds // 86400)
            hours = int((total_seconds % 86400) // 3600)
            minutes = int((total_seconds % 3600) // 60)
            parts = []
            if days > 0:
                parts.append(f"{days} dia{'s' if days > 1 else ''}")
            if hours > 0:
                parts.append(f"{hours} hora{'s' if hours > 1 else ''}")
            parts.append(f"{minutes} minuto{'s' if minutes > 1 else ''}")
            return "up " + ", ".join(parts) if parts else "recém iniciado"
    except Exception:
        pass

    return "Indisponível"


def get_ram_stats():
    """Obtém o percentual e valores de uso de RAM."""
    # 1. Tenta usar o comando 'free -m'
    try:
        env = dict(os.environ, LC_ALL="C")
        proc = subprocess.run(
            ["free", "-m"],
            capture_output=True,
            text=True,
            timeout=2,
            env=env
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                if line.lower().startswith("mem"):
                    parts = line.split()
                    total = int(parts[1])
                    used = int(parts[2])
                    # No free moderno a 7ª coluna (índice 6) é available
                    if len(parts) >= 7:
                        avail = int(parts[6])
                        actual_used = total - avail
                    else:
                        avail = int(parts[3])
                        actual_used = used

                    percent = round((actual_used / total) * 100, 1) if total > 0 else 0.0
                    return percent, {
                        "total_mb": total,
                        "used_mb": actual_used,
                        "available_mb": avail
                    }
    except Exception as e:
        print(f"Aviso: erro ao ler memória via free: {e}", file=sys.stderr)

    # 2. Fallback lendo /proc/meminfo
    try:
        meminfo = {}
        if os.path.exists("/proc/meminfo"):
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        key = parts[0].strip()
                        val = int(parts[1].split()[0])
                        meminfo[key] = val
            total = meminfo.get("MemTotal", 0)
            avail = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
            if total > 0:
                used = total - avail
                percent = round((used / total) * 100, 1)
                return percent, {
                    "total_mb": total // 1024,
                    "used_mb": used // 1024,
                    "available_mb": avail // 1024
                }
    except Exception:
        pass

    return 0.0, {"total_mb": 0, "used_mb": 0, "available_mb": 0}


def get_disk_stats():
    """Obtém o percentual de uso da partição raiz '/'."""
    # 1. Tenta usar o comando 'df -P /'
    try:
        env = dict(os.environ, LC_ALL="C")
        proc = subprocess.run(
            ["df", "-P", "/"],
            capture_output=True,
            text=True,
            timeout=2,
            env=env
        )
        if proc.returncode == 0:
            lines = [l.strip() for l in proc.stdout.strip().splitlines() if l.strip()]
            if len(lines) >= 2:
                last_line = lines[-1]
                match = re.search(r"(\d+)%", last_line)
                if match:
                    percent = float(match.group(1))
                    return percent, {"mount": "/"}
    except Exception as e:
        print(f"Aviso: erro ao ler disco via df: {e}", file=sys.stderr)

    # 2. Fallback usando os.statvfs
    try:
        st = os.statvfs("/")
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        used = total - free
        if total > 0:
            percent = round((used / total) * 100, 1)
            return percent, {
                "mount": "/",
                "total_gb": round(total / (1024**3), 1),
                "used_gb": round(used / (1024**3), 1),
                "free_gb": round(free / (1024**3), 1)
            }
    except Exception:
        pass

    return 0.0, {"mount": "/"}


_public_ip_cache = {"ip": None, "last_check": 0}


def get_public_ip():
    """Coleta o IP público com cache de 60 segundos."""
    global _public_ip_cache
    now = time.time()
    if _public_ip_cache["ip"] and (now - _public_ip_cache["last_check"] < 60):
        return _public_ip_cache["ip"]

    try:
        req = urllib.request.Request(
            "https://api.ipify.org",
            headers={"User-Agent": "curl/7.81.0"}
        )
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            ip = resp.read().decode("utf-8").strip()
            if ip:
                _public_ip_cache = {"ip": ip, "last_check": now}
                return ip
    except Exception:
        pass

    try:
        req2 = urllib.request.Request(
            "https://icanhazip.com",
            headers={"User-Agent": "curl/7.81.0"}
        )
        with urllib.request.urlopen(req2, timeout=1.5) as resp:
            ip = resp.read().decode("utf-8").strip()
            if ip:
                _public_ip_cache = {"ip": ip, "last_check": now}
                return ip
    except Exception:
        pass

    return _public_ip_cache["ip"] or "Indisponível"


def ping_target(target, timeout=1):
    """Executa um ping simples para o IP de destino com timeout configurado."""
    if not target:
        return None
    try:
        proc = subprocess.run(
            ["ping", "-c", "1", "-W", str(timeout), target],
            capture_output=True,
            text=True,
            timeout=timeout + 0.5
        )
        if proc.returncode == 0:
            match = re.search(r"time=([\d\.]+)\s*ms", proc.stdout)
            if match:
                return round(float(match.group(1)), 1)
    except Exception:
        pass
    return None


def get_default_gateway():
    """Identifica o IP do gateway padrão (roteador) do sistema."""
    try:
        proc = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True,
            text=True,
            timeout=1.5
        )
        if proc.returncode == 0 and proc.stdout.strip():
            match = re.search(r"default via ([\d\.]+)", proc.stdout)
            if match:
                return match.group(1)
    except Exception:
        pass

    # Fallback via /proc/net/route
    try:
        if os.path.exists("/proc/net/route"):
            with open("/proc/net/route", "r") as f:
                for line in f.readlines()[1:]:
                    parts = line.strip().split()
                    if len(parts) >= 3 and parts[1] == "00000000":
                        gw_hex = parts[2]
                        # Converte hex little-endian para IP
                        ip_parts = [str(int(gw_hex[i:i+2], 16)) for i in (6, 4, 2, 0)]
                        gw_ip = ".".join(ip_parts)
                        if gw_ip != "0.0.0.0":
                            return gw_ip
    except Exception:
        pass

    return None


_traffic_history = {
    "last_time": 0,
    "last_rx": 0,
    "last_tx": 0,
    "rx_kb_s": 0.0,
    "tx_kb_s": 0.0,
    "rx_dropped": 0,
    "tx_dropped": 0,
    "rx_errors": 0,
    "tx_errors": 0,
    "total_rx_mb": 0.0,
    "total_tx_mb": 0.0
}


def get_traffic_stats():
    """Calcula taxa de transferência (Rx/Tx em KB/s), drops e erros via /proc/net/dev."""
    global _traffic_history
    now = time.time()
    rx_bytes = 0
    tx_bytes = 0
    rx_dropped = 0
    tx_dropped = 0
    rx_errors = 0
    tx_errors = 0

    try:
        if os.path.exists("/proc/net/dev"):
            with open("/proc/net/dev", "r") as f:
                lines = f.readlines()[2:]

            non_lo_found = any(':' in l and l.split(':', 1)[0].strip() != 'lo' for l in lines)

            for line in lines:
                if ":" not in line:
                    continue
                iface, data = line.split(":", 1)
                iface = iface.strip()
                if non_lo_found and iface == "lo":
                    continue  # Ignora loopback se existirem interfaces físicas/virtuais

                cols = data.split()
                if len(cols) >= 16:
                    rx_bytes += int(cols[0])
                    rx_errors += int(cols[2])
                    rx_dropped += int(cols[3])
                    tx_bytes += int(cols[8])
                    tx_errors += int(cols[10])
                    tx_dropped += int(cols[11])

            prev_time = _traffic_history["last_time"]
            dt = now - prev_time

            if prev_time > 0 and dt > 0.4:
                delta_rx = max(0, rx_bytes - _traffic_history["last_rx"])
                delta_tx = max(0, tx_bytes - _traffic_history["last_tx"])
                rx_kb_s = round(delta_rx / dt / 1024, 1)
                tx_kb_s = round(delta_tx / dt / 1024, 1)
            else:
                rx_kb_s = _traffic_history["rx_kb_s"]
                tx_kb_s = _traffic_history["tx_kb_s"]

            _traffic_history = {
                "last_time": now,
                "last_rx": rx_bytes,
                "last_tx": tx_bytes,
                "rx_kb_s": rx_kb_s,
                "tx_kb_s": tx_kb_s,
                "rx_dropped": rx_dropped,
                "tx_dropped": tx_dropped,
                "rx_errors": rx_errors,
                "tx_errors": tx_errors,
                "total_rx_mb": round(rx_bytes / (1024 * 1024), 1),
                "total_tx_mb": round(tx_bytes / (1024 * 1024), 1)
            }
    except Exception as e:
        print(f"Aviso ao ler /proc/net/dev: {e}", file=sys.stderr)

    return {
        "rx_kb_s": _traffic_history["rx_kb_s"],
        "tx_kb_s": _traffic_history["tx_kb_s"],
        "rx_dropped": _traffic_history["rx_dropped"],
        "tx_dropped": _traffic_history["tx_dropped"],
        "rx_errors": _traffic_history["rx_errors"],
        "tx_errors": _traffic_history["tx_errors"],
        "total_rx_mb": _traffic_history["total_rx_mb"],
        "total_tx_mb": _traffic_history["total_tx_mb"]
    }


def get_socket_stats():
    """Obtém contagem de estados de conexões TCP e portas em escuta."""
    stats = {
        "established": 0,
        "listen": 0,
        "time_wait": 0,
        "close_wait": 0,
        "total": 0
    }
    try:
        proc = subprocess.run(["ss", "-s"], capture_output=True, text=True, timeout=1.5)
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                if "TCP:" in line:
                    m_est = re.search(r"estab\s+(\d+)", line)
                    if m_est:
                        stats["established"] = int(m_est.group(1))
                    m_tw = re.search(r"timewait\s+(\d+)", line)
                    if m_tw:
                        stats["time_wait"] = int(m_tw.group(1))
                if line.startswith("Total:"):
                    m_tot = re.search(r"Total:\s+(\d+)", line)
                    if m_tot:
                        stats["total"] = int(m_tot.group(1))

        # Portas em escuta (LISTEN)
        proc_l = subprocess.run(["ss", "-tlH"], capture_output=True, text=True, timeout=1.5)
        if proc_l.returncode == 0:
            stats["listen"] = len([l for l in proc_l.stdout.splitlines() if l.strip()])
    except Exception:
        pass

    return stats


def get_dns_stats():
    """Identifica servidor DNS e afere tempo de resolução em ms."""
    primary_ns = "Indisponível"
    try:
        if os.path.exists("/etc/resolv.conf"):
            with open("/etc/resolv.conf", "r") as f:
                for line in f:
                    if line.strip().startswith("nameserver"):
                        parts = line.split()
                        if len(parts) >= 2:
                            primary_ns = parts[1]
                            break
    except Exception:
        pass

    dns_latency_ms = None
    try:
        t0 = time.perf_counter()
        socket.getaddrinfo("cloudflare.com", 80, socket.AF_INET)
        dns_latency_ms = round((time.perf_counter() - t0) * 1000, 1)
    except Exception:
        pass

    return {
        "nameserver": primary_ns,
        "dns_latency_ms": dns_latency_ms
    }


def get_network_stats():
    """Verifica conectividade WAN/LAN, coleta IPs, tráfego, sockets e DNS."""
    # 1. Ping WAN (1.1.1.1)
    wan_latency = ping_target("1.1.1.1", timeout=1)
    status = "Online" if wan_latency is not None else "Offline"

    # 2. Gateway Local e latência LAN
    gateway_ip = get_default_gateway()
    gateway_latency = ping_target(gateway_ip, timeout=1) if gateway_ip else None

    # 3. IP Local principal
    local_ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("1.1.1.1", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        try:
            proc = subprocess.run(
                ["hostname", "-I"],
                capture_output=True,
                text=True,
                timeout=1
            )
            if proc.returncode == 0 and proc.stdout.strip():
                local_ip = proc.stdout.strip().split()[0]
        except Exception:
            pass

    # 4. IP Público
    public_ip = get_public_ip() if status == "Online" else "Desconectado"

    # 5. Métricas avançadas de rede
    traffic = get_traffic_stats()
    sockets = get_socket_stats()
    dns = get_dns_stats()

    return {
        "status": status,
        "latency_ms": wan_latency,
        "local_ip": local_ip,
        "public_ip": public_ip,
        "gateway_ip": gateway_ip or "Não detectado",
        "gateway_latency_ms": gateway_latency,
        "traffic": traffic,
        "sockets": sockets,
        "dns": dns
    }


def get_uptime_seconds():
    """Obtém o tempo de atividade do sistema em segundos (puro float)."""
    try:
        if os.path.exists("/proc/uptime"):
            with open("/proc/uptime", "r") as f:
                return float(f.readline().split()[0])
    except Exception:
        pass
    return 0.0


def generate_prometheus_metrics(stats):
    """Gera métricas no formato padrão de texto do Prometheus / OpenMetrics (RFC 0004)."""
    lines = []
    hostname = stats.get("hostname", "unknown")

    # 1. Informações gerais do Node
    lines.append("# HELP node_info Metadados estaticos do no Linux monitorado")
    lines.append("# TYPE node_info gauge")
    lines.append(f'node_info{{hostname="{hostname}"}} 1')

    # 2. Uptime
    uptime_secs = get_uptime_seconds()
    lines.append("# HELP node_uptime_seconds Tempo de atividade do sistema em segundos")
    lines.append("# TYPE node_uptime_seconds gauge")
    lines.append(f'node_uptime_seconds{{hostname="{hostname}"}} {uptime_secs:.1f}')

    # 3. Memória RAM
    ram = stats.get("ram", {})
    ram_pct = stats.get("ram_percent", 0.0)
    ram_ratio = round(ram_pct / 100.0, 4)
    total_bytes = int(ram.get("total_mb", 0)) * 1024 * 1024
    used_bytes = int(ram.get("used_mb", 0)) * 1024 * 1024
    avail_bytes = int(ram.get("available_mb", 0)) * 1024 * 1024

    lines.append("# HELP node_memory_usage_ratio Razao de uso da memoria RAM (0.0 a 1.0)")
    lines.append("# TYPE node_memory_usage_ratio gauge")
    lines.append(f'node_memory_usage_ratio{{hostname="{hostname}"}} {ram_ratio:.4f}')

    lines.append("# HELP node_memory_total_bytes Total de memoria fisica do sistema em bytes")
    lines.append("# TYPE node_memory_total_bytes gauge")
    lines.append(f'node_memory_total_bytes{{hostname="{hostname}"}} {total_bytes}')

    lines.append("# HELP node_memory_used_bytes Memoria utilizada em bytes (excluindo buffers/cache)")
    lines.append("# TYPE node_memory_used_bytes gauge")
    lines.append(f'node_memory_used_bytes{{hostname="{hostname}"}} {used_bytes}')

    lines.append("# HELP node_memory_available_bytes Memoria disponivel para novos processos em bytes")
    lines.append("# TYPE node_memory_available_bytes gauge")
    lines.append(f'node_memory_available_bytes{{hostname="{hostname}"}} {avail_bytes}')

    # 4. Disco (Raiz /)
    disk = stats.get("disk", {})
    disk_pct = stats.get("disk_percent", 0.0)
    disk_ratio = round(disk_pct / 100.0, 4)
    disk_total = float(disk.get("total_gb", 0)) * (1024**3)
    disk_used = float(disk.get("used_gb", 0)) * (1024**3)

    lines.append("# HELP node_disk_usage_ratio Razao de ocupacao da particao raiz (0.0 a 1.0)")
    lines.append("# TYPE node_disk_usage_ratio gauge")
    lines.append(f'node_disk_usage_ratio{{hostname="{hostname}",mount="/"}} {disk_ratio:.4f}')

    if disk_total > 0:
        lines.append("# HELP node_disk_total_bytes Capacidade total do sistema de arquivos em bytes")
        lines.append("# TYPE node_disk_total_bytes gauge")
        lines.append(f'node_disk_total_bytes{{hostname="{hostname}",mount="/"}} {int(disk_total)}')

        lines.append("# HELP node_disk_used_bytes Espaco utilizado no sistema de arquivos em bytes")
        lines.append("# TYPE node_disk_used_bytes gauge")
        lines.append(f'node_disk_used_bytes{{hostname="{hostname}",mount="/"}} {int(disk_used)}')

    # 5. Rede & Latência (SLIs)
    net = stats.get("network", {})
    is_online = 1 if net.get("status") == "Online" else 0
    lines.append("# HELP node_network_online_status Status de conectividade com a internet (1=Online, 0=Offline)")
    lines.append("# TYPE node_network_online_status gauge")
    lines.append(f'node_network_online_status{{hostname="{hostname}"}} {is_online}')

    wan_lat = net.get("latency_ms")
    if wan_lat is not None:
        lines.append("# HELP node_network_wan_latency_ms Latencia ICMP para o alvo WAN (1.1.1.1) em milissegundos")
        lines.append("# TYPE node_network_wan_latency_ms gauge")
        lines.append(f'node_network_wan_latency_ms{{hostname="{hostname}",target="1.1.1.1"}} {float(wan_lat):.2f}')

    gw_lat = net.get("gateway_latency_ms")
    if gw_lat is not None:
        gw_ip = net.get("gateway_ip", "gateway")
        lines.append("# HELP node_network_gateway_latency_ms Latencia ICMP para o gateway local (LAN) em milissegundos")
        lines.append("# TYPE node_network_gateway_latency_ms gauge")
        lines.append(f'node_network_gateway_latency_ms{{hostname="{hostname}",gateway="{gw_ip}"}} {float(gw_lat):.2f}')

    # Tráfego de Rede
    tr = net.get("traffic", {})
    rx_kb = float(tr.get("rx_kb_s", 0.0))
    tx_kb = float(tr.get("tx_kb_s", 0.0))
    lines.append("# HELP node_network_rx_kb_per_second Taxa instantanea de recepcao de rede em KB/s")
    lines.append("# TYPE node_network_rx_kb_per_second gauge")
    lines.append(f'node_network_rx_kb_per_second{{hostname="{hostname}"}} {rx_kb:.2f}')

    lines.append("# HELP node_network_tx_kb_per_second Taxa instantanea de transmissao de rede em KB/s")
    lines.append("# TYPE node_network_tx_kb_per_second gauge")
    lines.append(f'node_network_tx_kb_per_second{{hostname="{hostname}"}} {tx_kb:.2f}')

    rx_bytes_tot = int(float(tr.get("total_rx_mb", 0.0)) * 1024 * 1024)
    tx_bytes_tot = int(float(tr.get("total_tx_mb", 0.0)) * 1024 * 1024)
    lines.append("# HELP node_network_receive_bytes_total Total de bytes recebidos nas interfaces de rede")
    lines.append("# TYPE node_network_receive_bytes_total counter")
    lines.append(f'node_network_receive_bytes_total{{hostname="{hostname}"}} {rx_bytes_tot}')

    lines.append("# HELP node_network_transmit_bytes_total Total de bytes transmitidos nas interfaces de rede")
    lines.append("# TYPE node_network_transmit_bytes_total counter")
    lines.append(f'node_network_transmit_bytes_total{{hostname="{hostname}"}} {tx_bytes_tot}')

    drops = int(tr.get("rx_dropped", 0)) + int(tr.get("tx_dropped", 0))
    errors = int(tr.get("rx_errors", 0)) + int(tr.get("tx_errors", 0))
    lines.append("# HELP node_network_dropped_packets_total Pacotes descartados nas interfaces de rede")
    lines.append("# TYPE node_network_dropped_packets_total counter")
    lines.append(f'node_network_dropped_packets_total{{hostname="{hostname}"}} {drops}')

    lines.append("# HELP node_network_errors_total Erros de transmissao ou recepcao nas interfaces")
    lines.append("# TYPE node_network_errors_total counter")
    lines.append(f'node_network_errors_total{{hostname="{hostname}"}} {errors}')

    # Sockets TCP
    socks = net.get("sockets", {})
    lines.append("# HELP node_tcp_connections_state Contagem de conexoes TCP ativas por estado")
    lines.append("# TYPE node_tcp_connections_state gauge")
    for st in ("established", "listen", "time_wait", "total"):
        lines.append(f'node_tcp_connections_state{{hostname="{hostname}",state="{st}"}} {socks.get(st, 0)}')

    # DNS
    dns = net.get("dns", {})
    dns_lat = dns.get("dns_latency_ms")
    if dns_lat is not None:
        ns = dns.get("nameserver", "unknown")
        lines.append("# HELP node_dns_lookup_latency_ms Tempo de resolucao de consulta DNS em milissegundos")
        lines.append("# TYPE node_dns_lookup_latency_ms gauge")
        lines.append(f'node_dns_lookup_latency_ms{{hostname="{hostname}",nameserver="{ns}"}} {float(dns_lat):.2f}')

    lines.append("")
    return "\n".join(lines)


def collect_system_stats():
    """Agrega todas as métricas do sistema em um dicionário."""
    hostname = get_hostname()
    uptime = get_uptime()
    ram_percent, ram_details = get_ram_stats()
    disk_percent, disk_details = get_disk_stats()
    network = get_network_stats()

    return {
        "hostname": hostname,
        "uptime": uptime,
        "ram_percent": ram_percent,
        "ram_usage": ram_percent,
        "disk_percent": disk_percent,
        "disk_usage": disk_percent,
        "network": network,
        "network_status": network["status"],
        "latency_ms": network["latency_ms"],
        "local_ip": network["local_ip"],
        "public_ip": network["public_ip"],
        "traffic": network["traffic"],
        "sockets": network["sockets"],
        "dns": network["dns"],
        "ram": {
            "percent": ram_percent,
            **ram_details
        },
        "disk": {
            "percent": disk_percent,
            **disk_details
        }
    }


class NodeMonitorHandler(http.server.BaseHTTPRequestHandler):
    """Manipulador de requisições HTTP para o painel de monitoramento."""

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            self.serve_index()
        elif path == "/api/stats":
            self.serve_stats()
        elif path == "/metrics":
            self.serve_prometheus_metrics()
        else:
            self.send_error(404, "Rota não encontrada")

    def serve_index(self):
        if not os.path.isfile(INDEX_PATH):
            self.send_error(500, f"Arquivo index.html não encontrado em {INDEX_PATH}")
            return

        try:
            with open(INDEX_PATH, "rb") as f:
                content = f.read()

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, f"Erro interno ao ler index.html: {e}")

    def serve_stats(self):
        try:
            stats = collect_system_stats()
            body = json.dumps(stats, ensure_ascii=False, indent=2).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_error(500, f"Erro interno ao gerar métricas: {e}")

    def serve_prometheus_metrics(self):
        try:
            stats = collect_system_stats()
            body = generate_prometheus_metrics(stats).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_error(500, f"Erro interno ao gerar métricas do Prometheus: {e}")

    def log_message(self, format, *args):
        # Log simplificado e limpo no console
        sys.stdout.write(f"[{self.log_date_time_string()}] {self.command} {self.path} - {format % args}\n")
        sys.stdout.flush()


def run_server():
    server_address = ("0.0.0.0", PORT)
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    
    with http.server.ThreadingHTTPServer(server_address, NodeMonitorHandler) as httpd:
        print(f"==================================================")
        print(f" 🚀 Node Monitor iniciado com sucesso!")
        print(f" 🌐 Dashboard acessível em: http://localhost:{PORT}")
        print(f" 📊 API Stats acessível em: http://localhost:{PORT}/api/stats")
        print(f" 📈 Prometheus Exporter em: http://localhost:{PORT}/metrics")
        print(f" 📁 Diretório base: {BASE_DIR}")
        print(f"==================================================")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nEncerrando o servidor Node Monitor...")
            httpd.server_close()


if __name__ == "__main__":
    run_server()
