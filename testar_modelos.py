#pip install google-genai
from google import genai

import os

# Configure a variável de ambiente GEMINI_API_KEY ou informe sua chave
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", "SUA_CHAVE_AQUI"))

print("Modelos disponíveis para esta chave:")
for m in client.models.list():
    if "generateContent" in m.supported_actions:
        print(f"- {m.name}")