"""
Autor.....: Equipe EV ChargeOps (RM573133, RM571998, RM571913, RM568867, RM574003)
Assunto...: MODEL - camada de dados (persistencia em arquivos JSON)
Problema..: Guardar e consultar as seis tabelas definidas na Sprint 1
            (Unit, User, RFID_Card, Charger, Session, Invoice)
"""
import json
import os
from datetime import datetime

# ----- CONSTANTES
PASTA_DADOS = "dados"
ARQUIVO_CONFIG = "dados/config.json"
ARQUIVO_REGISTROS = "dados/registros.txt"
FORMATO_DATA_HORA = "%Y-%m-%d %H:%M"
FORMATO_DATA = "%Y-%m-%d"
LIMITE_CARTOES_POR_UNIDADE = 10      # regra da Sprint 1: ate 10 cartoes por unidade
ID_INICIAL_USUARIO = 101             # numeracao igual a dos exemplos da Sprint 1
ID_INICIAL_SESSAO = 5001
ID_INICIAL_FATURA = 9001
NOMES_DOS_DIAS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")

# valores de exemplo: o gestor pode alterar todos pela interface
CONFIG_PADRAO = {
    "tarifa_kwh": 0.95,              # T: tarifa da concessionaria (R$/kWh)
    "taxa_admin": 2.00,              # Tx_admin: taxa administrativa (R$ por fatura)
    "cobrar_taxa": False,            # opcao padrao do fechamento: com taxa ou sem taxa
    "cobrar_taxa_sem_uso": False,    # unidade sem recarga paga a taxa?
    "dias_para_vencimento": 30,
    "tensao_nominal_v": 230,
    "corrente_max_a": 30,
    "potencia_max_kw": 7.0,          # carregador GW7K-HCA
    "limite_quadro_kw": 10.0,        # potencia que o quadro eletrico suporta
    "limite_divergencia_sems": 0.03  # 3% de diferenca aceita na conciliacao
}


# ----- SUBALGORITMOS DE ARQUIVO
def caminho_tabela(nome: str) -> str:
    return PASTA_DADOS + "/" + nome + ".json"


def garantir_pasta() -> None:
    # cria a pasta dados/ na primeira gravacao
    if not os.path.exists(PASTA_DADOS):
        os.mkdir(PASTA_DADOS)


def carregar_tabela(nome: str) -> list:
    arquivo = caminho_tabela(nome)
    # se o arquivo ainda nao existe, a tabela esta vazia
    if not os.path.exists(arquivo):
        return []
    with open(arquivo, "r", encoding="utf-8") as arq:
        return json.loads(arq.read())


def salvar_tabela(nome: str, tabela: list) -> None:
    garantir_pasta()
    with open(caminho_tabela(nome), "w", encoding="utf-8") as arq:
        arq.write(json.dumps(tabela, indent=4, ensure_ascii=False))


def carregar_config() -> dict:
    # na primeira execucao grava a configuracao padrao
    if not os.path.exists(ARQUIVO_CONFIG):
        salvar_config(CONFIG_PADRAO.copy())
    with open(ARQUIVO_CONFIG, "r", encoding="utf-8") as arq:
        return json.loads(arq.read())


def salvar_config(config: dict) -> None:
    garantir_pasta()
    with open(ARQUIVO_CONFIG, "w", encoding="utf-8") as arq:
        arq.write(json.dumps(config, indent=4, ensure_ascii=False))


def base_existe() -> bool:
    return os.path.exists(caminho_tabela("units"))


# ----- SUBALGORITMOS DE DATA
def agora_texto() -> str:
    return datetime.now().strftime(FORMATO_DATA_HORA)


def hoje_texto() -> str:
    return datetime.now().strftime(FORMATO_DATA)


def texto_para_data(texto: str) -> datetime:
    return datetime.strptime(texto, FORMATO_DATA_HORA)


def mes_da_data(texto: str) -> str:
    # "2026-06-18 19:00" -> "06-2026" (formato do campo month da Sprint 1)
    # as posicoes 5 e 6 do texto guardam o mes; as posicoes 0 a 3, o ano
    return texto[5:7] + "-" + texto[0:4]


def chave_do_mes(mes: str) -> int:
    # "06-2026" -> 202606, numero que permite comparar e ordenar meses
    partes = mes.split("-")
    return int(partes[1]) * 100 + int(partes[0])


