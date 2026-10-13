"""
Autor.....: Equipe EV ChargeOps (RM573133, RM571998, RM568867, RM574003)
Assunto...: MODEL - camada de dados (banco de dados SQLite)
Problema..: Guardar e consultar as seis tabelas definidas na Sprint 1
            (Unit, User, RFID_Card, Charger, Session, Invoice)
            Este e o unico modulo que escreve comandos SQL. Os outros modulos
            recebem listas de dicionarios e nao sabem como os dados sao guardados.
"""
import json
import os
import sqlite3
from datetime import datetime

# ----- CONSTANTES
PASTA_DADOS = "dados"
ARQUIVO_BANCO = "dados/ev_chargeops.db"
ARQUIVO_ESQUEMA = "src/model/esquema.sql"
ARQUIVO_CONFIG = "dados/config.json"
ARQUIVO_REGISTROS = "dados/registros.txt"
# ordem de criacao: uma tabela vem sempre depois das tabelas que ela referencia
TABELAS = ("units", "users", "rfid_cards", "chargers", "sessions", "invoices", "sems_export")
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


# ----- SUBALGORITMOS DO BANCO DE DADOS
def garantir_pasta() -> None:
    # cria a pasta dados/ na primeira gravacao
    if not os.path.exists(PASTA_DADOS):
        os.mkdir(PASTA_DADOS)


def texto_para_booleano(valor: bytes) -> bool:
    # o SQLite guarda verdadeiro e falso como 1 e 0
    return int(valor) == 1


# toda coluna declarada como BOOLEAN no esquema volta ao Python como True ou False
sqlite3.register_converter("BOOLEAN", texto_para_booleano)


def conectar() -> sqlite3.Connection:
    # abre o arquivo do banco; na primeira vez, cria as tabelas a partir do esquema
    garantir_pasta()
    banco_novo = not os.path.exists(ARQUIVO_BANCO)
    conexao = sqlite3.connect(ARQUIVO_BANCO, detect_types=sqlite3.PARSE_DECLTYPES)
    conexao.row_factory = sqlite3.Row              # cada linha pode ser lida pelo nome da coluna
    conexao.execute("PRAGMA foreign_keys = ON")    # liga a conferencia das chaves estrangeiras
    if banco_novo:
        with open(ARQUIVO_ESQUEMA, "r", encoding="utf-8") as arq:
            conexao.executescript(arq.read())
    return conexao


def consultar(comando: str, valores: tuple = ()) -> list:
    # executa um SELECT e devolve o resultado como lista de dicionarios
    # os valores entram no lugar de cada "?" do comando, nunca colados no texto
    conexao = conectar()
    try:
        linhas = conexao.execute(comando, valores).fetchall()
    finally:
        conexao.close()                # fecha a conexao mesmo se o comando der erro
    resultado = []
    for linha in linhas:
        resultado.append(dict(linha))
    return resultado


def executar_varios(comando: str, linhas: list) -> None:
    # repete o mesmo INSERT, UPDATE ou DELETE para cada tupla de valores
    # tudo em uma unica transacao: o commit confirma todas as gravacoes de uma vez
    conexao = conectar()
    try:
        conexao.executemany(comando, linhas)
        conexao.commit()
    finally:
        conexao.close()                # se o banco recusar a gravacao, nada fica pela metade


def executar(comando: str, valores: tuple = ()) -> None:
    executar_varios(comando, [valores])


def inserir_varios(nome: str, registros: list) -> None:
    # grava varios registros da mesma tabela; as chaves do dicionario sao os nomes das colunas
    if len(registros) == 0:
        return
    campos = list(registros[0].keys())
    marcas = ["?"] * len(campos)
    comando = f"INSERT INTO {nome} ({', '.join(campos)}) VALUES ({', '.join(marcas)})"
    linhas = []
    for registro in registros:
        linhas.append(tuple(registro.values()))
    executar_varios(comando, linhas)


def inserir(nome: str, registro: dict) -> None:
    inserir_varios(nome, [registro])


def esvaziar_tabelas() -> None:
    # apaga na ordem inversa da criacao: primeiro quem referencia, depois quem e referenciado
    for i in range(len(TABELAS) - 1, -1, -1):
        executar(f"DELETE FROM {TABELAS[i]}")


