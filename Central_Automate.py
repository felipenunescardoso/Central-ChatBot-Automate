import io
import os
import sys
import time
import threading
from pathlib import Path
from datetime import datetime, timedelta

import psycopg

from Telegram import listar_chats, enviar_mensagem
from backup_alertas import (
    processar_erros_backup,
    registrar_pendencia_backup,
    processar_resposta_backup,
)


# ==========================================================
# LOG EM ARQUIVO (C:\Data_Agent\log\central_logs_YYYYMMDD.log)
# Espelha o padrao dos wrappers: um arquivo por dia,
# timestamp por linha, console continua funcionando.
# ==========================================================

LOG_DIR = Path(r"C:\Data_Agent\log")
LOG_DIR.mkdir(parents=True, exist_ok=True)


class _LogDiario:
    """Arquivo de log que gira por dia."""

    def __init__(self, prefixo):
        self.prefixo = prefixo
        self._data = None
        self._arq = None
        self._lock = threading.Lock()

    def _garantir(self):
        hoje = datetime.now().strftime("%Y%m%d")
        if self._data != hoje:
            if self._arq:
                self._arq.close()
            self._arq = open(
                LOG_DIR / f"{self.prefixo}_{hoje}.log",
                "a", encoding="utf-8", buffering=1
            )
            self._data = hoje

    def write(self, s):
        with self._lock:
            self._garantir()
            self._arq.write(s)
            self._arq.flush()
        return len(s)

    def flush(self):
        if self._arq:
            self._arq.flush()


class _ComTimestamp(io.TextIOBase):
    """Prefixa cada linha com data/hora."""

    def __init__(self, destino):
        self.destino = destino
        self._buf = ""

    def write(self, data):
        self._buf += data
        while "\n" in self._buf:
            linha, self._buf = self._buf.split("\n", 1)
            if linha.strip():
                ts = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                self.destino.write(f"{ts} | {linha}\n")
        return len(data)

    def flush(self):
        self.destino.flush()


class _Duplex(io.TextIOBase):
    """Espelha tudo para dois destinos (console + arquivo)."""

    def __init__(self, a, b):
        self.a, self.b = a, b

    def write(self, s):
        try:
            self.a.write(s)
        except UnicodeEncodeError:
            pass
        self.b.write(s)
        return len(s)

    def flush(self):
        try:
            self.a.flush()
        except Exception:
            pass
        self.b.flush()


def configurar_logs():
    # Console tolerante: nunca explode por causa de acento/emoji
    try:
        sys.__stdout__.reconfigure(errors="replace")
        sys.__stderr__.reconfigure(errors="replace")
    except Exception:
        pass

    arquivo = _LogDiario("central_logs")
    sys.stdout = _Duplex(sys.__stdout__, _ComTimestamp(arquivo))
    sys.stderr = _Duplex(sys.__stderr__, _ComTimestamp(arquivo))


# ==========================================================
# CONFIGURAÇÃO
# ==========================================================

DB_HOST = os.getenv("DB_AUTOMATE_HOST")
DB_PORT = os.getenv("DB_AUTOMATE_PORT")
DB_NAME = os.getenv("DB_AUTOMATE_NAME")
DB_USER = os.getenv("DB_AUTOMATE_USER")
DB_PASSWORD = os.getenv("DB_AUTOMATE_PASSWORD")


# 20 minutos
INTERVALO_EXECUCAO = 1200


# Guarda em memória a última rodada já processada
# Chave: (id_agente, id_funcao)
# Valor: ultima_execucao
ULTIMAS_EXECUCOES_PROCESSADAS = {}


# Guarda o último update do Telegram processado
ULTIMO_UPDATE_TELEGRAM = None


# ==========================================================
# CONEXÃO POSTGRESQL
# ==========================================================

def conectar_postgres():

    return psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        connect_timeout=5
    )


# ==========================================================
# CONTATOS TELEGRAM
# ==========================================================

def inserir_contato(
    conn,
    telegram_chat_id,
    nome,
    username
):

    with conn.cursor() as cursor:

        cursor.execute(
            """
            INSERT INTO db_automate.contatos
            (
                telegram_chat_id,
                nome,
                username,
                ativo
            )
            VALUES
            (
                %s,
                %s,
                %s,
                TRUE
            )
            ON CONFLICT (telegram_chat_id)
            DO NOTHING
            """,
            (
                telegram_chat_id,
                nome,
                username
            )
        )

    conn.commit()


# ==========================================================
# QUANTIDADE DE ENVIOS
# ==========================================================

