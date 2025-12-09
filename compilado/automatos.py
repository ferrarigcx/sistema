import hashlib
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

from PIL import Image

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
SHOW_GUI = os.getenv("AUTOMATOS_SHOW_GUI", "0").strip().lower() in {"1", "true", "yes", "on"}

BASE_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = BASE_DIR.parent / "besu" / "smart_contracts" / "scripts" / "public"
HRE_HASH_JS = SCRIPTS_DIR / "hre_hash.js"
HRE_FOUND_JS = SCRIPTS_DIR / "hre_found.js"
PADRAO_ENDERECO = re.compile(r"^0x[0-9a-fA-F]{40}$")
FRAME_OUTPUT_PATH_STR = os.getenv("AUTOMATOS_FRAME_PATH", "").strip()
FRAME_OUTPUT_PATH: Optional[Path] = None
if FRAME_OUTPUT_PATH_STR:
    try:
        FRAME_OUTPUT_PATH = Path(FRAME_OUTPUT_PATH_STR)
        FRAME_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        FRAME_OUTPUT_PATH = None


def centro(box):
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def esta_dentro(centro, box):
    x1, y1, x2, y2 = box
    cx, cy = centro
    return x1 <= cx <= x2 and y1 <= cy <= y2

# Limiar IoU para considerar "amostra dentro da cesta" em q3.
# Pode ser ajustado via variável de ambiente IOU_THR_Q3.
IOU_THR_Q3 = float(os.getenv("IOU_THR_Q3", "0.02"))
FRAC_THR_Q3 = float(os.getenv("FRAC_THR_Q3", "0.30"))  # fração mínima de cobertura da amostra

def iou_xyxy(a, b) -> float:
    try:
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
    except Exception:
        return 0.0
    inter_w = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    inter_h = max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = inter_w * inter_h
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    if union <= 0:
        return 0.0
    return inter / union

def inter_area(a, b) -> float:
    try:
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
    except Exception:
        return 0.0
    inter_w = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    inter_h = max(0.0, min(ay2, by2) - max(ay1, by1))
    return inter_w * inter_h

def area(box) -> float:
    try:
        x1, y1, x2, y2 = box
    except Exception:
        return 0.0
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


class BlockchainClient:
    """Integração simples com os scripts Node para registrar hashes na blockchain."""

    def __init__(self, base_dir: Path, source: Optional[str]):
        self.base_dir = base_dir
        self.source_input = (source or "").strip()
        self.source_path = self._resolve_source(self.source_input)
        self.contract_address = self._buscar_endereco()
        self.file_hash = None
        self._already_registered = False
        self._checked = False
        self.enabled = False

        if not self.contract_address:
            self._log("Contrato não encontrado (contract_address.txt). Integração desativada.")
            return
        if not self.source_path:
            self._log("Fonte não é um arquivo local. Integração blockchain inativa.")
            return
        if not HRE_HASH_JS.exists() or not HRE_FOUND_JS.exists():
            self._log("Scripts hre_hash.js/hre_found.js não encontrados.")
            return

        self.file_hash = self._calcular_hash(self.source_path)
        if not self.file_hash:
            self._log("Falha ao calcular hash do arquivo. Integração desativada.")
            return

        self.enabled = True
        self._log(
            f"pronto. contrato={self.contract_address} arquivo='{self.source_path.name}' hash={self.file_hash[:12]}..."
        )

    def _log(self, msg: str) -> None:
        print(f"[blockchain] {msg}")

    def _resolve_source(self, src: str) -> Optional[Path]:
        if not src or src.isdigit():
            return None
        cand = Path(src)
        if not cand.is_absolute():
            cand = self.base_dir / cand
        if cand.exists() and cand.is_file():
            return cand
        self._log(f"arquivo de origem não localizado: {cand}")
        return None

    def _buscar_endereco(self) -> str:
        for txt in self.base_dir.glob("*.txt"):
            try:
                conteudo = txt.read_text(encoding="utf-8").strip()
                if PADRAO_ENDERECO.match(conteudo):
                    return conteudo
            except Exception:
                continue
        return ""

    def _calcular_hash(self, path: Path) -> Optional[str]:
        sha = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    sha.update(chunk)
            return "0x" + sha.hexdigest()
        except OSError as exc:
            self._log(f"erro ao ler '{path}': {exc}")
            return None

    def _run_node(self, script: Path, *args: str) -> Optional[str]:
        try:
            res = subprocess.run(
                ["node", str(script), *args], capture_output=True, text=True, check=True
            )
            return res.stdout.strip()
        except FileNotFoundError:
            self._log("Node.js não encontrado no PATH. Verifique a instalação.")
        except subprocess.CalledProcessError as exc:
            self._log(f"falha ao executar '{script.name}': {exc}; stderr={exc.stderr}")
        return None

    def _check_registered(self) -> bool:
        if not self.enabled:
            return False
        out = self._run_node(HRE_FOUND_JS, self.file_hash, self.contract_address)
        if out is None:
            return False
        low = out.lower()
        if low in {"true", "false"}:
            return low == "true"
        if re.fullmatch(r"0x[0-9a-fA-F]{64}", out):
            return out.lower() == self.file_hash.lower()
        return False

    def _enviar_para_blockchain(self) -> bool:
        if not self.enabled:
            return False
        out = self._run_node(HRE_HASH_JS, self.file_hash, self.contract_address)
        if out is None:
            return False
        self._log(f"hash enviado. resposta: {out[:120]}")
        return True

    def reportar_nao_conformidade(self, registro: dict) -> None:
        if not self.enabled:
            return
        descricao = registro.get("mensagem", "Não conformidade detectada")
        self._log(f"registrando evento: {descricao}")
        if not self._checked:
            self._already_registered = self._check_registered()
            self._checked = True
        if self._already_registered:
            self._log("hash já presente no contrato. Nenhum envio necessário.")
            return
        if self._enviar_para_blockchain():
            self._already_registered = True

