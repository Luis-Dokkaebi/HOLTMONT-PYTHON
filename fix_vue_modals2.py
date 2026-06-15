import sys

def fix():
    with open("index.html", "r") as f:
        content = f.read()

    # Track A initialization bug: maybe the overlay component is missing a `v-cloak` wrapper?
    # Or let's just make the modal explicitly default to false
    content = content.replace("const showBlueprintModal = ref(true);", "const showBlueprintModal = ref(false);")

    # Just remove the v-if entirely or make it explicitly `showBlueprintModal === true`
    content = content.replace('v-if="showBlueprintModal"', 'v-if="showBlueprintModal === true"')

    with open("index.html", "w") as f:
        f.write(content)

if __name__ == "__main__":
    fix()