def carregar_tabela(nome: str) -> list:
    # tabela inteira, na ordem em que os registros foram gravados
    return consultar(f"SELECT * FROM {nome} ORDER BY rowid")


def primeiro(linhas: list) -> dict:
    # primeiro registro de uma consulta ou {} quando ela nao trouxe nada
    if len(linhas) == 0:
        return {}
    return linhas[0]


def buscar_registro(nome: str, campo: str, valor) -> dict:
    return primeiro(consultar(f"SELECT * FROM {nome} WHERE {campo} = ?", (valor,)))


def filtrar_registros(nome: str, campo: str, valor) -> list:
    return consultar(f"SELECT * FROM {nome} WHERE {campo} = ? ORDER BY rowid", (valor,))


def proximo_id(nome: str, inicial: int) -> int:
    # maior id existente + 1; "inicial" vale para a tabela vazia
    linha = consultar(f"SELECT COUNT(*) AS total, MAX(id) AS maior FROM {nome}")[0]
    if linha["total"] == 0:
        return inicial
    return linha["maior"] + 1


def base_existe() -> bool:
    # a base existe quando o banco ja foi criado e tem unidades cadastradas
    if not os.path.exists(ARQUIVO_BANCO):
        return False
    return consultar("SELECT COUNT(*) AS total FROM units")[0]["total"] > 0


# ----- SUBALGORITMOS DE CONFIGURACAO (ARQUIVO JSON)
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


def padrao_do_mes(mes: str) -> str:
    # "06-2026" -> "2026-06%": no LIKE, o % aceita qualquer texto depois do ano e do mes
    return mes[3:7] + "-" + mes[0:2] + "%"


def mes_atual() -> str:
    return datetime.now().strftime("%m-%Y")


# ----- SUBALGORITMOS DE REGISTRO (LOG EM ARQUIVO TEXTO)
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
    garantir_pasta()
    with open(ARQUIVO_REGISTROS, "w", encoding="utf-8") as arq:
        arq.write("")


# ----- SUBALGORITMOS DE BUSCA E ORDENACAO EM LISTAS
# usados sobre listas que ja estao na memoria (resultados de consultas e de calculos)
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
    unidade = {"id": proximo_id("units", 1), "name": nome, "block": bloco}
    inserir("units", unidade)
    registrar_evento("UNIDADE_CADASTRADA", f"{nome} / {bloco}")
    return unidade


def cadastrar_usuario(unit_id: int, nome: str, email: str) -> dict:
    if buscar_registro("units", "id", unit_id) == {}:
        return {}
    usuario = {"id": proximo_id("users", ID_INICIAL_USUARIO), "unit_id": unit_id,
               "name": nome, "email": email}
    inserir("users", usuario)
    registrar_evento("USUARIO_CADASTRADO", f"{nome} (unidade {unit_id})")
    return usuario


def cadastrar_cartao(uid: str, user_id: int) -> dict:
    usuario = buscar_registro("users", "id", user_id)
    if usuario == {}:
        return {"ok": False, "mensagem": "Usuário não encontrado."}
    if buscar_registro("rfid_cards", "uid", uid) != {}:
        return {"ok": False, "mensagem": "Já existe um cartão com esse UID."}
    # regra da Sprint 1: no maximo 10 cartoes RFID por unidade
    if len(cartoes_da_unidade(usuario["unit_id"])) >= LIMITE_CARTOES_POR_UNIDADE:
        return {"ok": False, "mensagem": "A unidade já tem 10 cartões cadastrados."}
    inserir("rfid_cards", {"uid": uid, "user_id": user_id, "status": True})
    registrar_evento("CARTAO_CADASTRADO", f"{uid} (usuário {user_id})")
    return {"ok": True, "mensagem": "Cartão cadastrado."}


def registrar_sessao(sessao: dict) -> dict:
    sessao["id"] = proximo_id("sessions", ID_INICIAL_SESSAO)
    inserir("sessions", sessao)
    return sessao


# ----- SUBALGORITMOS DE ATUALIZACAO
def marcar_fatura_paga(invoice_id: int, data_pagamento: str) -> None:
    executar("UPDATE invoices SET status = 'PAID', pago_em = ? WHERE id = ?",
             (data_pagamento, invoice_id))