class AFNRefinado:
    def __init__(self, audit_mode: bool = False, blockchain_client: Optional[BlockchainClient] = None):
        self.estado_atual = "q0"
        self.estado_anterior = None
        self.estados_finais = {"q5"}
        self.audit_mode = audit_mode
        self.erros_acumulados = []
        self.blockchain_client = blockchain_client

    def verificar_erro_critico(self, objetos, boxes=None):
        crit = "Sem_Luva" in objetos or "Ativimetro" not in objetos
        if crit:
            # Registra imediatamente o erro crítico
            self._registrar_nao_conformidade(
                "critical", objetos, boxes, "Erro crítico: mão sem luva ou ativímetro ausente"
            )
        return crit

    def mapear_entrada(self, objetos, boxes, nomes):
        if self.estado_atual == "q0":
            return "tem_mao" if "Com_Luva" in objetos else ""

        if self.estado_atual == "q1":
            return "com_luva" if "Com_Luva" in objetos else ""

        if self.estado_atual == "q2":
            has_cesta = any("cesta" in str(o).lower() for o in objetos)
            has_amostra = any("amostra" in str(o).lower() for o in objetos)
            if has_cesta and has_amostra:
                return "cesta_dentro"
            return ""

        if self.estado_atual == "q3":
            # Novo comportamento: usar IoU entre caixas "amostra" e "cesta".
            # Complementos:
            #  - aceita rótulos compostos (e.g., "cesta_com_amostra", "amostra_dentro_cesta").
            #  - fallback por centro-dentro e por fração de cobertura da amostra.
            box_amostras = []
            box_cestas = []
            for i, nome in enumerate(objetos):
                if i >= len(boxes):
                    continue
                b = boxes[i]
                if nome == "Amostra":
                    box_amostras.append(b)
                elif nome == "Cesta":
                    box_cestas.append(b)

            # Aceita rótulos compostos detectados pelo modelo (qualquer label contendo ambas as palavras)
            for lbl in objetos:
                l = str(lbl).strip().lower()
                if ("cesta" in l) and ("amostra" in l):
                    return "amostra_dentro_cesta"

            if box_amostras and box_cestas:
                for ba in box_amostras:
                    for bc in box_cestas:
                        # 1) IoU
                        if iou_xyxy(ba, bc) >= IOU_THR_Q3:
                            return "amostra_dentro_cesta"
                        # 2) Centro da amostra dentro da cesta
                        if esta_dentro(centro(ba), bc):
                            return "amostra_dentro_cesta"
                        # 3) Fração de cobertura da amostra (intersecção / área amostra)
                        a_am = area(ba)
                        if a_am > 0:
                            frac = inter_area(ba, bc) / a_am
                            if frac >= FRAC_THR_Q3:
                                return "amostra_dentro_cesta"
            return ""

        if self.estado_atual == "q4":
            box_amostra = None
            box_ativimetro = None

            for i, nome in enumerate(objetos):
                box = boxes[i]
                if nome == "Amostra":
                    box_amostra = box
                elif nome == "Ativimetro":
                    box_ativimetro = box

            if box_amostra and box_ativimetro:
                c = centro(box_amostra)
                return "tracking" if esta_dentro(c, box_ativimetro) else "erro_medio"
            return "erro_medio"

        return ""

    def transita(self, simbolo):
        transicoes = {
            ("q0", "tem_mao"): "q1",
            ("q1", "com_luva"): "q2",
            ("q2", "cesta_dentro"): "q3",
            ("q3", "amostra_dentro_cesta"): "q4",
            ("q4", "tracking"): "q5",
        }
        return transicoes.get((self.estado_atual, simbolo))

    def _registrar_nao_conformidade(self, tipo: str, objetos, boxes, mensagem: str) -> None:
        try:
            registro = {
                "tipo": tipo,
                "mensagem": mensagem,
                "state": self.estado_atual,
                "prev_state": self.estado_anterior,
                "ts": time.time(),
                "objetos": list(objetos) if objetos is not None else [],
                "boxes": boxes,
            }
            self.erros_acumulados.append(registro)
            if self.blockchain_client:
                self.blockchain_client.reportar_nao_conformidade(registro)
        except Exception:
            pass

    def processar(self, objetos, boxes, nomes):
        print(f"\n Simulando objetos: {objetos}")
        print(f" Estado atual: {self.estado_atual}")
        if self.verificar_erro_critico(objetos, boxes):
            print("Erro critico -> reset para q0")
            self.estado_atual = "q0"
            self.estado_anterior = None
            return

        simbolo = self.mapear_entrada(objetos, boxes, nomes)

        if simbolo == "erro_medio":
            self._registrar_nao_conformidade(
                "medium", objetos, boxes, "Erro medio: amostra fora do ativimetro ou condicao invalida"
            )
            print("Erro medio -> retornando ao estado anterior")
            self.estado_atual = self.estado_anterior
        elif simbolo:
            prox = self.transita(simbolo)
            if prox:
                print(f"{self.estado_atual} -> {prox} via '{simbolo}'")
                self.estado_anterior = self.estado_atual
                self.estado_atual = prox
                if self.estado_atual in self.estados_finais:
                    print("Final alcancado. Encerrando execucao.")
                    return "fim"
        else:
            print("Sem mudanca de estado.")

