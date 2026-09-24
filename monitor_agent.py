import os
import socket
import subprocess
import time
import logging

import psycopg
from dotenv import load_dotenv


# ==========================================================
# PASTAS DO AGENTE
# ==========================================================

PASTA_AGENT = r"C:\Monitor_Agent"
PASTA_LOG = os.path.join(PASTA_AGENT, "log")
ARQUIVO_ENV = os.path.join(PASTA_AGENT, ".env")
ARQUIVO_LOG = os.path.join(
    PASTA_LOG,
    "monitor_agent.log"
)


# ==========================================================
# PREPARA AMBIENTE
# ==========================================================

def preparar_ambiente():

    pasta_existia = os.path.exists(
        PASTA_AGENT
    )

    # Cria C:\Monitor_Agent somente se não existir
    if not pasta_existia:

        os.makedirs(
            PASTA_AGENT,
            exist_ok=True
        )

        # Cria o .env apenas na primeira criação da pasta
        with open(
            ARQUIVO_ENV,
            "w",
            encoding="utf-8"
        ) as arquivo:

            arquivo.write(
                "DB_HOST=\n"
                "DB_PORT=54320\n"
                "DB_NAME=automate\n"
                "DB_USER=automate_adm\n"
                "DB_PASSWORD=\n"
            )

    # Garante a existência da pasta de logs
    os.makedirs(
        PASTA_LOG,
        exist_ok=True
    )


# ==========================================================
# PREPARA PASTAS ANTES DO RESTANTE
# ==========================================================

preparar_ambiente()


# ==========================================================
# LOG
# ==========================================================

logging.basicConfig(
    filename=ARQUIVO_LOG,
    level=logging.INFO,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(message)s"
    ),
    datefmt="%d/%m/%Y %H:%M:%S",
    encoding="utf-8"
)


# ==========================================================
# CONFIGURAÇÃO
# ==========================================================

load_dotenv(
    dotenv_path=ARQUIVO_ENV
)

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

INTERVALO_EXECUCAO = 1200  # 20 minutos


# ==========================================================
# VALIDA CONFIGURAÇÃO
# ==========================================================

def validar_configuracao():

    if not DB_PASSWORD:

        mensagem = (
            "DB_PASSWORD não configurada no arquivo "
            r"C:\Monitor_Agent\.env"
        )

        print(mensagem)

        logging.warning(
            mensagem
        )

        return False

    if not DB_HOST:

        mensagem = (
            "DB_HOST não configurado no arquivo "
            r"C:\Monitor_Agent\.env"
        )

        print(mensagem)

        logging.warning(
            mensagem
        )

        return False

    return True


# ==========================================================
# CONEXÃO POSTGRESQL
# ==========================================================

def conectar_postgres():

    return psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )


# ==========================================================
# IDENTIFICA O AGENTE
# ==========================================================

def buscar_agente(conn):

    host_name = socket.gethostname()

    with conn.cursor() as cursor:

        cursor.execute(
            """
            SELECT id_agente
            FROM db_automate.agentes
            WHERE UPPER(host_name) = UPPER(%s)
            """,
            (host_name,)
        )

        agente = cursor.fetchone()

    if agente is None:

        raise Exception(
            f"Agente não cadastrado para o hostname: "
            f"{host_name}"
        )

    return agente[0], host_name


# ==========================================================
# BUSCA FUNÇÃO MONITOR ATIVA
# ==========================================================

def buscar_monitor(
    conn,
    id_agente
):

    with conn.cursor() as cursor:

        cursor.execute(
            """
            SELECT
                af.id_funcao,
                af.nomes_servicos

            FROM db_automate.agente_funcoes af

            INNER JOIN db_automate.funcoes f
                ON f.id_funcao = af.id_funcao

            WHERE af.id_agente = %s
              AND af.ativo = TRUE
              AND f.nome_funcao = 'Monitor'
            """,
            (id_agente,)
        )

        monitor = cursor.fetchone()

    return monitor


