"""
Autor.....: Equipe EV ChargeOps (RM573133, RM571998, RM568867, RM574003)
Assunto...: MODEL - base de demonstracao (dados sinteticos)
Problema..: Criar um condominio de exemplo com historico de recargas de junho a
            outubro de 2026, mantendo os registros de exemplo do README da Sprint 1
            (Apto 42, Joao Silva, cartao A1B2C3D4, GW-001, sessao 5001, fatura 9001)
"""
import random
from datetime import datetime, timedelta

from model import dados
from model import rateio
from model import telemetria

# ----- CONSTANTES (tuplas usadas como tabelas fixas)
SEMENTE = 42                       # mesma semente = mesma base em qualquer maquina
DATA_INICIAL = "2026-06-01"
DATA_FINAL = "2026-10-09"

UNIDADES = (
    ("Apto 42", "Torre A"), ("Apto 41", "Torre A"), ("Apto 32", "Torre A"), ("Apto 31", "Torre A"),
    ("Apto 22", "Torre B"), ("Apto 21", "Torre B"), ("Apto 12", "Torre B"), ("Apto 11", "Torre B")
)

# (id da unidade, nome, e-mail); os ids dos usuarios comecam em 101
USUARIOS = (
    (1, "João Silva", "joao@email.com"),
    (1, "Maria Silva", "maria@email.com"),
    (2, "Carlos Pereira", "carlos@email.com"),
    (3, "Ana Souza", "ana@email.com"),
    (4, "Bruno Lima", "bruno@email.com"),
    (5, "Fernanda Costa", "fernanda@email.com"),
    (6, "Rafael Almeida", "rafael@email.com"),
    (6, "Juliana Almeida", "juliana@email.com"),
    (7, "Paulo Mendes", "paulo@email.com"),
    (8, "Luciana Rocha", "luciana@email.com")
)

# (uid do cartao, id do usuario)
CARTOES = (
    ("A1B2C3D4", 101), ("B2C3D4E5", 102), ("C3D4E5F6", 103), ("D4E5F6A7", 104), ("E5F6A7B8", 105),
    ("F6A7B8C9", 106), ("A7B8C9D0", 107), ("B8C9D0E1", 108), ("C9D0E1F2", 109), ("D0E1F2A3", 110)
)

CARREGADORES = (
    ("GW-001", "GW7K-HCA", 7.0, "Vaga L1"),
    ("GW-002", "GW7K-HCA", 7.0, "Vaga L2")
)

# dias da semana em que cada unidade costuma recarregar (0 = segunda ... 6 = domingo)
PERFIS = {
    1: [0, 2, 3], 2: [0, 3], 3: [0, 2, 5], 4: [3],
    5: [1, 4, 6], 6: [0, 2, 3, 5], 7: [4], 8: [1]
}

# sessoes de junho do Apto 42: somam 120,0 kWh, como a fatura 9001 da Sprint 1.
# A primeira linha e a sessao 5001 do README. (cartao, inicio, fim, kWh)
SESSOES_FIXAS_APTO_42 = (
    ("A1B2C3D4", "2026-06-18 19:00", "2026-06-18 22:30", 21.5),
    ("A1B2C3D4", "2026-06-01 19:30", "2026-06-01 22:20", 17.2),
    ("A1B2C3D4", "2026-06-08 20:00", "2026-06-08 23:10", 19.8),
    ("A1B2C3D4", "2026-06-10 18:45", "2026-06-10 21:50", 18.5),
    ("A1B2C3D4", "2026-06-22 19:15", "2026-06-22 22:35", 20.4),
    ("B2C3D4E5", "2026-06-24 20:10", "2026-06-24 23:50", 22.6)
)

# (mes, data do fechamento, data dos pagamentos)
FECHAMENTOS = (
    ("06-2026", "2026-07-01", "2026-07-10"),
    ("07-2026", "2026-08-01", "2026-08-10"),
    ("08-2026", "2026-09-01", "2026-09-10"),
    ("09-2026", "2026-10-01", "2026-10-08")
)
UNIDADE_INADIMPLENTE = 3           # Apto 32 deixa de pagar a partir de agosto
MES_INICIO_INADIMPLENCIA = "08-2026"
DATA_DO_BLOQUEIO = "2026-10-02"   # dia seguinte ao vencimento da fatura de agosto
UNIDADE_SEM_RECARGA = 7            # Apto 12 nao recarrega em setembro (caso de isencao)
MES_SEM_RECARGA = "09-2026"


