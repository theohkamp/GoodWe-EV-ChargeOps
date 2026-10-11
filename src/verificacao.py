"""
Autor.....: Equipe EV ChargeOps (RM573133, RM571998, RM571913, RM568867, RM574003)
Assunto...: Plano de testes do protótipo (esperado x obtido)
Problema..: Conferir as regras da Sprint 1 com cenarios de resultado conhecido.
            Executar a partir da raiz do repositorio:  python src/verificacao.py
            ATENCAO: o script recria a base de demonstracao no inicio e no fim.
"""
from controller import controle_gestor
from controller import controle_sessao
from model import alertas
from model import dados
from model import ia_previsao
from model import rateio
from model import sindico_virtual
from model import telemetria

# ----- VARIAVEIS GLOBAIS DE CONTAGEM
total_ok = 0
total_falhas = 0


# ----- SUBALGORITMOS
def confere(descricao: str, esperado, obtido) -> None:
    global total_ok, total_falhas
    if esperado == obtido:
        situacao = "OK"
        total_ok += 1
    else:
        situacao = "FALHOU"
        total_falhas += 1
    print(f"[{situacao}] {descricao}")
    print(f"        esperado: {esperado} | obtido: {obtido}")


def secao(texto: str) -> None:
    print("\n" + "-" * 78)
    print(texto)
    print("-" * 78)


# ----- PROGRAMA PRINCIPAL
print("Recriando a base de demonstração...")
controle_sessao.recriar_base()

secao("1. FÓRMULA DO RATEIO: Fatura = soma(E_sessao x T) + Tx_admin")
confere("120 kWh x R$ 0,95 sem taxa (exemplo da Sprint 1)", 114.0, rateio.calcula_total(120.0, 0.95, 0.0))
confere("12,4 kWh x R$ 0,95 + taxa de R$ 2,00 (exemplo do pitch)", 13.78, rateio.calcula_total(12.4, 0.95, 2.0))
opcoes = rateio.comparar_com_e_sem_taxa(50.0, 0.95, 2.0)
confere("50 kWh: opção SEM taxa", 47.5, opcoes["total_sem_taxa"])
confere("50 kWh: opção COM taxa", 49.5, opcoes["total_com_taxa"])

secao("2. REGISTROS DE EXEMPLO DO README DA SPRINT 1")
sessao = dados.buscar_registro("sessions", "id", 5001)
confere("sessão 5001: cartão", "A1B2C3D4", sessao["rfid_uid"])
confere("sessão 5001: carregador", "GW-001", sessao["charger_id"])
confere("sessão 5001: início", "2026-06-18 19:00", sessao["start_time"])
confere("sessão 5001: fim", "2026-06-18 22:30", sessao["end_time"])
confere("sessão 5001: energia (kWh)", 21.5, sessao["kwh_delivered"])
unidade = dados.unidade_do_cartao("A1B2C3D4")
confere("cartão A1B2C3D4 pertence a", "Apto 42 / Torre A", unidade["name"] + " / " + unidade["block"])
fatura = dados.buscar_registro("invoices", "id", 9001)
confere("fatura 9001: unidade e mês", "1 / 06-2026", str(fatura["unit_id"]) + " / " + fatura["month"])
confere("fatura 9001: total_kwh", 120.0, fatura["total_kwh"])
confere("fatura 9001: total_value", 114.0, fatura["total_value"])
calculo = rateio.calcular_fatura(1, "06-2026", 0.95, 0.0, False)
confere("fatura 9001 no fechamento: status", "PENDING", calculo["status"])

secao("3. VÁRIOS CARTÕES NA MESMA UNIDADE")
cartoes_usados = []
for linha in calculo["detalhe"]:
    if linha["cartao"] not in cartoes_usados:
        cartoes_usados.append(linha["cartao"])
confere("cartões diferentes somados na fatura do Apto 42 em junho", 2, len(cartoes_usados))
confere("sessões somadas", 6, calculo["sessoes"])

