# 🐧 Linux Node Monitor

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.8+" />
  <img src="https://img.shields.io/badge/Tailwind_CSS-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white" alt="Tailwind CSS" />
  <img src="https://img.shields.io/badge/Linux-FCC624?style=for-the-badge&logo=linux&logoColor=black" alt="Linux" />
  <img src="https://img.shields.io/badge/systemd-integrated-red?style=for-the-badge&logo=gnu-bash&logoColor=white" alt="systemd" />
  <img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="MIT License" />
</p>

<p align="center">
  <strong>Dashboard profissional de monitoramento e telemetria em tempo real para servidores e estações Linux, com visual moderno inspirado no Datadog e Grafana.</strong>
</p>

---

## 🌟 Destaques do Projeto

- **⚡ Zero Dependências Externas (Core):** O servidor web e o coletor de métricas (`app.py`) utilizam **exclusivamente módulos nativos da biblioteca padrão do Python** (`http.server`, `subprocess`, `socket`). Sem necessidade de instalar pacotes pesados para rodar o backend.
- **📐 Exportador Nativo Prometheus & Stack SRE (`/metrics`):** Expõe métricas no padrão oficial OpenMetrics/Prometheus para integração direta com Prometheus e Grafana, acompanhado de manifestos com SLOs e alertas formais em PromQL na pasta `sre/`.
- **🤖 Agente SRE com IA (AIOps & Root Cause Analysis):** Receptor de alertas integrado que intercepta webhooks do Alertmanager ou simulações de caos, coleta evidências do kernel (processos `ps`, logs `journalctl`, `dmesg` OOM) e diagnostica a causa raiz (RCA) com plano de remediação acionável.
- **💥 Central de Incidentes com Simulador de Caos (Live Demo):** Painel AIOps embutido no dashboard com botões de disparo de caos sob demanda (saturação de RAM, queda de link WAN, esgotamento de disco) permitindo demonstrar o diagnóstico de IA ao vivo em entrevistas com cópia de comandos de mitigação em 1 clique.
- **🎨 Interface Moderna em Dark Mode:** Construída com **Tailwind CSS** e ícones **FontAwesome 6**, oferecendo um visual limpo de alta legibilidade inspirado em ferramentas de observabilidade corporativas (Datadog/Grafana).
- **🛡️ Modo Privacidade em 1 Clique (Portfólio Ready):** Botão dedicado no cabeçalho para mascarar instantaneamente dados de rede e identificação (IP Público, IP Local, Gateway LAN, Hostname e DNS) com formato `***.***.*.*`, permitindo tirar prints e gravar demonstrações com total segurança sem expor vulnerabilidades.
- **📈 Telemetria de Hardware em Tempo Real:**
  - **Uso de Memória RAM:** Percentual, memória utilizada vs total em MB e barra de progresso com **alertas dinâmicos por cor** (🟢 `<70%`, 🟡 `<85%`, 🔴 `>85%`).
  - **Armazenamento:** Percentual de uso da partição raiz (`/`) e volume ocupado.
  - **Uptime do Sistema:** Tempo de atividade contínua detalhado.
- **🌐 Monitoramento Completo de Rede & Conectividade:**
  - **Latência WAN:** Ping contínuo para `1.1.1.1` com escala dinâmica (🟢 `<50ms`, 🟡 `<150ms`, 🔴 `>150ms / Offline`).
  - **Gateway LAN:** Detecção automática do roteador e latência local.
  - **Detecção de IPs:** IP Local principal e IP Público (com cache inteligente para zero impacto de performance).
  - **Tráfego em Tempo Real:** Throughput de entrada e saída (Rx/Tx em KB/s e total transferido).
  - **Estados de Sockets:** Contagem de conexões ativas (`ESTABLISHED`, `LISTEN`, `TIME_WAIT`).
  - **DNS:** Identificação do nameserver primário e latência de resolução em milissegundos.
- **🖥️ Modo Desktop Integrado (Opcional):** Wrapper desktop nativo via **PyQt5 / QWebEngine** (`main.py`) para quem deseja usar como aplicativo de janela sem abrir o navegador.
- **⚙️ Inicialização Automática no Boot:** Pronto para integração como serviço de usuário **systemd** com reinício automático (`Restart=always`).

---

## 🚀 Como Executar

### Pré-requisitos
- Distribuição Linux (Ubuntu, Debian, Fedora, Arch, etc.)
- Python 3.8 ou superior

### 1. Executando o Servidor Web (Dashboard no Navegador)

Clone o repositório e inicie o servidor:

```bash
git clone https://github.com/Pavlosk1994/linux-monitor.git
cd linux-monitor

# Executa o servidor nativo na porta 8080
python3 app.py
```