def mes_atual() -> str:
    return datetime.now().strftime("%m-%Y")


# ----- SUBALGORITMOS DE REGISTRO (LOG)
def registrar_evento(evento: str, detalhe: str, data_hora: str = "") -> None:
    if data_hora == "":
        data_hora = agora_texto()
    garantir_pasta()
    # modo "a": acrescenta uma linha sem apagar as anteriores
    with open(ARQUIVO_REGISTROS, "a", encoding="utf-8") as arq:
        arq.write(f"{data_hora};{evento};{detalhe}\n")


def ler_eventos() -> list:
    eventos = []
    if not os.path.exists(ARQUIVO_REGISTROS):
        return eventos
    with open(ARQUIVO_REGISTROS, "r", encoding="utf-8") as arq:
        linhas = arq.readlines()
    for linha in linhas:
        partes = linha.strip().split(";")
        if len(partes) >= 3:
            eventos.append({"data_hora": partes[0], "evento": partes[1], "detalhe": partes[2]})
    return eventos


def limpar_eventos() -> None:
    with open(ARQUIVO_REGISTROS, "w", encoding="utf-8") as arq:
        arq.write("")


# ----- SUBALGORITMOS DE BUSCA E ORDENACAO
def proximo_id(tabela: list, inicial: int) -> int:
    # maior id existente + 1; "inicial" vale para a tabela vazia
    maior = inicial - 1
    for registro in tabela:
        if registro["id"] > maior:
            maior = registro["id"]
    return maior + 1


def buscar(tabela: list, campo: str, valor) -> dict:
    # busca sequencial: devolve o primeiro registro ou {} quando nao encontra
    for registro in tabela:
        if registro[campo] == valor:
            return registro
    return {}


def filtrar(tabela: list, campo: str, valor) -> list:
    resultado = []
    for registro in tabela:
        if registro[campo] == valor:
            resultado.append(registro)
    return resultado


def ordenar(tabela: list, campo: str, decrescente: bool) -> list:
    # ordenacao por selecao (selection sort) sobre uma copia da tabela
    lista = tabela.copy()
    n = len(lista)
    for i in range(n - 1):
        escolhido = i
        for j in range(i + 1, n):
            if decrescente:
                if lista[j][campo] > lista[escolhido][campo]:
                    escolhido = j
            else:
                if lista[j][campo] < lista[escolhido][campo]:
                    escolhido = j
        temp = lista[i]
        lista[i] = lista[escolhido]
        lista[escolhido] = temp
    return lista


# ----- SUBALGORITMOS DE CADASTRO
def cadastrar_unidade(nome: str, bloco: str) -> dict:
    tabela = carregar_tabela("units")
    unidade = {"id": proximo_id(tabela, 1), "name": nome, "block": bloco}
    tabela.append(unidade)
    salvar_tabela("units", tabela)
    registrar_evento("UNIDADE_CADASTRADA", f"{nome} / {bloco}")
    return unidade


def cadastrar_usuario(unit_id: int, nome: str, email: str) -> dict:
    unidades = carregar_tabela("units")
    if buscar(unidades, "id", unit_id) == {}:
        return {}
    tabela = carregar_tabela("users")
    usuario = {"id": proximo_id(tabela, ID_INICIAL_USUARIO), "unit_id": unit_id,
               "name": nome, "email": email}
    tabela.append(usuario)
    salvar_tabela("users", tabela)
    registrar_evento("USUARIO_CADASTRADO", f"{nome} (unidade {unit_id})")
    return usuario


def cadastrar_cartao(uid: str, user_id: int) -> dict:
    usuarios = carregar_tabela("users")
    cartoes = carregar_tabela("rfid_cards")
    usuario = buscar(usuarios, "id", user_id)
    if usuario == {}:
        return {"ok": False, "mensagem": "Usuário não encontrado."}
    if buscar(cartoes, "uid", uid) != {}:
        return {"ok": False, "mensagem": "Já existe um cartão com esse UID."}
    # regra da Sprint 1: no maximo 10 cartoes RFID por unidade
    if len(cartoes_da_unidade(usuario["unit_id"])) >= LIMITE_CARTOES_POR_UNIDADE:
        return {"ok": False, "mensagem": "A unidade já tem 10 cartões cadastrados."}
    cartoes.append({"uid": uid, "user_id": user_id, "status": True})
    salvar_tabela("rfid_cards", cartoes)
    registrar_evento("CARTAO_CADASTRADO", f"{uid} (usuário {user_id})")
    return {"ok": True, "mensagem": "Cartão cadastrado."}


