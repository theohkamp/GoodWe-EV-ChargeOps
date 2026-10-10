"""
Autor.....: Equipe EV ChargeOps (RM573133, RM571998, RM571913, RM568867, RM574003)
Assunto...: CONTROLLER - inteligencia artificial
Problema..: Ligar as telas as duas frentes de IA: previsao de demanda e Sindico Virtual
"""
from datetime import datetime

from model import dados
from model import ia_previsao
from model import sindico_virtual


# ----- SUBALGORITMOS DA PREVISAO DE DEMANDA
def treinar() -> dict:
    return ia_previsao.executar_previsao_completa()


def previsao_atual() -> dict:
    return ia_previsao.carregar_previsao()


def meta_de_precisao() -> float:
    # KPI definido na Sprint 1: precisao do modelo preditivo acima de 85%
    return 0.85


def janela_sugerida(duracao_h: int) -> dict:
    previsao = ia_previsao.carregar_previsao()
    if previsao == {}:
        return {}
    return ia_previsao.sugerir_janela(previsao["curva_de_carga"], datetime.now().weekday(), duracao_h)


def serie_diaria() -> dict:
    # historico diario para o grafico de consumo
    tabela = ia_previsao.montar_tabela_diaria()
    return {"datas": list(tabela["data"].values), "kwh": list(tabela["kwh_total"].values)}


# ----- SUBALGORITMOS DO SINDICO VIRTUAL
def modo_da_ia() -> str:
    if sindico_virtual.modo_llm_ativo():
        return "LLM " + sindico_virtual.MODELO_LLM
    return "simulado"


def perguntar(pergunta: str, unit_id: int, historico: list) -> dict:
    # unit_id = 0 quando quem pergunta e o gestor (sem unidade padrao)
    unidade = {}
    if unit_id != 0:
        unidade = dados.buscar(dados.carregar_tabela("units"), "id", unit_id)
    return sindico_virtual.responder(pergunta, unidade, historico)


def perguntas_sugeridas() -> list:
    return ["Quanto o apto 42 consumiu em junho?",
            "Qual o valor da fatura do apto 21 em setembro?",
            "Teve algum problema este mês?"]
