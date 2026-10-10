"""
Autor.....: Equipe EV ChargeOps (RM573133, RM571998, RM571913, RM568867, RM574003)
Assunto...: VIEW - interface web (Streamlit)
Problema..: Painel web do gestor e interface do morador previstos na Sprint 1.
            Cada pagina e uma funcao que chama os controllers e desenha o resultado.
            Nenhuma regra de negocio fica nesta camada.
"""
import pandas as pd
import streamlit as st

from controller import controle_gestor
from controller import controle_ia
from controller import controle_morador
from controller import controle_sessao
from formato import decimal, percentual, reais, sim_ou_nao
from view import graficos

# ----- CONSTANTES
PAGINAS = ("Início", "Painel do Gestor", "Interface do Morador", "Simulador de Rateio",
           "Sessão de Recarga", "Previsão de Demanda", "Síndico Virtual")
ETAPAS_DO_FLUXO = (
    ("RFID", "O morador aproxima o cartão e o sistema autoriza ou recusa."),
    ("Sessão iniciada", "O carregador GoodWe HCA G2 libera a energia."),
    ("Energia medida (kWh)", "Tensão e corrente viram potência e energia."),
    ("Associação à unidade", "Cartão, usuário e apartamento são ligados."),
    ("Rateio", "kWh x tarifa, com ou sem taxa administrativa."),
    ("Painel e Insights", "Gestor e morador acompanham e a IA alerta.")
)


# ----- SUBALGORITMOS AUXILIARES
def sem_formula(mensagem: str) -> str:
    # o Streamlit interpreta o que fica entre dois cifroes como formula matematica;
    # a barra invertida faz o "R$" aparecer como texto comum
    return mensagem.replace("$", "\\$")


def mostrar_tabela(linhas: list, colunas: list) -> None:
    # colunas: lista de tuplas (campo, titulo, tipo); o tipo define a formatacao
    tabela = {}
    for coluna in colunas:
        valores = []
        for linha in linhas:
            valor = linha[coluna[0]]
            match coluna[2]:
                case "reais":
                    valor = reais(valor)
                case "kwh":
                    valor = decimal(valor, 2)
                case "pct":
                    valor = percentual(valor, 1)
                case "bool":
                    valor = sim_ou_nao(valor)
                case _:
                    valor = str(valor)
            valores.append(valor)
        tabela[coluna[1]] = valores
    st.dataframe(pd.DataFrame(tabela), hide_index=True)


def mostrar_grafico(fig) -> None:
    st.pyplot(fig)
    graficos.fechar(fig)


def escolher_mes(rotulo: str, chave: str) -> str:
    meses = controle_gestor.meses_disponiveis()
    return st.selectbox(rotulo, meses, index=len(meses) - 1, key=chave)


def mostrar_alertas(alertas: list) -> None:
    if len(alertas) == 0:
        st.success("Nenhum alerta no momento.")
    for alerta in alertas:
        texto = sem_formula(f"**[{alerta['prioridade']}] {alerta['tipo']}** - {alerta['mensagem']}")
        if alerta["prioridade"] >= 8:
            st.error(texto)
        elif alerta["prioridade"] >= 5:
            st.warning(texto)
        else:
            st.info(texto)


def mostrar_auditoria(auditoria: dict) -> None:
    # mesma composicao para gestor e morador (auditoria compartilhada)
    fatura = auditoria["fatura"]
    st.markdown(f"**Fatura {fatura['id']}** - {auditoria['unidade']['name']} - {fatura['month']}")
    mostrar_tabela(auditoria["detalhe"], [("sessao", "Sessão", "texto"), ("inicio", "Início", "texto"),
                                          ("fim", "Fim", "texto"), ("cartao", "Cartão", "texto"),
                                          ("carregador", "Carregador", "texto"), ("kwh", "kWh", "kwh"),
                                          ("valor", "Valor", "reais"),
                                          ("interrompida", "Interrompida", "bool")])
    colunas = st.columns(4)
    colunas[0].metric("Energia", decimal(fatura["total_kwh"], 2) + " kWh")
    colunas[1].metric("Tarifa", reais(fatura["tarifa"]) + "/kWh")
    if fatura["taxa_admin"] > 0:
        colunas[2].metric("Taxa administrativa", reais(fatura["taxa_admin"]))
    else:
        colunas[2].metric("Taxa administrativa", "sem taxa")
    colunas[3].metric("Total", reais(fatura["total_value"]))
    st.caption(f"Situação: {fatura['status']} | fechado em {fatura['fechado_em']} | "
               f"vencimento {fatura['vencimento']}")
    if auditoria["confere"]:
        st.success(sem_formula(f"Auditoria: o total recalculado ({reais(auditoria['valor_recalculado'])}) "
                               f"confere com as sessões registradas."))
    else:
        st.error(sem_formula(f"Auditoria: divergência. Recalculado {reais(auditoria['valor_recalculado'])}, "
                             f"gravado {reais(fatura['total_value'])}."))


