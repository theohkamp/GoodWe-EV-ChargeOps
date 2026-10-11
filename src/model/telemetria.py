"""
Autor.....: Equipe EV ChargeOps (RM573133, RM571998, RM571913, RM568867, RM574003)
Assunto...: MODEL - telemetria simulada do carregador GoodWe GW7K-HCA
Problema..: Reproduzir o ciclo de uma sessao de recarga (IEC 61851-1, estados A, B e C)
            gerando as mesmas grandezas que o gateway Modbus entregaria:
            tensao, corrente, potencia e energia acumulada
"""
import random
from datetime import timedelta

import formato
from model import dados
from model import rateio


# ----- SUBALGORITMOS DE AUTORIZACAO (ESTADO B)
def carregador_livre(charger_id: str, inicio_texto: str) -> bool:
    # o carregador esta ocupado se existe sessao com inicio <= momento < fim
    for sessao in dados.filtrar_registros("sessions", "charger_id", charger_id):
        if sessao["start_time"] <= inicio_texto and inicio_texto < sessao["end_time"]:
            return False
    return True


def autorizar_cartao(uid: str, charger_id: str, inicio_texto: str) -> dict:
    # equivalente ao Authorize.req / Authorize.conf do OCPP
    cartao = dados.buscar_registro("rfid_cards", "uid", uid)
    if cartao == {}:
        return {"autorizado": False, "motivo": "cartão não cadastrado", "unidade": {}}
    unidade = dados.unidade_do_cartao(uid)
    hoje = inicio_texto.split(" ")[0]

    cartao_ativo = cartao["status"]
    inadimplente = rateio.unidade_inadimplente(unidade["id"], hoje)
    livre = carregador_livre(charger_id, inicio_texto)

    # AUTORIZA = CARTAO_ATIVO AND NOT UNIDADE_INADIMPLENTE AND CARREGADOR_LIVRE
    autorizado = cartao_ativo and not inadimplente and livre

    if autorizado:
        motivo = "Accepted"
    elif not cartao_ativo or inadimplente:
        motivo = "cartão bloqueado por fatura vencida"
    else:
        motivo = "carregador ocupado"
    return {"autorizado": autorizado, "motivo": motivo, "unidade": unidade}


def proximo_horario_livre(charger_id: str) -> str:
    # agora, ou o fim da ultima sessao se o carregador ainda estiver ocupado
    momento = dados.agora_texto()
    for sessao in dados.filtrar_registros("sessions", "charger_id", charger_id):
        if sessao["end_time"] > momento:
            momento = sessao["end_time"]
    return momento


# ----- SUBALGORITMOS DE MEDICAO (ESTADO C)
def passo_de_euler(energia_kwh: float, potencia_kw: float, passo_h: float) -> float:
    # metodo de Euler: E[n+1] = E[n] + h x P[n]
    return energia_kwh + passo_h * potencia_kw


def simular_leituras(duracao_min: int, corrente_alvo: float, minuto_interrupcao: int) -> list:
    # uma leitura por minuto, como o gateway faria ao consultar o carregador
    config = dados.carregar_config()
    passo_h = 1 / 60                       # 1 minuto em horas
    energia_kwh = 0.0
    leituras = []
    for minuto in range(duracao_min):
        # queda de energia ou cabo desconectado antes do fim
        if minuto == minuto_interrupcao:
            break
        fracao = minuto / duracao_min
        corrente = corrente_alvo
        # nos ultimos 15% da sessao o veiculo reduz a corrente (bateria quase cheia)
        if fracao > 0.85:
            corrente = corrente_alvo * (1 - (fracao - 0.85) / 0.15 * 0.7)
        corrente = corrente + random.randint(-3, 3) / 10          # ruido de +-0,3 A
        tensao = config["tensao_nominal_v"] + random.randint(-30, 30) / 10   # 230 V +-3
        potencia_kw = tensao * corrente / 1000                    # P = V x I
        if potencia_kw > config["potencia_max_kw"]:
            potencia_kw = config["potencia_max_kw"]
        # integra a potencia no tempo para obter a energia (kWh)
        energia_kwh = passo_de_euler(energia_kwh, potencia_kw, passo_h)
        leituras.append({
            "minuto": minuto + 1,
            "tensao_v": round(tensao, 1),
            "corrente_a": round(corrente, 1),
            "potencia_kw": round(potencia_kw, 3),
            "energia_kwh": round(energia_kwh, 3)
        })
    return leituras


