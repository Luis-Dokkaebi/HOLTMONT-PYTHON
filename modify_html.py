import re

html_content = open('index.html', 'r', encoding='utf-8').read()

# Box 1
search1 = """<div class="flex-grow-1 border border-secondary p-3 bg-light rounded-end" style="min-height: 80px; overflow-y: auto;">
                                    <h6 class="text-muted mb-0 fw-bold" v-if="!engineeringQuestions">Preguntas Precargadas</h6>
                                    <div v-html="formattedEngineeringQuestions" class="markdown-content" v-if="engineeringQuestions"></div>
                                </div>"""

replace1 = """<div class="flex-grow-1 border border-secondary p-3 bg-light rounded-end position-relative" style="min-height: 80px; overflow-y: auto;">
                                    <h6 class="text-muted mb-0 fw-bold text-dark" v-if="!engineeringQuestions" style="font-size: 1.2rem;">Preguntas Precargadas en Automático</h6>
                                    <div v-html="formattedEngineeringQuestions" class="markdown-content" v-if="engineeringQuestions"></div>
                                    <div class="position-absolute bottom-0 end-0 p-1 mb-2 me-2 d-flex align-items-center bg-white" style="font-size: 0.75rem; border: 1px solid #999; border-radius: 2px;">
                                        <span class="me-2 fw-bold text-dark" style="font-size: 0.8rem;">Lectura</span>
                                        <div class="rounded-circle bg-danger me-1" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                        <div class="rounded-circle bg-success" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                    </div>
                                </div>"""

html_content = html_content.replace(search1, replace1)

# Box 2
search2 = """<div class="flex-grow-1 position-relative">
                                    <!-- [MAPEO IA] TEXTAREA ID=sin-id VAR=workorderData.preguntasAdicionales PROPOSITO=Integracion -->
                                    <textarea v-model="workorderData.preguntasAdicionales" class="form-control border-secondary rounded-end w-100 h-100" placeholder="Espacio para el texto" style="resize: none; min-height: 80px;"></textarea>
                                </div>"""

replace2 = """<div class="flex-grow-1 position-relative d-flex flex-column">
                                    <!-- [MAPEO IA] TEXTAREA ID=sin-id VAR=workorderData.preguntasAdicionales PROPOSITO=Integracion -->
                                    <textarea v-model="workorderData.preguntasAdicionales" class="form-control border-secondary rounded-end w-100 h-100" placeholder="Captura de Preguntas Adicionales de Cotizador" style="resize: none; min-height: 80px; font-size: 1.2rem;"></textarea>
                                    <div class="position-absolute bottom-0 end-0 p-1 mb-2 me-2 d-flex align-items-center bg-white" style="font-size: 0.75rem; border: 1px solid #999; border-radius: 2px;">
                                        <span class="me-2 fw-bold text-dark" style="font-size: 0.8rem;">Realizo</span>
                                        <div class="rounded-circle bg-danger me-1" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                        <div class="rounded-circle bg-success" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                    </div>
                                </div>"""

html_content = html_content.replace(search2, replace2)

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html_content)