# ----- PAGINA: INICIO
def pagina_inicio() -> None:
    st.title("EV ChargeOps")
    st.subheader("Gestão inteligente de recargas compartilhadas")
    st.write("Transformamos cada sessão de recarga em uma cobrança justa, auditável e inteligente.")

    st.markdown("#### Da identificação do usuário à cobrança mensal")
    colunas = st.columns(6)
    for i in range(len(ETAPAS_DO_FLUXO)):
        colunas[i].markdown(f"**{i + 1}. {ETAPAS_DO_FLUXO[i][0]}**")
        colunas[i].caption(ETAPAS_DO_FLUXO[i][1])

    meses = controle_gestor.meses_disponiveis()
    mes = meses[len(meses) - 1]
    painel = controle_gestor.painel_do_mes(mes)
    resumo = painel["resumo"]
    st.markdown(f"#### Mês atual: {mes}")
    colunas = st.columns(4)
    colunas[0].metric("Sessões", resumo["sessoes"])
    colunas[1].metric("Energia entregue", decimal(resumo["total_kwh"], 1) + " kWh")
    # mes fechado mostra o valor faturado; mes aberto, a previa sem taxa
    if resumo["fechado"]:
        colunas[2].metric("Faturado", reais(resumo["valor_faturado"]))
    else:
        colunas[2].metric("Consumo a ratear",
                          reais(controle_gestor.total_da_coluna(painel["previa"], "total_sem_taxa")))
    colunas[3].metric("Unidades com fatura vencida", painel["unidades_inadimplentes"])

    st.markdown("#### Alertas")
    mostrar_alertas(painel["alertas"])

    st.markdown("#### Indicadores definidos na Sprint 1")
    mostrar_tabela(controle_gestor.indicadores_da_sprint1(),
                   [("indicador", "Indicador", "texto"), ("meta", "Meta", "texto"),
                    ("resultado", "Resultado no protótipo", "texto"), ("como", "Como medimos", "texto")])
    st.caption(f"Síndico Virtual em modo: {controle_ia.modo_da_ia()}. "
               f"Arquitetura: GoodWe HCA G2 (simulado) > Gateway local / SEMS+ > Camada EV ChargeOps > "
               f"Regras e IA > Interfaces do gestor e do morador.")