secao("4. INTEGRAÇÃO DA ENERGIA (MÉTODO DE EULER)")
energia = 0.0
for minuto in range(60):
    energia = telemetria.passo_de_euler(energia, 7.0, 1 / 60)
confere("60 leituras de 7,0 kW, uma por minuto (kWh)", 7.0, round(energia, 2))

secao("5. SESSÃO INTERROMPIDA COBRA SÓ O VALIDADO")
resultado = telemetria.simular_sessao("C3D4E5F6", "GW-002", telemetria.proximo_horario_livre("GW-002"), 120, True)
gravada = resultado["sessao"]
inicio = dados.texto_para_data(gravada["start_time"])
fim = dados.texto_para_data(gravada["end_time"])
confere("duração registrada (min) de uma sessão de 120 min cortada na metade", 60,
        int((fim - inicio).total_seconds() / 60))
confere("sessão marcada como interrompida", True, gravada["interrompida"])
confere("as seis etapas do fluxo foram percorridas", 6, len(resultado["etapas"]))

secao("6. UNIDADE SEM RECARGA NO MÊS")
isenta = dados.fatura_da_unidade(7, "09-2026")
confere("Apto 12 em 09-2026: status", "ISENTO", isenta["status"])
confere("Apto 12 em 09-2026: valor", 0.0, isenta["total_value"])

secao("7. INADIMPLÊNCIA, BLOQUEIO E DESBLOQUEIO")
confere("Apto 32 com fatura vencida", True, rateio.unidade_inadimplente(3, "2026-10-09"))
cartao = dados.buscar_registro("rfid_cards", "uid", "D4E5F6A7")
confere("cartão D4E5F6A7 ativo", False, cartao["status"])
tentativa = telemetria.autorizar_cartao("D4E5F6A7", "GW-001", telemetria.proximo_horario_livre("GW-001"))
confere("autorização do cartão bloqueado", "cartão bloqueado por fatura vencida", tentativa["motivo"])
for pendente in controle_gestor.faturas_pendentes():
    if pendente["unidade"] == "Apto 32":
        rateio.registrar_pagamento(pendente["fatura"], "2026-10-09")
rateio.atualizar_bloqueios("2026-10-09")
tentativa = telemetria.autorizar_cartao("D4E5F6A7", "GW-001", telemetria.proximo_horario_livre("GW-001"))
confere("autorização depois do pagamento", "Accepted", tentativa["motivo"])

secao("8. FECHAMENTO COM TAXA E SEM TAXA")
previa = rateio.calcular_fatura(1, "10-2026", 0.95, 0.0, False)
fechamento = rateio.fechar_mes("10-2026", True, "2026-10-09")
confere("fechamento de 10-2026 COM taxa aceito", True, fechamento["ok"])
com_taxa = dados.fatura_da_unidade(1, "10-2026")
confere("taxa gravada na fatura do Apto 42", 2.0, com_taxa["taxa_admin"])
confere("total COM taxa = total SEM taxa + 2,00", round(previa["total_value"] + 2.0, 2), com_taxa["total_value"])
confere("junho foi fechado SEM taxa", 0.0, fatura["taxa_admin"])
confere("fechar o mesmo mês duas vezes é recusado", False, rateio.fechar_mes("10-2026", False, "2026-10-09")["ok"])

secao("9. CONSOLIDADO MENSAL E AUDITORIA")
consolidado = controle_gestor.consolidado_do_mes("06-2026")
confere("uma linha por unidade no consolidado", 8, len(consolidado))
soma = 0.0
for linha in consolidado:
    soma += linha["total"]
confere("total do consolidado = valor faturado do mês", rateio.resumo_do_mes("06-2026")["valor_faturado"],
        round(soma, 2))
