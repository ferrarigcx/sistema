import hashlib

def gerar_hash_arquivo(caminho_do_video):
    sha256 = hashlib.sha256()
    with open(caminho_do_video, "rb") as f:
        for bloco in iter(lambda: f.read(4096), b""):
            sha256.update(bloco)
    return "0x" + sha256.hexdigest()