# ----- PAGINA: PAINEL DO GESTOR
def aba_consolidado(mes: str) -> None:
    painel = controle_gestor.painel_do_mes(mes)
    config = painel["config"]

    # mes aberto: o gestor escolhe fechar COM taxa ou SEM taxa
    if not painel["resumo"]["fechado"]:
        st.info(f"O mês {mes} ainda está aberto. A prévia abaixo mostra as duas opções de fechamento.")
        opcoes = ("Sem taxa administrativa", f"Com taxa administrativa de {reais(config['taxa_admin'])}")
        padrao = 0
        if config["cobrar_taxa"]:
            padrao = 1
        escolha = st.radio("Opção de fechamento", opcoes, index=padrao, horizontal=True)
        if st.button("Fechar mês"):
            resultado = controle_gestor.fechar_mes(mes, escolha == opcoes[1])
            if resultado["ok"]:
                st.success(sem_formula(resultado["mensagem"]))
            else:
                st.warning(sem_formula(resultado["mensagem"]))
            painel = controle_gestor.painel_do_mes(mes)

    resumo = painel["resumo"]
    colunas = st.columns(4)
    colunas[0].metric("Sessões", resumo["sessoes"])
    colunas[1].metric("Energia entregue", decimal(resumo["total_kwh"], 1) + " kWh")
    if resumo["fechado"]:
        colunas[2].metric("Faturado", reais(resumo["valor_faturado"]))
        colunas[3].metric("Pendente", reais(resumo["valor_pendente"]))
        st.markdown("**Consolidado mensal** (uma linha por unidade)")
        mostrar_tabela(painel["consolidado"], [("fatura", "Fatura", "texto"), ("unidade", "Unidade", "texto"),
                                               ("bloco", "Bloco", "texto"), ("sessoes", "Sessões", "texto"),
                                               ("kwh", "kWh", "kwh"), ("tarifa", "Tarifa", "reais"),
                                               ("taxa", "Taxa", "reais"), ("total", "Total", "reais"),
                                               ("status", "Status", "texto"),
                                               ("vencimento", "Vencimento", "texto")])
    else:
        previa = painel["previa"]
        colunas[2].metric("Total sem taxa", reais(controle_gestor.total_da_coluna(previa, "total_sem_taxa")))
        colunas[3].metric("Total com taxa", reais(controle_gestor.total_da_coluna(previa, "total_com_taxa")))
        st.markdown("**Prévia do mês**")
        mostrar_tabela(previa, [("unidade", "Unidade", "texto"), ("bloco", "Bloco", "texto"),
                                ("sessoes", "Sessões", "texto"), ("kwh", "kWh", "kwh"),
                                ("total_sem_taxa", "Total sem taxa", "reais"),
                                ("total_com_taxa", "Total com taxa", "reais")])

    mostrar_grafico(graficos.grafico_ranking(painel["ranking"], mes))
    for codigo in resumo["kwh_por_carregador"]:
        st.caption(f"Carregador {codigo}: {decimal(resumo['kwh_por_carregador'][codigo], 1)} kWh, "
                   f"ocioso em {percentual(resumo['ociosidade'][codigo], 1)} do mês.")


def aba_pagamentos() -> None:
    pendentes = controle_gestor.faturas_pendentes()
    if len(pendentes) == 0:
        st.success("Não há faturas pendentes.")
    else:
        rotulos = []
        for linha in pendentes:
            rotulos.append(f"{linha['fatura']} | {linha['unidade']} | {linha['mes']} | "
                           f"{reais(linha['total'])} | vence em {linha['vencimento']}")
        escolha = st.selectbox("Fatura pendente", rotulos)
        if st.button("Registrar pagamento"):
            numero = int(escolha.split(" | ")[0])
            resultado = controle_gestor.registrar_pagamento(numero)
            if resultado["ok"]:
                st.success(sem_formula(resultado["mensagem"]))
            else:
                st.warning(sem_formula(resultado["mensagem"]))

    st.markdown("**Bloqueio de inadimplentes**")
    st.write("Regra: fatura pendente e vencida bloqueia todos os cartões RFID da unidade.")
    if st.button("Atualizar bloqueios"):
        resultado = controle_gestor.atualizar_bloqueios()
        st.info(f"{resultado['bloqueados']} cartão(ões) bloqueado(s) e "
                f"{resultado['desbloqueados']} desbloqueado(s) agora.")
    mostrar_tabela(controle_gestor.listar_cadastros()["cartoes"],
                   [("uid", "UID", "texto"), ("usuario", "Usuário", "texto"),
                    ("unidade", "Unidade", "texto"), ("situacao", "Situação", "texto")])


def aba_auditoria(mes: str) -> None:
    consolidado = controle_gestor.consolidado_do_mes(mes)
    if len(consolidado) == 0:
        st.info("O mês ainda não foi fechado; não há faturas para auditar.")
        return
    rotulos = []
    for linha in consolidado:
        rotulos.append(f"{linha['fatura']} | {linha['unidade']} | {reais(linha['total'])}")
    escolha = st.selectbox("Fatura", rotulos)
    mostrar_auditoria(controle_gestor.auditar(int(escolha.split(" | ")[0])))