def mudar_status_do_cartao(uid: str, ativo: bool) -> None:
    executar("UPDATE rfid_cards SET status = ? WHERE uid = ?", (ativo, uid))


# ----- SUBALGORITMOS DE CONSULTA
def cartoes_da_unidade(unit_id: int) -> list:
    # unifica todos os cartoes dos usuarios da mesma unidade
    return consultar("""SELECT rfid_cards.*
                        FROM rfid_cards
                        JOIN users ON users.id = rfid_cards.user_id
                        WHERE users.unit_id = ?
                        ORDER BY rfid_cards.rowid""", (unit_id,))


def cartoes_detalhados() -> list:
    # cada cartao com o nome do usuario, a unidade e a situacao, pronto para as telas
    linhas = consultar("""SELECT rfid_cards.uid, rfid_cards.status, users.name AS usuario,
                                 units.id AS unit_id, units.name AS unidade
                          FROM rfid_cards
                          JOIN users ON users.id = rfid_cards.user_id
                          JOIN units ON units.id = users.unit_id
                          ORDER BY rfid_cards.rowid""")
    resultado = []
    for linha in linhas:
        situacao = "ativo"
        if not linha["status"]:
            situacao = "bloqueado"
        resultado.append({"uid": linha["uid"], "usuario": linha["usuario"], "unit_id": linha["unit_id"],
                          "unidade": linha["unidade"], "situacao": situacao})
    return resultado


def mapa_cartao_unidade() -> dict:
    # dicionario {uid do cartao: id da unidade}; evita repetir consultas
    mapa = {}
    for linha in consultar("""SELECT rfid_cards.uid, users.unit_id
                              FROM rfid_cards
                              JOIN users ON users.id = rfid_cards.user_id"""):
        mapa[linha["uid"]] = linha["unit_id"]
    return mapa


def unidade_do_cartao(uid: str) -> dict:
    # caminho da Sprint 1: cartao -> usuario -> unidade
    return primeiro(consultar("""SELECT units.*
                                 FROM rfid_cards
                                 JOIN users ON users.id = rfid_cards.user_id
                                 JOIN units ON units.id = users.unit_id
                                 WHERE rfid_cards.uid = ?""", (uid,)))


def sessoes_do_mes(mes: str) -> list:
    return consultar("""SELECT * FROM sessions
                        WHERE start_time LIKE ?
                        ORDER BY start_time, id""", (padrao_do_mes(mes),))


def sessoes_da_unidade(unit_id: int, mes: str) -> list:
    # sessoes de todos os cartoes da unidade no mes (base do rateio)
    return consultar("""SELECT sessions.*
                        FROM sessions
                        JOIN rfid_cards ON rfid_cards.uid = sessions.rfid_uid
                        JOIN users ON users.id = rfid_cards.user_id
                        WHERE users.unit_id = ? AND sessions.start_time LIKE ?
                        ORDER BY sessions.start_time, sessions.id""", (unit_id, padrao_do_mes(mes)))


def energia_por_dia(mes: str) -> list:
    # soma dos kWh das sessoes iniciadas em cada dia, por carregador
    return consultar("""SELECT substr(start_time, 1, 10) AS dia, charger_id,
                               SUM(kwh_delivered) AS kwh
                        FROM sessions
                        WHERE start_time LIKE ?
                        GROUP BY dia, charger_id
                        ORDER BY dia, charger_id""", (padrao_do_mes(mes),))


def faturas_do_mes(mes: str) -> list:
    return consultar("SELECT * FROM invoices WHERE month = ? ORDER BY id", (mes,))


def fatura_da_unidade(unit_id: int, mes: str) -> dict:
    return primeiro(consultar("SELECT * FROM invoices WHERE unit_id = ? AND month = ?", (unit_id, mes)))


def meses_com_sessoes() -> list:
    # lista de meses "MM-AAAA" em ordem cronologica, sem repeticao
    # substr(start_time, 1, 7) pega o trecho "AAAA-MM" do inicio de cada sessao
    meses = []
    for linha in consultar("""SELECT DISTINCT substr(start_time, 1, 7) AS ano_mes
                              FROM sessions
                              ORDER BY ano_mes"""):
        meses.append(mes_da_data(linha["ano_mes"]))
    return meses
