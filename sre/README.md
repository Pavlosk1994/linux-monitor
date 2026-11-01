# 📐 Arquitetura SRE, SLOs e Observabilidade

Este diretório contém a especificação formal de Engenharia de Confiabilidade de Sites (**Site Reliability Engineering - SRE**) implementada no **Linux Node Monitor**, permitindo a integração direta com **Prometheus** e **Alertmanager**.

---

## 📊 Matriz de SLOs (Service Level Objectives)

| SLO | SLI (Indicador de Nível de Serviço) | Meta (SLO) | PromQL de Alerta | Severidade |
| :--- | :--- | :--- | :--- | :--- |
| **Saturação de RAM** | `node_memory_usage_ratio` | `< 85%` | `node_memory_usage_ratio > 0.85` | `warning` |
| **Exaustão de RAM** | `node_memory_usage_ratio` | `< 95%` | `node_memory_usage_ratio > 0.95` | `critical` |
| **Qualidade WAN** | `node_network_wan_latency_ms` | `< 50ms (95%)` | `node_network_wan_latency_ms > 150 or node_network_online_status == 0` | `critical` |
| **Espaço em Disco** | `node_disk_usage_ratio{mount="/"}` | `< 85%` | `node_disk_usage_ratio{mount="/"} > 0.85` | `warning` |
| **Resolução DNS** | `node_dns_lookup_latency_ms` | `< 150ms` | `node_dns_lookup_latency_ms > 200` | `warning` |

---

## 🛠️ Como Iniciar a Stack de Observabilidade Local

Para subir o **Prometheus** (porta 9090) e o **Alertmanager** (porta 9093) integrados ao seu **Node Monitor**:

```bash
cd sre
docker compose up -d
```

### URLs de Acesso:
- **Node Monitor Metrics:** [http://localhost:8080/metrics](http://localhost:8080/metrics)
- **Prometheus UI:** [http://localhost:9090](http://localhost:9090)
- **Prometheus Targets:** [http://localhost:9090/targets](http://localhost:9090/targets)
- **Alertmanager UI:** [http://localhost:9093](http://localhost:9093)

---

## 🔄 Fluxo de Alertas para o Agente de IA

1. O **Prometheus** coleta o endpoint `/metrics` a cada **3 segundos**.
2. Quando uma regra de SLO é violada (ex: `node_memory_usage_ratio > 0.85` por 1 minuto), o alerta transita para o estado `FIRING`.
3. O **Alertmanager** recebe o alerta e despacha um webhook HTTP `POST` para o endpoint `/api/ai/webhook` do **Node Monitor**.
4. O **Agente SRE de IA** correlaciona as métricas do alerta com os logs de erro do sistema (`journalctl`) e executa o diagnóstico de Causa Raiz (**RCA**).

---

## 🤖 Agente SRE de IA: Diagnóstico e Causa Raiz (RCA)

O módulo [`ai_agent.py`](ai_agent.py) implementa um motor de correlação inteligente:

- **Context Harvester:** No momento do alerta, captura:
  - Top processos por consumo de memória e CPU via `ps aux`.
  - Logs recentes do `journalctl` com severidade `err..warning`.
  - Evidências de OOM Killer no `dmesg`.
  - Snapshot de telemetria de hardware e rede.
- **RCA Engine Dual-Mode:**
  - **LLM Mode:** Se `GEMINI_API_KEY` estiver configurada, chama o modelo Gemini para síntese aprofundada em linguagem natural.
  - **Deterministic SRE Expert System:** Se offline ou sem chave de API, executa um motor determinístico de regras de engenharia Linux para diagnosticar a causa raiz e listar comandos de mitigação com 100% de disponibilidade.
- **Simulação de Caos para Entrevistas:**
  ```bash
  # Simula um alerta de saturação de RAM e gera o RCA imediatamente:
  curl -X POST http://localhost:8080/api/ai/simulate -H "Content-Type: application/json" -d '{"scenario":"memory"}'
  
  # Consulta o histórico de incidentes diagnosticados:
  curl http://localhost:8080/api/ai/incidents
  ```