def registrar_sessao(sessao: dict) -> dict:
    tabela = carregar_tabela("sessions")
    sessao["id"] = proximo_id(tabela, ID_INICIAL_SESSAO)
    tabela.append(sessao)
    salvar_tabela("sessions", tabela)
    return sessao


# ----- SUBALGORITMOS DE CONSULTA
def usuarios_da_unidade(unit_id: int) -> list:
    return filtrar(carregar_tabela("users"), "unit_id", unit_id)


def cartoes_da_unidade(unit_id: int) -> list:
    # unifica todos os cartoes dos usuarios da mesma unidade
    usuarios = usuarios_da_unidade(unit_id)
    cartoes = carregar_tabela("rfid_cards")
    resultado = []
    for cartao in cartoes:
        for usuario in usuarios:
            if cartao["user_id"] == usuario["id"]:
                resultado.append(cartao)
    return resultado


def cartoes_detalhados() -> list:
    # cada cartao com o nome do usuario, a unidade e a situacao, pronto para as telas
    usuarios = carregar_tabela("users")
    unidades = carregar_tabela("units")
    linhas = []
    for cartao in carregar_tabela("rfid_cards"):
        usuario = buscar(usuarios, "id", cartao["user_id"])
        unidade = buscar(unidades, "id", usuario["unit_id"])
        situacao = "ativo"
        if not cartao["status"]:
            situacao = "bloqueado"
        linhas.append({"uid": cartao["uid"], "usuario": usuario["name"], "unit_id": unidade["id"],
                       "unidade": unidade["name"], "situacao": situacao})
    return linhas


def mapa_cartao_unidade() -> dict:
    # dicionario {uid do cartao: id da unidade}; evita repetir buscas
    usuarios = carregar_tabela("users")
    cartoes = carregar_tabela("rfid_cards")
    mapa = {}
    for cartao in cartoes:
        usuario = buscar(usuarios, "id", cartao["user_id"])
        if usuario != {}:
            mapa[cartao["uid"]] = usuario["unit_id"]
    return mapa


def unidade_do_cartao(uid: str) -> dict:
    # caminho da Sprint 1: cartao -> usuario -> unidade
    cartao = buscar(carregar_tabela("rfid_cards"), "uid", uid)
    if cartao == {}:
        return {}
    usuario = buscar(carregar_tabela("users"), "id", cartao["user_id"])
    if usuario == {}:
        return {}
    return buscar(carregar_tabela("units"), "id", usuario["unit_id"])


def sessoes_do_mes(mes: str) -> list:
    resultado = []
    for sessao in carregar_tabela("sessions"):
        if mes_da_data(sessao["start_time"]) == mes:
            resultado.append(sessao)
    return ordenar(resultado, "start_time", False)


def sessoes_da_unidade(unit_id: int, mes: str) -> list:
    mapa = mapa_cartao_unidade()
    resultado = []
    for sessao in sessoes_do_mes(mes):
        uid = sessao["rfid_uid"]
        if uid in mapa and mapa[uid] == unit_id:
            resultado.append(sessao)
    return resultado


def faturas_do_mes(mes: str) -> list:
    return filtrar(carregar_tabela("invoices"), "month", mes)


def fatura_da_unidade(unit_id: int, mes: str) -> dict:
    for fatura in faturas_do_mes(mes):
        if fatura["unit_id"] == unit_id:
            return fatura
    return {}


def meses_com_sessoes() -> list:
    # lista de meses "MM-AAAA" em ordem cronologica, sem repeticao
    meses = []
    for sessao in carregar_tabela("sessions"):
        mes = mes_da_data(sessao["start_time"])
        if mes not in meses:
            meses.append(mes)
    # ordenacao por insercao usando a chave numerica do mes
    for i in range(1, len(meses)):
        atual = meses[i]
        j = i - 1
        while j >= 0 and chave_do_mes(meses[j]) > chave_do_mes(atual):
            meses[j + 1] = meses[j]
            j -= 1
        meses[j + 1] = atual
    return meses