def inserir_quantidade_envios(
    conn,
    telegram_chat_id
):

    with conn.cursor() as cursor:

        cursor.execute(
            """
            INSERT INTO db_automate.quantidade_envios
            (
                telegram_chat_id,
                quantidade_atual
            )
            VALUES
            (
                %s,
                0
            )
            ON CONFLICT (telegram_chat_id)
            DO NOTHING
            """,
            (
                telegram_chat_id,
            )
        )

    conn.commit()


# ==========================================================
# PROCESSAR TELEGRAM
# ==========================================================

def processar_telegram(conn):

    global ULTIMO_UPDATE_TELEGRAM

    offset = None

    if ULTIMO_UPDATE_TELEGRAM is not None:
        offset = ULTIMO_UPDATE_TELEGRAM + 1

    chats = listar_chats(
        offset=offset
    )

    for chat in chats:

        update_id = chat["update_id"]

        if (
            ULTIMO_UPDATE_TELEGRAM is None
            or update_id > ULTIMO_UPDATE_TELEGRAM
        ):
            ULTIMO_UPDATE_TELEGRAM = update_id

        chat_id = chat["chat_id"]
        nome = chat["nome"]
        username = chat["username"]
        texto = chat.get("texto")

        # Insere somente se o chat_id ainda não existir
        inserir_contato(
            conn,
            chat_id,
            nome,
            username
        )

        # Insere controle de envio somente se ainda não existir
        inserir_quantidade_envios(
            conn,
            chat_id
        )

        # Processa resposta pendente de alerta de backup
        if texto is not None:

            resposta_backup = processar_resposta_backup(
                conn,
                chat_id,
                texto
            )

            if resposta_backup is not None:

                enviar_mensagem(
                    chat_id,
                    resposta_backup
                )

            # Processa resposta pendente de alerta do Data Agent
            resposta_data = processar_resposta_data_agent(
                conn,
                chat_id,
                texto
            )

            if resposta_data is not None:

                enviar_mensagem(
                    chat_id,
                    resposta_data
                )


# ==========================================================
# RESET DIÁRIO DA QUANTIDADE
# ==========================================================

def resetar_quantidade_diaria(conn):

    with conn.cursor() as cursor:

        cursor.execute(
            """
            UPDATE db_automate.quantidade_envios

            SET
                quantidade_atual = 0,
                data_ultimo_envio = CURRENT_DATE

            WHERE data_ultimo_envio < CURRENT_DATE
            """
        )

    conn.commit()


# ==========================================================
# BUSCA MONITORES ATIVOS
# ==========================================================

def buscar_monitores(conn):

    with conn.cursor() as cursor:

        cursor.execute(
            """
            SELECT
                a.id_agente,
                a.host_name,
                a.hora_excecao,
                f.id_funcao,
                f.nome_funcao,
                MAX(l.data_log) AS ultima_execucao

            FROM db_automate.agentes a

            INNER JOIN db_automate.agente_funcoes af
                ON af.id_agente = a.id_agente

            INNER JOIN db_automate.funcoes f
                ON f.id_funcao = af.id_funcao

            INNER JOIN db_automate.logs_db_automate l
                ON l.id_agente = a.id_agente
                AND l.id_funcao = f.id_funcao

            WHERE af.ativo = TRUE
              AND UPPER(f.nome_funcao) = 'MONITOR'

            GROUP BY
                a.id_agente,
                a.host_name,
                a.hora_excecao,
                f.id_funcao,
                f.nome_funcao
            """
        )

        return cursor.fetchall()


# ==========================================================
# VERIFICA HORÁRIO DE EXCEÇÃO
# ==========================================================

def esta_em_horario_excecao(
    hora_excecao,
    ultima_execucao
):

    if not hora_excecao:
        return False

    intervalos = hora_excecao.split(";")

    for intervalo in intervalos:

        intervalo = intervalo.strip()

        if not intervalo:
            continue

        inicio_txt, fim_txt = intervalo.split("-")

        hora_inicio = int(inicio_txt)
        hora_fim = int(fim_txt)

        inicio = ultima_execucao.replace(
            hour=hora_inicio,
            minute=0,
            second=0,
            microsecond=0
        )

        # Exemplo: 11-12
        if hora_fim > hora_inicio:

            fim = ultima_execucao.replace(
                hour=hora_fim,
                minute=2,
                second=0,
                microsecond=0
            )

        # Exemplo: 23-00
        else:

            fim = (
                inicio + timedelta(days=1)
            ).replace(
                hour=hora_fim,
                minute=2,
                second=0,
                microsecond=0
            )

            # Se o log ocorreu após meia-noite,
            # considera que a janela começou no dia anterior
            if ultima_execucao.hour < hora_inicio:

                inicio = inicio - timedelta(days=1)
                fim = fim - timedelta(days=1)

        if inicio <= ultima_execucao <= fim:
            return True

    return False


