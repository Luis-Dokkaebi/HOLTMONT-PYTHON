import asyncio
from api.paperclip_agents import run_paperclip_agency

print("Running agency...")
result = run_paperclip_agency("Construir una habitación de 3x3 metros")
print(result)
