import re

html_content = open('index.html', 'r', encoding='utf-8').read()

search7 = """<div class="d-flex gap-2 pt-2 border-top border-dark border-2 w-100" style="margin-top: -2px;">
                                    <button class="btn btn-primary text-white fw-bold btn-sm px-3 position-relative" style="font-size: 0.85rem;" @click="triggerUpload('FOTOS')">
                                        Correo de Cliente
                                        <div class="position-absolute bottom-0 start-50 translate-middle-x mb-n3 p-1 d-flex align-items-center bg-white" style="font-size: 0.75rem; border: 1px solid #999; border-radius: 2px;">
                                            <span class="me-2 fw-bold text-dark" style="font-size: 0.8rem;">Lectura</span>
                                            <div class="rounded-circle bg-danger me-1" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                            <div class="rounded-circle bg-success" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                        </div>
                                        <i class="fas fa-paperclip position-absolute top-50 start-100 translate-middle-y ms-2 text-dark fs-5"></i>
                                    </button>

                                    <button class="btn btn-outline-secondary bg-white text-dark fw-bold btn-sm px-3 position-relative" style="font-size: 0.85rem;" @click="triggerUpload('LAYOUT_DIBUJO')">
                                        <i class="fas fa-map me-1"></i> PLANOS
                                        <div class="position-absolute bottom-0 start-50 translate-middle-x mb-n3 p-1 d-flex align-items-center bg-white" style="font-size: 0.75rem; border: 1px solid #999; border-radius: 2px;">
                                            <span class="me-2 fw-bold text-dark" style="font-size: 0.8rem;">Lectura</span>
                                            <div class="rounded-circle bg-danger me-1" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                            <div class="rounded-circle bg-success" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                        </div>
                                        <i class="fas fa-paperclip position-absolute top-50 start-100 translate-middle-y ms-2 text-dark fs-5"></i>
                                    </button>
                                    <button class="btn btn-primary text-white fw-bold btn-sm px-3 position-relative ms-4" style="font-size: 0.85rem;" @click="triggerUpload('PLANOS')">
                                        Scope del Trabajo
                                        <div class="position-absolute bottom-0 start-50 translate-middle-x mb-n3 p-1 d-flex align-items-center bg-white" style="font-size: 0.75rem; border: 1px solid #999; border-radius: 2px;">
                                            <span class="me-2 fw-bold text-dark" style="font-size: 0.8rem;">Lectura</span>"""

replace7 = """<div class="d-flex gap-4 pt-3 pb-3 border-top border-dark border-2 w-100" style="margin-top: -2px;">
                                    <button class="btn btn-primary text-white fw-bold btn-sm px-4 py-2 position-relative d-flex align-items-center" style="font-size: 0.9rem; background-color: #5b9bd5; border-color: #333;" @click="triggerUpload('FOTOS')">
                                        Correo de Cliente
                                        <div class="position-absolute top-100 start-50 translate-middle-x mt-1 p-1 d-flex align-items-center bg-white" style="font-size: 0.75rem; border: 1px solid #999; border-radius: 2px;">
                                            <span class="me-2 fw-bold text-dark" style="font-size: 0.8rem;">Lectura</span>
                                            <div class="rounded-circle bg-danger me-1" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                            <div class="rounded-circle bg-success" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                            <i class="fas fa-paperclip ms-2 text-dark fs-5"></i>
                                        </div>
                                    </button>

                                    <button class="btn btn-outline-secondary bg-white text-dark fw-bold btn-sm px-4 py-2 position-relative d-flex align-items-center" style="font-size: 0.9rem; border-color: #333;" @click="triggerUpload('LAYOUT_DIBUJO')">
                                        <i class="fas fa-map me-2"></i> PLANOS
                                        <div class="position-absolute top-100 start-50 translate-middle-x mt-1 p-1 d-flex align-items-center bg-white" style="font-size: 0.75rem; border: 1px solid #999; border-radius: 2px;">
                                            <span class="me-2 fw-bold text-dark" style="font-size: 0.8rem;">Lectura</span>
                                            <div class="rounded-circle bg-danger me-1" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                            <div class="rounded-circle bg-success" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                            <i class="fas fa-paperclip ms-2 text-dark fs-5"></i>
                                        </div>
                                    </button>

                                    <button class="btn btn-primary text-white fw-bold btn-sm px-4 py-2 position-relative d-flex align-items-center" style="font-size: 0.9rem; background-color: #5b9bd5; border-color: #333;" @click="triggerUpload('PLANOS')">
                                        Scope del Trabajo
                                        <div class="position-absolute top-100 start-50 translate-middle-x mt-1 p-1 d-flex align-items-center bg-white" style="font-size: 0.75rem; border: 1px solid #999; border-radius: 2px;">
                                            <span class="me-2 fw-bold text-dark" style="font-size: 0.8rem;">Lectura</span>"""

html_content = html_content.replace(search7, replace7)

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html_content)
