# ============================================================
# DATA_AGENT.PY
#
# Parte 1  - Pombo:  varre o CICLO ATUAL do log (do ultimo
#                    "POMBO - INICIO DO CICLO" ate o fim),
#                    captura erros.
# Parte 1b - Pombo parado: servico UP mas log sem andar
#                    por mais de POMBO_STALE_MINUTOS -> ERRO.
# Parte 2  - Metabase: erros no RABO do log do dia
#                    (ultimas METABASE_LOG_LINHAS_MAX linhas).
# Parte 3  - Health check: http://localhost:3000/api/health.
#
# Dedupe (esquema do backup): ERRO uma vez por episodio;
# sumiu da janela -> RESOLVIDO.
# Exclusoes: por REGEX (linha) e por CHAVE (assinatura).
# Tudo cai em db_automate.logs_db_automate, id_funcao = 1.
# Execucao: a cada 1 hora.
# ============================================================

import os
import re
import socket
import time
import logging
import hashlib
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv


# ============================================================
# CONFIGURACOES
# ============================================================

PASTA_BASE = Path(r"C:\Data_Agent")
PASTA_LOG = PASTA_BASE / "log"
ARQUIVO_ENV = PASTA_BASE / ".env"
ARQUIVO_LOG = PASTA_LOG / "data_agent.log"

ID_FUNCAO_MONITOR = 1
INTERVALO_VERIFICACAO = 3600          # 1 hora

SERVICOS_MONITORADOS = ["MetabaseService", "PomboService"]
METABASE_HEALTH_URL = "http://localhost:3000/api/health"
METABASE_TIMEOUT_SEGUNDOS = 10
METABASE_LOG_LINHAS_MAX = 2000        # rabo do log do Metabase

POMBO_STALE_MINUTOS = 20              # sem linha nova no log por mais que isso = travado

PASTA_LOG_POMBO = Path(r"C:\Users\svc-qlikv\PycharmProjects\WelcomeScreen\Pombo\logs")
PASTA_LOG_METABASE = Path(r"D:\Metabase\logs")

# Exclusao por REGEX (aplicada na linha do log).
EXCLUSOES = [
    # Pombo: BDP_900 / BDP_3700 com timeout de parquet
    r"BDP[_ ]?900.*(timeout|timed out|time.?out)",
    r"BDP[_ ]?3700.*(timeout|timed out|time.?out)",
    r"(timeout|timed out|time.?out).*BDP[_ ]?900",
    r"(timeout|timed out|time.?out).*BDP[_ ]?3700",

    # Metabase: startup do scheduler Quartz (bate no "ERROR" do texto)
    r"reset from ERROR state to",
    # Metabase: ClusterManager varrendo instancia reiniciada
    r"ClusterManager:.*(failed|restarted)",
    # Metabase: metabot sem chave de IA configurada
    r"Nenhuma chave de API",
    r"missing_api_key",
    r"Example question generation failed",
    r"Suggested prompts generation failed",
    # Metabase: health 503 durante inicializacao (o proprio health check cobre)
    r"ERROR middleware\.log :: GET /api/health",
]

# Exclusao por CHAVE (assinatura de 12 caracteres ja observada).
# Adicionar aqui os erros conhecidos/ignorados para nao abrir episodio.
EXCLUSOES_CHAVES = {
    "ebf78ea1fb1a", "470f23a45fec", "ce9d352eaf84", "b3dc260cc875",
    "777f2aa9982f", "069cb027097d", "bcd178eda97d", "34bf03599963",
    "cfeaea9e76a9", "078e39b483ba", "f349ff963e9c", "94f948d56939",
    "026cdb455290", "a18e10831cfc", "fc1f277c6777", "8f0f764e3816",
    "6774874e43bc", "7456fbddc45d", "95cd98d98b9e", "a9c6912aaaa1",
    "fa97619f3ded", "c3227a013a7f", "b678a734e6dc", "61ca08021f02",
    "40ec7d99e2a7", "5fc8a30374e1", "d3815cf5f9cf",
}

PASTA_BASE.mkdir(exist_ok=True)
PASTA_LOG.mkdir(exist_ok=True)


