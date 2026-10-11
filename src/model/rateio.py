"""
Autor.....: Equipe EV ChargeOps (RM573133, RM571998, RM571913, RM568867, RM574003)
Assunto...: MODEL - regras de rateio e cobranca
Problema..: Aplicar o modelo pay-per-use da Sprint 1:
            Fatura = soma(E_sessao x T) + Tx_admin
            com fechamento mensal COM taxa ou SEM taxa, auditoria e bloqueio
"""
from datetime import datetime, timedelta

import formato
from model import dados


# ----- SUBALGORITMOS DA FORMULA
def calcula_total(kwh: float, tarifa: float, taxa_admin: float) -> float:
    # a formula pura da Sprint 1, usada por todo o sistema
    return round(kwh * tarifa + taxa_admin, 2)


def taxa_do_fechamento(config: dict, com_taxa: bool) -> float:
    # opcao COM taxa usa o valor configurado; opcao SEM taxa usa zero
    if com_taxa:
        return config["taxa_admin"]
    return 0.0


def comparar_com_e_sem_taxa(kwh: float, tarifa: float, taxa_admin: float) -> dict:
    # as duas opcoes partem do mesmo consumo, ja arredondado em centavos
    consumo = round(kwh * tarifa, 2)
    return {
        "kwh": kwh,
        "tarifa": tarifa,
        "taxa_admin": taxa_admin,
        "consumo": consumo,
        "total_sem_taxa": consumo,
        "total_com_taxa": round(consumo + taxa_admin, 2)
    }


# ----- SUBALGORITMOS DE FATURA
def detalhar_sessoes(sessoes: list, tarifa: float) -> list:
    # composicao da fatura: uma linha por sessao (base da auditoria)
    detalhe = []
    for sessao in sessoes:
        detalhe.append({
            "sessao": sessao["id"],
            "inicio": sessao["start_time"],
            "fim": sessao["end_time"],
            "cartao": sessao["rfid_uid"],
            "carregador": sessao["charger_id"],
            "kwh": sessao["kwh_delivered"],
            "valor": round(sessao["kwh_delivered"] * tarifa, 2),
            "interrompida": sessao["interrompida"]
        })
    return detalhe


def calcular_fatura(unit_id: int, mes: str, tarifa: float, taxa_admin: float,
                    cobrar_taxa_sem_uso: bool) -> dict:
    # soma todas as sessoes de todos os cartoes da unidade no mes
    sessoes = dados.sessoes_da_unidade(unit_id, mes)
    total_kwh = 0.0
    soma_valor = 0.0
    for sessao in sessoes:
        # sessao interrompida entra com o kWh validado ate a queda
        total_kwh += sessao["kwh_delivered"]
        soma_valor += sessao["kwh_delivered"] * tarifa      # E_sessao x T

    if len(sessoes) > 0:
        taxa_cobrada = taxa_admin
        total = round(soma_valor + taxa_cobrada, 2)          # + Tx_admin
        status = "PENDING"
    elif cobrar_taxa_sem_uso and taxa_admin > 0:
        taxa_cobrada = taxa_admin
        total = round(taxa_cobrada, 2)
        status = "PENDING"
    else:
        # unidade sem recarga no mes: nao ha consumo variavel a cobrar
        taxa_cobrada = 0.0
        total = 0.0
        status = "ISENTO"

    return {
        "unit_id": unit_id,
        "month": mes,
        "total_kwh": round(total_kwh, 2),
        "total_value": total,
        "status": status,
        "tarifa": tarifa,
        "taxa_admin": taxa_cobrada,
        "sessoes": len(sessoes),
        "detalhe": detalhar_sessoes(sessoes, tarifa)
    }


