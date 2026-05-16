import re

html_content = open('index.html', 'r', encoding='utf-8').read()

search10 = """<button class="btn btn-primary text-white fw-bold btn-sm px-4 py-2 position-relative d-flex align-items-center" style="font-size: 0.9rem; background-color: #5b9bd5; border-color: #333;" @click="triggerUpload('PLANOS')">
                                        Scope del Trabajo
                                        <div class="position-absolute top-100 start-50 translate-middle-x mt-1 p-1 d-flex align-items-center bg-white" style="font-size: 0.75rem; border: 1px solid #999; border-radius: 2px;">
                                            <span class="me-2 fw-bold text-dark" style="font-size: 0.8rem;">Lectura</span>
                                            <div class="rounded-circle bg-danger me-1" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                            <div class="rounded-circle bg-success" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                            <i class="fas fa-paperclip ms-2 text-dark fs-5"></i>
                                        </div>
                                    </button>"""

replace10 = """<button class="btn btn-primary text-white fw-bold btn-sm px-4 py-2 position-relative d-flex align-items-center" style="font-size: 0.9rem; background-color: #5b9bd5; border-color: #333;" @click="triggerUpload('PLANOS')">
                                        Scope del Trabajo
                                        <div class="position-absolute top-100 start-50 translate-middle-x mt-1 p-1 d-flex align-items-center bg-white" style="font-size: 0.75rem; border: 1px solid #999; border-radius: 2px;">
                                            <span class="me-2 fw-bold text-dark" style="font-size: 0.8rem;">Lectura</span>
                                            <div class="rounded-circle bg-danger me-1" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                            <div class="rounded-circle bg-success" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                            <i class="fas fa-paperclip ms-2 text-dark fs-5"></i>
                                        </div>
                                    </button>"""

search_btn_1 = """<button class="btn btn-primary text-white fw-bold btn-sm px-4 py-2 position-relative d-flex align-items-center" style="font-size: 0.9rem; background-color: #5b9bd5; border-color: #333;" @click="triggerUpload('FOTOS')">
                                        Correo de Cliente
                                        <div class="position-absolute top-100 start-50 translate-middle-x mt-1 p-1 d-flex align-items-center bg-white" style="font-size: 0.75rem; border: 1px solid #999; border-radius: 2px;">
                                            <span class="me-2 fw-bold text-dark" style="font-size: 0.8rem;">Lectura</span>
                                            <div class="rounded-circle bg-danger me-1" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                            <div class="rounded-circle bg-success" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                            <i class="fas fa-paperclip ms-2 text-dark fs-5"></i>
                                        </div>
                                    </button>"""

replace_btn_1 = """<div class="position-relative" style="margin-bottom: 30px;">
                                        <button class="btn btn-primary text-white fw-bold btn-sm px-4 py-2 position-relative d-flex align-items-center" style="font-size: 0.9rem; background-color: #5b9bd5; border-color: #333; z-index: 1;" @click="triggerUpload('FOTOS')">
                                            Correo de Cliente
                                        </button>
                                        <div class="position-absolute top-100 start-50 translate-middle-x p-1 d-flex align-items-center bg-white" style="font-size: 0.75rem; border: 1px solid #999; border-radius: 2px; margin-top: -5px; z-index: 2;">
                                            <span class="me-2 fw-bold text-dark" style="font-size: 0.8rem;">Lectura</span>
                                            <div class="rounded-circle bg-danger me-1" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                            <div class="rounded-circle bg-success" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                            <i class="fas fa-paperclip ms-2 text-dark fs-5"></i>
                                        </div>
                                    </div>"""

html_content = html_content.replace(search_btn_1, replace_btn_1)


search_btn_2 = """<button class="btn btn-outline-secondary bg-white text-dark fw-bold btn-sm px-4 py-2 position-relative d-flex align-items-center" style="font-size: 0.9rem; border-color: #333;" @click="triggerUpload('LAYOUT_DIBUJO')">
                                        <i class="fas fa-map me-2"></i> PLANOS
                                        <div class="position-absolute top-100 start-50 translate-middle-x mt-1 p-1 d-flex align-items-center bg-white" style="font-size: 0.75rem; border: 1px solid #999; border-radius: 2px;">
                                            <span class="me-2 fw-bold text-dark" style="font-size: 0.8rem;">Lectura</span>
                                            <div class="rounded-circle bg-danger me-1" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                            <div class="rounded-circle bg-success" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                            <i class="fas fa-paperclip ms-2 text-dark fs-5"></i>
                                        </div>
                                    </button>"""

replace_btn_2 = """<div class="position-relative" style="margin-bottom: 30px;">
                                        <button class="btn btn-outline-secondary bg-white text-dark fw-bold btn-sm px-4 py-2 position-relative d-flex align-items-center" style="font-size: 0.9rem; border-color: #333; z-index: 1;" @click="triggerUpload('LAYOUT_DIBUJO')">
                                            <i class="fas fa-map me-2"></i> PLANOS
                                        </button>
                                        <div class="position-absolute top-100 start-50 translate-middle-x p-1 d-flex align-items-center bg-white" style="font-size: 0.75rem; border: 1px solid #999; border-radius: 2px; margin-top: -5px; z-index: 2;">
                                            <span class="me-2 fw-bold text-dark" style="font-size: 0.8rem;">Lectura</span>
                                            <div class="rounded-circle bg-danger me-1" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                            <div class="rounded-circle bg-success" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                            <i class="fas fa-paperclip ms-2 text-dark fs-5"></i>
                                        </div>
                                    </div>"""

html_content = html_content.replace(search_btn_2, replace_btn_2)

search_btn_3 = """<button class="btn btn-primary text-white fw-bold btn-sm px-4 py-2 position-relative d-flex align-items-center" style="font-size: 0.9rem; background-color: #5b9bd5; border-color: #333;" @click="triggerUpload('PLANOS')">
                                        Scope del Trabajo
                                        <div class="position-absolute top-100 start-50 translate-middle-x mt-1 p-1 d-flex align-items-center bg-white" style="font-size: 0.75rem; border: 1px solid #999; border-radius: 2px;">
                                            <span class="me-2 fw-bold text-dark" style="font-size: 0.8rem;">Lectura</span>
                                            <div class="rounded-circle bg-danger me-1" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                            <div class="rounded-circle bg-success" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                            <i class="fas fa-paperclip ms-2 text-dark fs-5"></i>
                                        </div>
                                    </button>"""

replace_btn_3 = """<div class="position-relative" style="margin-bottom: 30px;">
                                        <button class="btn btn-primary text-white fw-bold btn-sm px-4 py-2 position-relative d-flex align-items-center" style="font-size: 0.9rem; background-color: #5b9bd5; border-color: #333; z-index: 1;" @click="triggerUpload('PLANOS')">
                                            Scope del Trabajo
                                        </button>
                                        <div class="position-absolute top-100 start-50 translate-middle-x p-1 d-flex align-items-center bg-white" style="font-size: 0.75rem; border: 1px solid #999; border-radius: 2px; margin-top: -5px; z-index: 2;">
                                            <span class="me-2 fw-bold text-dark" style="font-size: 0.8rem;">Lectura</span>
                                            <div class="rounded-circle bg-danger me-1" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                            <div class="rounded-circle bg-success" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                            <i class="fas fa-paperclip ms-2 text-dark fs-5"></i>
                                        </div>
                                    </div>"""

html_content = html_content.replace(search_btn_3, replace_btn_3)

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html_content)
