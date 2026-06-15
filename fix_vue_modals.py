import sys

def fix():
    with open("index.html", "r") as f:
        content = f.read()

    # Maybe the legacy code is overriding it somewhere else.
    # Let's completely force the v-if evaluation or ensure we only define it once.
    if "const showBlueprintModal = ref(true);" in content:
        content = content.replace("const showBlueprintModal = ref(true);", "const showBlueprintModal = ref(false);")
    if "showBlueprintModal.value = true;" in content:
        print("Found active assignment")

    with open("index.html", "w") as f:
        f.write(content)

if __name__ == "__main__":
    fix()