# ==========================================================
# BUSCA SERVIÇOS COM PROBLEMA NA ÚLTIMA RODADA
# ==========================================================

def buscar_servicos_problema(
    conn,
    id_agente,
    id_funcao,
    ultima_execucao
):

    with conn.cursor() as cursor:

        cursor.execute(
            """
            SELECT
                log_detalhe

            FROM db_automate.logs_db_automate

            WHERE id_agente = %s
              AND id_funcao = %s

              AND DATE_TRUNC('minute', data_log) =
                  DATE_TRUNC('minute', %s)

              AND
              (
                    UPPER(log_detalhe)
                        LIKE '%%STATUS=STOPPED%%'

                 OR UPPER(log_detalhe)
                        LIKE '%%STATUS=STOPPING%%'
              )

            ORDER BY data_log
            """,
            (
                id_agente,
                id_funcao,
                ultima_execucao
            )
        )

        return cursor.fetchall()


# ==========================================================
# EXTRAI NOME DO SERVIÇO DO LOG
# ==========================================================

def extrair_nome_servico(log_detalhe):

    partes = log_detalhe.split(";")

    for parte in partes:

        if parte.startswith("Servico="):

            return (
                parte
                .replace("Servico=", "")
                .strip()
            )

    return log_detalhe


# ==========================================================
# BUSCA CONTATOS QUE AINDA PODEM RECEBER
# ==========================================================

def buscar_destinatarios(conn):

    with conn.cursor() as cursor:

        cursor.execute(
            """
            SELECT
                c.telegram_chat_id,
                c.nome,
                q.quantidade_atual,
                q.quantidade_final

            FROM db_automate.contatos c

            INNER JOIN db_automate.quantidade_envios q
                ON q.telegram_chat_id =
                   c.telegram_chat_id

            WHERE c.ativo = TRUE

              AND q.quantidade_atual
                  < q.quantidade_final
            """
        )

        return cursor.fetchall()


# ==========================================================
# INCREMENTA QUANTIDADE APÓS ENVIO
# ==========================================================

def registrar_envio(
    conn,
    telegram_chat_id
):

    with conn.cursor() as cursor:

        cursor.execute(
            """
            UPDATE db_automate.quantidade_envios

            SET
                quantidade_atual =
                    quantidade_atual + 1,

                data_ultimo_envio =
                    CURRENT_DATE

            WHERE telegram_chat_id = %s
            """,
            (
                telegram_chat_id,
            )
        )

    conn.commit()


# ==========================================================
# MONTA MENSAGEM
# ==========================================================

def montar_mensagem(
    host_name,
    nome_funcao,
    ultima_execucao,
    servicos
):

    lista_servicos = "\n".join(
        f"- {servico}"
        for servico in servicos
    )

    data_formatada = ultima_execucao.strftime(
        "%d/%m/%Y %H:%M:%S"
    )

    return (
        "⚠️ DB Automate - Warning\n\n"
        f"Servidor: {host_name}\n"
        f"Função: {nome_funcao}\n"
        f"Data: {data_formatada}\n\n"
        f"Serviços interrompidos:\n"
        f"{lista_servicos}"
    )


# ==========================================================
# ENVIA ALERTA
# ==========================================================

def enviar_alerta(
    conn,
    mensagem
):

    destinatarios = buscar_destinatarios(
        conn
    )

    for (
        chat_id,
        nome,
        quantidade_atual,
        quantidade_final
    ) in destinatarios:

        try:

            enviar_mensagem(
                chat_id,
                mensagem
            )

            registrar_envio(
                conn,
                chat_id
            )

            print(
                f"Telegram enviado para "
                f"{nome} "
                f"({quantidade_atual + 1}/"
                f"{quantidade_final})"
            )

        except Exception as erro:

            print(
                f"Erro ao enviar Telegram "
                f"para {nome}: {erro}"
            )


# ==========================================================
# ENVIA ALERTA DE BACKUP
# ==========================================================