def aba_sems(mes: str) -> None:
    st.write("Compara a energia das sessões com o total diário exportado do SEMS Portal. "
             "Diferença relativa acima do limite configurado é marcada como divergente.")
    mostrar_tabela(controle_gestor.conciliacao(mes),
                   [("data", "Data", "texto"), ("carregador", "Carregador", "texto"),
                    ("kwh_sessoes", "Sessões (kWh)", "kwh"), ("kwh_sems", "SEMS (kWh)", "kwh"),
                    ("erro_absoluto", "Erro absoluto", "kwh"), ("erro_relativo", "Erro relativo", "pct"),
                    ("divergente", "Divergente", "bool")])


def aba_configuracao() -> None:
    config = controle_gestor.configuracao()
    st.write("Tarifa única por kWh e taxa administrativa opcional, como definido na Sprint 1.")
    tarifa = st.number_input("Tarifa (R$/kWh)", value=float(config["tarifa_kwh"]), min_value=0.0, step=0.01)
    taxa = st.number_input("Taxa administrativa (R$ por fatura)", value=float(config["taxa_admin"]),
                           min_value=0.0, step=0.50)
    cobrar = st.checkbox("Fechar os meses COM taxa por padrão", value=config["cobrar_taxa"])
    if st.button("Gravar configuração"):
        resultado = controle_gestor.alterar_configuracao(tarifa, taxa, cobrar)
        if resultado["ok"]:
            st.success(sem_formula(resultado["mensagem"]))
        else:
            st.warning(sem_formula(resultado["mensagem"]))


def pagina_gestor() -> None:
    st.title("Painel do Gestor")
    mes = escolher_mes("Mês de referência", "mes_gestor")
    abas = st.tabs(["Consolidado", "Alertas", "Pagamentos e bloqueios", "Auditoria",
                    "Conciliação SEMS", "Tarifa e taxa"])
    with abas[0]:
        aba_consolidado(mes)
    with abas[1]:
        mostrar_alertas(controle_gestor.listar_alertas(mes))
    with abas[2]:
        aba_pagamentos()
    with abas[3]:
        aba_auditoria(mes)
    with abas[4]:
        aba_sems(mes)
    with abas[5]:
        aba_configuracao()


# ----- PAGINA: INTERFACE DO MORADOR
def pagina_morador() -> None:
    st.title("Interface do Morador")
    unidades = controle_morador.listar_unidades()
    nomes = []
    for unidade in unidades:
        nomes.append(f"{unidade['name']} / {unidade['block']}")
    escolha = st.selectbox("Minha unidade", nomes)
    unidade = unidades[nomes.index(escolha)]
    mes = escolher_mes("Mês", "mes_morador")
    painel = controle_morador.painel_da_unidade(unidade["id"], mes)

    colunas = st.columns(3)
    colunas[0].metric("Recargas no mês", len(painel["sessoes"]))
    colunas[1].metric("Energia", decimal(painel["kwh"], 2) + " kWh")
    colunas[2].metric("Consumo", reais(painel["consumo_rs"]))
    if painel["inadimplente"]:
        st.error("Há fatura vencida. Os cartões da unidade estão bloqueados até o pagamento.")

    st.markdown("#### Sessões de recarga")
    mostrar_tabela(painel["sessoes"], [("sessao", "Sessão", "texto"), ("inicio", "Início", "texto"),
                                       ("fim", "Fim", "texto"), ("cartao", "Cartão", "texto"),
                                       ("kwh", "kWh", "kwh"), ("valor", "Valor", "reais"),
                                       ("interrompida", "Interrompida", "bool")])

    st.markdown("#### Fatura do mês")
    if painel["tem_fatura"]:
        mostrar_auditoria(painel["auditoria"])
    else:
        st.info("O mês ainda não foi fechado. O valor acima é o consumo acumulado até agora.")

    st.markdown("#### Meus cartões RFID")
    mostrar_tabela(painel["cartoes"], [("uid", "UID", "texto"), ("usuario", "Usuário", "texto"),
                                       ("situacao", "Situação", "texto")])

    st.markdown("#### Melhor horário para recarregar hoje")
    duracao = st.number_input("Duração da recarga (horas)", min_value=1, max_value=8, value=3, step=1)
    janela = controle_ia.janela_sugerida(int(duracao))
    if janela == {}:
        st.warning("O modelo de previsão ainda não foi treinado.")
    else:
        colunas = st.columns(3)
        colunas[0].metric("À noite", f"{janela['noite_inicio']}h às {janela['noite_fim']}h")
        colunas[1].metric("Durante o dia", f"{janela['dia_inicio']}h às {janela['dia_fim']}h")
        colunas[2].metric("Evite", f"por volta das {janela['hora_pico']}h")
        st.caption(f"Hoje é {janela['dia_semana']}. Sugestão calculada pela curva de carga histórica do condomínio.")


