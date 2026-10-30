@echo off
echo Starting RFP Intelligence Platform FastAPI Backend (Port 8000)...
"C:\Users\swain\AppData\Local\Programs\Python\Python311\python.exe" -m uvicorn api.app:app --host 127.0.0.1 --port 8000 --reload
pause
