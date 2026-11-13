import subprocess
import sys

if __name__ == "__main__":
    print("=== KHỞI CHẠY HỆ THỐNG ĐẶT MÓN & ĐIỀU PHỐI GIAO HÀNG ĐA NHÀ HÀNG ===")
    print("-> Giao diện Web: http://localhost:8000")
    print("-> Swagger API:   http://localhost:8000/docs")
    subprocess.run([sys.executable, "-m", "uvicorn", "api.main:app", "--reload", "--port", "8000"])