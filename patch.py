import re

with open("index.html", "r", encoding="utf-8") as f:
    content = f.read()

# Let's add a big visible button for Pascal 3D inside the "2. Requerimiento Pre-Diseños..." section
# Just next to the "Agregar Requerimiento" button

search_str = """<button class="btn btn-primary fw-bold text-white fs-4 py-0 px-3" @click="addProjectItem('reqCotizacion')" title="Agregar Requerimiento">+</button>"""

replace_str = """<!-- BOTON PASCAL 3D -->
                                    <button class="btn btn-info fw-bold text-white shadow-sm" @click="currentView = 'PASCAL_DESIGNER'" title="Abrir Editor 3D" style="display: flex; align-items: center; gap: 8px;">
                                        <i class="fas fa-cube"></i> Editor 3D Pascal
                                    </button>
                                    <button class="btn btn-primary fw-bold text-white fs-4 py-0 px-3" @click="addProjectItem('reqCotizacion')" title="Agregar Requerimiento">+</button>"""

content = content.replace(search_str, replace_str)

with open("index.html", "w", encoding="utf-8") as f:
    f.write(content)