def fechar_mes(mes: str, com_taxa: bool, data_fechamento: str = "") -> dict:
    # consolidacao mensal: gera uma linha (fatura) por unidade do condominio
    if data_fechamento == "":
        data_fechamento = dados.hoje_texto()
    if len(dados.faturas_do_mes(mes)) > 0:
        return {"ok": False, "mensagem": f"O mês {mes} já foi fechado.",
                "faturas": dados.faturas_do_mes(mes)}

    config = dados.carregar_config()
    tarifa = config["tarifa_kwh"]
    taxa = taxa_do_fechamento(config, com_taxa)
    data = datetime.strptime(data_fechamento, dados.FORMATO_DATA)
    vencimento = data + timedelta(days=config["dias_para_vencimento"])

    novas = []
    numero = dados.proximo_id("invoices", dados.ID_INICIAL_FATURA)
    for unidade in dados.carregar_tabela("units"):
        calculo = calcular_fatura(unidade["id"], mes, tarifa, taxa, config["cobrar_taxa_sem_uso"])
        fatura = {
            "id": numero,
            "unit_id": unidade["id"],
            "month": mes,
            "total_kwh": calculo["total_kwh"],
            "total_value": calculo["total_value"],
            "status": calculo["status"],
            # campos extras: guardam os valores usados para a auditoria
            "tarifa": calculo["tarifa"],
            "taxa_admin": calculo["taxa_admin"],
            "sessoes": calculo["sessoes"],
            "fechado_em": data_fechamento,
            "vencimento": vencimento.strftime(dados.FORMATO_DATA),
            "pago_em": ""
        }
        novas.append(fatura)
        numero += 1
    dados.inserir_varios("invoices", novas)

    if com_taxa:
        opcao = f"com taxa de {formato.reais(taxa)}"
    else:
        opcao = "sem taxa"
    dados.registrar_evento("MES_FECHADO", f"{mes} ({opcao}, tarifa {formato.reais(tarifa)}/kWh)",
                           data_fechamento + " 08:00")
    return {"ok": True, "mensagem": f"Mês {mes} fechado {opcao}.", "faturas": novas}


def registrar_pagamento(invoice_id: int, data_pagamento: str = "") -> bool:
    if data_pagamento == "":
        data_pagamento = dados.hoje_texto()
    fatura = dados.buscar_registro("invoices", "id", invoice_id)
    # so uma fatura pendente pode ser paga
    if fatura == {} or fatura["status"] != "PENDING":
        return False
    dados.marcar_fatura_paga(invoice_id, data_pagamento)
    dados.registrar_evento("PAGAMENTO_REGISTRADO",
                           f"fatura {invoice_id} ({formato.reais(fatura['total_value'])})",
                           data_pagamento + " 10:00")
    return True


def auditar_fatura(invoice_id: int) -> dict:
    # auditoria compartilhada: refaz a conta a partir das sessoes gravadas
    # e compara com o valor armazenado. Gestor e morador usam esta mesma funcao.
    fatura = dados.buscar_registro("invoices", "id", invoice_id)
    if fatura == {}:
        return {"encontrada": False}
    config = dados.carregar_config()
    unidade = dados.buscar_registro("units", "id", fatura["unit_id"])
    # a taxa guardada na fatura diz se o fechamento foi com taxa ou sem taxa
    if fatura["status"] == "ISENTO":
        taxa = 0.0
    else:
        taxa = fatura["taxa_admin"]
    calculo = calcular_fatura(fatura["unit_id"], fatura["month"], fatura["tarifa"],
                              taxa, config["cobrar_taxa_sem_uso"])
    diferenca_valor = abs(calculo["total_value"] - fatura["total_value"])
    diferenca_kwh = abs(calculo["total_kwh"] - fatura["total_kwh"])
    return {
        "encontrada": True,
        "fatura": fatura,
        "unidade": unidade,
        "detalhe": calculo["detalhe"],
        "kwh_recalculado": calculo["total_kwh"],
        "valor_recalculado": calculo["total_value"],
        "confere": diferenca_valor < 0.005 and diferenca_kwh < 0.005
    }


def conferir_faturas() -> dict:
    # indicador "precisao do faturamento" da Sprint 1 (meta de 100%):
    # audita todas as faturas fechadas e conta quantas conferem com as sessoes
    total = 0
    conferem = 0
    for fatura in dados.carregar_tabela("invoices"):
        total += 1
        if auditar_fatura(fatura["id"])["confere"]:
            conferem += 1
    precisao = 0.0
    if total > 0:
        precisao = conferem / total
    return {"faturas": total, "conferem": conferem, "precisao": precisao}


# ----- SUBALGORITMOS DE INADIMPLENCIA E BLOQUEIO
def faturas_vencidas(hoje: str) -> list:
    # INADIMPLENCIA = FATURA_PENDENTE AND VENCIDA
    # datas no formato AAAA-MM-DD podem ser comparadas como texto
    resultado = []
    for fatura in dados.carregar_tabela("invoices"):
        if fatura["status"] == "PENDING" and fatura["vencimento"] < hoje:
            resultado.append(fatura)
    return resultado


def unidade_inadimplente(unit_id: int, hoje: str) -> bool:
    for fatura in faturas_vencidas(hoje):
        if fatura["unit_id"] == unit_id:
            return True
    return False


