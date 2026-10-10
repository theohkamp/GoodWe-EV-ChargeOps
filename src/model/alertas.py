"""
Autor.....: Equipe EV ChargeOps (RM573133, RM571998, RM571913, RM568867, RM574003)
Assunto...: MODEL - alertas com fila de prioridade (heap maximo)
Problema..: Reunir as anomalias do condominio e entregar primeiro as mais graves
"""
from datetime import datetime, timedelta

import formato
from model import dados
from model import ia_previsao
from model import rateio
from model import telemetria

# ----- CONSTANTES: prioridade de cada tipo de alerta (maior = mais grave)
PRIORIDADE_INADIMPLENCIA = 9
PRIORIDADE_SOBRECARGA = 8
PRIORIDADE_CARTAO_BLOQUEADO = 7
PRIORIDADE_DIVERGENCIA_SEMS = 6
PRIORIDADE_SESSAO_INTERROMPIDA = 5
PRIORIDADE_OCIOSIDADE = 2
DIAS_PARA_OCIOSIDADE = 7


# ----- SUBALGORITMOS DO HEAP MAXIMO (vetor: filhos de i em 2i+1 e 2i+2)
def trocar(heap: list, i: int, j: int) -> None:
    temp = heap[i]
    heap[i] = heap[j]
    heap[j] = temp


def heapify_up(heap: list, i: int) -> None:
    # sobe o elemento enquanto ele for maior que o pai
    while i > 0:
        pai = (i - 1) // 2
        if heap[i]["prioridade"] > heap[pai]["prioridade"]:
            trocar(heap, i, pai)
            i = pai
        else:
            break


def heapify_down(heap: list, n: int, i: int) -> None:
    # desce o elemento enquanto algum filho for maior que ele
    maior = i
    esquerda = 2 * i + 1
    direita = 2 * i + 2
    if esquerda < n and heap[esquerda]["prioridade"] > heap[maior]["prioridade"]:
        maior = esquerda
    if direita < n and heap[direita]["prioridade"] > heap[maior]["prioridade"]:
        maior = direita
    if maior != i:
        trocar(heap, i, maior)
        heapify_down(heap, n, maior)


def inserir_alerta(heap: list, prioridade: int, tipo: str, mensagem: str) -> None:
    heap.append({"prioridade": prioridade, "tipo": tipo, "mensagem": mensagem})
    heapify_up(heap, len(heap) - 1)


def remover_maior(heap: list) -> dict:
    # o topo do heap e sempre o alerta mais grave
    maior = heap[0]
    ultimo = heap.pop()
    if len(heap) > 0:
        heap[0] = ultimo
        heapify_down(heap, len(heap), 0)
    return maior


def esvaziar_em_ordem(heap: list) -> list:
    resultado = []
    while len(heap) > 0:
        resultado.append(remover_maior(heap))
    return resultado


# ----- SUBALGORITMOS QUE COLETAM CADA TIPO DE ANOMALIA
def coletar_inadimplencia(heap: list, hoje: str) -> None:
    unidades = dados.carregar_tabela("units")
    for fatura in rateio.faturas_vencidas(hoje):
        unidade = dados.buscar(unidades, "id", fatura["unit_id"])
        inserir_alerta(heap, PRIORIDADE_INADIMPLENCIA, "INADIMPLENCIA",
                       f"{unidade['name']}: fatura {fatura['id']} de {fatura['month']} "
                       f"({formato.reais(fatura['total_value'])}) vencida em {fatura['vencimento']}. "
                       f"Cartões da unidade bloqueados.")


def coletar_sobrecarga(heap: list) -> None:
    previsao = ia_previsao.carregar_previsao()
    if previsao == {}:
        return
    dias = ""
    for dia in previsao["previsao_7_dias"]:
        if dia["risco_alto"]:
            if dias != "":
                dias += ", "
            dias += f"{dia['dia_semana']} {dia['data']} ({formato.decimal(dia['prob_sobrecarga'] * 100, 0)}%)"
    if dias != "":
        inserir_alerta(heap, PRIORIDADE_SOBRECARGA, "SOBRECARGA_PREVISTA",
                       f"Risco de ultrapassar {formato.decimal(previsao['limite_quadro_kw'], 0)} kW no quadro em: {dias}.")


def coletar_cartao_bloqueado(heap: list, mes: str) -> None:
    for evento in dados.ler_eventos():
        if evento["evento"] == "TENTATIVA_CARTAO_BLOQUEADO":
            if dados.mes_da_data(evento["data_hora"]) == mes:
                inserir_alerta(heap, PRIORIDADE_CARTAO_BLOQUEADO, "CARTAO_BLOQUEADO",
                               f"Tentativa de recarga com cartão bloqueado em {evento['data_hora']}: "
                               f"{evento['detalhe']}.")


def coletar_divergencia_sems(heap: list, mes: str) -> None:
    for linha in telemetria.conciliar_sems(mes):
        if linha["divergente"]:
            inserir_alerta(heap, PRIORIDADE_DIVERGENCIA_SEMS, "DIVERGENCIA_SEMS",
                           f"{linha['data']} / {linha['carregador']}: sessões somam "
                           f"{formato.decimal(linha['kwh_sessoes'], 2)} kWh e o SEMS registra {formato.decimal(linha['kwh_sems'], 2)} kWh "
                           f"(diferença de {formato.decimal(linha['erro_relativo'] * 100, 1)}%).")


def coletar_sessoes_interrompidas(heap: list, mes: str) -> None:
    quantidade = 0
    numeros = ""
    for sessao in dados.sessoes_do_mes(mes):
        if sessao["interrompida"]:
            quantidade += 1
            if numeros != "":
                numeros += ", "
            numeros += str(sessao["id"])
    if quantidade > 0:
        inserir_alerta(heap, PRIORIDADE_SESSAO_INTERROMPIDA, "SESSAO_INTERROMPIDA",
                       f"{quantidade} sessão(ões) interrompida(s) em {mes} (ids {numeros}). "
                       f"Cobrado apenas o kWh validado até a queda.")


def coletar_ociosidade(heap: list, mes: str, hoje: str) -> None:
    # carregador sem nenhuma sessao nos ultimos 7 dias
    data_hoje = datetime.strptime(hoje, dados.FORMATO_DATA)
    limite = (data_hoje - timedelta(days=DIAS_PARA_OCIOSIDADE)).strftime(dados.FORMATO_DATA)
    if dados.mes_da_data(hoje + " 00:00") != mes:
        return
    sessoes = dados.carregar_tabela("sessions")
    for carregador in dados.carregar_tabela("chargers"):
        usado = False
        for sessao in sessoes:
            if sessao["charger_id"] == carregador["id"] and sessao["start_time"] >= limite:
                usado = True
        if not usado:
            inserir_alerta(heap, PRIORIDADE_OCIOSIDADE, "OCIOSIDADE",
                           f"Carregador {carregador['id']} ({carregador['location']}) sem sessões "
                           f"há mais de {DIAS_PARA_OCIOSIDADE} dias.")


# ----- SUBALGORITMO PRINCIPAL
def gerar_alertas(mes: str, hoje: str) -> list:
    # monta o heap com todas as anomalias e devolve da mais grave para a mais leve
    heap = []
    coletar_inadimplencia(heap, hoje)
    coletar_sobrecarga(heap)
    coletar_cartao_bloqueado(heap, mes)
    coletar_divergencia_sems(heap, mes)
    coletar_sessoes_interrompidas(heap, mes)
    coletar_ociosidade(heap, mes, hoje)
    return esvaziar_em_ordem(heap)
