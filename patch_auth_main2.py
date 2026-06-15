import re

def fix():
    with open("api/main.py", "r") as f:
        content = f.read()

    # The StaticFiles mount needs to explicitly mount the current directory so index.html works
    if "from fastapi.staticfiles import StaticFiles" not in content:
        content = content.replace("from fastapi.middleware.cors import CORSMiddleware",
                                  "from fastapi.middleware.cors import CORSMiddleware\nfrom fastapi.staticfiles import StaticFiles")

        # Mount the root directory to "/"
        content = content.replace('app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])',
                                  'app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])\napp.mount("/", StaticFiles(directory=".", html=True), name="static")')

    # Ensure app creation does not fail. Wait, why did the server not start?
    # Because of ValueError in StaticFiles?
    # Let's run uvicorn manually to see the error.
    pass

if __name__ == "__main__":
    fix()
