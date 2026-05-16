with open("index.html", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if '<!-- Multimedia Section (Merged) -->' in line:
        # We need to find if there is a missing card-body
        # Looking closely at output above:
        # <div class="card border-0 shadow-sm">
        #
        # <!-- Multimedia Section (Merged) -->

        # We need to insert <div class="card-body"> right after the card div
        idx = i - 1
        while idx > 0 and lines[idx].strip() == '':
            idx -= 1

        if '<div class="card border-0 shadow-sm">' in lines[idx]:
            lines.insert(idx+1, '                            <div class="card-body">\n')
            break

with open("index.html", "w", encoding="utf-8") as f:
    f.writelines(lines)
