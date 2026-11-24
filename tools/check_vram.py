"""Проверка реального состояния VRAM через CUDA."""
import subprocess
import sys
import os

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

py = r"C:\Users\cyril\AppData\Local\Auraloom\engine\Scripts\python.exe"
if not os.path.exists(py):
    print("движок не найден:", py)
    sys.exit(1)

code = (
    "import torch\n"
    "print('cuda:', torch.cuda.is_available())\n"
    "if torch.cuda.is_available():\n"
    "    free, total = torch.cuda.mem_get_info()\n"
    "    print('free_MB:', round(free/1048576))\n"
    "    print('total_MB:', round(total/1048576))\n"
    "    print('reserved_MB:', round(torch.cuda.memory_reserved()/1048576))\n"
    "    print('allocated_MB:', round(torch.cuda.memory_allocated()/1048576))\n"
)
r = subprocess.run([py, "-c", code], capture_output=True, text=True,
                   timeout=180)
print(r.stdout)
if r.returncode != 0:
    print("STDERR:", r.stderr[-800:])