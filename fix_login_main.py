import os
def fix():
    # Remove the second logout declaration
    with open("index.html", "r") as f:
        lines = f.readlines()
    out = []
    skip = False
    for i, line in enumerate(lines):
        if "const logout = () => {" in line and i > 6300:
            skip = True
        if skip and "};" in line:
            skip = False
            continue
        if not skip:
            out.append(line)
    with open("index.html", "w") as f:
        f.writelines(out)

    # Fix FastAPI Static files mounting
    with open("api/main.py", "r") as f:
        content = f.read()
    if "from fastapi.staticfiles import StaticFiles" not in content:
        content = content.replace("from fastapi.middleware.cors import CORSMiddleware",
                                  "from fastapi.middleware.cors import CORSMiddleware\nfrom fastapi.staticfiles import StaticFiles")
        if 'app.mount("/static", ' in content:
            content = content.replace('app.mount("/static", StaticFiles(directory="."), name="static")',
                                      'app.mount("/static", StaticFiles(directory="."), name="static")\napp.mount("/", StaticFiles(directory=".", html=True), name="root")')
        else:
            content = content.replace('allow_headers=["*"],\n)',
                                      'allow_headers=["*"],\n)\napp.mount("/", StaticFiles(directory=".", html=True), name="root")')
    with open("api/main.py", "w") as f:
        f.write(content)

if __name__ == "__main__":
    fix()
