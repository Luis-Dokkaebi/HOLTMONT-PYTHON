with open("index.html", "r", encoding="utf-8") as f:
    lines = f.readlines()

desc_start = -1
desc_end = -1
for i, line in enumerate(lines):
    if '<h6 class="fw-bold mb-0"><i class="fas fa-robot me-2"></i>Descripción del Trabajo a Realizar' in line:
        desc_start = i - 1 # the <div class="card-header bg-dark...
    if desc_start != -1 and '<!-- Multimedia Section (Merged) -->' in line:
        desc_end = i - 1 # the </div> enclosing the row mb-4
        break

extracted_desc = lines[desc_start:desc_end]
# Remove it from the bottom
lines_removed = lines[:desc_start] + lines[desc_end:]

# At the top, between 1659 and 1692
top_start = -1
top_end = -1
for i, line in enumerate(lines_removed):
    if "<!-- NOMBRE DE COTIZADOR TOP -->" in line:
        top_start = i
    if top_start != -1 and "<!-- CHECKLIST VISITA -->" in line:
        top_end = i
        break

top_block_lines = lines_removed[top_start+1:top_end]

# Make sure to close and open tags appropriately
# In the original, top_block_lines starts with <div class="card border-0 shadow-sm mb-4"> and ends with </div>
new_top_section = [
    '                <!-- TOP ROW SECTION -->\n',
    '                <div class="row mb-4">\n',
    '                    <div class="col-md-6">\n',
]
new_top_section.extend(["                        " + l for l in top_block_lines])
new_top_section.extend([
    '                    </div>\n',
    '                    <div class="col-md-6">\n',
    '                        <div class="card border-0 shadow-sm mb-4 h-100">\n',
])
# Add the extracted header and body parts
# Note: extracted_desc doesn't contain a wrapping card body if we start at card-header
# Let's inspect extracted_desc:
# [0] <div class="card-header...">...</div>
# [1] <div class="card-body">  <-- Wait! Is card-body there? Yes, it's at i+1
# [2]   <div class="row mb-4">
# ...
# [-1]  </div>  (closes row mb-4)
# So extracted_desc is missing the closing </div> for card-body and card.

for l in extracted_desc:
    new_top_section.append("    " + l)
new_top_section.extend([
    '                            </div>\n', # close card-body
    '                        </div>\n', # close card border-0 shadow-sm
    '                    </div>\n',
    '                </div>\n',
])

final_lines = lines_removed[:top_start] + new_top_section + lines_removed[top_end:]

with open("index.html", "w", encoding="utf-8") as f:
    f.writelines(final_lines)
