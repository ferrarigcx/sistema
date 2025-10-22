import hashlib
import os
import time
import subprocess

# --- ÁREA DE CONFIGURAÇÃO ---
PASTA_DE_VIDEOS = "../trechos_nao_conformes"
DB_FILE = "registros_offchain.db"
EXTENSOES_VIDEO = ('.mp4', '.avi', '.mov', '.mkv')

# --- PONTO DE PARTIDA DO SCRIPT ---
if __name__ == "__main__":
    # --- INÍCIO DO TIMER ---
    inicio = time.time()
    
    contract = os.path.join("../besu/smart_contracts/scripts/public", "deploy.js")
    value = os.path.join("../besu/smart_contracts/scripts/public", "hre_hash.js")
    contract_number = ""

    # Pega a lista de todos os arquivos na pasta de vídeos.
    try:
        arquivos_na_pasta = os.listdir(PASTA_DE_VIDEOS)
    except FileNotFoundError:
        print(f"‼️  ERRO CRÍTICO: A pasta '{PASTA_DE_VIDEOS}' não foi encontrada.")
        print("    Por favor, configure o caminho correto na variável 'PASTA_DE_VIDEOS' no início do script.")
        exit()  # Encerra o script se a pasta não existe.

    videos_encontrados = [f for f in arquivos_na_pasta if f.endswith(EXTENSOES_VIDEO)]
    
    if not videos_encontrados:
        print("ℹ️  Nenhum arquivo de vídeo encontrado na pasta para processar.")
    else:
        print(f"🔎 Encontrados {len(videos_encontrados)} vídeos na pasta. Verificando...")

    novos_arquivos_processados = 0

    if contract_number == "":
        result = subprocess.run(['node', contract], capture_output=True, text=True, check=True)
        node_output = result.stdout.strip()
        contract_number = node_output
        print(f" Criado o contrato no endereço {node_output}")

    def calcular_hash_video(caminho_do_video):
        sha256_hash = hashlib.sha256()

        try:
            with open(caminho_do_video, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return "0x" + sha256_hash.hexdigest()
        except IOError as e:
            print(f"‼️  Erro ao ler o arquivo {os.path.basename(caminho_do_video)}: {e}")
            return None

    # Itera sobre cada arquivo de vídeo encontrado.
    for nome_arquivo in videos_encontrados:
        print(f"\n📥 Novo arquivo detectado: '{nome_arquivo}'.")
        caminho_completo = os.path.join(PASTA_DE_VIDEOS, nome_arquivo)
        
        hash_calculado = calcular_hash_video(caminho_completo)
        if hash_calculado:
            try:
                result = subprocess.run(['node', value, contract_number, hash_calculado],
                                        capture_output=True, text=True, check=True)
                node_output = result.stdout.strip()
                contract_number = node_output
                print(f" Dado enviado à blockchain: {node_output}")
            except subprocess.CalledProcessError as e:
                print(f"Error running Node.js script: {e}")
                print(f"Stderr: {e.stderr}")
            except FileNotFoundError:
                print("Error: 'node' command not found. Make sure Node.js is installed and in PATH.")
                print("Saída do JS:", result.stdout)
            novos_arquivos_processados += 1

    print("\n--- Processamento Concluído ---")
    if novos_arquivos_processados > 0:
        print(f"🎉 Resumo: {novos_arquivos_processados} nova(s) não conformidade(s) foram processadas e salvas.")
    else:
        print("👍 Nenhum arquivo novo para processar.")

    # --- FIM DO TIMER ---
    fim = time.time()
    duracao = fim - inicio
    print(f"\n⏱️ Script finalizado em {duracao:.2f} segundos ({duracao/60:.2f} minutos).")
