# launcher.py
import os
import sys
import webbrowser
import threading
import time
import uvicorn

def open_browser():
    time.sleep(1.5)  # Aguarda 1.5s para o servidor subir
    webbrowser.open("http://127.0.0.1:8000")

if __name__ == "__main__":
    # Garante o diretório de trabalho correto
    if getattr(sys, 'frozen', False):
        os.chdir(os.path.dirname(sys.executable))
    
    # Abre o navegador em thread separada
    threading.Thread(target=open_browser, daemon=True).start()
    
    # Inicia o servidor Uvicorn
    import app
    uvicorn.run(app.app, host="127.0.0.1", port=8000, log_level="info")