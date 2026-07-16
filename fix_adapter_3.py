with open("api_service.js", "r") as f:
    content = f.read()

# Make sure google.script.run is initialized
replacement = """
// Expose to window
window.google = window.google || {};
window.google.script = window.google.script || {};
window.google.script.run = new GoogleScriptRunAdapter();
"""
if "window.google.script.run =" not in content:
    content = content.replace("// Use: google.script.run = new GoogleScriptRunAdapter();", replacement)

with open("api_service.js", "w") as f:
    f.write(content)
