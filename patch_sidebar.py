import re

with open("index.html", "r", encoding="utf-8") as f:
    content = f.read()

# Buscamos donde renderiza los módulos especiales (ACCIONES)
# Y donde agrega el botón del editor Pascal para que se vea debajo de 'Pre Work Order'
# O bien en la vista del formulario 'WORKORDER_FORM' para que pueda abrirlo