# ----- SUBALGORITMOS DE CADASTRO INICIAL
def criar_cadastros() -> None:
    unidades = []
    for i in range(len(UNIDADES)):
        unidades.append({"id": i + 1, "name": UNIDADES[i][0], "block": UNIDADES[i][1]})
    dados.inserir_varios("units", unidades)

    usuarios = []
    for i in range(len(USUARIOS)):
        usuarios.append({"id": dados.ID_INICIAL_USUARIO + i, "unit_id": USUARIOS[i][0],
                         "name": USUARIOS[i][1], "email": USUARIOS[i][2]})
    dados.inserir_varios("users", usuarios)

    cartoes = []
    for cartao in CARTOES:
        cartoes.append({"uid": cartao[0], "user_id": cartao[1], "status": True})
    dados.inserir_varios("rfid_cards", cartoes)

    carregadores = []
    for c in CARREGADORES:
        carregadores.append({"id": c[0], "model": c[1], "max_power_kw": c[2], "location": c[3]})
    dados.inserir_varios("chargers", carregadores)


# ----- SUBALGORITMOS DO HISTORICO DE SESSOES
def monta_sessao(numero: int, uid: str, carregador: str, inicio: str, fim: str, kwh: float,
                 media_kw: float, pico_kw: float, interrompida: bool) -> dict:
    return {
        "id": numero, "rfid_uid": uid, "charger_id": carregador,
        "start_time": inicio, "end_time": fim, "kwh_delivered": kwh,
        "potencia_media_kw": media_kw, "pico_kw": pico_kw, "interrompida": interrompida
    }


def sessoes_fixas() -> list:
    sessoes = []
    numero = dados.ID_INICIAL_SESSAO
    for linha in SESSOES_FIXAS_APTO_42:
        inicio = dados.texto_para_data(linha[1])
        fim = dados.texto_para_data(linha[2])
        horas = (fim - inicio).total_seconds() / 3600
        media = round(linha[3] / horas, 2)
        sessoes.append(monta_sessao(numero, linha[0], "GW-001", linha[1], linha[2], linha[3],
                                    media, round(media * 1.06, 2), False))
        numero += 1
    return sessoes


def carregador_ocupado(sessoes: list, carregador: str, inicio: str, fim: str) -> bool:
    # dois intervalos se sobrepoem quando um comeca antes de o outro terminar
    for sessao in sessoes:
        if sessao["charger_id"] == carregador:
            if sessao["start_time"] < fim and inicio < sessao["end_time"]:
                return True
    return False


def sorteia_inicio(dia: datetime) -> datetime:
    if dia.weekday() < 5:
        # dia util: 70% das recargas comecam a noite, depois do trabalho
        if random.randint(1, 100) <= 70:
            hora = random.randint(18, 21)
        else:
            hora = random.randint(8, 17)
    else:
        hora = random.randint(9, 19)
    minuto = random.randint(0, 5) * 10
    return dia + timedelta(hours=hora, minutes=minuto)


def unidade_recarrega(unit_id: int, dia: datetime, indice: int, total_dias: int) -> bool:
    mes = dia.strftime("%m-%Y")
    if unit_id == 1 and mes == "06-2026":
        return False                      # junho do Apto 42 usa as sessoes fixas
    if unit_id == UNIDADE_SEM_RECARGA and mes == MES_SEM_RECARGA:
        return False
    if unit_id == UNIDADE_INADIMPLENTE and mes == "10-2026":
        return False                      # cartao bloqueado: nao consegue iniciar sessao
    # a adesao cresce de 80% para 92% ao longo do periodo (mais uso com o tempo)
    if dia.weekday() in PERFIS[unit_id]:
        chance = 80 + 12 * indice / total_dias
    else:
        chance = 4
    return random.randint(1, 100) <= chance