def enviar_alerta_backup(
    conn,
    alerta
):

    destinatarios = buscar_destinatarios(
        conn
    )

    for (
        chat_id,
        nome,
        quantidade_atual,
        quantidade_final
    ) in destinatarios:

        try:

            enviar_mensagem(
                chat_id,
                alerta["mensagem"]
            )

            registrar_pendencia_backup(
                chat_id,
                alerta["id_base"],
                alerta["objeto"]
            )

            registrar_envio(
                conn,
                chat_id
            )

            print(
                f"Telegram de backup enviado para "
                f"{nome} "
                f"({quantidade_atual + 1}/"
                f"{quantidade_final})"
            )

        except Exception as erro:

            print(
                f"Erro ao enviar Telegram de backup "
                f"para {nome}: {erro}"
            )


# ==========================================================
# PROCESSA ALERTAS DE BACKUP
# ==========================================================

def processar_alertas_backup(conn):

    alertas = processar_erros_backup(
        conn
    )

    for alerta in alertas:

        print()
        print(
            alerta["mensagem"]
        )

        enviar_alerta_backup(
            conn,
            alerta
        )


# ==========================================================
# DATA AGENT - ALERTAS DE ERRO (episodios do Data Agent:
# pombo:* | metabase_log:* | metabase_http:*)
# Dedupe em memoria por id_log (mesmo padrao dos outros).
#
# CONFIRMACAO: alertas de ERRO pedem resposta "1" no Telegram.
# Digitando 1, o Central APAGA o episodio (logs do agente 7
# com aquela chave) - nao re-alerta coisa ja arrumada.
# Qualquer outra resposta (ou nenhuma) apenas descarta.
# ==========================================================

DATA_AGENT_PROCESSADOS = set()

PENDENCIAS_DATA_AGENT = {}


def buscar_eventos_data_agent(conn):

    with conn.cursor() as cursor:

        cursor.execute(
            """
            SELECT
                id_log,
                objeto,
                status,
                data_log,
                log_detalhe

            FROM db_automate.logs_db_automate

            WHERE id_funcao = 1
              AND objeto ~ '^(pombo|metabase_log|metabase_http):'
              AND status IN ('ERRO', 'RESOLVIDO')

            ORDER BY id_log
            """
        )

        return cursor.fetchall()


def origem_do_objeto(objeto):
    """Rotulo amigavel da origem, conforme o prefixo da chave."""
    if objeto.startswith("pombo:"):
        return "Data Pombo Agent"
    if objeto.startswith(("metabase_log:", "metabase_http:")):
        return "Data Metabase Agent"
    return "Data Agent"


def montar_mensagem_data_agent(
    objeto,
    status,
    data_log,
    log_detalhe
):

    data_formatada = data_log.strftime(
        "%d/%m/%Y %H:%M:%S"
    )

    origem = origem_do_objeto(
        objeto
    )

    if status == "ERRO":
        icone = "🚨"
        titulo = "DB Automate - Erro detectado"
        rodape = (
            "\n\nJá arrumou? Responda 1 para confirmar "
            "e parar os alertas deste erro."
        )
    else:
        icone = "✅"
        titulo = "DB Automate - Erro resolvido"
        rodape = ""

    return (
        f"{icone} {titulo}\n\n"
        f"Origem: {origem}\n"
        f"Chave: {objeto}\n"
        f"Data: {data_formatada}\n\n"
        f"{(log_detalhe or '')[:800]}"
        f"{rodape}"
    )


def apagar_episodio_data_agent(conn, objeto):

    with conn.cursor() as cursor:

        cursor.execute(
            """
            DELETE FROM db_automate.logs_db_automate
            WHERE id_agente = 7
              AND objeto = %s
            """,
            (
                objeto,
            )
        )

    conn.commit()


def registrar_pendencia_data_agent(
    telegram_chat_id,
    id_log,
    objeto
):

    PENDENCIAS_DATA_AGENT[
        telegram_chat_id
    ] = {
        "id_log": id_log,
        "objeto": objeto
    }


def processar_resposta_data_agent(
    conn,
    telegram_chat_id,
    texto
):

    if telegram_chat_id not in PENDENCIAS_DATA_AGENT:
        return None

    pendencia = PENDENCIAS_DATA_AGENT.pop(
        telegram_chat_id
    )

    if texto is not None and texto.strip() == "1":

        apagar_episodio_data_agent(
            conn,
            pendencia["objeto"]
        )

        return (
            "✅ DB Automate\n\n"
            f"Logs do episódio {pendencia['objeto']} "
            f"apagados.\n"
            "Não vai mais alertar sobre ele."
        )

    # Qualquer outra resposta: ignora (pendencia ja descartada)
    return None


