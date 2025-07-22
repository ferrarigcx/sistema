import subprocess
import os

js_path = os.path.join("besu/smart_contracts/scripts/public", "hre_hash.js")
# Executa script.js com Node.js
result = subprocess.run(["node", js_path, "0x4e944b578d55dc7f4e21f83f17b497c44d2bb3bcb2a1d2f37cf4297a2a6f3fdd"], capture_output=True, text=True)

print("Saída do JS:", result.stdout)