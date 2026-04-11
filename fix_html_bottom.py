with open("index.html", "r", encoding="utf-8") as f:
    lines = f.readlines()

# Ensure that the Multimedia Section is inside the card-body
# Actually, since we removed the header and the first row mb-4,
# the div class="card border-0 shadow-sm" doesn't have a card-body around Multimedia Section
# Let's fix that.
for i, line in enumerate(lines):
    if '<!-- Multimedia Section (Merged) -->' in line:
        # Check if the line above is <div class="card border-0 shadow-sm">
        if '<div class="card border-0 shadow-sm">' in lines[i-1]:
            # Insert card-body
            lines.insert(i, '                            <div class="card-body">\n')

            # Now we need to find where this card-body should be closed
            # In the original file, where was the closing div?
            # It was at the end of the col-12. Let's find "<!-- NEXT MODULE... -->" or similar
            break

# The card-body was enclosing everything until the end of the Restricciones.
# We can find the closing tags of this col-12.
