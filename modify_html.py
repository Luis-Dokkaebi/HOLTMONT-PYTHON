with open("index_backup.html", "r", encoding="utf-8") as f:
    lines = f.readlines()

# The description section spans from line 2262 (<div class="card border-0 shadow-sm">)
# up to line 2311 (</div> before <!-- Multimedia Section (Merged) -->)
# Oh wait, the visual reference shows "Descripción del Trabajo" next to "Nombre de cotizador".
# Let's extract the card-header and card-body (which contains the textarea and logic card).
# It starts at:
# <div class="card border-0 shadow-sm">
#     <div class="card-header bg-dark text-white border-0 pt-3 ps-3 d-flex justify-content-between align-items-center">
#         <h6 class="fw-bold mb-0"><i class="fas fa-robot me-2"></i>Descripción del Trabajo a Realizar...
# and ends right before Multimedia Section.

desc_block = []
in_desc = False
start_idx = 0
end_idx = 0

for i, line in enumerate(lines):
    if '<!-- BOTTOM: DESCRIPTION & MEDIA -->' in line:
        pass
    if '<h6 class="fw-bold mb-0"><i class="fas fa-robot me-2"></i>Descripción del Trabajo a Realizar' in line:
        # Step back to the <div class="card border-0 shadow-sm">
        start_idx = i - 2
        in_desc = True

    if in_desc and '<!-- Multimedia Section (Merged) -->' in line:
        # the closing divs for the row mb-4
        end_idx = i - 1
        break

extracted_desc = lines[start_idx:end_idx]
# Since we extracted up to the row mb-4 closing div, we need to add </div></div> for card-body and card
extracted_desc.append("                            </div>\n")
extracted_desc.append("                        </div>\n")

# Now we need to remove this from the bottom
lines_bottom_removed = lines[:start_idx] + lines[end_idx:]

# Now insert it at the top, inside a row.
# The top block starts at line 1661: <!-- NOMBRE DE COTIZADOR TOP -->
# It goes to line 1692 (</div> before <!-- CHECKLIST VISITA -->)

# Let's build the new top block
top_start = -1
top_end = -1
for i, line in enumerate(lines_bottom_removed):
    if "<!-- NOMBRE DE COTIZADOR TOP -->" in line:
        top_start = i
    if top_start != -1 and "<!-- CHECKLIST VISITA -->" in line:
        top_end = i
        break

top_block_lines = lines_bottom_removed[top_start+1:top_end] # the card border-0 shadow-sm mb-4

# Build new top section
new_top_section = [
    '                <!-- TOP ROW SECTION -->\n',
    '                <div class="row mb-4">\n',
    '                    <div class="col-md-6">\n',
]
new_top_section.extend(["                        " + l for l in top_block_lines])
new_top_section.extend([
    '                    </div>\n',
    '                    <div class="col-md-6">\n',
])
# Clean indentation for extracted_desc
for l in extracted_desc:
    new_top_section.append("    " + l)
new_top_section.extend([
    '                    </div>\n',
    '                </div>\n',
])

final_lines = lines_bottom_removed[:top_start] + new_top_section + lines_bottom_removed[top_end:]

with open("index.html", "w", encoding="utf-8") as f:
    f.writelines(final_lines)