def gerar_sessoes() -> list:
    sessoes = sessoes_fixas()
    numero = dados.ID_INICIAL_SESSAO + len(sessoes)
    inicio_periodo = datetime.strptime(DATA_INICIAL, dados.FORMATO_DATA)
    fim_periodo = datetime.strptime(DATA_FINAL, dados.FORMATO_DATA)
    total_dias = (fim_periodo - inicio_periodo).days + 1
    cartoes_por_unidade = {}
    for unit_id in PERFIS:
        cartoes_por_unidade[unit_id] = []
    for i in range(len(CARTOES)):
        cartoes_por_unidade[USUARIOS[i][0]].append(CARTOES[i][0])

    for indice in range(total_dias):
        dia = inicio_periodo + timedelta(days=indice)
        for unit_id in PERFIS:
            if not unidade_recarrega(unit_id, dia, indice, total_dias):
                continue
            inicio = sorteia_inicio(dia)
            duracao = random.randint(120, 240)
            corrente = random.randint(20, 30)
            # procura um carregador livre; se os dois estao ocupados, espera 30 minutos
            carregador = ""
            for tentativa in range(6):
                inicio_texto = inicio.strftime(dados.FORMATO_DATA_HORA)
                fim_texto = (inicio + timedelta(minutes=duracao)).strftime(dados.FORMATO_DATA_HORA)
                primeiro = random.randint(0, 1)
                opcoes = (CARREGADORES[primeiro][0], CARREGADORES[1 - primeiro][0])
                for codigo in opcoes:
                    if carregador == "" and not carregador_ocupado(sessoes, codigo, inicio_texto, fim_texto):
                        carregador = codigo
                if carregador != "":
                    break
                inicio = inicio + timedelta(minutes=30)
            if carregador == "":
                continue                  # fila cheia: a unidade desiste nesse dia

            # 8% das sessoes sao interrompidas (queda de energia ou cabo desconectado)
            minuto_interrupcao = -1
            if random.randint(1, 100) <= 8:
                minuto_interrupcao = random.randint(duracao * 20 // 100, duracao * 80 // 100)
            leituras = telemetria.simular_leituras(duracao, corrente, minuto_interrupcao)
            resumo = telemetria.resumir_leituras(leituras)
            fim = inicio + timedelta(minutes=resumo["duracao_min"])
            opcoes_cartao = cartoes_por_unidade[unit_id]
            uid = opcoes_cartao[random.randint(0, len(opcoes_cartao) - 1)]
            sessoes.append(monta_sessao(numero, uid, carregador,
                                        inicio.strftime(dados.FORMATO_DATA_HORA),
                                        fim.strftime(dados.FORMATO_DATA_HORA),
                                        resumo["kwh"], resumo["potencia_media_kw"],
                                        resumo["pico_kw"], resumo["duracao_min"] < duracao))
            numero += 1
    return sessoes


# ----- SUBALGORITMO DO EXPORT DO SEMS PORTAL
def gerar_export_sems(sessoes: list) -> list:
    # soma diaria por carregador, com pequena diferenca de medicao (+-1,5%)
    chaves = []
    energia = {}
    for sessao in dados.ordenar(sessoes, "start_time", False):
        chave = sessao["start_time"].split(" ")[0] + "|" + sessao["charger_id"]
        if chave not in energia:
            energia[chave] = 0.0
            chaves.append(chave)
        energia[chave] += sessao["kwh_delivered"]

    # tres dias recebem uma diferenca maior, para a conciliacao ter o que apontar
    total = len(chaves)
    divergentes = {total // 4: 1.05, total // 2: 0.94, total - 4: 1.045}
    export = []
    for i in range(total):
        fator = 1 + random.randint(-15, 15) / 1000
        if i in divergentes:
            fator = divergentes[i]
        partes = chaves[i].split("|")
        export.append({"data": partes[0], "charger_id": partes[1],
                       "energia_dia_kwh": round(energia[chaves[i]] * fator, 2)})
    return export


# ----- SUBALGORITMO PRINCIPAL
def gerar_base() -> dict:
    random.seed(SEMENTE)

    # 1) zera as tabelas e grava a configuracao padrao
    dados.esvaziar_tabelas()
    dados.salvar_config(dados.CONFIG_PADRAO.copy())
    dados.limpar_eventos()
    dados.registrar_evento("BASE_CRIADA", "base de demonstração", DATA_INICIAL + " 00:00")

    # 2) cadastros e historico de sessoes
    criar_cadastros()
    sessoes = gerar_sessoes()
    dados.inserir_varios("sessions", sessoes)
    dados.inserir_varios("sems_export", gerar_export_sems(sessoes))

    # 3) fechamentos mensais (sem taxa) e pagamentos
    for linha in FECHAMENTOS:
        mes = linha[0]
        rateio.fechar_mes(mes, False, linha[1])
        for fatura in dados.faturas_do_mes(mes):
            if fatura["status"] != "PENDING":
                continue
            deve = (fatura["unit_id"] == UNIDADE_INADIMPLENTE
                    and dados.chave_do_mes(mes) >= dados.chave_do_mes(MES_INICIO_INADIMPLENCIA))
            if not deve:
                rateio.registrar_pagamento(fatura["id"], linha[2])

    # 4) bloqueio do inadimplente e uma tentativa de uso com o cartao bloqueado
    rateio.atualizar_bloqueios(DATA_DO_BLOQUEIO, DATA_DO_BLOQUEIO + " 08:00")
    dados.registrar_evento("TENTATIVA_CARTAO_BLOQUEADO", "D4E5F6A7 no carregador GW-002",
                           "2026-10-05 19:20")

    return {"unidades": len(UNIDADES), "usuarios": len(USUARIOS), "cartoes": len(CARTOES),
            "sessoes": len(sessoes), "faturas": len(dados.carregar_tabela("invoices"))}