# ==========================================================
# VERIFICA SERVIÇO WINDOWS
# ==========================================================

def verificar_servico(
    nome_servico
):

    comando = [
        "powershell",
        "-NoProfile",
        "-Command",
        (
            f"(Get-Service -Name "
            f"'{nome_servico}').Status.ToString()"
        )
    ]

    resultado = subprocess.run(
        comando,
        capture_output=True,
        text=True
    )

    if resultado.returncode != 0:
        return "NAO_ENCONTRADO"

    return (
        resultado
        .stdout
        .strip()
        .upper()
    )


# ==========================================================
# GRAVA LOG NO POSTGRESQL
# ==========================================================

def gravar_log(
    conn,
    id_agente,
    id_funcao,
    objeto,
    status,
    log_detalhe
):

    with conn.cursor() as cursor:

        cursor.execute(
            """
            INSERT INTO db_automate.logs_db_automate
            (
                id_agente,
                id_funcao,
                data_log,
                objeto,
                status,
                log_detalhe
            )
            VALUES
            (
                %s,
                %s,
                CURRENT_TIMESTAMP,
                %s,
                %s,
                %s
            )
            """,
            (
                id_agente,
                id_funcao,
                objeto,
                status,
                log_detalhe
            )
        )

    conn.commit()


# ==========================================================
# EXECUTA UMA RODADA
# ==========================================================

def executar_monitoramento():

    print()
    print("DB Automate - Monitor")
    print("---------------------")

    logging.info(
        "Iniciando rodada de monitoramento."
    )

    if not validar_configuracao():

        logging.warning(
            "Monitoramento não executado "
            "por falta de configuração."
        )

        return

    with conectar_postgres() as conn:

        id_agente, host_name = buscar_agente(
            conn
        )

        print(
            f"Host: {host_name}"
        )

        print(
            f"Agente: {id_agente}"
        )

        logging.info(
            f"Agente identificado: "
            f"{id_agente} | "
            f"Host: {host_name}"
        )

        monitor = buscar_monitor(
            conn,
            id_agente
        )

        if monitor is None:

            mensagem = (
                "Função Monitor não está ativa."
            )

            print(mensagem)
            logging.warning(mensagem)

            return

        id_funcao, nomes_servicos = monitor

        if not nomes_servicos:

            mensagem = (
                "Nenhum serviço configurado."
            )

            print(mensagem)
            logging.warning(mensagem)

            return

        servicos = nomes_servicos.split(";")

        print(
            f"Serviços encontrados: "
            f"{len(servicos)}"
        )

        print()

        for servico in servicos:

            servico = servico.strip()

            if not servico:
                continue

            status = verificar_servico(
                servico
            )

            print(
                f"{servico}: {status}"
            )

            logging.info(
                f"Servico={servico};"
                f"Status={status}"
            )

            detalhe = (
                f"Servico={servico};"
                f"Status={status}"
            )

            gravar_log(
                conn,
                id_agente,
                id_funcao,
                servico,
                status,
                detalhe
            )

    print()
    print(
        "Monitoramento finalizado."
    )

    logging.info(
        "Rodada de monitoramento finalizada."
    )


# ==========================================================
# PRINCIPAL
# ==========================================================

def main():

    logging.info(
        "DB Automate Monitor iniciado."
    )

    while True:

        try:

            executar_monitoramento()

        except Exception as erro:

            print()
            print(
                f"Erro no DB Automate - Monitor: "
                f"{erro}"
            )

            logging.exception(
                f"Erro no DB Automate - Monitor: "
                f"{erro}"
            )

        print()
        print(
            "Próxima verificação em "
            "20 minutos..."
        )

        logging.info(
            "Próxima verificação em "
            "20 minutos."
        )

        time.sleep(
            INTERVALO_EXECUCAO
        )


if __name__ == "__main__":
    main()