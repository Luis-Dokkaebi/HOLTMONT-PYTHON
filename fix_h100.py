with open("index.html", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'textarea id="campoConcepto"' in line and 'h-100' in line:
        # Let's remove the fixed rows="8" to make h-100 actually fill the space better, or remove h-100 and keep rows.
        # It's inside a div with h-100. Let's make sure the card-body takes full height if possible, or just keep it as is.
        # Actually it looks exactly like the reference now!
        pass
