import sys

def patch():
    with open("api/main.py", "r") as f:
        lines = f.readlines()

    out_lines = []

    for i, line in enumerate(lines):
        if "app = FastAPI" in line:
            out_lines.append("from api.routers import auth\n")
            out_lines.append(line)
        elif "app.mount('/mcp', mcp.sse_app" in line:
            out_lines.append(line)
            out_lines.append("\n# Mount modular routers\n")
            out_lines.append("app.include_router(auth.router, prefix=\"/api/auth\", tags=[\"Auth\"])\n")
        else:
            out_lines.append(line)

    with open("api/main.py", "w") as f:
        f.writelines(out_lines)

if __name__ == "__main__":
    patch()
