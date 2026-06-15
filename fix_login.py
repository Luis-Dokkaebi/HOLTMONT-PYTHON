import sys

def replace_login():
    with open("index.html", "r") as f:
        content = f.read()

    new_login = """
      const doLogin = async () => {
        if(!loginPass.value || !loginUser.value) return;
        loggingIn.value = true;
        try {
            const res = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: loginUser.value, password: loginPass.value })
            });
            const data = await res.json();
            loggingIn.value = false;

            if (data.status === 'success') {
                isLoggedIn.value = true;
                currentUser.value = data.name || data.username;
                currentUsername.value = data.username;
                currentRole.value = data.role;
                config.value = data.config;

                // Set default view based on role
                if (data.role === 'ADMIN' || data.role === 'VENTAS') {
                    currentView.value = 'DASHBOARD';
                } else {
                    currentView.value = 'WORKORDER_FORM';
                }
            } else {
                Swal.fire('Error', data.message || 'Error de inicio de sesión', 'error');
            }
        } catch (e) {
            loggingIn.value = false;
            Swal.fire('Error', 'Fallo de conexión', 'error');
        }
      };

      const loadConfig = (r) => {
          // Config is now loaded directly in doLogin from our FastAPI backend
          console.log("Config loaded in login step.");
      };

      const logout = async () => {
          try {
              await fetch('/api/auth/logout', { method: 'POST' });
          } catch(e) {}
          isLoggedIn.value = false;
          loginPass.value = '';
          loginUser.value = '';
          currentView.value = 'DASHBOARD'; // Returns to generic login screen state
          currentUser.value = '';
          currentRole.value = '';
          currentUsername.value = '';
      };
"""
    # Replace the proxy doLogin
    start_proxy = content.find("const doLogin = () => { \n        if(!loginPass.value || !loginUser.value) return;")
    end_proxy = content.find("      };", start_proxy) + 8

    if start_proxy != -1 and end_proxy != -1:
        content = content[:start_proxy] + "/* removed mock doLogin */\n" + content[end_proxy:]

    # Now replace the real legacy doLogin block
    start_legacy = content.find("const doLogin = () => { if(!loginPass.value || !loginUser.value) return; loggingIn.value=true;")
    end_legacy = content.find("}).getSystemConfig(r); };", start_legacy) + 26

    if start_legacy != -1 and end_legacy != -1:
        content = content[:start_legacy] + new_login + content[end_legacy:]

    # Now replace logout
    start_logout = content.find("const logout = () => { Swal.fire")
    if start_logout != -1:
        end_logout = content.find("};", start_logout) + 2
        content = content[:start_logout] + "/* logout handled above */" + content[end_logout:]

    with open("index.html", "w") as f:
        f.write(content)

if __name__ == "__main__":
    replace_login()
