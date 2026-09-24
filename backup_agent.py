import os
import socket
import time
import logging
from datetime import datetime, timedelta

import pyodbc
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv


# ============================================================
# CONFIGURAÇÕES
# ============================================================

PASTA_BASE = r"C:\Backup_Agent"
PASTA_LOG = os.path.join(PASTA_BASE, "log")
ARQUIVO_ENV = os.path.join(PASTA_BASE, ".env")
ARQUIVO_LOG = os.path.join(PASTA_LOG, "backup_agent.log")

ID_FUNCAO_BACKUP = 4

# Tempo entre verificações da agenda.
INTERVALO_VERIFICACAO = 600


# ============================================================
# PREPARAÇÃO DAS PASTAS
# ============================================================

os.makedirs(PASTA_BASE, exist_ok=True)
os.makedirs(PASTA_LOG, exist_ok=True)


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

if not os.path.exists(ARQUIVO_ENV):
    with open(ARQUIVO_ENV, "w", encoding="utf-8") as arquivo:
        arquivo.write(
            "DB_AUTOMATE_HOST=\n"
            "DB_AUTOMATE_PORT=54320\n"
            "DB_AUTOMATE_NAME=automate\n"
            "DB_AUTOMATE_USER=automate_adm\n"
            "DB_AUTOMATE_PASSWORD=\n"
        )

load_dotenv(ARQUIVO_ENV)


DB_HOST = os.getenv("DB_AUTOMATE_HOST")
DB_PORT = os.getenv("DB_AUTOMATE_PORT")
DB_NAME = os.getenv("DB_AUTOMATE_NAME")
DB_USER = os.getenv("DB_AUTOMATE_USER")
DB_PASSWORD = os.getenv("DB_AUTOMATE_PASSWORD")


# ============================================================
# CONEXÃO POSTGRESQL
# ============================================================

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


# ============================================================
# IDENTIFICAR AGENTE
# ============================================================

def buscar_agente():
    host_name = socket.gethostname()

    with conectar_postgres() as conexao:
        with conexao.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    id_agente,
                    host_name,
                    id_funcao
                FROM db_automate.agentes
                WHERE UPPER(host_name) = UPPER(%s)
                  AND id_funcao = %s
                LIMIT 1;
                """,
                (
                    host_name,
                    ID_FUNCAO_BACKUP
                )
            )

            agente = cursor.fetchone()

    return agente


# ============================================================
# BUSCAR BASES DO SERVIDOR
# ============================================================

def buscar_bases(host_name):
    with conectar_postgres() as conexao:
        with conexao.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    b.id_base,
                    b.nome,
                    b.service_name,
                    b.ip,
                    b.host_name,
                    b.porta,
                    b.usuario,
                    b.senha,
                    b.driver_odbc,
                    b.diretorio_backup,

                    p.periodo,
                    p.start_time,
                    p.horario_ult_backup,
                    p.horario_proximo_backup,
                    p.forcar_backup

                FROM db_automate.bases b

                INNER JOIN db_automate.periodicidade_backup p
                    ON p.id_base = b.id_base

                WHERE UPPER(b.host_name) = UPPER(%s)
                  AND b.ativo = TRUE

                ORDER BY b.id_base;
                """,
                (host_name,)
            )

            bases = cursor.fetchall()

    return bases


# ============================================================
# GRAVAR LOG NO DB_AUTOMATE
# ============================================================