# ----- PAGINA: SIMULADOR DE RATEIO
def pagina_simulador() -> None:
    st.title("Simulador de Rateio")
    st.markdown("**Fatura = (Σ kWh das sessões × Tarifa) + Taxa Administrativa**")
    config = controle_gestor.configuracao()
    cenarios = controle_gestor.cenarios_de_rateio()
    nomes = ["Valores da configuração atual"]
    for cenario in cenarios:
        nomes.append(cenario["nome"])
    escolha = st.selectbox("Cenário", nomes)
    kwh = 50.0
    tarifa = float(config["tarifa_kwh"])
    taxa = float(config["taxa_admin"])
    for cenario in cenarios:
        if cenario["nome"] == escolha:
            kwh = cenario["kwh"]
            tarifa = cenario["tarifa"]
            taxa = cenario["taxa"]
    # a chave muda com o cenario para os campos assumirem os novos valores
    colunas = st.columns(3)
    kwh = colunas[0].number_input("Energia das sessões (kWh)", value=kwh, min_value=0.0, step=0.1,
                                  key="kwh_" + escolha)
    tarifa = colunas[1].number_input("Tarifa (R$/kWh)", value=tarifa, min_value=0.0, step=0.01,
                                     key="tarifa_" + escolha)
    taxa = colunas[2].number_input("Taxa administrativa (R$)", value=taxa, min_value=0.0, step=0.50,
                                   key="taxa_" + escolha)

    simulacao = controle_gestor.simular_rateio(kwh, tarifa, taxa)
    st.write(sem_formula(f"Consumo: {decimal(kwh, 2)} kWh × {reais(tarifa)} = {reais(simulacao['consumo'])}"))
    colunas = st.columns(2)
    colunas[0].metric("Opção SEM taxa", reais(simulacao["total_sem_taxa"]))
    colunas[1].metric("Opção COM taxa", reais(simulacao["total_com_taxa"]))

    st.markdown("#### Regras do rateio")
    st.write("1. Sessão interrompida: cobra-se apenas o kWh validado até a queda.")
    st.write("2. Vários cartões RFID (até 10) são somados na mesma unidade.")
    st.write("3. Unidade sem recarga no mês não tem consumo a pagar e aparece como isenta.")
    st.write("4. Fatura vencida bloqueia os cartões da unidade até o pagamento.")


# ----- PAGINA: SESSAO DE RECARGA
def pagina_sessao() -> None:
    st.title("Sessão de Recarga")
    st.write("Simulação do carregador GoodWe GW7K-HCA: autenticação por RFID, leituras de tensão e "
             "corrente a cada minuto e energia acumulada.")
    opcoes = controle_sessao.opcoes_de_sessao()
    codigos = []
    for carregador in opcoes["carregadores"]:
        codigos.append(f"{carregador['id']} | {carregador['location']}")
    colunas = st.columns(3)
    cartao = colunas[0].selectbox("Cartão RFID", opcoes["rotulos"])
    carregador = colunas[1].selectbox("Carregador", codigos)
    duracao = colunas[2].number_input("Duração planejada (min)", min_value=10, max_value=480, value=120, step=10)
    interromper = st.checkbox("Simular queda de energia no meio da sessão")

    if st.button("Iniciar sessão"):
        # guarda o resultado para continuar na tela depois da proxima reexecucao
        st.session_state["ultima_sessao"] = controle_sessao.iniciar_sessao(
            cartao.split(" | ")[0], carregador.split(" | ")[0], int(duracao), interromper)

    if "ultima_sessao" in st.session_state:
        resultado = st.session_state["ultima_sessao"]
        if not resultado["valido"]:
            st.warning(sem_formula(resultado["mensagem"]))
            return
        st.markdown("#### Fluxo da sessão")
        for etapa in resultado["etapas"]:
            texto = sem_formula(f"**{etapa['numero']}. {etapa['nome']}** - {etapa['detalhe']}")
            if resultado["autorizado"]:
                st.success(texto)
            else:
                st.error(texto)
        if resultado["autorizado"]:
            st.markdown("#### Potência medida (kW)")
            potencias = []
            for leitura in resultado["leituras"]:
                potencias.append(leitura["potencia_kw"])
            st.line_chart(pd.DataFrame({"kW": potencias}))
            sessao = resultado["sessao"]
            st.caption(f"Sessão {sessao['id']} gravada: {sessao['start_time']} a {sessao['end_time']}, "
                       f"{decimal(sessao['kwh_delivered'], 2)} kWh.")


