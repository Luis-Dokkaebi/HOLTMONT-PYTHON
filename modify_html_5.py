import re

html_content = open('index.html', 'r', encoding='utf-8').read()

search9 = """<button class="btn btn-primary text-white fw-bold btn-sm px-4 py-2 position-relative d-flex align-items-center" style="font-size: 0.9rem; background-color: #5b9bd5; border-color: #333;" @click="triggerUpload('PLANOS')">
                                        Scope del Trabajo
                                        <div class="position-absolute top-100 start-50 translate-middle-x mt-1 p-1 d-flex align-items-center bg-white" style="font-size: 0.75rem; border: 1px solid #999; border-radius: 2px;">
                                            <span class="me-2 fw-bold text-dark" style="font-size: 0.8rem;">Lectura</span>
                                            <div class="rounded-circle bg-danger me-1" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                            <div class="rounded-circle bg-success" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                        </div>
                                        <i class="fas fa-paperclip position-absolute top-50 start-100 translate-middle-y ms-2 text-dark fs-5"></i>
                                    </button>"""

replace9 = """<button class="btn btn-primary text-white fw-bold btn-sm px-4 py-2 position-relative d-flex align-items-center" style="font-size: 0.9rem; background-color: #5b9bd5; border-color: #333;" @click="triggerUpload('PLANOS')">
                                        Scope del Trabajo
                                        <div class="position-absolute top-100 start-50 translate-middle-x mt-1 p-1 d-flex align-items-center bg-white" style="font-size: 0.75rem; border: 1px solid #999; border-radius: 2px;">
                                            <span class="me-2 fw-bold text-dark" style="font-size: 0.8rem;">Lectura</span>
                                            <div class="rounded-circle bg-danger me-1" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                            <div class="rounded-circle bg-success" style="width: 15px; height: 15px; border: 1px solid #333;"></div>
                                            <i class="fas fa-paperclip ms-2 text-dark fs-5"></i>
                                        </div>
                                    </button>"""
html_content = html_content.replace(search9, replace9)


with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html_content)