# ============================================================
# LOG LOCAL
# ============================================================

logging.basicConfig(
    filename=ARQUIVO_LOG,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%d/%m/%Y %H:%M:%S"
)


# ============================================================
# .ENV
# ============================================================

if not ARQUIVO_ENV.exists():
    ARQUIVO_ENV.write_text(
        "DB_HOST=\n"
        "DB_PORT=54320\n"
        "DB_NAME=automate\n"
        "DB_USER=\n"
        "DB_PASSWORD=\n",
        encoding="utf-8"
    )

load_dotenv(ARQUIVO_ENV)

DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", "54320"))
DB_NAME = os.getenv("DB_NAME", "automate")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")


# ============================================================
# CONEXAO / IDENTIDADE / GRAVACAO
# ============================================================

class conexo_cursor:
    def __init__(self, conn):
        self.conn = conn
    def __enter__(self):
        self.cur = self.conn.cursor()
        return self.cur
    def __exit__(self, *args):
        self.cur.close()


def conectar_postgres():
    return psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        row_factory=dict_row,
        connect_timeout=5
    )


def buscar_agente():
    host_name = socket.gethostname()

    with conectar_postgres() as conexao:
        with conexo_cursor(conexao) as cursor:
            cursor.execute(
                """
                SELECT id_agente, host_name, id_funcao
                FROM db_automate.agentes
                WHERE UPPER(host_name) = UPPER(%s)
                  AND id_funcao = %s
                LIMIT 1;
                """,
                (host_name, ID_FUNCAO_MONITOR)
            )
            agente = cursor.fetchone()

    return agente


def gravar_log(id_agente, objeto, status, log_detalhe):
    with conectar_postgres() as conexao:
        with conexo_cursor(conexao) as cursor:
            cursor.execute(
                """
                INSERT INTO db_automate.logs_db_automate
                    (id_agente, id_funcao, data_log, objeto, status, log_detalhe)
                VALUES (%s, %s, CURRENT_TIMESTAMP, %s, %s, %s);
                """,
                (id_agente, ID_FUNCAO_MONITOR, objeto, status, log_detalhe)
            )
        conexao.commit()


def ultimo_status_do_objeto(id_agente, objeto):
    with conectar_postgres() as conexao:
        with conexo_cursor(conexao) as cursor:
            cursor.execute(
                """
                SELECT status
                FROM db_automate.logs_db_automate
                WHERE id_agente = %s
                  AND id_funcao = %s
                  AND objeto = %s
                ORDER BY data_log DESC, id_log DESC
                LIMIT 1;
                """,
                (id_agente, ID_FUNCAO_MONITOR, objeto)
            )
            linha = cursor.fetchone()
    return linha["status"] if linha else None


# ============================================================
# MAQUINA DE EPISODIOS
# ============================================================

EPISODIOS_ABERTOS = set()


def assinatura(texto):
    texto = re.sub(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2} \| ", "", texto)
    texto = re.sub(r"\d+", "#", texto)
    texto = re.sub(r"\s+", " ", texto).strip().lower()
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()


def abrir_episodio(id_agente, chave, detalhe):
    if chave in EPISODIOS_ABERTOS:
        return
    if ultimo_status_do_objeto(id_agente, chave) == "ERRO":
        EPISODIOS_ABERTOS.add(chave)
        return
    gravar_log(id_agente, chave, "ERRO", detalhe[:1800])
    EPISODIOS_ABERTOS.add(chave)
    logging.info("Erro novo registrado | Chave=%s", chave)


def fechar_episodio(id_agente, chave, mensagem):
    if chave in EPISODIOS_ABERTOS:
        gravar_log(id_agente, chave, "RESOLVIDO", mensagem)
        EPISODIOS_ABERTOS.discard(chave)
        logging.info("Erro resolvido | Chave=%s", chave)


def fechar_episodios_ausentes(id_agente, prefixo_fonte, vistos):
    for chave in list(EPISODIOS_ABERTOS):
        if chave.startswith(prefixo_fonte) and chave not in vistos:
            fechar_episodio(
                id_agente,
                chave,
                f"Mensagem=Erro ausente na janela;Encerrado em={datetime.now():%d/%m/%Y %H:%M:%S}"
            )


