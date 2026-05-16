import re

with open("index.html", "r", encoding="utf-8") as f:
    lines = f.readlines()

# 1. Find the top block
start_top = -1
end_top = -1

for i, line in enumerate(lines):
    if "<!-- NOMBRE DE COTIZADOR TOP -->" in line:
        start_top = i
    if start_top != -1 and "<!-- CHECKLIST VISITA -->" in line:
        end_top = i
        break

print(f"Top block from {start_top} to {end_top}")

# 2. Find the description block
start_desc = -1
end_desc = -1

for i, line in enumerate(lines):
    if "<!-- BOTTOM: DESCRIPTION & MEDIA -->" in line:
        start_desc = i
    if start_desc != -1 and "<!-- RESTRICCIONES Section (Merged) -->" in line:
        end_desc = i
        break

print(f"Desc block from {start_desc} to {end_desc}")
