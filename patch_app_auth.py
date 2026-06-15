import sys

def patch():
    with open("api/main.py", "r") as f:
        lines = f.readlines()

    out_lines = []

    for i, line in enumerate(lines):
        out_lines.append(line)
        if "app = FastAPI" in line:
            out_lines.append("app.include_router(auth.router, prefix=\"/api/auth\", tags=[\"Auth\"])\n")

    with open("api/main.py", "w") as f:
        f.writelines(out_lines)

if __name__ == "__main__":
    patch()
