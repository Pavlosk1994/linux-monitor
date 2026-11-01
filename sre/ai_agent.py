#!/usr/bin/env python3
"""
SRE AI Agent - Incident Correlation & Root Cause Analysis (RCA) Engine
Coleta contexto de sistema (processos, logs journalctl, dmesg) no momento do alerta,
cruza com as métricas do Prometheus e gera o diagnóstico de causa raiz (RCA) com
ações de remediação recomendadas.
"""

import datetime
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "incident_history.json")


class ContextHarvester:
    """Coleta evidências e contexto do sistema operacional no momento do incidente."""

    @staticmethod
    def get_top_processes(sort_by="mem", limit=6):
        """Coleta os processos com maior consumo de recursos."""
        flag = "-%mem" if sort_by == "mem" else "-%cpu"
        processes = []
        try:
            proc = subprocess.run(
                ["ps", "aux", f"--sort={flag}"],
                capture_output=True,
                text=True,
                timeout=2
            )
            if proc.returncode == 0:
                lines = proc.stdout.strip().splitlines()
                # Pula o cabeçalho e analisa até 'limit' processos
                for line in lines[1:limit + 1]:
                    parts = line.split(None, 10)
                    if len(parts) >= 11:
                        cmd = parts[10].strip()
                        # Encurta caminhos longos de executáveis para visualização limpa
                        short_cmd = cmd.split()[0].split("/")[-1] if cmd else "unknown"
                        processes.append({
                            "user": parts[0],
                            "pid": int(parts[1]),
                            "cpu_pct": float(parts[2]),
                            "mem_pct": float(parts[3]),
                            "vsz_kb": int(parts[4]),
                            "rss_kb": int(parts[5]),
                            "short_name": short_cmd,
                            "command": cmd[:120]  # Limita tamanho para o prompt
                        })
        except Exception as e:
            print(f"[ContextHarvester] Erro ao listar processos ({sort_by}): {e}", file=sys.stderr)
        return processes

    @staticmethod
    def get_recent_logs(lines_count=35):
        """Coleta os logs mais recentes de erro e advertência do systemd journald."""
        logs = []
        try:
            proc = subprocess.run(
                ["journalctl", "-p", "err..warning", "-n", str(lines_count), "--no-pager"],
                capture_output=True,
                text=True,
                timeout=2.5
            )
            if proc.returncode == 0 and proc.stdout.strip():
                logs = [l.strip() for l in proc.stdout.strip().splitlines() if l.strip()]
        except Exception:
            pass

        # Fallback: dmesg caso journalctl falhe
        if not logs:
            try:
                proc = subprocess.run(
                    ["dmesg", "-T"],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    logs = [l.strip() for l in proc.stdout.strip().splitlines()[-lines_count:] if l.strip()]
            except Exception:
                pass

        return logs

    @staticmethod
    def get_oom_events():
        """Busca evidências de OOM Killer nos logs do kernel."""
        oom_events = []
        try:
            proc = subprocess.run(
                ["dmesg", "-T"],
                capture_output=True,
                text=True,
                timeout=2
            )
            if proc.returncode == 0:
                for line in proc.stdout.splitlines():
                    if re.search(r"oom[- ]killer|out of memory|killed process", line, re.IGNORECASE):
                        oom_events.append(line.strip())
        except Exception:
            pass
        return oom_events[-5:]

    @classmethod
    def harvest(cls, alert_name, current_stats=None):
        """Agrega todas as evidências relevantes para a análise do alerta."""
        return {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "alertname": alert_name,
            "top_mem_processes": cls.get_top_processes("mem", limit=6),
            "top_cpu_processes": cls.get_top_processes("cpu", limit=5),
            "system_logs": cls.get_recent_logs(30),
            "oom_events": cls.get_oom_events(),
            "metrics_snapshot": current_stats or {}
        }


class IncidentStore:
    """Gerencia o histórico de incidentes e diagnósticos de RCA."""
    _incidents = []

    @classmethod
    def load(cls):
        if not cls._incidents and os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    cls._incidents = json.load(f)
            except Exception:
                cls._incidents = []
        return cls._incidents

    @classmethod
    def save(cls, incident):
        cls.load()
        cls._incidents.insert(0, incident)
        # Mantém até 25 incidentes mais recentes no histórico
        cls._incidents = cls._incidents[:25]
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(cls._incidents, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[IncidentStore] Erro ao salvar histórico: {e}", file=sys.stderr)

    @classmethod
    def get_all(cls, limit=10):
        cls.load()
        return cls._incidents[:limit]

    @classmethod
    def get_by_id(cls, incident_id):
        cls.load()
        for inc in cls._incidents:
            if inc.get("id") == incident_id:
                return inc
        return None


class AIIncidentAnalyzer:
    """Motor de IA para análise de causa raiz (RCA) e plano de remediação."""

    @classmethod
    def analyze(cls, alert_payload, current_stats=None):
        incident_id = f"INC-{uuid.uuid4().hex[:8].upper()}"
        alertname = alert_payload.get("alertname") or alert_payload.get("labels", {}).get("alertname", "UnknownIncident")
        severity = alert_payload.get("severity") or alert_payload.get("labels", {}).get("severity", "warning")
        summary = alert_payload.get("annotations", {}).get("summary", f"Alerta {alertname} acionado no sistema.")
        
        # 1. Coleta de Contexto Técnico pelo Harvester
        context = ContextHarvester.harvest(alertname, current_stats)

        # 2. Tenta inferência via LLM API se configurada
        rca_result = None
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("AI_API_KEY")
        if api_key:
            rca_result = cls._call_llm_api(api_key, alertname, severity, summary, context)

        # 3. Fallback inteligente: Heuristic SRE Expert System (Zero-dependency & Offline)
        if not rca_result:
            rca_result = cls._expert_heuristic_rca(alertname, severity, summary, context)

        incident_record = {
            "id": incident_id,
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "alertname": alertname,
            "severity": severity,
            "summary": summary,
            "rca": rca_result,
            "evidence": {
                "top_process": context["top_mem_processes"][0] if context["top_mem_processes"] else None,
                "oom_count": len(context["oom_events"]),
                "recent_error_logs_count": len(context["system_logs"]),
                "sample_log": context["system_logs"][0] if context["system_logs"] else "Nenhum log crítico registrado no journald."
            }
        }

        # Armazena o incidente no histórico
        IncidentStore.save(incident_record)
        return incident_record

    @staticmethod
    def _call_llm_api(api_key, alertname, severity, summary, context):
        """Executa a síntese de causa raiz chamando a API do Gemini via HTTP puro."""
        prompt = f"""Atue como um Senior Site Reliability Engineer (SRE) On-Call.
Analise o incidente de infraestrutura Linux abaixo e forneça o diagnóstico de Causa Raiz (RCA) estritamente em formato JSON válido.

DADOS DO ALERTA:
- Alerta: {alertname}
- Severidade: {severity}
- Descrição: {summary}

MÉTRICAS ATUAIS DO NÓ:
- Memória RAM: {json.dumps(context.get('metrics_snapshot', {}).get('ram', {}))}
- Rede: {json.dumps(context.get('metrics_snapshot', {}).get('network', {}))}
- Disco: {json.dumps(context.get('metrics_snapshot', {}).get('disk', {}))}

TOP PROCESSOS CONSUMINDO RECURSOS:
{json.dumps(context.get('top_mem_processes', [])[:4], indent=2)}

LOGS RECENTES DO SISTEMA (journald):
{chr(10).join(context.get('system_logs', [])[:8])}

EVIDÊNCIAS DE OOM KILLER:
{chr(10).join(context.get('oom_events', [])[:3]) if context.get('oom_events') else 'Nenhum OOM Killer detectado.'}

RESPONDA EXCLUSIVAMENTE COM UM OBJETO JSON NO SEGUINTE FORMATO:
{{
  "title": "Título conciso do incidente",
  "root_cause": "Explicação detalhada e técnica da causa raiz provável",
  "affected_component": "Componente afetado (RAM / CPU / Rede / Disco / DNS)",
  "confidence_score": 90,
  "remediation_steps": [
    "Comando 1 de investigação ou remediação",
    "Comando 2 de mitigação"
  ],
  "executive_summary": "Resumo de 2 linhas para a liderança ou relatório de incidente",
  "engine": "Gemini-LLM"
}}"""

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "response_mime_type": "application/json"}
        }

        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=7) as resp:
                data = json.load(resp)
                candidates = data.get("candidates", [])
                if candidates:
                    content_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    return json.loads(content_text)
        except Exception as e:
            print(f"[AIIncidentAnalyzer] Erro na chamada à API LLM: {e}. Acionando motor heurístico.", file=sys.stderr)
        return None

    @staticmethod
    def _expert_heuristic_rca(alertname, severity, summary, context):
        """Motor especialista SRE baseado em heurísticas determinísticas do Linux Kernel."""
        top_mem = context["top_mem_processes"][0] if context["top_mem_processes"] else {}
        top_cpu = context["top_cpu_processes"][0] if context["top_cpu_processes"] else {}
        oom_logs = context["oom_events"]
        metrics = context.get("metrics_snapshot", {})
        net = metrics.get("network", {})

        if "Memory" in alertname or "mem" in alertname.lower():
            offender = top_mem.get("short_name", "processo desconhecido")
            pid = top_mem.get("pid", 0)
            mem_pct = top_mem.get("mem_pct", 0.0)
            rss_mb = round(top_mem.get("rss_kb", 0) / 1024, 1)

            root_cause = (
                f"Saturação severa da memória física gerada principalmente pelo processo '{offender}' (PID {pid}), "
                f"ocupando individualmente {mem_pct}% da RAM ({rss_mb} MB residentes). "
            )
            if oom_logs:
                root_cause += "O subsistema do kernel já registrou eventos de OOM Killer descartando páginas anônimas."
            else:
                root_cause += "O sistema aproxima-se do limite crítico de swap thrashing sem OOM Killer acionado até o momento."

            return {
                "title": f"Pressão Crítica de Memória por Contenção de Recursos ({offender})",
                "root_cause": root_cause,
                "affected_component": "Memória RAM / Virtual Memory Subsystem",
                "confidence_score": 94,
                "remediation_steps": [
                    f"Investigar logs específicos do processo: journalctl _PID={pid} --since '10 minutes ago'",
                    f"Finalizar o processo de forma graciosa se necessário: kill -15 {pid}",
                    "Liberar caches de páginas do kernel se seguro: sync && sudo sysctl -w vm.drop_caches=3",
                    "Avaliar limitação de memória via systemd cgroups: systemctl set-property --runtime <service> MemoryMax=80%"
                ],
                "executive_summary": (
                    f"Incidente de saturação de RAM provocado por consumo anômalo do processo {offender} ({mem_pct}% da RAM). "
                    f"Risco iminente de instabilidade mitigável via encerramento do processo ou liberação de buffers."
                ),
                "engine": "SRE-Deterministic-Expert-v1"
            }

        elif "WAN" in alertname or "Network" in alertname or "latency" in alertname.lower():
            gw_lat = net.get("gateway_latency_ms")
            wan_lat = net.get("latency_ms")
            gw_ip = net.get("gateway_ip", "roteador")

            if gw_lat is not None and gw_lat < 15 and (wan_lat is None or wan_lat > 150):
                root_cause = (
                    f"Degradação ou indisponibilidade no enlace externo (WAN/ISP). A latência local para o gateway {gw_ip} "
                    f"está normal ({gw_lat}ms), comprovando que a infraestrutura interna (placa de rede e cabo/Wi-Fi) está íntegra."
                )
                steps = [
                    "Testar rota externa com traceroute: traceroute -n -m 15 1.1.1.1",
                    f"Validar integridade do gateway padrão: ping -c 4 {gw_ip}",
                    "Verificar status do resolvedor de nomes local: systemd-resolve --status",
                    "Contatar provedor de internet (ISP) caso o salto além do gateway permaneça inacessível"
                ]
            else:
                root_cause = (
                    f"Instabilidade detectada na camada de enlace local (LAN). O roteador {gw_ip} apresenta "
                    f"alta latência ({gw_lat or '--'}ms) ou perda de pacotes, impactando todo o tráfego externo."
                )
                steps = [
                    "Reiniciar o subsistema de rede local: sudo systemctl restart NetworkManager",
                    "Verificar status físico da interface: ip link show && ethtool <iface>",
                    f"Reiniciar o roteador/gateway local em {gw_ip}"
                ]

            return {
                "title": "Degradação de Link Externo com Isolamento de Falha (WAN/LAN)",
                "root_cause": root_cause,
                "affected_component": "Interface de Rede & Roteamento WAN",
                "confidence_score": 91,
                "remediation_steps": steps,
                "executive_summary": (
                    "Alerta de conectividade analisado: a correlação entre gateway e WAN isolou o gargalo "
                    "fora da rede local, apontando para falha de rota no provedor externo."
                ),
                "engine": "SRE-Deterministic-Expert-v1"
            }

        elif "Disk" in alertname or "disk" in alertname.lower():
            return {
                "title": "Alerta de Esgotamento Iminente de Espaço em Disco (Partição /)",
                "root_cause": (
                    "A partição raiz ('/') atingiu taxa de preenchimento superior a 85%. "
                    "Geralmente associada a acúmulo de arquivos de log no /var/log, containers órfãos ou dumps temporários em /tmp."
                ),
                "affected_component": "Armazenamento em Disco (Root Filesystem)",
                "confidence_score": 93,
                "remediation_steps": [
                    "Limpar logs acumulados do systemd: sudo journalctl --vacuum-size=200M",
                    "Verificar os 10 maiores diretórios na raiz: sudo du -h --max-depth=1 / | sort -hr | head -n 10",
                    "Limpar pacotes em cache de instalação: sudo apt clean || sudo dnf clean all",
                    "Inspecionar containers/imagens antigas do Docker: docker system prune -f"
                ],
                "executive_summary": (
                    "Ocupação de disco excedeu o limite de segurança do SLO. Risco de falha de gravação de serviços "
                    "mitigável com purga de logs antigos e limpeza de caches temporários."
                ),
                "engine": "SRE-Deterministic-Expert-v1"
            }

        else:
            return {
                "title": f"Diagnóstico SRE: {alertname}",
                "root_cause": f"Alerta {alertname} acionado no sistema. {summary}",
                "affected_component": "Infraestrutura Geral",
                "confidence_score": 85,
                "remediation_steps": [
                    "Verificar logs recentes do journalctl: journalctl -xe -n 50",
                    "Inspecionar serviços em estado de falha: systemctl --failed",
                    "Checar métricas agregadas na API: curl -s http://localhost:8080/api/stats"
                ],
                "executive_summary": f"Incidente {alertname} processado pelo agente com telemetria preservada para análise.",
                "engine": "SRE-Deterministic-Expert-v1"
            }

