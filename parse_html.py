from bs4 import BeautifulSoup

with open("index.html", "r", encoding="utf-8") as f:
    html_content = f.read()

soup = BeautifulSoup(html_content, "html.parser")

# Find the Descripcion del trabajo block
desc_block = soup.find(lambda tag: tag.name == "h6" and "Descripción del Trabajo a Realizar basado" in tag.text)
if desc_block:
    # the card is desc_block.parent.parent
    desc_card = desc_block.parent.parent
    # the col-12 wrapper
    desc_col = desc_card.parent

    if "col-12" in desc_col.get("class", []):
        print("Found the description block col-12 wrapper.")

# Find the top block "NOMBRE DE COTIZADOR TOP"
# It has a label "Nombre de cotizador"
top_label = soup.find(lambda tag: tag.name == "label" and "Nombre de cotizador" in tag.text)
if top_label:
    top_card_body = top_label.parent
    top_card = top_card_body.parent
    if "card" in top_card.get("class", []):
        print("Found the top card.")