# ----- PAGINA: PREVISAO DE DEMANDA
def pagina_previsao() -> None:
    st.title("Previsão de Demanda Coletiva")
    st.write("Regressão sobre a série diária de energia (dia da semana, tendência, ontem e média de 7 dias) "
             "e regressão logística para o risco de sobrecarga do quadro elétrico.")
    if st.button("Treinar e avaliar o modelo"):
        controle_ia.treinar()
        st.success("Modelo treinado com o histórico atual.")
    previsao = controle_ia.previsao_atual()
    if previsao == {}:
        st.warning("O modelo ainda não foi treinado.")
        return

    metricas = previsao["metricas"]
    colunas = st.columns(4)
    colunas[0].metric("Modelo escolhido", previsao["modelo_escolhido"])
    colunas[1].metric("R²", decimal(metricas["r2"], 3))
    colunas[2].metric("MAE", decimal(metricas["mae"], 1) + " kWh/dia")
    colunas[3].metric("Precisão estimada", percentual(previsao["precisao_estimada"], 1))
    st.caption(f"Histórico de {previsao['dias_de_historico']} dias: {previsao['dias_treino']} de treino "
               f"(passado) e {previsao['dias_teste']} de teste (futuro). Treinado em {previsao['gerado_em']}.")

    linhas = []
    for nome in ("Regressão Linear", "Ridge"):
        if nome == "Ridge":
            m = previsao["metricas_ridge"]
            rotulo = f"Ridge (alpha = {previsao['melhor_alpha']})"
        else:
            m = previsao["metricas_linear"]
            rotulo = nome
        linhas.append({"modelo": rotulo, "mae": m["mae"], "rmse": m["rmse"],
                       "r2": decimal(m["r2"], 3), "erro": m["erro_relativo"]})
    mostrar_tabela(linhas, [("modelo", "Modelo", "texto"), ("mae", "MAE (kWh)", "kwh"),
                            ("rmse", "RMSE (kWh)", "kwh"), ("r2", "R²", "texto"),
                            ("erro", "Erro relativo", "pct")])

    mostrar_grafico(graficos.grafico_previsao_vs_real(previsao["datas_teste"], previsao["y_teste"],
                                                      previsao["y_previsto"]))
    mostrar_grafico(graficos.grafico_curva_de_carga(previsao["curva_de_carga"],
                                                    previsao["limite_quadro_kw"]))

    if "analise_do_limite" in previsao:
        limite = previsao["analise_do_limite"]
        meta = controle_ia.meta_de_precisao()
        st.markdown("#### De onde vem o erro")
        st.write(f"Precisão no período de teste, comparada com a meta de {percentual(meta, 0)} da Sprint 1. "
                 f"O modelo já está no teto do que o calendário explica. O erro que sobra é a variação de quem "
                 f"recarrega e de quanto recarrega em cada dia.")
        colunas = st.columns(4)
        colunas[0].metric("Modelo, por dia", percentual(limite["modelo_por_dia"], 1))
        colunas[1].metric("Teto do calendário", percentual(limite["teto_do_calendario"], 1))
        colunas[2].metric("Sabendo as recargas do dia", percentual(limite["sabendo_as_recargas"], 1))
        colunas[3].metric(f"Modelo, por semana ({limite['semanas_de_teste']} semanas)",
                          percentual(limite["modelo_por_semana"], 1))
        mostrar_grafico(graficos.grafico_limite_dos_dados(limite, meta))
        st.caption("Teto do calendário: média real de cada dia da semana, calculada com o histórico inteiro. "
                   "Sabendo as recargas do dia: quantidade de recargas conhecida de antemão, como em um "
                   "agendamento. Com dados reais chegando continuamente, o modelo é treinado de novo com mais "
                   "histórico e pode usar esse tipo de informação.")

    st.markdown("#### Próximos 7 dias")
    mostrar_grafico(graficos.grafico_previsao_7_dias(previsao["previsao_7_dias"]))
    mostrar_tabela(previsao["previsao_7_dias"],
                   [("data", "Data", "texto"), ("dia_semana", "Dia", "texto"),
                    ("kwh_previsto", "kWh previstos", "kwh"),
                    ("prob_sobrecarga", "Probabilidade de sobrecarga", "pct"),
                    ("risco_alto", "Risco alto", "bool")])

    risco = previsao["risco"]
    if risco["treinado"]:
        st.markdown(f"#### Risco de sobrecarga (limite de {decimal(previsao['limite_quadro_kw'], 0)} kW)")
        colunas = st.columns(4)
        colunas[0].metric("Acurácia", percentual(risco["acuracia"], 1))
        colunas[1].metric("Precisão", percentual(risco["precisao"], 1))
        colunas[2].metric("Recall", percentual(risco["recall"], 1))
        colunas[3].metric("F1-score", decimal(risco["f1"], 3))
        st.caption(f"{risco['dias_com_sobrecarga']} dias com sobrecarga em {risco['amostras']} dias analisados. "
                   f"Matriz de confusão: {risco['matriz_confusao']}.")