def resumir_leituras(leituras: list) -> dict:
    if len(leituras) == 0:
        return {"kwh": 0.0, "potencia_media_kw": 0.0, "pico_kw": 0.0, "duracao_min": 0}
    soma = 0.0
    pico = 0.0
    for leitura in leituras:
        soma += leitura["potencia_kw"]
        if leitura["potencia_kw"] > pico:
            pico = leitura["potencia_kw"]
    return {
        "kwh": round(leituras[len(leituras) - 1]["energia_kwh"], 2),
        "potencia_media_kw": round(soma / len(leituras), 2),
        "pico_kw": round(pico, 2),
        "duracao_min": len(leituras)
    }


# ----- SUBALGORITMO PRINCIPAL: UMA SESSAO COMPLETA
def simular_sessao(uid: str, charger_id: str, inicio_texto: str, duracao_min: int,
                   forcar_interrupcao: bool) -> dict:
    # devolve as seis etapas do fluxo, as leituras e a sessao gravada
    config = dados.carregar_config()
    etapas = []

    # ETAPA 1 - RFID (Estado A: cabo conectado; Estado B: veiculo detectado)
    autorizacao = autorizar_cartao(uid, charger_id, inicio_texto)
    if not autorizacao["autorizado"]:
        etapas.append({"numero": 1, "nome": "RFID",
                       "detalhe": f"Cartão {uid} recusado: {autorizacao['motivo']}."})
        if autorizacao["motivo"] == "cartão bloqueado por fatura vencida":
            dados.registrar_evento("TENTATIVA_CARTAO_BLOQUEADO",
                                   f"{uid} no carregador {charger_id}", inicio_texto)
        else:
            dados.registrar_evento("SESSAO_RECUSADA", f"{uid}: {autorizacao['motivo']}", inicio_texto)
        return {"autorizado": False, "etapas": etapas, "leituras": [], "sessao": {}}
    unidade = autorizacao["unidade"]
    etapas.append({"numero": 1, "nome": "RFID",
                   "detalhe": f"Cartão {uid} lido e autorizado (Authorize: Accepted)."})

    # ETAPA 2 - SESSAO INICIADA (Estado C: handshake PWM define a corrente)
    corrente_alvo = random.randint(20, config["corrente_max_a"])
    etapas.append({"numero": 2, "nome": "Sessão iniciada",
                   "detalhe": f"StartTransaction: carregador {charger_id}, início {inicio_texto}, "
                              f"corrente negociada de {corrente_alvo} A."})

    # ETAPA 3 - ENERGIA MEDIDA (kWh)
    minuto_interrupcao = -1
    if forcar_interrupcao:
        minuto_interrupcao = duracao_min // 2
    leituras = simular_leituras(duracao_min, corrente_alvo, minuto_interrupcao)
    resumo = resumir_leituras(leituras)
    interrompida = resumo["duracao_min"] < duracao_min
    texto_medicao = (f"{formato.decimal(resumo['kwh'], 2)} kWh em {resumo['duracao_min']} min "
                     f"(média {formato.decimal(resumo['potencia_media_kw'], 2)} kW, pico {formato.decimal(resumo['pico_kw'], 2)} kW).")
    if interrompida:
        texto_medicao += " Sessão interrompida: vale o volume validado até a queda."
    etapas.append({"numero": 3, "nome": "Energia medida (kWh)",
                   "detalhe": "StopTransaction: " + texto_medicao})

    inicio = dados.texto_para_data(inicio_texto)
    fim = inicio + timedelta(minutes=resumo["duracao_min"])
    sessao = dados.registrar_sessao({
        "id": 0,
        "rfid_uid": uid,
        "charger_id": charger_id,
        "start_time": inicio_texto,
        "end_time": fim.strftime(dados.FORMATO_DATA_HORA),
        "kwh_delivered": resumo["kwh"],
        # campos extras em relacao ao esquema da Sprint 1
        "potencia_media_kw": resumo["potencia_media_kw"],
        "pico_kw": resumo["pico_kw"],
        "interrompida": interrompida
    })
    if interrompida:
        dados.registrar_evento("SESSAO_INTERROMPIDA", f"sessão {sessao['id']} ({uid})", inicio_texto)
    else:
        dados.registrar_evento("SESSAO_CONCLUIDA", f"sessão {sessao['id']} ({uid})", inicio_texto)

    # ETAPA 4 - ASSOCIACAO A UNIDADE (cartao -> usuario -> unidade)
    etapas.append({"numero": 4, "nome": "Associação à unidade",
                   "detalhe": f"Sessão {sessao['id']} associada a {unidade['name']} / {unidade['block']}."})

    # ETAPA 5 - RATEIO (E_sessao x T; a taxa entra no fechamento do mes)
    valor = rateio.calcula_total(resumo["kwh"], config["tarifa_kwh"], 0.0)
    etapas.append({"numero": 5, "nome": "Rateio",
                   "detalhe": f"{formato.decimal(resumo['kwh'], 2)} kWh x {formato.reais(config['tarifa_kwh'])} = {formato.reais(valor)}. "
                              f"A taxa administrativa, quando ativada, entra no fechamento do mês."})

    # ETAPA 6 - PAINEL E INSIGHTS
    mes = dados.mes_da_data(inicio_texto)
    kwh_mes = 0.0
    for registro in dados.sessoes_da_unidade(unidade["id"], mes):
        kwh_mes += registro["kwh_delivered"]
    etapas.append({"numero": 6, "nome": "Painel e Insights",
                   "detalhe": f"{unidade['name']} acumula {formato.decimal(kwh_mes, 2)} kWh em {mes} "
                              f"({formato.reais(rateio.calcula_total(kwh_mes, config['tarifa_kwh'], 0.0))} de consumo)."})

    return {"autorizado": True, "etapas": etapas, "leituras": leituras, "sessao": sessao}


