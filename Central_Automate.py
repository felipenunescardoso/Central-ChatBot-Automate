import os
import time
from datetime import timedelta

import psycopg

from Telegram import listar_chats, enviar_mensagem
from backup_alertas import (
    processar_erros_backup,
    registrar_pendencia_backup,
    processar_resposta_backup,
)


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


# ==========================================================
# PRINCIPAL
# ==========================================================

def main():

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