confere("auditoria da fatura 9001 confere", True, rateio.auditar_fatura(9001)["confere"])
confere("indicador da Sprint 1: precisão do faturamento (todas as faturas conferem)", 1.0,
        rateio.conferir_faturas()["precisao"])
dados.executar("UPDATE invoices SET total_value = 150.0 WHERE id = 9001")
confere("auditoria acusa valor alterado à mão", False, rateio.auditar_fatura(9001)["confere"])

secao("10. LIMITE DE 10 CARTÕES POR UNIDADE")
aceitos = 0
for numero in range(12):
    if dados.cadastrar_cartao("TESTE" + str(numero), 105)["ok"]:
        aceitos += 1
confere("cartões aceitos para o Apto 31, que já tinha 1", 9, aceitos)

secao("11. FILA DE PRIORIDADE DOS ALERTAS (HEAP)")
heap = []
for prioridade in (5, 9, 2, 8):
    alertas.inserir_alerta(heap, prioridade, "TESTE", "alerta de teste")
ordem = []
for alerta in alertas.esvaziar_em_ordem(heap):
    ordem.append(alerta["prioridade"])
confere("ordem de saída do heap", [9, 8, 5, 2], ordem)

secao("12. CONCILIAÇÃO COM O SEMS PORTAL")
divergentes = 0
for mes in dados.meses_com_sessoes():
    for linha in telemetria.conciliar_sems(mes):
        if linha["divergente"]:
            divergentes += 1
confere("dias com diferença acima de 3% no histórico", 3, divergentes)

secao("13. INTELIGÊNCIA ARTIFICIAL")
previsao = ia_previsao.executar_previsao_completa()
confere("dias previstos", 7, len(previsao["previsao_7_dias"]))
confere("modelo de risco treinado", True, previsao["risco"]["treinado"])
limite = previsao["analise_do_limite"]
confere("análise do limite: precisão por dia igual à precisão estimada do modelo",
        previsao["precisao_estimada"], limite["modelo_por_dia"])
valores_validos = True
for chave in ("modelo_por_dia", "teto_do_calendario", "sabendo_as_recargas", "modelo_por_semana"):
    if limite[chave] < 0 or limite[chave] > 1:
        valores_validos = False
confere("análise do limite: as quatro precisões ficam entre 0 e 1", True, valores_validos)
confere("precisão de uma previsão perfeita", 1.0, ia_previsao.precisao_das_previsoes([10, 20, 30], [10, 20, 30]))
confere("precisão com erro de 10% em cada dia", 0.9,
        round(ia_previsao.precisao_das_previsoes([10, 20, 30], [11, 22, 33]), 2))
janela = ia_previsao.sugerir_janela(previsao["curva_de_carga"], 0, 3)
confere("janela noturna começa entre 18h e 23h", True, janela["noite_inicio"] >= 18 and janela["noite_inicio"] <= 23)
confere("janela diurna começa entre 6h e 17h", True, janela["dia_inicio"] >= 6 and janela["dia_inicio"] <= 17)
confere("intenção: 'Quanto o apto 42 consumiu em junho?'", "consumo_unidade",
        sindico_virtual.classificar_por_palavras("Quanto o apto 42 consumiu em junho?"))
confere("intenção: 'Qual o valor da fatura do apto 21?'", "fatura_unidade",
        sindico_virtual.classificar_por_palavras("Qual o valor da fatura do apto 21?"))
confere("intenção: 'Teve algum problema este mês?'", "anomalias",
        sindico_virtual.classificar_por_palavras("Teve algum problema este mês?"))
confere("unidade encontrada na pergunta", "Apto 42",
        sindico_virtual.encontrar_unidade("Quanto o apto 42 consumiu em junho?")["name"])

secao("RESULTADO")
print(f"Cenários OK.......: {total_ok}")
print(f"Cenários com falha: {total_falhas}")

print("\nRecriando a base de demonstração para deixar os dados limpos...")
controle_sessao.recriar_base()