# ----- SUBALGORITMOS DE CONCILIACAO COM O SEMS PORTAL
def energia_por_dia_e_carregador(mes: str) -> dict:
    # chave "AAAA-MM-DD|carregador" -> soma dos kWh das sessoes iniciadas no dia
    # a soma por dia e por carregador e feita pelo banco (SUM com GROUP BY)
    tabela = {}
    for linha in dados.energia_por_dia(mes):
        tabela[linha["dia"] + "|" + linha["charger_id"]] = linha["kwh"]
    return tabela


def conciliar_sems(mes: str) -> list:
    # compara a energia das sessoes com o export diario do SEMS (auditoria)
    config = dados.carregar_config()
    medido = energia_por_dia_e_carregador(mes)
    linhas = []
    for registro in dados.carregar_tabela("sems_export"):
        dia = registro["data"]
        if dados.mes_da_data(dia + " 00:00") != mes:
            continue
        chave = dia + "|" + registro["charger_id"]
        energia_sessoes = 0.0
        if chave in medido:
            energia_sessoes = medido[chave]
        energia_sems = registro["energia_dia_kwh"]
        erro_absoluto = abs(energia_sessoes - energia_sems)
        erro_relativo = 0.0
        if energia_sems > 0:
            erro_relativo = erro_absoluto / energia_sems
        linhas.append({
            "data": dia,
            "carregador": registro["charger_id"],
            "kwh_sessoes": round(energia_sessoes, 2),
            "kwh_sems": round(energia_sems, 2),
            "erro_absoluto": round(erro_absoluto, 2),
            "erro_relativo": round(erro_relativo, 4),
            "divergente": erro_relativo > config["limite_divergencia_sems"]
        })
    return linhas
