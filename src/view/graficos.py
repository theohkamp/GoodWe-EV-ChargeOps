"""
Autor.....: Equipe EV ChargeOps (RM573133, RM571998, RM571913, RM568867, RM574003)
Assunto...: VIEW - graficos (matplotlib)
Problema..: Desenhar os graficos usados na interface web, no notebook e nas evidencias.
            Cada funcao recebe os dados prontos e devolve a figura.
"""
import matplotlib.pyplot as plt

# ----- CONSTANTES
COR_PRINCIPAL = "#0b5394"
COR_DESTAQUE = "#d62728"
COR_APOIO = "#7f7f7f"
ROTULOS_DIAS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")


# ----- SUBALGORITMOS
def nova_figura(titulo: str, rotulo_x: str, rotulo_y: str):
    fig, ax = plt.subplots(figsize=(8, 4), dpi=120)
    ax.set_title(titulo)
    ax.set_xlabel(rotulo_x)
    ax.set_ylabel(rotulo_y)
    ax.grid(True, alpha=0.3)
    return fig, ax


def fechar(fig) -> None:
    plt.close(fig)                       # libera a memoria da figura


def salvar(fig, arquivo: str) -> None:
    fig.savefig(arquivo, bbox_inches="tight")
    fechar(fig)
    print(f"Gráfico salvo: {arquivo}")


def grafico_consumo_diario(datas: list, kwh: list):
    fig, ax = nova_figura("Energia entregue por dia", "dia do histórico", "kWh")
    posicoes = []
    for i in range(len(datas)):
        posicoes.append(i)
    ax.plot(posicoes, kwh, color=COR_PRINCIPAL, linewidth=1.5)
    # mostra uma data a cada 14 dias para o eixo nao ficar ilegivel
    marcas = []
    rotulos = []
    for i in range(0, len(datas), 14):
        marcas.append(i)
        rotulos.append(datas[i][5:])
    ax.set_xticks(marcas)
    ax.set_xticklabels(rotulos, rotation=45)
    return fig


def grafico_curva_de_carga(curva: list, limite_kw: float):
    # media dos dias uteis, media do fim de semana e o dia mais carregado
    fig, ax = nova_figura("Curva de carga por hora do dia", "hora", "potência média (kW)")
    horas = []
    uteis = []
    fim_de_semana = []
    for h in range(24):
        horas.append(h)
        soma_uteis = 0.0
        for d in range(5):
            soma_uteis += curva[d][h]
        uteis.append(soma_uteis / 5)
        fim_de_semana.append((curva[5][h] + curva[6][h]) / 2)
    dia_mais_carregado = 0
    for d in range(7):
        if max(curva[d]) > max(curva[dia_mais_carregado]):
            dia_mais_carregado = d
    ax.plot(horas, uteis, color=COR_PRINCIPAL, linewidth=2, label="dias úteis (média)")
    ax.plot(horas, fim_de_semana, color=COR_APOIO, linewidth=2, label="fim de semana (média)")
    ax.plot(horas, curva[dia_mais_carregado], color=COR_DESTAQUE, linewidth=1.5, linestyle="--",
            label=f"dia mais carregado ({ROTULOS_DIAS[dia_mais_carregado]})")
    ax.axhline(y=limite_kw, color="black", linestyle=":", label=f"limite do quadro ({limite_kw:.0f} kW)")
    ax.set_xticks(horas)
    ax.legend()
    return fig


def grafico_previsao_vs_real(datas: list, real: list, previsto: list):
    fig, ax = nova_figura("Demanda diária no período de teste: real x previsto", "dia", "kWh")
    posicoes = []
    rotulos = []
    for i in range(len(datas)):
        posicoes.append(i)
        rotulos.append(datas[i][5:])
    ax.plot(posicoes, real, color=COR_PRINCIPAL, linewidth=2, marker="o", label="real")
    ax.plot(posicoes, previsto, color=COR_DESTAQUE, linewidth=2, marker="s", linestyle="--", label="previsto")
    ax.set_xticks(posicoes)
    ax.set_xticklabels(rotulos, rotation=90)
    ax.legend()
    return fig


def grafico_residuos(real: list, previsto: list):
    fig, ax = nova_figura("Análise dos resíduos", "valores previstos (kWh)", "resíduo (real - previsto)")
    residuos = []
    for i in range(len(real)):
        residuos.append(real[i] - previsto[i])
    ax.scatter(previsto, residuos, color=COR_PRINCIPAL)
    ax.axhline(y=0, color=COR_DESTAQUE, linestyle="--")
    return fig


def grafico_ranking(ranking: list, mes: str):
    fig, ax = nova_figura(f"Consumo por unidade em {mes}", "unidade", "kWh")
    nomes = []
    valores = []
    for linha in ranking:
        nomes.append(linha["unidade"])
        valores.append(linha["kwh"])
    ax.bar(nomes, valores, color=COR_PRINCIPAL)
    return fig


def grafico_previsao_7_dias(previsoes: list):
    fig, ax = nova_figura("Previsão de demanda para os próximos 7 dias", "dia", "kWh previstos")
    rotulos = []
    valores = []
    cores = []
    for dia in previsoes:
        rotulos.append(dia["dia_semana"][:3] + "\n" + dia["data"][5:])
        valores.append(dia["kwh_previsto"])
        # dia com risco alto de sobrecarga aparece em vermelho
        if dia["risco_alto"]:
            cores.append(COR_DESTAQUE)
        else:
            cores.append(COR_PRINCIPAL)
    ax.bar(rotulos, valores, color=cores)
    return fig


def grafico_limite_dos_dados(limite: dict, meta: float):
    # precisao do modelo comparada com as duas referencias e com a meta da Sprint 1
    fig, ax = nova_figura("Precisão da previsão e o limite dos dados simulados", "", "precisão (%)")
    rotulos = ["modelo\npor dia", "teto do\ncalendário", "sabendo as\nrecargas do dia",
               f"modelo\npor semana ({limite['semanas_de_teste']} sem.)"]
    valores = [limite["modelo_por_dia"] * 100, limite["teto_do_calendario"] * 100,
               limite["sabendo_as_recargas"] * 100, limite["modelo_por_semana"] * 100]
    cores = [COR_PRINCIPAL, COR_APOIO, COR_APOIO, COR_PRINCIPAL]
    ax.bar(rotulos, valores, color=cores)
    ax.axhline(y=meta * 100, color=COR_DESTAQUE, linestyle="--", label=f"meta da Sprint 1 ({meta * 100:.0f}%)")
    ax.set_ylim(0, 100)
    ax.legend(loc="lower right")
    return fig


def grafico_potencia_da_sessao(leituras: list):
    fig, ax = nova_figura("Potência medida durante a sessão", "minuto", "kW")
    minutos = []
    potencias = []
    for leitura in leituras:
        minutos.append(leitura["minuto"])
        potencias.append(leitura["potencia_kw"])
    ax.plot(minutos, potencias, color=COR_PRINCIPAL, linewidth=1.5)
    return fig