def atualizar_bloqueios(hoje: str, data_hora: str = "") -> dict:
    # bloqueio logico binario da tag (Sprint 1): status = NOT inadimplente
    usuarios = dados.carregar_tabela("users")
    cartoes = dados.carregar_tabela("rfid_cards")
    bloqueados = 0
    desbloqueados = 0
    for cartao in cartoes:
        usuario = dados.buscar(usuarios, "id", cartao["user_id"])
        if usuario == {}:
            continue
        novo_status = not unidade_inadimplente(usuario["unit_id"], hoje)
        # so grava no banco quando o cartao muda de situacao
        if novo_status != cartao["status"]:
            dados.mudar_status_do_cartao(cartao["uid"], novo_status)
            if novo_status:
                desbloqueados += 1
                dados.registrar_evento("CARTAO_DESBLOQUEADO", cartao["uid"], data_hora)
            else:
                bloqueados += 1
                dados.registrar_evento("CARTAO_BLOQUEADO", cartao["uid"] + " (fatura vencida)", data_hora)
    return {"bloqueados": bloqueados, "desbloqueados": desbloqueados}


# ----- SUBALGORITMOS DE RELATORIO
def consumo_por_unidade(mes: str) -> list:
    # ranking de consumo do mes, do maior para o menor
    config = dados.carregar_config()
    mapa = dados.mapa_cartao_unidade()
    sessoes = dados.sessoes_do_mes(mes)
    linhas = []
    for unidade in dados.carregar_tabela("units"):
        kwh = 0.0
        quantidade = 0
        for sessao in sessoes:
            uid = sessao["rfid_uid"]
            if uid in mapa and mapa[uid] == unidade["id"]:
                kwh += sessao["kwh_delivered"]
                quantidade += 1
        linhas.append({
            "unit_id": unidade["id"],
            "unidade": unidade["name"],
            "bloco": unidade["block"],
            "sessoes": quantidade,
            "kwh": round(kwh, 2),
            "consumo_rs": round(kwh * config["tarifa_kwh"], 2)
        })
    return dados.ordenar(linhas, "kwh", True)


def horas_do_mes(mes: str) -> int:
    # diferenca entre o primeiro dia do mes e o primeiro dia do mes seguinte
    partes = mes.split("-")
    numero_mes = int(partes[0])
    ano = int(partes[1])
    inicio = datetime(ano, numero_mes, 1)
    if numero_mes == 12:
        fim = datetime(ano + 1, 1, 1)
    else:
        fim = datetime(ano, numero_mes + 1, 1)
    return (fim - inicio).days * 24


def resumo_do_mes(mes: str) -> dict:
    sessoes = dados.sessoes_do_mes(mes)
    faturas = dados.faturas_do_mes(mes)
    total_kwh = 0.0
    interrompidas = 0
    kwh_por_carregador = {}
    horas_por_carregador = {}
    for carregador in dados.carregar_tabela("chargers"):
        kwh_por_carregador[carregador["id"]] = 0.0
        horas_por_carregador[carregador["id"]] = 0.0
    for sessao in sessoes:
        total_kwh += sessao["kwh_delivered"]
        if sessao["interrompida"]:
            interrompidas += 1
        inicio = dados.texto_para_data(sessao["start_time"])
        fim = dados.texto_para_data(sessao["end_time"])
        duracao_h = (fim - inicio).total_seconds() / 3600
        if sessao["charger_id"] in kwh_por_carregador:
            kwh_por_carregador[sessao["charger_id"]] += sessao["kwh_delivered"]
            horas_por_carregador[sessao["charger_id"]] += duracao_h

    # taxa de ociosidade: parte do mes em que o carregador ficou sem sessao
    ociosidade = {}
    total_horas = horas_do_mes(mes)
    for codigo in horas_por_carregador:
        kwh_por_carregador[codigo] = round(kwh_por_carregador[codigo], 2)
        ociosidade[codigo] = round(1 - horas_por_carregador[codigo] / total_horas, 3)

    faturado = 0.0
    recebido = 0.0
    pendente = 0.0
    for fatura in faturas:
        faturado += fatura["total_value"]
        if fatura["status"] == "PAID":
            recebido += fatura["total_value"]
        elif fatura["status"] == "PENDING":
            pendente += fatura["total_value"]

    return {
        "mes": mes,
        "sessoes": len(sessoes),
        "interrompidas": interrompidas,
        "total_kwh": round(total_kwh, 2),
        "fechado": len(faturas) > 0,
        "valor_faturado": round(faturado, 2),
        "valor_recebido": round(recebido, 2),
        "valor_pendente": round(pendente, 2),
        "kwh_por_carregador": kwh_por_carregador,
        "ociosidade": ociosidade
    }