Abra o seu navegador e acesse:
- 🌐 **Dashboard:** [http://localhost:8080](http://localhost:8080)
- 📊 **API JSON:** [http://localhost:8080/api/stats](http://localhost:8080/api/stats)
- 📈 **Métricas Prometheus:** [http://localhost:8080/metrics](http://localhost:8080/metrics)

---

### 2. Executando como Aplicativo Desktop (Janela Nativa)

Caso queira uma janela nativa independente do navegador:

```bash
pip install -r requirements.txt
python3 main.py
```

---

### 3. Configurando para Iniciar no Boot do Linux (Systemd)

Para manter o monitoramento rodando 24/7 em segundo plano:

1. Crie o diretório de serviços do usuário:
   ```bash
   mkdir -p ~/.config/systemd/user
   ```

2. Copie o arquivo de serviço de exemplo e ajuste o caminho se necessário:
   ```bash
   cp linux-monitor.service.example ~/.config/systemd/user/linux-monitor.service
   ```

3. Habilite e inicie o serviço:
   ```bash
   systemctl --user daemon-reload
   systemctl --user enable linux-monitor.service
   systemctl --user start linux-monitor.service
   ```

4. Verifique o status:
   ```bash
   systemctl --user status linux-monitor.service
   ```

---

## 📡 API REST (`/api/stats`)

O servidor expõe um endpoint RESTful de alta velocidade (`< 15ms` de tempo de resposta) com os dados agregados:

```json
{
  "hostname": "pavi-Inspiron-5458",
  "uptime": "up 1 hour, 8 minutes",
  "ram_percent": 73.1,
  "ram_usage": 73.1,
  "disk_percent": 7.0,
  "disk_usage": 7.0,
  "network": {
    "status": "Online",
    "latency_ms": 7.2,
    "local_ip": "192.168.1.9",
    "public_ip": "181.225.xxx.xxx",
    "gateway_ip": "192.168.1.1",
    "gateway_latency_ms": 1.4,
    "traffic": {
      "rx_kb_s": 14.5,
      "tx_kb_s": 2.1,
      "total_rx_mb": 420.5,
      "total_tx_mb": 85.3
    },
    "sockets": {
      "established": 18,
      "listen": 12,
      "time_wait": 4,
      "total": 45
    },
    "dns": {
      "nameserver": "127.0.0.53",
      "dns_latency_ms": 12.4
    }
  },
  "ram": {
    "percent": 73.1,
    "total_mb": 3821,
    "used_mb": 2793,
    "available_mb": 1028
  },
  "disk": {
    "percent": 7.0,
    "mount": "/"
  }
}
```

### 🛣️ Tabela de Endpoints da API

| Rota | Método | Função |
| :--- | :--- | :--- |
| `/` | `GET` | Dashboard Web em Dark Mode (Tailwind CSS + FontAwesome) |
| `/api/stats` | `GET` | Telemetria completa do sistema em formato JSON nativo |
| `/metrics` | `GET` | Métricas no padrão OpenMetrics/Prometheus para scraping |
| `/api/ai/incidents` | `GET` | Histórico dos incidentes e relatórios de Causa Raiz (RCA) |
| `/api/ai/webhook` | `POST` | Receptor de alertas (Webhook) do Prometheus Alertmanager |
| `/api/ai/simulate` | `POST` | Simulação de incidentes de caos para demonstração técnica |

---

## 📂 Estrutura do Projeto

```text
linux-monitor/
├── app.py                         # Servidor HTTP nativo, APIs e coletor Linux
├── index.html                     # Interface Dark Mode (Tailwind CSS + FontAwesome)
├── main.py                        # Wrapper desktop nativo (PyQt5 + QWebEngine)
├── requirements.txt               # Dependências opcionais do modo Desktop
├── linux-monitor.service.example  # Template de serviço systemd para inicialização no boot
├── Linux-Monitor.desktop.example  # Atalho de aplicativo para a Área de Trabalho
├── LICENSE                        # Licença MIT
├── README.md                      # Documentação completa
└── sre/                           # Stack de Observabilidade SRE & AIOps
    ├── ai_agent.py                # Context Harvester e Motor de Causa Raiz (RCA)
    ├── alert.rules.yml            # Regras de alerta formais de SLOs em PromQL
    ├── alertmanager.yml           # Roteamento de alertas para o webhook do Agente de IA
    ├── docker-compose.yml         # Prometheus v2.50 + Alertmanager v0.27
    ├── prometheus.yml             # Scrape config apontando para o Node Monitor
    └── README.md                  # Matriz de SLOs e guia da stack SRE
```

---

## 🛡️ Segurança e Privacidade

Este projeto foi desenhado priorizando a segurança defensiva:
- Nenhuma métrica ou credencial é exposta para serviços externos desnecessários.
- A consulta de IP público utiliza endpoints HTTPS confiáveis com cache local de 60s.
- Em ambientes de demonstração pública ou portfólio web, os dados sensíveis de IP podem ser facilmente mascarados via variáveis de ambiente.

---

## 👤 Autor

Desenvolvido por **Pavlosk da Silva Martins**  
- GitHub: [@Pavlosk1994](https://github.com/Pavlosk1994)
- LinkedIn: [Pavlosk Martins](https://www.linkedin.com/)

---

## 📄 Licença

Este projeto está licenciado sob a Licença MIT - consulte o arquivo [LICENSE](LICENSE) para obter mais detalhes.