class AFNAuditoria(AFNRefinado):
    def __init__(self, blockchain_client: Optional[BlockchainClient] = None):
        super().__init__(audit_mode=True, blockchain_client=blockchain_client)

    def processar(self, objetos, boxes, nomes):
        print(f"\n Simulando objetos: {objetos}")
        print(f" Estado atual: {self.estado_atual}")
        if self.verificar_erro_critico(objetos, boxes):
            print("Erro critico (auditoria) - permanecendo no estado atual")
            return

        simbolo = self.mapear_entrada(objetos, boxes, nomes)

        if simbolo == "erro_medio":
            self._registrar_nao_conformidade(
                "medium", objetos, boxes, "Erro medio: amostra fora do ativimetro ou condicao invalida"
            )
            print("Erro medio (auditoria) - permanecendo no estado atual")
        elif simbolo:
            prox = self.transita(simbolo)
            if prox:
                print(f"{self.estado_atual} -> {prox} via '{simbolo}'")
                self.estado_anterior = self.estado_atual
                self.estado_atual = prox
                if self.estado_atual in self.estados_finais:
                    print("Final alcancado. Encerrando execucao.")
                    return "fim"
        else:
            print("Sem mudanca de estado.")
        # já acumulado em _registrar_nao_conformidade

class AFNAuditoria2(AFNRefinado):
    def __init__(self, blockchain_client: Optional[BlockchainClient] = None):
        super().__init__(audit_mode=True, blockchain_client=blockchain_client)

    def processar(self, objetos, boxes, nomes):
        print(f"\n Simulando objetos: {objetos}")
        print(f" Estado atual: {self.estado_atual}")
        if self.verificar_erro_critico(objetos, boxes):
            print("Erro critico (auditoria) - permanecendo no estado atual")
            return

        simbolo = self.mapear_entrada(objetos, boxes, nomes)

        if simbolo == "erro_medio":
            self._registrar_nao_conformidade(
                "medium", objetos, boxes, "Erro medio: amostra fora do ativimetro ou condicao invalida"
            )
            print("Erro medio (auditoria) - permanecendo no estado atual")
        elif simbolo:
            prox = self.transita(simbolo)
            if prox:
                print(f"{self.estado_atual} -> {prox} via '{simbolo}'")
                self.estado_anterior = self.estado_atual
                self.estado_atual = prox
                if self.estado_atual in self.estados_finais:
                    print("Final alcancado.")
                    self.estado_atual = "q0"
                    self.estado_anterior = None
        else:
            print("Sem mudanca de estado.")
