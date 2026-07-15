Start-Process powershell -ArgumentList "-NoExit", "-Command", ".\venv\Scripts\Activate.ps1; uvicorn coordinator.main:app --host 0.0.0.0 --port 8000"
Start-Sleep -Seconds 2

Start-Process powershell -ArgumentList "-NoExit", "-Command", ".\venv\Scripts\Activate.ps1; python clients\genie_client.py --id phone"
Start-Process powershell -ArgumentList "-NoExit", "-Command", ".\venv\Scripts\Activate.ps1; python clients\mock_client.py --id laptop"
Start-Process powershell -ArgumentList "-NoExit", "-Command", ".\venv\Scripts\Activate.ps1; python clients\mock_client.py --id tablet"

Write-Host "Coordinator, Real Genie Phone (via dummy script), and 2 Mock Clients started."
Write-Host "Run 'python scripts\submit_prompt.py' to simulate a dashboard request."
