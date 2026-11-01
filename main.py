#!/usr/bin/env python3
"""
Linux System Monitor - Aplicação Desktop Nativa (PyQt5 + QWebEngineView)
Inicia o servidor backend do app.py em uma thread em segundo plano
e exibe o dashboard nativamente através do Chromium integrado via QtWebEngine.
"""

import http.server
import os
import sys
import threading
import time

from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtWebEngineWidgets import QWebEngineView

# Adiciona o diretório do projeto ao sys.path para garantir a importação de app.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app import PORT, NodeMonitorHandler


class SystemMonitorWindow(QMainWindow):
    def __init__(self, server=None):
        super().__init__()
        self.server = server

        # Configurações da janela
        self.setWindowTitle("Linux System Monitor")
        self.resize(1000, 700)

        # Ícone da janela do sistema, se disponível
        icon = QIcon.fromTheme("utilities-system-monitor")
        if not icon.isNull():
            self.setWindowIcon(icon)

        # Componente WebEngine
        self.browser = QWebEngineView(self)
        self.browser.setUrl(QUrl(f"http://localhost:{PORT}"))
        self.setCentralWidget(self.browser)

    def closeEvent(self, event):
        """Garante encerramento do servidor backend ao fechar a janela."""
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception as e:
                print(f"Aviso ao encerrar servidor: {e}")
        event.accept()


def start_backend_server():
    """Inicializa o servidor HTTP do app.py em segundo plano."""
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    server = None
    try:
        server = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), NodeMonitorHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        print(f"Servidor HTTP iniciado em http://localhost:{PORT} (thread daemon)")
    except OSError as e:
        print(f"Servidor na porta {PORT} já está rodando ou não pôde ser vinculado: {e}")
    return server


def main():
    server = start_backend_server()

    # Pequena pausa para garantir que o socket local esteja pronto
    time.sleep(0.3)

    app = QApplication(sys.argv)
    app.setApplicationName("Linux System Monitor")

    # Finalização limpa em caso de saída da aplicação
    if server:
        app.aboutToQuit.connect(lambda: server.shutdown())

    window = SystemMonitorWindow(server=server)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