def _choose_model_path(base_dir: str) -> str:
    # Preferência solicitada: ModeloTreinadoV3.pt
    cand0 = os.path.join(base_dir, "sistema\compilado\ModeloTreinadoV3.pt")
    cand1 = os.path.join(base_dir, "modelo_treinadov2.1.pt")
    cand2 = os.path.join(base_dir, "yolov8n.pt")
    for c in (cand0, cand1, cand2):
        if os.path.exists(c):
            return c
    return cand0


def _gen_from_image(model, path):
    import cv2
    import numpy as np

    img = cv2.imread(path)
    if img is None:
        print(f"Não foi possível ler a imagem: {path}")
        return []
    res = model(img, verbose=False)
    if not res:
        return []
    r0 = res[0]
    names = r0.names
    boxes = r0.boxes.xyxy.cpu().tolist() if r0.boxes is not None else []
    classes = r0.boxes.cls.tolist() if r0.boxes is not None else []
    objetos = [names[int(i)] for i in classes]
    # Sinaliza presença de mão quando houver luva ou sem luva
    if ("com luva" in objetos) or ("sem luva" in objetos):
        objetos = list(set(objetos + ["mão"]))
    return [(objetos, boxes)]


def _stream_from_capture(model, cap, afn):
    import cv2
    import numpy as np
    WIN = "YOLO + AFN"
    MAX_W, MAX_H = 960, 540  # janela padrão para enquadrar o vídeo
    def _letterbox_display(img):
        h, w = img.shape[:2]
        # escala para caber inteiramente na janela alvo
        scale = min(MAX_W / max(w, 1), MAX_H / max(h, 1))
        new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
        resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        canvas = np.zeros((MAX_H, MAX_W, 3), dtype=resized.dtype)
        off_x = (MAX_W - new_w) // 2
        off_y = (MAX_H - new_h) // 2
        canvas[off_y:off_y + new_h, off_x:off_x + new_w] = resized
        return canvas
    if SHOW_GUI:
        try:
            cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(WIN, MAX_W, MAX_H)
        except Exception:
            pass
    # Uma vez que alguns ambientes têm incompatibilidade numpy/scipy
    # ao usar tracking (model.track), caímos para detecção simples
    # quando o tracking falhar.
    frame_output_path = FRAME_OUTPUT_PATH
    frame_notice_emitted = False
    frame_error_reported = False

    def _publish_frame(image):
        nonlocal frame_notice_emitted, frame_error_reported
        if not frame_output_path:
            return
        tmp_path = frame_output_path.parent / f".{frame_output_path.name}.tmp"
        try:
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            Image.fromarray(rgb).save(tmp_path, format="JPEG")
            os.replace(tmp_path, frame_output_path)
            if not frame_notice_emitted:
                frame_notice_emitted = True
                print(f"[frames] enviando visualiza��o para {frame_output_path}")
        except Exception as exc:
            if not frame_error_reported:
                frame_error_reported = True
                print(f"[frames] falha ao salvar frames: {exc}")
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass

    def _draw_overlays(img, boxes, labels, state):
        colors = {
            "amostra": (0, 255, 255),
            "cesta": (255, 165, 0),
            "ativimetro": (0, 128, 255),
            "com_luva": (0, 255, 0),
            "sem_luva": (0, 0, 255),
        }
        if not (SHOW_GUI or frame_output_path):
            return img
        for lbl, box in zip(labels, boxes):
            try:
                x1, y1, x2, y2 = [int(v) for v in box]
            except Exception:
                continue
            color = colors.get(str(lbl).lower(), (255, 255, 255))
            cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
            cv2.putText(
                img,
                str(lbl),
                (x1, max(20, y1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2,
                cv2.LINE_AA,
            )
        try:
            cv2.putText(
                img,
                f"Estado: {state}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )
        except Exception:
            pass
        return img

    warned_fallback = False
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        try:
            res = model.track(frame, persist=True, verbose=False)
        except Exception as e:
            if not warned_fallback:
                try:
                    print("[aviso] Tracking indisponível (scipy/numpy). Usando detecção por frame. Detalhe:", str(e))
                except Exception:
                    pass
                warned_fallback = True
            res = model(frame, verbose=False)
        if not res:
            continue
        r0 = res[0]
        names = r0.names
        boxes = r0.boxes.xyxy.cpu().tolist() if r0.boxes is not None else []
        classes = r0.boxes.cls.tolist() if r0.boxes is not None else []
        objetos = [names[int(i)] for i in classes]
        # Sinaliza presença de mão quando houver luva ou sem luva
        if ("com luva" in objetos) or ("sem luva" in objetos):
            if "mão" not in objetos:
                objetos.append("mão")

        r = afn.processar(objetos, boxes, objetos)
        if r == "fim":
            print("[info] Autômato finalizado. Saindo do loop de captura.")
            break

        if SHOW_GUI or frame_output_path:
            try:
                annotated = _draw_overlays(frame.copy(), boxes, objetos, afn.estado_atual)
                disp = _letterbox_display(annotated)
                if SHOW_GUI:
                    cv2.imshow(WIN, disp)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                if frame_output_path:
                    _publish_frame(disp)
            except Exception:
                pass

    try:
        cap.release()
        if SHOW_GUI:
            import cv2 as _cv
            _cv.destroyAllWindows()
    except Exception:
        pass


def main():
    import argparse
    parser = argparse.ArgumentParser(description="AFN + YOLO (imagem/vídeo)")
    parser.add_argument("--source", type=str, default=os.getenv("SOURCE", "0"),
                        help="Caminho de vídeo/imagem ou índice da webcam (ex: 0)")
    parser.add_argument("--model", type=str, default=os.getenv("MODEL", ""),
                        help="Caminho do modelo .pt (padrão: ModeloTreinadoV3.pt)")
    parser.add_argument("--simulate", action="store_true", help="Usar palavras simuladas (modo legado)")
    args = parser.parse_args()

    _mode = os.getenv("MODO", "").strip().lower()
    _audit = _mode in {"auditoria", "audit"}

    base_dir = os.path.dirname(__file__)
    blockchain_client = BlockchainClient(BASE_DIR, args.source)
    bc = blockchain_client if blockchain_client.enabled else None
    afn = AFNAuditoria2(blockchain_client=bc) if _audit else AFNRefinado(blockchain_client=bc)

    if args.simulate:
        print("Usando modo simulado legado.")
        # Pequena simulação mínima só para manter compatibilidade
        palavras = [
            (["mão", "ativimetro"], [[0, 0, 100, 100], [300, 300, 400, 400]]),
            (["com luva", "ativimetro"], [[0, 0, 100, 100], [300, 300, 400, 400]]),
            (["cesta", "amostra", "ativimetro"], [[50, 50, 100, 100], [70, 70, 110, 110], [300, 300, 400, 400]]),
            # A partir daqui, q3 vai validar se amostra está dentro da cesta via boxes
            (["amostra", "cesta", "ativimetro"], [[60, 60, 100, 100], [50, 50, 120, 120], [300, 300, 400, 400]]),
            (["amostra", "ativimetro"], [[320, 320, 350, 350], [300, 300, 400, 400]]),
        ]
        for objetos, boxes in palavras:
            afn.processar(objetos, boxes, objetos)
        return

    # YOLO em imagem/vídeo/webcam
    try:
        from ultralytics import YOLO
        import cv2
    except Exception as e:
        print("YOLO não disponível. Instale com: pip install ultralytics opencv-python")
        return

    model_path = args.model.strip() or _choose_model_path(base_dir)
    if not os.path.exists(model_path):
        print("Modelo YOLO não encontrado. Coloque 'ModeloTreinadoV3.pt' (padrão) ou outro .pt na pasta Automatos e/ou use --model.")
        return
    print(f"Carregando modelo: {model_path}")
    modelo = YOLO(model_path)

    src = args.source
    # Webcam se número inteiro
    cap = None
    if src.isdigit():
        cap = cv2.VideoCapture(int(src))
    elif os.path.isfile(src):
        # Detecta se é imagem por extensão
        ext = os.path.splitext(src)[1].lower()
        if ext in {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}:
            pares = _gen_from_image(modelo, src)
            for objetos, boxes in pares:
                r = afn.processar(objetos, boxes, objetos)
                if r == "fim":
                    break
            return
        else:
            cap = cv2.VideoCapture(src)
    else:
        print(f"Fonte inválida: {src}")
        return

    if not cap or not cap.isOpened():
        print(f"Não foi possível abrir a fonte: {src}")
        return

    _stream_from_capture(modelo, cap, afn)


if __name__ == "__main__":
    main()
