Write-Host "Iniciando Holtmont Workspace..." -ForegroundColor Green

# 1. Start Backend in a new window
Write-Host "Iniciando Backend (Puerto 8000)..."
Start-Process powershell -ArgumentList "python main.py" -NoNewWindow:$false

# 2. Wait a bit for backend to initialize
Start-Sleep -Seconds 3

# 3. Start Frontend in a new window
Write-Host "Iniciando Frontend (Puerto 8080)..."
Start-Process powershell -ArgumentList "python -m http.server 8080" -NoNewWindow:$false

# 4. Open Browser
Start-Sleep -Seconds 2
Start-Process "http://localhost:8080"

Write-Host "Todo listo. Presiona Enter para salir." -ForegroundColor Cyan
Read-Host