# ============================================================
# LEITURA E CLASSIFICACAO DE ERROS
# ============================================================

RE_EXCLUSAO = [re.compile(p, re.IGNORECASE) for p in EXCLUSOES]

RE_INICIO_TRACEBACK = re.compile(r"Traceback \(most recent call last\)")
RE_FIM_TRACEBACK = re.compile(r"^([A-Za-z_][\w.]*?(?:Error|Exception|Interrupt))\b")
RE_ERRO_ISOLADO = re.compile(
    r"\bERRO\b|\bERROR\b|FATAL|Failed|RecursionError|ModuleNotFoundError|"
    r"Falha na etapa|\[SILVER ERRO\]", re.IGNORECASE
)


def linha_excluida(linha):
    return any(p.search(linha) for p in RE_EXCLUSAO)


def extrair_eventos(linhas):
    eventos = []
    i = 0
    total = len(linhas)

    while i < total:
        linha = linhas[i]

        if linha_excluida(linha):
            i += 1
            continue

        bloco = None

        if RE_INICIO_TRACEBACK.search(linha):
            j = i
            limite = min(i + 40, total)
            while j < limite:
                if RE_FIM_TRACEBACK.search(linhas[j].strip()) and j > i:
                    bloco = linhas[i:j + 1]
                    i = j + 1
                    break
                j += 1
            else:
                bloco = linhas[i:limite]
                i = limite

        elif RE_ERRO_ISOLADO.search(linha):
            bloco = linhas[i:i + 3]
            i += 1

        else:
            i += 1
            continue

        if not bloco:
            continue

        assin_bloco = None
        for l in reversed(bloco):
            if RE_FIM_TRACEBACK.search(l.strip()):
                assin_bloco = l
                break
        if not assin_bloco:
            assin_bloco = bloco[0]

        eventos.append((assinatura(assin_bloco)[:12], "\n".join(bloco)))

    return eventos


def ler_log_do_dia(pasta, prefixo):
    if not pasta.is_dir():
        return []
    hoje = datetime.now().strftime("%Y%m%d")
    arquivo = pasta / f"{prefixo}_{hoje}.log"
    if not arquivo.is_file():
        return []
    return arquivo.read_text(encoding="utf-8", errors="replace").splitlines()


def processar_eventos(id_agente, prefixo_fonte, eventos):
    vistos = set()
    for assin, detalhe in eventos:
        if assin in EXCLUSOES_CHAVES:
            continue                      # chave ignorada: nem vira episodio
        chave = f"{prefixo_fonte}:{assin}"
        vistos.add(chave)
        abrir_episodio(id_agente, chave, detalhe)
    fechar_episodios_ausentes(id_agente, f"{prefixo_fonte}:", vistos)


# ============================================================
# PARTE 1 - ERROS DO POMBO (janela = ciclo atual)
# ============================================================

def checar_pombo(id_agente):
    linhas = ler_log_do_dia(PASTA_LOG_POMBO, "pombo")

    inicio = 0
    for idx in range(len(linhas) - 1, -1, -1):
        if "POMBO - IN" in linhas[idx] and "CICLO" in linhas[idx]:
            inicio = idx
            break

    janela = linhas[inicio:] if linhas else []
    processar_eventos(id_agente, "pombo", extrair_eventos(janela))


# ============================================================
# PARTE 1b - POMBO PARADO (servico UP mas log sem andar)
# ============================================================

