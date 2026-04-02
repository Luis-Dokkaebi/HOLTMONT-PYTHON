import re

html_content = open('index.html', 'r', encoding='utf-8').read()

# Box 3
search3 = """<button class="btn btn-outline-secondary bg-light text-dark fw-bold btn-sm px-3" style="font-size: 0.75rem;" @click="triggerUpload('FOTOS')"><i class="fas fa-camera me-1"></i> FOTOS</button>"""
replace3 = """<button class="btn btn-primary text-white fw-bold btn-sm px-3 position-relative" style="font-size: 0.85rem;" @click="triggerUpload('FOTOS')">
                                        Correo de Cliente
                                        <div class="position-absolute bottom-0 start-50 translate-middle-x mb-n3 p-1 d-flex align-items-center bg-white" style="font-size: 0.75rem; border: 1px solid #999; border-radius: 2px;">
                                            <span class="me-2 fw-bold text-dark" style="font-size: 0.8rem;">Lectura</span>
                                            <div class="rounded-circle bg-danger me-1" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                            <div class="rounded-circle bg-success" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                        </div>
                                        <i class="fas fa-paperclip position-absolute top-50 start-100 translate-middle-y ms-2 text-dark fs-5"></i>
                                    </button>"""
html_content = html_content.replace(search3, replace3)

search4 = """<button class="btn btn-outline-secondary bg-light text-dark fw-bold btn-sm px-3" style="font-size: 0.75rem;" @click="triggerUpload('VIDEOS')"><i class="fas fa-video me-1"></i> VIDEOS</button>"""
replace4 = ""
html_content = html_content.replace(search4, replace4)

search5 = """<button class="btn btn-outline-secondary bg-light text-dark fw-bold btn-sm px-3" style="font-size: 0.75rem;" @click="triggerUpload('LAYOUT_DIBUJO')"><i class="fas fa-drafting-compass me-1"></i> LAYOUT / DIBUJO <i class="fas fa-paperclip ms-1"></i></button>"""
replace5 = """<button class="btn btn-outline-secondary bg-white text-dark fw-bold btn-sm px-3 position-relative" style="font-size: 0.85rem;" @click="triggerUpload('LAYOUT_DIBUJO')">
                                        <i class="fas fa-map me-1"></i> PLANOS
                                        <div class="position-absolute bottom-0 start-50 translate-middle-x mb-n3 p-1 d-flex align-items-center bg-white" style="font-size: 0.75rem; border: 1px solid #999; border-radius: 2px;">
                                            <span class="me-2 fw-bold text-dark" style="font-size: 0.8rem;">Lectura</span>
                                            <div class="rounded-circle bg-danger me-1" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                            <div class="rounded-circle bg-success" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                        </div>
                                        <i class="fas fa-paperclip position-absolute top-50 start-100 translate-middle-y ms-2 text-dark fs-5"></i>
                                    </button>"""
html_content = html_content.replace(search5, replace5)

search6 = """<button class="btn btn-outline-secondary bg-light text-dark fw-bold btn-sm px-3" style="font-size: 0.75rem;" @click="triggerUpload('PLANOS')"><i class="fas fa-map me-1"></i> PLANOS <i class="fas fa-paperclip ms-1"></i></button>"""
replace6 = """<button class="btn btn-primary text-white fw-bold btn-sm px-3 position-relative ms-4" style="font-size: 0.85rem;" @click="triggerUpload('PLANOS')">
                                        Scope del Trabajo
                                        <div class="position-absolute bottom-0 start-50 translate-middle-x mb-n3 p-1 d-flex align-items-center bg-white" style="font-size: 0.75rem; border: 1px solid #999; border-radius: 2px;">
                                            <span class="me-2 fw-bold text-dark" style="font-size: 0.8rem;">Lectura</span>
                                            <div class="rounded-circle bg-danger me-1" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                            <div class="rounded-circle bg-success" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                        </div>
                                        <i class="fas fa-paperclip position-absolute top-50 start-100 translate-middle-y ms-2 text-dark fs-5"></i>
                                    </button>"""
html_content = html_content.replace(search6, replace6)


with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html_content)