def gravar_log(
    id_agente,
    id_funcao,
    objeto,
    status,
    log_detalhe
):
    with conectar_postgres() as conexao:
        with conexao.cursor() as cursor:

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
                );
                """,
                (
                    id_agente,
                    id_funcao,
                    objeto,
                    status,
                    log_detalhe
                )
            )

        conexao.commit()


# ============================================================
# VERIFICAR SE A BASE ESTÁ NA HORA DO BACKUP
# ============================================================

def deve_executar_backup(base):
    # Backup forçado tem prioridade sobre qualquer regra de horário.
    if base["forcar_backup"] is True:
        return True

    agora = datetime.now()
    hora_atual = agora.time()

    start_time = base["start_time"]
    proximo_backup = base["horario_proximo_backup"]

    # Primeira execução.
    if proximo_backup is None:
        return hora_atual >= start_time

    # A agenda diária começa às 00:00.
    #
    # Se o último horário registrado ficou maior que o horário
    # atual, significa que viramos o dia.
    ultimo_backup = base["horario_ult_backup"]

    if (
        ultimo_backup is not None
        and hora_atual < ultimo_backup
    ):
        return hora_atual >= start_time

    return hora_atual >= proximo_backup


# ============================================================
# CONEXÃO SQL ANYWHERE
# ============================================================

def conectar_sql_anywhere(base):
    connection_string = (
        f"DRIVER={{{base['driver_odbc']}}};"
        f"UID={base['usuario']};"
        f"PWD={base['senha']};"
        f"ENG={base['service_name']};"
        f"DBN={base['nome']};"
        f"LINKS=tcpip("
        f"host={base['ip']}:{base['porta']}"
        f");"
    )

    return pyodbc.connect(
        connection_string,
        autocommit=True,
        timeout=30
    )


# ============================================================
# EXECUTAR BACKUP
# ============================================================

def executar_backup(base):
    conexao = None

    try:
        conexao = conectar_sql_anywhere(base)

        cursor = conexao.cursor()

        diretorio = base["diretorio_backup"]

        # Protege a string caso algum caminho possua apóstrofo.
        diretorio_sql = diretorio.replace("'", "''")

        comando = f"""
            BACKUP DATABASE
            DIRECTORY '{diretorio_sql}'
            TRANSACTION LOG TRUNCATE
        """

        logging.info(
            "Iniciando backup | Base=%s | Destino=%s",
            base["service_name"],
            diretorio
        )

        inicio = datetime.now()

        cursor.execute(comando)

        fim = datetime.now()

        logging.info(
            "Backup concluido | Base=%s | Duracao=%s",
            base["service_name"],
            fim - inicio
        )

        return True, None

    except Exception as erro:

        logging.exception(
            "Erro no backup | Base=%s",
            base["service_name"]
        )

        return False, str(erro)

    finally:

        if conexao is not None:
            try:
                conexao.close()
            except Exception:
                pass


# ============================================================
# DESATIVAR BACKUP FORÇADO
# ============================================================

def desativar_backup_forcado(id_base):
    with conectar_postgres() as conexao:
        with conexao.cursor() as cursor:

            cursor.execute(
                """
                UPDATE db_automate.periodicidade_backup
                SET forcar_backup = FALSE
                WHERE id_base = %s;
                """,
                (id_base,)
            )

        conexao.commit()


# ============================================================
# ATUALIZAR HORÁRIOS
# ============================================================

def atualizar_periodicidade(id_base, periodo):
    horario_ultimo = datetime.now()

    horario_proximo = (
        horario_ultimo + periodo
    ).time()

    with conectar_postgres() as conexao:
        with conexao.cursor() as cursor:

            cursor.execute(
                """
                UPDATE db_automate.periodicidade_backup
                SET
                    horario_ult_backup = %s,
                    horario_proximo_backup = %s
                WHERE id_base = %s;
                """,
                (
                    horario_ultimo.time(),
                    horario_proximo,
                    id_base
                )
            )

        conexao.commit()


# ============================================================
# PROCESSAR UMA BASE
# ============================================================

def processar_base(
    agente,
    base
):
    nome_base = base["service_name"]

    backup_forcado = base["forcar_backup"] is True

    if backup_forcado:
        logging.info(
            "Backup forcado solicitado | ID Base=%s | Base=%s",
            base["id_base"],
            nome_base
        )

    sucesso, erro = executar_backup(base)

    # O comando de backup terminou, com sucesso ou erro.
    # Se a execução foi forçada, libera imediatamente o indicador.
    if backup_forcado:
        desativar_backup_forcado(base["id_base"])

        logging.info(
            "Backup forcado finalizado | ID Base=%s | Base=%s | forcar_backup=FALSE",
            base["id_base"],
            nome_base
        )

    horario = datetime.now().strftime("%H:%M:%S")

    if sucesso:

        detalhe = (
            f"Horario={horario};"
            f"Base={nome_base};"
            f"Mensagem=Backup realizado com sucesso"
        )

        gravar_log(
            id_agente=agente["id_agente"],
            id_funcao=agente["id_funcao"],
            objeto=nome_base,
            status="SUCESSO",
            log_detalhe=detalhe
        )

        # Backup forçado é emergencial e não altera a agenda normal.
        # Somente backups executados pela periodicidade atualizam
        # horario_ult_backup e horario_proximo_backup.
        if not backup_forcado:
            atualizar_periodicidade(
                id_base=base["id_base"],
                periodo=base["periodo"]
            )

    else:

        detalhe = (
            f"Horario={horario};"
            f"Base={nome_base};"
            f"Mensagem=Backup não realizado: {erro}"
        )

        gravar_log(
            id_agente=agente["id_agente"],
            id_funcao=agente["id_funcao"],
            objeto=nome_base,
            status="ERRO",
            log_detalhe=detalhe
        )


# ============================================================
# CICLO DO AGENTE
# ============================================================

def executar_ciclo():
    agente = buscar_agente()

    if not agente:

        host = socket.gethostname()

        mensagem = (
            f"Nenhum agente de Backup encontrado "
            f"para Host={host} e id_funcao={ID_FUNCAO_BACKUP}"
        )

        logging.warning(mensagem)

        return

    logging.info(
        "Agente encontrado | ID=%s | Host=%s | Funcao=%s",
        agente["id_agente"],
        agente["host_name"],
        agente["id_funcao"]
    )

    bases = buscar_bases(
        agente["host_name"]
    )

    logging.info(
        "Bases encontradas para backup: %s",
        len(bases)
    )

    for base in bases:

        try:

            if not deve_executar_backup(base):
                continue

            logging.info(
                "Backup vencido | ID Base=%s | Base=%s",
                base["id_base"],
                base["service_name"]
            )

            processar_base(
                agente,
                base
            )

        except Exception as erro:

            logging.exception(
                "Erro ao processar Base=%s",
                base["service_name"]
            )

            horario = datetime.now().strftime(
                "%H:%M:%S"
            )

            detalhe = (
                f"Horario={horario};"
                f"Base={base['service_name']};"
                f"Mensagem=Backup não realizado: {erro}"
            )

            try:
                gravar_log(
                    id_agente=agente["id_agente"],
                    id_funcao=agente["id_funcao"],
                    objeto=base["service_name"],
                    status="ERRO",
                    log_detalhe=detalhe
                )

            except Exception:
                logging.exception(
                    "Nao foi possivel gravar o erro no PostgreSQL"
                )


# ============================================================
# MAIN
# ============================================================

def main():
    logging.info(
        "Backup Agent iniciado | Host=%s",
        socket.gethostname()
    )

    while True:

        try:
            executar_ciclo()

        except Exception:
            logging.exception(
                "Erro geral no ciclo do Backup Agent"
            )

        time.sleep(
            INTERVALO_VERIFICACAO
        )


if __name__ == "__main__":
    main()