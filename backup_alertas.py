# ==========================================================
# BACKUP_ALERTAS.PY
# ==========================================================


# Guarda em memória os erros de backup já processados
ERROS_BACKUP_PROCESSADOS = set()

# Guarda pendências de resposta por chat
PENDENCIAS_BACKUP = {}


# ==========================================================
# BUSCAR ERROS DE BACKUP
# ==========================================================

def buscar_erros_backup(conn):

    with conn.cursor() as cursor:

        cursor.execute(
            """
            SELECT
    ultimo.id_log,
    ultimo.id_agente,
    ultimo.host_name,
    ultimo.id_funcao,
    ultimo.nome_funcao,
    ultimo.data_log,
    ultimo.objeto,
    ultimo.log_detalhe,
    ultimo.id_base

FROM
(
    SELECT DISTINCT ON (b.id_base)
        l.id_log,
        a.id_agente,
        a.host_name,
        l.id_funcao,
        f.nome_funcao,
        l.data_log,
        l.objeto,
        l.log_detalhe,
        l.status,
        b.id_base

    FROM db_automate.logs_db_automate l

    INNER JOIN db_automate.agentes a
        ON a.id_agente = l.id_agente

    INNER JOIN db_automate.funcoes f
        ON f.id_funcao = l.id_funcao

    INNER JOIN db_automate.bases b
        ON UPPER(b.host_name) = UPPER(a.host_name)
       AND UPPER(b.service_name) = UPPER(l.objeto)

    WHERE l.id_funcao = 4

    ORDER BY
        b.id_base,
        l.data_log DESC,
        l.id_log DESC
) ultimo

WHERE UPPER(ultimo.status) = 'ERRO'

ORDER BY ultimo.id_log;

            """
        )

        return cursor.fetchall()


# ==========================================================
# MONTAR MENSAGEM
# ==========================================================

def montar_mensagem_backup(
    host_name,
    nome_funcao,
    data_log,
    objeto,
    log_detalhe
):

    data_formatada = data_log.strftime(
        "%d/%m/%Y %H:%M:%S"
    )

    return (
        "🚨 DB Automate - Erro de Backup\n\n"
        f"Servidor: {host_name}\n"
        f"Função: {nome_funcao}\n"
        f"Base: {objeto}\n"
        f"Data: {data_formatada}\n\n"
        f"Erro:\n"
        f"{log_detalhe}\n\n"
        "Deseja forçar uma nova tentativa de backup?\n\n"
        "Digite 1 para SIM.\n"
        "Qualquer outra resposta para NÃO."
    )


# ==========================================================
# PROCESSAR ERROS
# ==========================================================

def processar_erros_backup(conn):

    erros = buscar_erros_backup(conn)

    mensagens = []

    for (
        id_log,
        id_agente,
        host_name,
        id_funcao,
        nome_funcao,
        data_log,
        objeto,
        log_detalhe,
        id_base
    ) in erros:

        if id_log in ERROS_BACKUP_PROCESSADOS:
            continue

        mensagem = montar_mensagem_backup(
            host_name,
            nome_funcao,
            data_log,
            objeto,
            log_detalhe
        )

        mensagens.append(
            {
                "id_log": id_log,
                "id_agente": id_agente,
                "id_funcao": id_funcao,
                "id_base": id_base,
                "host_name": host_name,
                "objeto": objeto,
                "data_log": data_log,
                "mensagem": mensagem
            }
        )

        ERROS_BACKUP_PROCESSADOS.add(
            id_log
        )

    return mensagens


# ==========================================================
# REGISTRAR PENDÊNCIA DE RESPOSTA
# ==========================================================

def registrar_pendencia_backup(
    telegram_chat_id,
    id_base,
    objeto
):

    PENDENCIAS_BACKUP[
        telegram_chat_id
    ] = {
        "id_base": id_base,
        "objeto": objeto
    }


# ==========================================================
# FORÇAR BACKUP
# ==========================================================

def forcar_backup(
    conn,
    id_base
):

    with conn.cursor() as cursor:

        cursor.execute(
            """
            UPDATE db_automate.periodicidade_backup
            SET forcar_backup = TRUE
            WHERE id_base = %s
            """,
            (
                id_base,
            )
        )

    conn.commit()


# ==========================================================
# PROCESSAR RESPOSTA DO TELEGRAM
# ==========================================================

def processar_resposta_backup(
    conn,
    telegram_chat_id,
    texto
):

    if telegram_chat_id not in PENDENCIAS_BACKUP:
        return None

    pendencia = PENDENCIAS_BACKUP[
        telegram_chat_id
    ]

    id_base = pendencia["id_base"]
    objeto = pendencia["objeto"]

    resposta = texto.strip()

    del PENDENCIAS_BACKUP[
        telegram_chat_id
    ]

    if resposta == "1":

        forcar_backup(
            conn,
            id_base
        )

        return (
            "✅ DB Automate\n\n"
            f"Backup da base {objeto} "
            f"marcado para execução forçada "
            f"no próximo ciclo."
        )

    return (
        "ℹ️ DB Automate\n\n"
        f"Backup forçado da base {objeto} "
        f"não solicitado."
    )
