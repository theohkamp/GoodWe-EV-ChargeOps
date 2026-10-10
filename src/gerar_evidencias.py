"""
Autor.....: Equipe EV ChargeOps (RM573133, RM571998, RM571913, RM568867, RM574003)
Assunto...: Geracao das evidencias de funcionamento
Problema..: Salvar na pasta evidencias/ os graficos em PNG e uma conversa de
            demonstracao com o Sindico Virtual.
            Executar a partir da raiz do repositorio:  python src/gerar_evidencias.py
"""
import os

from controller import controle_gestor
from controller import controle_ia
from controller import controle_sessao
from model import telemetria
from view import graficos

# ----- CONSTANTES
PASTA = "evidencias"
MES_DO_RANKING = "09-2026"
PERGUNTAS = (
    "Quanto o apto 42 consumiu em junho?",
    "Qual o valor da fatura do apto 42 em junho?",
    "Por que a conta do apto 21 subiu?",
    "O cartão do apto 32 está bloqueado?",
    "Teve algum problema este mês?",
    "Qual a previsão de demanda para os próximos dias?",
    "Qual o melhor horário para carregar por 4 horas?",
    "Me dê um resumo do condomínio em setembro"
)

# ----- PROGRAMA PRINCIPAL
controle_sessao.preparar_sistema()
if not os.path.exists(PASTA):
    os.mkdir(PASTA)

# 1) graficos da previsao de demanda
previsao = controle_ia.treinar()
serie = controle_ia.serie_diaria()
graficos.salvar(graficos.grafico_consumo_diario(serie["datas"], serie["kwh"]),
                PASTA + "/consumo_diario.png")
graficos.salvar(graficos.grafico_curva_de_carga(previsao["curva_de_carga"], previsao["limite_quadro_kw"]),
                PASTA + "/curva_carga_horaria.png")
graficos.salvar(graficos.grafico_previsao_vs_real(previsao["datas_teste"], previsao["y_teste"],
                                                  previsao["y_previsto"]),
                PASTA + "/previsao_vs_real.png")
graficos.salvar(graficos.grafico_residuos(previsao["y_teste"], previsao["y_previsto"]),
                PASTA + "/residuos.png")
graficos.salvar(graficos.grafico_previsao_7_dias(previsao["previsao_7_dias"]),
                PASTA + "/previsao_7_dias.png")
graficos.salvar(graficos.grafico_limite_dos_dados(previsao["analise_do_limite"], controle_ia.meta_de_precisao()),
                PASTA + "/limite_dos_dados.png")

# 2) ranking de consumo e curva de potencia de uma sessao
painel = controle_gestor.painel_do_mes(MES_DO_RANKING)
graficos.salvar(graficos.grafico_ranking(painel["ranking"], MES_DO_RANKING),
                PASTA + "/ranking_unidades.png")
leituras = telemetria.simular_leituras(180, 26, -1)
graficos.salvar(graficos.grafico_potencia_da_sessao(leituras), PASTA + "/potencia_sessao.png")

# 3) conversa de demonstracao com o Sindico Virtual
with open(PASTA + "/demo_sindico_virtual.txt", "w", encoding="utf-8") as arq:
    arq.write(f"SÍNDICO VIRTUAL - conversa de demonstração [modo: {controle_ia.modo_da_ia()}]\n\n")
    for pergunta in PERGUNTAS:
        resultado = controle_ia.perguntar(pergunta, 0, [])
        arq.write(f"Pergunta: {pergunta}\n")
        arq.write(f"Intenção: {resultado['intencao']}\n")
        arq.write(f"Resposta: {resultado['resposta']}\n\n")
print(f"Conversa salva: {PASTA}/demo_sindico_virtual.txt")