# ----- PAGINA: SINDICO VIRTUAL
def pagina_sindico() -> None:
    st.title("Síndico Virtual")
    st.caption(f"Modo: {controle_ia.modo_da_ia()}. As respostas usam somente os dados do sistema.")
    unidades = controle_morador.listar_unidades()
    nomes = ["Gestor (todas as unidades)"]
    for unidade in unidades:
        nomes.append(unidade["name"])
    quem = st.selectbox("Quem está perguntando?", nomes)
    unit_id = 0
    for unidade in unidades:
        if unidade["name"] == quem:
            unit_id = unidade["id"]

    # historico da conversa guardado entre as reexecucoes da pagina
    if "msgs" not in st.session_state:
        st.session_state["msgs"] = []

    pergunta = ""
    colunas = st.columns(3)
    sugestoes = controle_ia.perguntas_sugeridas()
    for i in range(len(sugestoes)):
        if colunas[i].button(sugestoes[i]):
            pergunta = sugestoes[i]
    digitada = st.chat_input("Pergunte sobre consumo, cobranças, anomalias ou previsão")
    if digitada:
        pergunta = digitada

    if pergunta != "":
        resultado = controle_ia.perguntar(pergunta, unit_id, st.session_state["msgs"])
        st.session_state["msgs"].append({"role": "user", "content": pergunta})
        st.session_state["msgs"].append({"role": "assistant", "content": resultado["resposta"],
                                         "modo": resultado["modo"]})

    if len(st.session_state["msgs"]) > 0:
        if st.button("Limpar conversa"):
            st.session_state["msgs"] = []
    for mensagem in st.session_state["msgs"]:
        caixa = st.chat_message(mensagem["role"])
        caixa.write(sem_formula(mensagem["content"]))
        # mostra se a resposta veio do LLM ou do modo simulado
        if "modo" in mensagem:
            caixa.caption("modo: " + mensagem["modo"])


# ----- SUBALGORITMO PRINCIPAL
def mostrar_aplicacao() -> None:
    st.set_page_config(page_title="EV ChargeOps", layout="wide")
    controle_sessao.preparar_sistema()
    st.sidebar.title("EV ChargeOps")
    st.sidebar.caption("GoodWe + FIAP | Enterprise Challenge 2026")
    pagina = st.sidebar.radio("Navegação", PAGINAS)
    match pagina:
        case "Início":
            pagina_inicio()
        case "Painel do Gestor":
            pagina_gestor()
        case "Interface do Morador":
            pagina_morador()
        case "Simulador de Rateio":
            pagina_simulador()
        case "Sessão de Recarga":
            pagina_sessao()
        case "Previsão de Demanda":
            pagina_previsao()
        case "Síndico Virtual":
            pagina_sindico()
