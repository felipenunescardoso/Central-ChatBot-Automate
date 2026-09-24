import os
import json
import urllib.request
import urllib.parse


# ==========================================================
# CONFIGURAÇÃO
# ==========================================================

TELEGRAM_TOKEN = os.getenv("DB_AUTOMATE_TELEGRAM_TOKEN")


def validar_configuracao():

    if not TELEGRAM_TOKEN:
        raise ValueError(
            "Variável de ambiente "
            "DB_AUTOMATE_TELEGRAM_TOKEN não encontrada."
        )


# ==========================================================
# BUSCAR UPDATES
# ==========================================================

def buscar_updates(offset=None):

    validar_configuracao()

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/getUpdates"
    )

    parametros = {}

    if offset is not None:
        parametros["offset"] = offset

    if parametros:
        url += "?" + urllib.parse.urlencode(parametros)

    with urllib.request.urlopen(
        url,
        timeout=10
    ) as resposta:

        dados = json.loads(
            resposta.read().decode("utf-8")
        )

    return dados


# ==========================================================
# LISTAR MENSAGENS RECEBIDAS
# ==========================================================

def listar_chats(offset=None):

    dados = buscar_updates(offset)

    chats = []

    for update in dados.get("result", []):

        mensagem = update.get("message")

        if not mensagem:
            continue

        chat = mensagem.get("chat", {})

        chat_id = chat.get("id")

        if chat_id is None:
            continue

        chats.append(
            {
                "update_id": update.get("update_id"),
                "chat_id": chat_id,
                "nome": chat.get("first_name"),
                "sobrenome": chat.get("last_name"),
                "username": chat.get("username"),
                "texto": mensagem.get("text", "")
            }
        )

    return chats


# ==========================================================
# BUSCAR COMANDOS
# ==========================================================

def buscar_comandos(offset=None):

    chats = listar_chats(offset)

    comandos = []

    for chat in chats:

        texto = chat["texto"].strip()

        if not texto.startswith("/"):
            continue

        comando = texto.split()[0].lower()

        # Caso futuramente o Telegram entregue:
        # /start@focus_db_automate_bot
        if "@" in comando:
            comando = comando.split("@")[0]

        comandos.append(
            {
                "update_id": chat["update_id"],
                "chat_id": chat["chat_id"],
                "nome": chat["nome"],
                "sobrenome": chat["sobrenome"],
                "username": chat["username"],
                "comando": comando,
                "texto": texto
            }
        )

    return comandos


# ==========================================================
# ENVIAR MENSAGEM
# ==========================================================

def enviar_mensagem(chat_id, mensagem):

    validar_configuracao()

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/sendMessage"
    )

    dados = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": mensagem
        }
    ).encode("utf-8")

    requisicao = urllib.request.Request(
        url,
        data=dados,
        method="POST"
    )

    with urllib.request.urlopen(
        requisicao,
        timeout=10
    ) as resposta:

        retorno = json.loads(
            resposta.read().decode("utf-8")
        )

    return retorno


# ==========================================================
# TESTE DIRETO
# ==========================================================

if __name__ == "__main__":

    print("DB Automate - Telegram")
    print("----------------------")

    try:

        chats = listar_chats()

        if not chats:

            print("Nenhuma mensagem recebida pelo bot.")

        else:

            for chat in chats:

                print(
                    f"Update ID: {chat['update_id']} | "
                    f"Chat ID: {chat['chat_id']} | "
                    f"Nome: {chat['nome']} | "
                    f"Username: {chat['username']} | "
                    f"Texto: {chat['texto']}"
                )

    except Exception as erro:

        print(
            f"Erro ao acessar Telegram: {erro}"
        )