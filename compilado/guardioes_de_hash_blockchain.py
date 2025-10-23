import hashlib
import os
import time
import subprocess
import re
import sqlite3
from pathlib import Path
from datetime import datetime

# --- ÁREA DE CONFIGURAÇÃO ---
PASTA_DE_VIDEOS = "../trechos_nao_conformes"
DB_FILE = "registros_offchain.db"
EXTENSOES_VIDEO = ('.mp4', '.avi', '.mov', '.mkv')

# Caminhos dos scripts Node
DEPLOY_JS = os.path.join("../besu/smart_contracts/scripts/public", "deploy.js")
HRE_HASH_JS = os.path.join("../besu/smart_contracts/scripts/public", "hre_hash.js")
HRE_EXISTS_JS = os.path.join("../besu/smart_contracts/scripts/public", "hre_exists.js")  # << novo (esperado)

# --- Utilidades para endereço em TXT ---
BASE_DIR = Path(__file__).resolve().parent
ARQUIVO_ENDERECO_PADRAO = BASE_DIR / "contract_address.txt"
PADRAO_ENDERECO = re.compile(r"^0x[0-9a-fA-F]{40}$")

# ------------- DB (SQLite) ------------- #
def init_db(db_path: str):
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS registros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_address TEXT NOT NULL,
            file_name TEXT,
            file_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(contract_address, file_hash)
        )
    """)
    con.commit()
    return con

def db_has_hash(con, contract_address: str, file_hash: str) -> bool:
    cur = con.cursor()
    cur.execute("SELECT 1 FROM registros WHERE contract_address=? AND file_hash=? LIMIT 1",
                (contract_address, file_hash))
    return cur.fetchone() is not None

def db_insert_hash(con, contract_address: str, file_name: str, file_hash: str):
    cur = con.cursor()
    cur.execute("INSERT OR IGNORE INTO registros (contract_address, file_name, file_hash, created_at) VALUES (?, ?, ?, ?)",
                (contract_address, file_name, file_hash, datetime.utcnow().isoformat()))
    con.commit()

# ------------- Endereço em TXT ------------- #
def buscar_arquivo_endereco():
    """
    Procura por qualquer .txt no diretório do script contendo APENAS um endereço Ethereum válido.
    Retorna (Path, endereço) se encontrar; caso contrário, (None, "").
    """
    for txt in BASE_DIR.glob("*.txt"):
        try:
            conteudo = txt.read_text(encoding="utf-8").strip()
            if PADRAO_ENDERECO.match(conteudo):
                print(f"➡️  Endereço encontrado no arquivo: {txt.name}")
                print(f"    {conteudo}")
                return txt, conteudo
        except Exception as e:
            print(f"⚠️  Não foi possível ler '{txt.name}': {e}")
    return None, ""

def salvar_endereco_em_txt(endereco: str, destino: Path = ARQUIVO_ENDERECO_PADRAO):
    if not PADRAO_ENDERECO.match(endereco):
        raise ValueError(f"Endereço inválido para salvar: {endereco}")
    destino.write_text(endereco.strip() + "\n", encoding="utf-8")
    print(f"💾 Endereço salvo em: {destino.name}")

# ------------- Utilidades gerais ------------- #
def calcular_hash_video(caminho_do_video: str) -> str | None:
    sha256_hash = hashlib.sha256()
    try:
        with open(caminho_do_video, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return "0x" + sha256_hash.hexdigest()
    except IOError as e:
        print(f"‼️  Erro ao ler o arquivo {os.path.basename(caminho_do_video)}: {e}")
        return None

def node_exists_script_available() -> bool:
    return Path(HRE_EXISTS_JS).exists()

def check_hash_onchain(contract_address: str, file_hash: str) -> bool:
    """
    Verifica on-chain via Node se file_hash já está registrado no contrato.
    Espera que hre_exists.js retorne 'true' ou 'false' no stdout.
    """
    try:
        result = subprocess.run(
            ['node', HRE_EXISTS_JS, contract_address, file_hash],
            capture_output=True, text=True, check=True
        )
        out = result.stdout.strip().lower()
        if out in ("true", "false"):
            return out == "true"
        # Saída inesperada: trata como não encontrado, mas alerta
        print(f"⚠️  Saída inesperada do hre_exists.js: '{result.stdout.strip()}' (esperado 'true'/'false').")
        return False
    except FileNotFoundError:
        print("⚠️  hre_exists.js não encontrado; pulando verificação on-chain.")
        return False
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Erro ao executar hre_exists.js: {e}; stderr: {e.stderr}")
        return False

# --- PONTO DE PARTIDA DO SCRIPT ---
if __name__ == "__main__":
    # --- INÍCIO DO TIMER ---
    inicio = time.time()

    # Inicializa DB (off-chain cache)
    con = init_db(DB_FILE)
    
    contract_number = ""
    # Pega a lista de todos os arquivos na pasta de vídeos.
    try:
        arquivos_na_pasta = os.listdir(PASTA_DE_VIDEOS)
    except FileNotFoundError:
        print(f"‼️  ERRO CRÍTICO: A pasta '{PASTA_DE_VIDEOS}' não foi encontrada.")
        print("    Por favor, configure o caminho correto na variável 'PASTA_DE_VIDEOS' no início do script.")
        exit()

    # considerar extensões maiúsculas também
    videos_encontrados = [f for f in arquivos_na_pasta if f.lower().endswith(EXTENSOES_VIDEO)]
    
    if not videos_encontrados:
        print("ℹ️  Nenhum arquivo de vídeo encontrado na pasta para processar.")
    else:
        print(f"🔎 Encontrados {len(videos_encontrados)} vídeos na pasta. Verificando...")

    novos_arquivos_processados = 0

    # Verificar TXT com endereço
    _, contract_number = buscar_arquivo_endereco()

    # Se não houver endereço salvo, faz deploy e salva em TXT
    if contract_number == "":
        print("⚙️  Nenhum endereço válido encontrado em .txt. Fazendo deploy...")
        try:
            result = subprocess.run(['node', DEPLOY_JS], capture_output=True, text=True, check=True)
            node_output = result.stdout.strip()
            if not PADRAO_ENDERECO.match(node_output):
                print(f"‼️  Saída inesperada do deploy.js: '{node_output}'")
                print("    Esperado: um endereço 0x... com 40 caracteres hexadecimais.")
                exit(1)
            contract_number = node_output
            print(f"✅  Criado o contrato no endereço {contract_number}")
            salvar_endereco_em_txt(contract_number)
        except subprocess.CalledProcessError as e:
            print(f"‼️  Erro ao executar deploy.js: {e}")
            print(f"Stderr: {e.stderr}")
            exit(1)
        except FileNotFoundError:
            print("‼️  'node' não encontrado. Instale o Node.js e garanta que está no PATH.")
            exit(1)
    else:
        print(f"🔗  Usando contrato existente: {contract_number}")

    # Itera sobre cada arquivo de vídeo encontrado.
    for nome_arquivo in videos_encontrados:
        print(f"\n📥 Novo arquivo detectado: '{nome_arquivo}'.")
        caminho_completo = os.path.join(PASTA_DE_VIDEOS, nome_arquivo)
        
        file_hash = calcular_hash_video(caminho_completo)
        if not file_hash:
            continue

        # --- 1) Verificação on-chain (se existir o script hre_exists.js) ---
        exists_onchain = False
        if node_exists_script_available():
            try:
                exists_onchain = check_hash_onchain(contract_number, file_hash)
            except Exception as e:
                # Qualquer erro nessa verificação NÃO interrompe o fluxo; apenas loga e segue
                print(f"⚠️  Falha na verificação on-chain para {nome_arquivo}: {e}")

        if exists_onchain:
            print(f"🛑 Hash já está registrado on-chain para este contrato. Pulando: {file_hash}")
            # Garante que o cache local também saiba (idempotência)
            db_insert_hash(con, contract_number, nome_arquivo, file_hash)
            continue

        # --- 2) Verificação off-chain (cache local) ---
        if db_has_hash(con, contract_number, file_hash):
            print(f"🛑 Hash já encontrado no cache local para este contrato. Pulando: {file_hash}")
            continue

        # --- Envio on-chain (somente se não é duplicado) ---
        try:
            result = subprocess.run(['node', HRE_HASH_JS, contract_number, file_hash],
                                    capture_output=True, text=True, check=True)
            node_output = result.stdout.strip()
            print(f"📡 Dado enviado à blockchain. Resposta do hre_hash.js: {node_output}")

            # Sucesso no envio: registra no cache local
            db_insert_hash(con, contract_number, nome_arquivo, file_hash)
            novos_arquivos_processados += 1

        except subprocess.CalledProcessError as e:
            print(f"‼️  Erro ao executar hre_hash.js: {e}")
            print(f"Stderr: {e.stderr}")
        except FileNotFoundError:
            print("‼️  'node' não encontrado. Instale o Node.js e garanta que está no PATH.")
            print("Saída do JS (se houver):", result.stdout if 'result' in locals() else "")

    print("\n--- Processamento Concluído ---")
    if novos_arquivos_processados > 0:
        print(f"🎉 Resumo: {novos_arquivos_processados} nova(s) não conformidade(s) foram processadas e salvas.")
    else:
        print("👍 Nenhum arquivo novo para processar.")

    # --- FIM DO TIMER ---
    fim = time.time()
    duracao = fim - inicio
    print(f"\n⏱️ Script finalizado em {duracao:.2f} segundos ({duracao/60:.2f} minutos).")
