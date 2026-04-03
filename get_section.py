import re

with open('index.html', 'r', encoding='utf-8') as f:
    content = f.read()

start = content.find('<!-- 2. REQUERIMIENTO PARA COTIZACION -->')
end = content.find('<!-- 3. COTIZACION PRECONSTRUCCION -->')

print(content[start:end])
