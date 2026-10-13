"""
Autor.....: Equipe EV ChargeOps (RM573133, RM571998, RM568867, RM574003)
Assunto...: Funcoes de formatacao usadas pelas tres camadas (model, view, controller)
Problema..: Escrever numeros e valores em reais do jeito brasileiro (virgula decimal)
"""


# ----- SUBALGORITMOS
def decimal(valor: float, casas: int) -> str:
    # 12.4 -> "12,4"
    texto = format(valor, "." + str(casas) + "f")
    return texto.replace(".", ",")


def reais(valor: float) -> str:
    # 13.78 -> "R$ 13,78"
    return "R$ " + decimal(valor, 2)


def percentual(valor: float, casas: int) -> str:
    # 0.257 -> "25,7%"
    return decimal(valor * 100, casas) + "%"


def sim_ou_nao(valor: bool) -> str:
    if valor:
        return "sim"
    return "não"
