with open("index.html", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if '<!-- Multimedia Section (Merged) -->' in line:
        if '<div class="card border-0 shadow-sm">' in lines[i-1]:
            lines.insert(i, '                            <div class="card-body">\n')
            break

with open("index.html", "w", encoding="utf-8") as f:
    f.writelines(lines)