def enviar_alerta_data_agent(
    conn,
    alerta
):

    destinatarios = buscar_destinatarios(
        conn
    )

    for (
        chat_id,
        nome,
        quantidade_atual,
        quantidade_final
    ) in destinatarios:

        try:

            enviar_mensagem(
                chat_id,
                alerta["mensagem"]
            )

            registrar_pendencia_data_agent(
                chat_id,
                alerta["id_log"],
                alerta["objeto"]
            )

            registrar_envio(
                conn,
                chat_id
            )

            print(
                f"Telegram de data agent enviado para "
                f"{nome} "
                f"({quantidade_atual + 1}/"
                f"{quantidade_final})"
            )

        except Exception as erro:

            print(
                f"Erro ao enviar Telegram de data agent "
                f"para {nome}: {erro}"
            )


def processar_alertas_data_agent(conn):

    eventos = buscar_eventos_data_agent(
        conn
    )

    for (
        id_log,
        objeto,
        status,
        data_log,
        log_detalhe
    ) in eventos:

        if id_log in DATA_AGENT_PROCESSADOS:
            continue

        DATA_AGENT_PROCESSADOS.add(
            id_log
        )

        mensagem = montar_mensagem_data_agent(
            objeto,
            status,
            data_log,
            log_detalhe
        )

        print()
        print(mensagem)

        if status == "ERRO":
            enviar_alerta_data_agent(
                conn,
                {
                    "id_log": id_log,
                    "objeto": objeto,
                    "mensagem": mensagem
                }
            )
        else:
            enviar_alerta(
                conn,
                mensagem
            )


# ==========================================================
# PROCESSA MONITORAMENTO
# ==========================================================

def processar_monitoramento(conn):

    monitores = buscar_monitores(conn)

    for (
        id_agente,
        host_name,
        hora_excecao,
        id_funcao,
        nome_funcao,
        ultima_execucao
    ) in monitores:

        chave = (
            id_agente,
            id_funcao
        )

        ultima_processada = (
            ULTIMAS_EXECUCOES_PROCESSADAS
            .get(chave)
        )

        # ----------------------------------------------
        # ESSA RODADA JÁ FOI PROCESSADA
        # ----------------------------------------------

        if (
            ultima_processada
            == ultima_execucao
        ):
            continue

        # Marca como processada
        ULTIMAS_EXECUCOES_PROCESSADAS[
            chave
        ] = ultima_execucao

        # ----------------------------------------------
        # VERIFICA A NOVA RODADA
        # ----------------------------------------------

        logs_problema = (
            buscar_servicos_problema(
                conn,
                id_agente,
                id_funcao,
                ultima_execucao
            )
        )

        servicos = [
            extrair_nome_servico(log[0])
            for log in logs_problema
        ]

        # Tudo OK
        if not servicos:
            continue

        # ----------------------------------------------
        # HORÁRIO DE EXCEÇÃO
        # ----------------------------------------------

        if esta_em_horario_excecao(
            hora_excecao,
            ultima_execucao
        ):

            data_formatada = (
                ultima_execucao.strftime(
                    "%d/%m/%Y %H:%M:%S"
                )
            )

            print(
                f"Alerta não enviado para "
                f"{host_name}. "
                f"Log: {data_formatada}. "
                f"Horário de exceção: "
                f"{hora_excecao}"
            )

            continue

        # ----------------------------------------------
        # MONTA E ENVIA ALERTA
        # ----------------------------------------------

        mensagem = montar_mensagem(
            host_name,
            nome_funcao,
            ultima_execucao,
            servicos
        )

        print()
        print(mensagem)

        enviar_alerta(
            conn,
            mensagem
        )


# ==========================================================
# CICLO
# ==========================================================

def executar_ciclo():

    print()
    print("DB Automate - Central")
    print("---------------------")

    with conectar_postgres() as conn:

        # 1 - Captura novos chats do Telegram
        processar_telegram(conn)

        # 2 - Reseta quantidade no primeiro ciclo do novo dia
        resetar_quantidade_diaria(conn)

        # 3 - Processa somente novas rodadas
        processar_monitoramento(conn)

        # 4 - Processa erros de backup
        processar_alertas_backup(conn)

        # 5 - Alertas de erro do Data Agent (Pombo/Metabase)
        processar_alertas_data_agent(conn)


# ==========================================================
# PRINCIPAL
# ==========================================================

def main():

    configurar_logs()

    while True:

        try:

            executar_ciclo()

        except Exception as erro:

            print(
                f"Erro no Central Automate: "
                f"{erro}"
            )

        print()
        print(
            "Próxima verificação em "
            "20 minutos..."
        )

        time.sleep(
            INTERVALO_EXECUCAO
        )


if __name__ == "__main__":
    main()