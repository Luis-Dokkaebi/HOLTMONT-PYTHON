def fix():
    with open("api/main.py", "r") as f:
        content = f.read()

    # Maybe FastAPI doesn't like both a static mount to "/" and other routes?
    # Wait, 405 Method Not Allowed means the route exists but not for POST, or it's hitting the StaticFiles instead of the POST route!
    # YES! app.mount("/", StaticFiles...) MUST come LAST.
    if 'app.mount("/",' in content:
        content = content.replace('app.mount("/", StaticFiles(directory=".", html=True), name="root")', '')
        content += '\napp.mount("/", StaticFiles(directory=".", html=True), name="root")\n'

    with open("api/main.py", "w") as f:
        f.write(content)

if __name__ == "__main__":
    fix()