def checar_pombo_stale(id_agente, status_servicos):
    # So faz sentido se o servico estiver de pe; OFF ja e
    # alerta de STOPPED do Central.
    if status_servicos.get("PomboService") != "RUNNING":
        return

    hoje = datetime.now().strftime("%Y%m%d")
    arquivo = PASTA_LOG_POMBO / f"pombo_{hoje}.log"

    if not arquivo.is_file():
        return

    ultima_escrita = datetime.fromtimestamp(arquivo.stat().st_mtime)
    parado_min = (datetime.now() - ultima_escrita).total_seconds() / 60

    chave = "pombo:stale_log"

    if parado_min > POMBO_STALE_MINUTOS:
        abrir_episodio(
            id_agente,
            chave,
            f"Fonte=pombo;Mensagem=Pombo sem escrever no log ha "
            f"{parado_min:.0f} min (limite {POMBO_STALE_MINUTOS});"
            f"Ultima linha em={ultima_escrita:%d/%m/%Y %H:%M:%S}"
        )
    else:
        fechar_episodio(
            id_agente,
            chave,
            f"Mensagem=Pombo voltou a escrever no log "
            f"(ultima linha {parado_min:.0f} min atras);"
            f"Encerrado em={datetime.now():%d/%m/%Y %H:%M:%S}"
        )


# ============================================================
# PARTE 2 - ERROS DO METABASE (rabo do log do dia)
# ============================================================

def checar_metabase_log(id_agente):
    linhas = ler_log_do_dia(PASTA_LOG_METABASE, "metabase")
    linhas = linhas[-METABASE_LOG_LINHAS_MAX:]
    processar_eventos(id_agente, "metabase_log", extrair_eventos(linhas))


# ============================================================
# PARTE 3 - HEALTH CHECK DO METABASE
# ============================================================

def checar_metabase_http(id_agente, status_servicos):
    if status_servicos.get("MetabaseService") != "RUNNING":
        return

    chave = "metabase_http:health"
    ok = False
    erro_msg = ""

    try:
        with urllib.request.urlopen(
            METABASE_HEALTH_URL,
            timeout=METABASE_TIMEOUT_SEGUNDOS
        ) as resp:
            corpo = resp.read().decode("utf-8", errors="replace")
            ok = (resp.status == 200 and '"status"' in corpo)
            if not ok:
                erro_msg = f"HTTP {resp.status}: {corpo[:200]}"
    except Exception as e:
        erro_msg = f"{type(e).__name__}: {e}"

    if ok:
        fechar_episodio(
            id_agente, chave,
            f"Mensagem=Metabase voltou a responder em {METABASE_HEALTH_URL};"
            f"Encerrado em={datetime.now():%d/%m/%Y %H:%M:%S}"
        )
    else:
        abrir_episodio(
            id_agente, chave,
            f"Fonte=metabase_http;Mensagem=Health check falhou: {erro_msg};"
            f"URL={METABASE_HEALTH_URL}"
        )


# ============================================================
# SERVICOS
# ============================================================

def status_servico_windows(nome_servico):
    try:
        resultado = subprocess.run(
            ["sc", "queryex", nome_servico],
            capture_output=True, text=True, timeout=15
        )
        m = re.search(r"STATE\s*:\s*\d+\s+(\w+)", resultado.stdout)
        return m.group(1) if m else "NAO_ENCONTRADO"
    except Exception:
        return "ERRO_CONSULTA"


def checar_servicos(id_agente):
    status = {}
    for servico in SERVICOS_MONITORADOS:
        st = status_servico_windows(servico)
        status[servico] = st
        gravar_log(id_agente, servico, st, f"Servico={servico};Status={st}")
    return status


# ============================================================
# CICLO / MAIN
# ============================================================

def executar_ciclo(id_agente):
    status = checar_servicos(id_agente)
    checar_pombo(id_agente)
    checar_pombo_stale(id_agente, status)
    checar_metabase_log(id_agente)
    checar_metabase_http(id_agente, status)


def main():
    logging.info("Data Agent iniciado | Host=%s", socket.gethostname())

    try:
        agente = buscar_agente()
    except Exception:
        logging.exception("FALHA ao conectar no banco / identificar agente")
        return

    if not agente:
        logging.warning("Nenhum agente Monitor encontrado para Host=%s",
                        socket.gethostname())
        return

    logging.info("Agente encontrado | ID=%s | Host=%s",
                 agente["id_agente"], agente["host_name"])

    while True:
        try:
            executar_ciclo(agente["id_agente"])
        except Exception:
            logging.exception("Erro geral no ciclo do Data Agent")
        time.sleep(INTERVALO_VERIFICACAO)


if __name__ == "__main__":
    main()