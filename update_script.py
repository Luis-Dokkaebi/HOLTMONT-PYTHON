import re

with open('index.html', 'r') as f:
    content = f.read()

# Pattern for the object after "workorderData.value = {" where it lacks the new fields
pattern = r"""(workorderData\.value\s*=\s*\{\s*
\s*cliente:\s*'',\s*planta:\s*'',\s*requisitor:\s*'',\s*newRequisitor:\s*'',\s*contactName:\s*'',\s*contacto:\s*'',\s*celular:\s*'',\s*fechaCotizacion:\s*'',\s*proyecto:\s*'',\s*
\s*cotizador:\s*'?',?\s*departamento:\s*'',\s*tipoTrabajo:\s*'',\s*fechaEntrega:\s*'',\s*tiempoEstimado:\s*'',\s*items:\s*\[\],\s*
\s*prioridad:\s*'AAA - Alta Prioridad',\s*conceptoDesc:\s*''\s*)(\};)"""

replacement = r"""\1,
                         checkList: { libreta: false, cinta: false, bernier: false, chaleco: false, laser: false, epp: false, casco: false, credencial: false, zapato: false, sua: false, lentes: false },
                         restricciones: { produccion: '', seguridad: '', dificultad: '', horarios: '', especificidad: '' },
                         files: [],
                         designValidation: { items: [{ diseno: [], maquinados: [], dibujos: [] }] },
                         cotizacion_externa: false,
                         preguntasAdicionales: '',
                         estructuracionAudioText: '',
                         alcanceAdicionalText: ''
                     \2"""

new_content = re.sub(pattern, replacement, content)

with open('index.html', 'w') as f:
    f.write(new_content)
