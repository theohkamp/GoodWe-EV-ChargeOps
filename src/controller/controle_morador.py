"""
Autor.....: Equipe EV ChargeOps (RM573133, RM571998, RM571913, RM568867, RM574003)
Assunto...: CONTROLLER - acoes do morador
Problema..: Montar o painel de uma unidade: consumo, sessoes, fatura auditada
            e situacao dos cartoes RFID
"""
from model import dados
from model import rateio


# ----- SUBALGORITMOS
def listar_unidades() -> list:
    return dados.carregar_tabela("units")


def buscar_unidade(unit_id: int) -> dict:
    return dados.buscar_registro("units", "id", unit_id)


def cartoes_da_unidade(unit_id: int) -> list:
    return dados.filtrar(dados.cartoes_detalhados(), "unit_id", unit_id)


def painel_da_unidade(unit_id: int, mes: str) -> dict:
    config = dados.carregar_config()
    unidade = buscar_unidade(unit_id)
    sessoes = dados.sessoes_da_unidade(unit_id, mes)
    kwh = 0.0
    for sessao in sessoes:
        kwh += sessao["kwh_delivered"]
    painel = {
        "unidade": unidade,
        "mes": mes,
        "tarifa": config["tarifa_kwh"],
        "sessoes": rateio.detalhar_sessoes(sessoes, config["tarifa_kwh"]),
        "kwh": round(kwh, 2),
        "consumo_rs": round(kwh * config["tarifa_kwh"], 2),
        "cartoes": cartoes_da_unidade(unit_id),
        "inadimplente": rateio.unidade_inadimplente(unit_id, dados.hoje_texto()),
        "tem_fatura": False,
        "auditoria": {}
    }
    # a fatura do morador passa pela mesma auditoria usada pelo gestor
    fatura = dados.fatura_da_unidade(unit_id, mes)
    if fatura != {}:
        painel["tem_fatura"] = True
        painel["auditoria"] = rateio.auditar_fatura(fatura["id"])
    return painel
