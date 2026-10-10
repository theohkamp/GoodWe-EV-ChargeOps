"""
Autor.....: Equipe EV ChargeOps (RM573133, RM571998, RM571913, RM568867, RM574003)
Assunto...: VIEW - interface de console (menus de terminal)
Problema..: Exibir menus, ler as escolhas do usuario e mostrar os resultados.
            Esta camada so conversa com os controllers; nenhuma regra de negocio aqui.
"""
from controller import controle_gestor
from controller import controle_ia
from controller import controle_morador
from controller import controle_sessao
from formato import decimal, reais, sim_ou_nao

# ----- CONSTANTES
LINHA = "-" * 78
LINHA_DUPLA = "=" * 78


# ----- SUBALGORITMOS AUXILIARES DE ENTRADA
def ler_inteiro(mensagem: str) -> int:
    texto = input(mensagem).strip()
    while not texto.isnumeric():
        print("***** Digite um número inteiro! *****")
        texto = input(mensagem).strip()
    return int(texto)


def numero_valido(texto: str) -> bool:
    # aceita "12", "12.4" ou "12,4"
    texto = texto.replace(",", ".")
    partes = texto.split(".")
    if len(partes) == 1:
        return partes[0].isnumeric()
    if len(partes) == 2:
        return partes[0].isnumeric() and partes[1].isnumeric()
    return False


def ler_decimal(mensagem: str) -> float:
    texto = input(mensagem).strip()
    while not numero_valido(texto):
        print("***** Digite um número, por exemplo 12,4 *****")
        texto = input(mensagem).strip()
    return float(texto.replace(",", "."))


def ler_sim_nao(mensagem: str) -> bool:
    resp = input(mensagem + " [S]im ou [N]ão: ").strip()
    while resp not in ("S", "s", "N", "n"):
        print("***** Opção inválida! Digite S ou N. *****")
        resp = input(mensagem + " [S]im ou [N]ão: ").strip()
    return resp == "S" or resp == "s"


# ----- SUBALGORITMOS AUXILIARES DE SAIDA
def titulo(texto: str) -> None:
    print("\n" + LINHA_DUPLA)
    print(texto)
    print(LINHA_DUPLA)


def mostrar_tabela(linhas: list, colunas: list) -> None:
    # colunas: lista de tuplas (campo do dicionario, titulo, largura)
    cabecalho = ""
    for coluna in colunas:
        cabecalho += coluna[1].ljust(coluna[2])
    print(cabecalho)
    print(LINHA)
    for linha in linhas:
        texto = ""
        for coluna in colunas:
            valor = linha[coluna[0]]
            if type(valor) == float:
                valor = decimal(valor, 2)
            elif type(valor) == bool:
                valor = sim_ou_nao(valor)
            texto += str(valor).ljust(coluna[2])
        print(texto)
    if len(linhas) == 0:
        print("(sem registros)")


def escolher_opcao(mensagem: str, opcoes: list) -> int:
    # mostra as opcoes numeradas e devolve a posicao escolhida (0 para a primeira)
    for i in range(len(opcoes)):
        print(f"  {i + 1} - {opcoes[i]}")
    numero = ler_inteiro(mensagem)
    while numero < 1 or numero > len(opcoes):
        print("***** Opção inválida! *****")
        numero = ler_inteiro(mensagem)
    return numero - 1


def escolher_mes() -> str:
    meses = controle_gestor.meses_disponiveis()
    print("\nMeses com sessões:")
    return meses[escolher_opcao("Mês desejado...: ", meses)]


def escolher_unidade() -> dict:
    unidades = controle_morador.listar_unidades()
    print("\nUnidades:")
    for unidade in unidades:
        print(f"  {unidade['id']} - {unidade['name']} / {unidade['block']}")
    numero = ler_inteiro("Id da unidade...: ")
    unidade = controle_morador.buscar_unidade(numero)
    while unidade == {}:
        print("***** Unidade não encontrada! *****")
        numero = ler_inteiro("Id da unidade...: ")
        unidade = controle_morador.buscar_unidade(numero)
    return unidade


def mostrar_alertas(alertas: list) -> None:
    print("\nALERTAS (do mais grave para o mais leve)")
    print(LINHA)
    for alerta in alertas:
        print(f"[{alerta['prioridade']}] {alerta['tipo']}: {alerta['mensagem']}")
    if len(alertas) == 0:
        print("(nenhum alerta)")


def mostrar_auditoria(auditoria: dict) -> None:
    # mesma composicao para gestor e morador (auditoria compartilhada)
    if not auditoria["encontrada"]:
        print("***** Fatura não encontrada! *****")
        return
    fatura = auditoria["fatura"]
    print(f"\nFATURA {fatura['id']} - {auditoria['unidade']['name']} - {fatura['month']}")
    mostrar_tabela(auditoria["detalhe"], [("sessao", "Sessão", 8), ("inicio", "Início", 18),
                                          ("cartao", "Cartão", 10), ("carregador", "Carreg.", 9),
                                          ("kwh", "kWh", 9), ("valor", "Valor R$", 10),
                                          ("interrompida", "Interrompida", 12)])
    print(LINHA)
    print(f"Energia.............: {decimal(fatura['total_kwh'], 2)} kWh")
    print(f"Tarifa..............: {reais(fatura['tarifa'])}/kWh")
    if fatura["taxa_admin"] > 0:
        print(f"Taxa administrativa.: {reais(fatura['taxa_admin'])} (fechamento COM taxa)")
    else:
        print("Taxa administrativa.: não cobrada (fechamento SEM taxa)")
    print(f"Total gravado.......: {reais(fatura['total_value'])}")
    print(f"Total recalculado...: {reais(auditoria['valor_recalculado'])}")
    print(f"Situação............: {fatura['status']} (vencimento {fatura['vencimento']})")
    if auditoria["confere"]:
        print("Auditoria...........: CONFERE com as sessões registradas")
    else:
        print("Auditoria...........: ***** DIVERGÊNCIA entre a fatura e as sessões *****")


def mostrar_simulacao_de_rateio(s: dict) -> None:
    print("\nFatura = (kWh x Tarifa) + Taxa administrativa")
    print(f"Consumo.............: {decimal(s['kwh'], 2)} kWh x {reais(s['tarifa'])} = {reais(s['consumo'])}")
    print(f"Opção SEM taxa......: {reais(s['total_sem_taxa'])}")
    print(f"Opção COM taxa......: {reais(s['consumo'])} + {reais(s['taxa_admin'])} = {reais(s['total_com_taxa'])}")


# ----- TELAS DO GESTOR
def tela_painel_do_mes() -> None:
    mes = escolher_mes()
    painel = controle_gestor.painel_do_mes(mes)
    resumo = painel["resumo"]
    titulo(f"PAINEL DO GESTOR - {mes}")
    print(f"Sessões.............: {resumo['sessoes']} ({resumo['interrompidas']} interrompidas)")
    print(f"Energia entregue....: {decimal(resumo['total_kwh'], 2)} kWh")
    for codigo in resumo["kwh_por_carregador"]:
        print(f"  {codigo}............: {decimal(resumo['kwh_por_carregador'][codigo], 2)} kWh, "
              f"ocioso {decimal(resumo['ociosidade'][codigo] * 100, 1)}% do mês")
    if resumo["fechado"]:
        print(f"Faturado............: {reais(resumo['valor_faturado'])}")
        print(f"Recebido............: {reais(resumo['valor_recebido'])}")
        print(f"Pendente............: {reais(resumo['valor_pendente'])}")
        print("\nCONSOLIDADO MENSAL (mês fechado)")
        mostrar_tabela(painel["consolidado"], [("fatura", "Fatura", 8), ("unidade", "Unidade", 10),
                                               ("bloco", "Bloco", 9), ("sessoes", "Sessões", 9),
                                               ("kwh", "kWh", 10), ("taxa", "Taxa R$", 9),
                                               ("total", "Total R$", 11), ("status", "Status", 9)])
    else:
        print("\nPRÉVIA DO MÊS (ainda aberto): as duas opções de fechamento")
        mostrar_tabela(painel["previa"], [("unidade", "Unidade", 10), ("bloco", "Bloco", 9),
                                          ("sessoes", "Sessões", 9), ("kwh", "kWh", 10),
                                          ("total_sem_taxa", "Sem taxa R$", 13),
                                          ("total_com_taxa", "Com taxa R$", 13)])
        print(LINHA)
        print(f"Total SEM taxa......: {reais(controle_gestor.total_da_coluna(painel['previa'], 'total_sem_taxa'))}")
        print(f"Total COM taxa......: {reais(controle_gestor.total_da_coluna(painel['previa'], 'total_com_taxa'))}")
    mostrar_alertas(painel["alertas"])


def tela_fechar_mes() -> None:
    mes = escolher_mes()
    config = controle_gestor.configuracao()
    print(f"\nTarifa atual: {reais(config['tarifa_kwh'])}/kWh. Taxa administrativa: {reais(config['taxa_admin'])}.")
    opcao = escolher_opcao("Opção desejada...: ", ["Fechar SEM taxa administrativa",
                                                   "Fechar COM taxa administrativa"])
    resultado = controle_gestor.fechar_mes(mes, opcao == 1)
    print("\n" + resultado["mensagem"])
    if resultado["ok"]:
        mostrar_tabela(controle_gestor.consolidado_do_mes(mes),
                       [("fatura", "Fatura", 8), ("unidade", "Unidade", 10), ("kwh", "kWh", 10),
                        ("taxa", "Taxa R$", 9), ("total", "Total R$", 11), ("status", "Status", 9)])


def tela_registrar_pagamento() -> None:
    print("\nFATURAS PENDENTES")
    mostrar_tabela(controle_gestor.faturas_pendentes(),
                   [("fatura", "Fatura", 8), ("unidade", "Unidade", 10), ("mes", "Mês", 10),
                    ("total", "Total R$", 11), ("vencimento", "Vencimento", 12)])
    numero = ler_inteiro("Número da fatura paga (0 cancela)...: ")
    if numero != 0:
        print(controle_gestor.registrar_pagamento(numero)["mensagem"])


def tela_atualizar_bloqueios() -> None:
    resultado = controle_gestor.atualizar_bloqueios()
    print(f"\nCartões bloqueados agora......: {resultado['bloqueados']}")
    print(f"Cartões desbloqueados agora...: {resultado['desbloqueados']}")
    print("Unidades com fatura vencida:")
    for unidade in controle_gestor.unidades_inadimplentes():
        print(f"  {unidade['name']} / {unidade['block']}")


def tela_auditar_fatura() -> None:
    numero = ler_inteiro("Número da fatura...: ")
    mostrar_auditoria(controle_gestor.auditar(numero))


def tela_conciliacao() -> None:
    mes = escolher_mes()
    titulo(f"CONCILIAÇÃO COM O SEMS PORTAL - {mes}")
    linhas = controle_gestor.conciliacao(mes)
    for linha in linhas:
        linha["erro_pct"] = decimal(linha["erro_relativo"] * 100, 1) + "%"
        linha["situacao"] = "ok"
        if linha["divergente"]:
            linha["situacao"] = "DIVERGENTE"
    mostrar_tabela(linhas, [("data", "Data", 12), ("carregador", "Carreg.", 9),
                            ("kwh_sessoes", "Sessões kWh", 13), ("kwh_sems", "SEMS kWh", 11),
                            ("erro_absoluto", "Erro abs.", 11), ("erro_pct", "Erro rel.", 11),
                            ("situacao", "Situação", 10)])


def tela_cadastros() -> None:
    while True:
        print("""
    CADASTROS
    0 - VOLTAR
    1 - Listar unidades, usuários, cartões e carregadores
    2 - Cadastrar unidade
    3 - Cadastrar usuário
    4 - Cadastrar cartão RFID
        """)
        opcao = ler_inteiro("Opção desejada...: ")
        match opcao:
            case 0:
                break
            case 1:
                cadastros = controle_gestor.listar_cadastros()
                print("\nUNIDADES")
                mostrar_tabela(cadastros["unidades"], [("id", "Id", 5), ("name", "Nome", 12), ("block", "Bloco", 10)])
                print("\nUSUÁRIOS")
                mostrar_tabela(cadastros["usuarios"], [("id", "Id", 5), ("nome", "Nome", 20),
                                                       ("unidade", "Unidade", 10), ("email", "E-mail", 25)])
                print("\nCARTÕES RFID")
                mostrar_tabela(cadastros["cartoes"], [("uid", "UID", 11), ("usuario", "Usuário", 20),
                                                      ("unidade", "Unidade", 10), ("situacao", "Situação", 10)])
                print("\nCARREGADORES")
                mostrar_tabela(cadastros["carregadores"], [("id", "Id", 9), ("model", "Modelo", 11),
                                                           ("max_power_kw", "kW", 7), ("location", "Local", 10)])
            case 2:
                nome = input("Nome da unidade (ex.: Apto 51)...: ")
                bloco = input("Bloco (ex.: Torre A)...: ")
                print(controle_gestor.cadastrar_unidade(nome, bloco)["mensagem"])
            case 3:
                unidade = escolher_unidade()
                nome = input("Nome do usuário...: ")
                email = input("E-mail...: ")
                print(controle_gestor.cadastrar_usuario(unidade["id"], nome, email)["mensagem"])
            case 4:
                uid = input("UID do cartão (ex.: E1F2A3B4)...: ")
                usuario = ler_inteiro("Id do usuário dono do cartão...: ")
                print(controle_gestor.cadastrar_cartao(uid, usuario)["mensagem"])
            case _:
                print("***** Opção inválida! *****")


def tela_configuracao() -> None:
    config = controle_gestor.configuracao()
    print(f"\nTarifa atual.................: {reais(config['tarifa_kwh'])}/kWh")
    print(f"Taxa administrativa atual....: {reais(config['taxa_admin'])}")
    if config["cobrar_taxa"]:
        print("Opção padrão do fechamento...: COM taxa")
    else:
        print("Opção padrão do fechamento...: SEM taxa")
    if ler_sim_nao("Alterar esses valores?"):
        tarifa = ler_decimal("Nova tarifa (R$/kWh)...: ")
        taxa = ler_decimal("Nova taxa administrativa (R$)...: ")
        cobrar = ler_sim_nao("Fechar os meses COM taxa por padrão?")
        print(controle_gestor.alterar_configuracao(tarifa, taxa, cobrar)["mensagem"])


def tela_simulador_de_rateio() -> None:
    config = controle_gestor.configuracao()
    cenarios = controle_gestor.cenarios_de_rateio()
    rotulos = []
    for cenario in cenarios:
        rotulos.append(cenario["nome"])
    rotulos.append("Digitar os valores")
    print("\nSIMULADOR DE RATEIO")
    opcao = escolher_opcao("Opção desejada...: ", rotulos)
    if opcao < len(cenarios):
        cenario = cenarios[opcao]
        simulacao = controle_gestor.simular_rateio(cenario["kwh"], cenario["tarifa"], cenario["taxa"])
    else:
        kwh = ler_decimal("Energia das sessões (kWh)...: ")
        simulacao = controle_gestor.simular_rateio(kwh, config["tarifa_kwh"], config["taxa_admin"])
    mostrar_simulacao_de_rateio(simulacao)


def tela_indicadores() -> None:
    titulo("INDICADORES DEFINIDOS NA SPRINT 1")
    for linha in controle_gestor.indicadores_da_sprint1():
        print(f"{linha['indicador']} (meta: {linha['meta']})")
        print(f"   Resultado...: {linha['resultado']}")
        print(f"   Como medimos: {linha['como']}")


def menu_gestor() -> None:
    while True:
        print("""
    PAINEL DO GESTOR
    0 - VOLTAR
    1 - Painel do mês (resumo, consolidado e alertas)
    2 - Fechar mês (com taxa ou sem taxa)
    3 - Registrar pagamento
    4 - Atualizar bloqueios de inadimplentes
    5 - Auditar fatura
    6 - Conciliar com o SEMS Portal
    7 - Cadastros
    8 - Configurar tarifa e taxa
    9 - Simulador de rateio
    10 - Indicadores da Sprint 1
        """)
        opcao = ler_inteiro("Opção desejada...: ")
        match opcao:
            case 0:
                break
            case 1:
                tela_painel_do_mes()
            case 2:
                tela_fechar_mes()
            case 3:
                tela_registrar_pagamento()
            case 4:
                tela_atualizar_bloqueios()
            case 5:
                tela_auditar_fatura()
            case 6:
                tela_conciliacao()
            case 7:
                tela_cadastros()
            case 8:
                tela_configuracao()
            case 9:
                tela_simulador_de_rateio()
            case 10:
                tela_indicadores()
            case _:
                print("***** Opção inválida! *****")


# ----- TELAS DO MORADOR
def tela_consumo_do_morador(unidade: dict) -> None:
    mes = escolher_mes()
    painel = controle_morador.painel_da_unidade(unidade["id"], mes)
    titulo(f"{unidade['name']} / {unidade['block']} - {mes}")
    mostrar_tabela(painel["sessoes"], [("sessao", "Sessão", 8), ("inicio", "Início", 18), ("fim", "Fim", 18),
                                       ("cartao", "Cartão", 10), ("kwh", "kWh", 9), ("valor", "Valor R$", 10)])
    print(LINHA)
    print(f"Energia no mês......: {decimal(painel['kwh'], 2)} kWh")
    print(f"Consumo.............: {reais(painel['consumo_rs'])} (tarifa de {reais(painel['tarifa'])}/kWh)")
    if painel["tem_fatura"]:
        mostrar_auditoria(painel["auditoria"])
    else:
        print("Fatura..............: mês ainda não fechado")


def tela_cartoes_do_morador(unidade: dict) -> None:
    print(f"\nCARTÕES RFID DE {unidade['name']}")
    mostrar_tabela(controle_morador.cartoes_da_unidade(unidade["id"]),
                   [("uid", "UID", 11), ("usuario", "Usuário", 20), ("situacao", "Situação", 10)])


def tela_melhor_horario() -> None:
    duracao = ler_inteiro("Duração da recarga em horas (1 a 8)...: ")
    while duracao < 1 or duracao > 8:
        print("***** Informe um valor de 1 a 8! *****")
        duracao = ler_inteiro("Duração da recarga em horas (1 a 8)...: ")
    janela = controle_ia.janela_sugerida(duracao)
    if janela == {}:
        print("***** O modelo de previsão ainda não foi treinado! *****")
        return
    print(f"\nHoje é {janela['dia_semana']}. Para {duracao} hora(s) de recarga:")
    print(f"À noite.............: das {janela['noite_inicio']}h às {janela['noite_fim']}h "
          f"(demanda média de {decimal(janela['noite_demanda_kw'], 1)} kW)")
    print(f"Durante o dia.......: das {janela['dia_inicio']}h às {janela['dia_fim']}h "
          f"(demanda média de {decimal(janela['dia_demanda_kw'], 1)} kW)")
    print(f"Evite...............: por volta das {janela['hora_pico']}h "
          f"(pico de {decimal(janela['demanda_no_pico_kw'], 1)} kW)")
    if not janela["dentro_do_limite"]:
        print("Atenção: mesmo na janela noturna a soma pode passar do limite do quadro.")


def tela_sindico_virtual(unit_id: int) -> None:
    titulo(f"SÍNDICO VIRTUAL [modo: {controle_ia.modo_da_ia()}]")
    print("Pergunte sobre consumo, faturas, anomalias, previsão ou melhor horário.")
    print("Digite SAIR para encerrar a conversa.")
    historico = []
    while True:
        pergunta = input("\nVocê: ").strip()
        if pergunta.upper() == "SAIR":
            break
        if pergunta == "":
            continue
        resultado = controle_ia.perguntar(pergunta, unit_id, historico)
        # o modo mostra se a resposta veio do LLM ou do modo simulado
        print(f"Síndico Virtual [{resultado['modo']}]: {resultado['resposta']}")
        # memoria da conversa: pergunta e resposta ficam guardadas na lista
        historico.append({"role": "user", "content": pergunta})
        historico.append({"role": "assistant", "content": resultado["resposta"]})


def menu_morador() -> None:
    unidade = escolher_unidade()
    while True:
        print(f"""
    INTERFACE DO MORADOR - {unidade['name']} / {unidade['block']}
    0 - VOLTAR
    1 - Consumo, sessões e fatura do mês
    2 - Meus cartões RFID
    3 - Melhor horário para recarregar
    4 - Conversar com o Síndico Virtual
        """)
        opcao = ler_inteiro("Opção desejada...: ")
        match opcao:
            case 0:
                break
            case 1:
                tela_consumo_do_morador(unidade)
            case 2:
                tela_cartoes_do_morador(unidade)
            case 3:
                tela_melhor_horario()
            case 4:
                tela_sindico_virtual(unidade["id"])
            case _:
                print("***** Opção inválida! *****")


# ----- TELAS DA SIMULACAO DO CARREGADOR
def mostrar_resultado_da_sessao(resultado: dict) -> None:
    if not resultado["valido"]:
        print("***** " + resultado["mensagem"] + " *****")
        return
    titulo("FLUXO DA SESSÃO DE RECARGA")
    for etapa in resultado["etapas"]:
        print(f"{etapa['numero']}. {etapa['nome']}")
        print(f"   {etapa['detalhe']}")
    if resultado["autorizado"]:
        # mostra uma leitura a cada 15 minutos para nao encher a tela
        print("\nLEITURAS DO CARREGADOR (amostra)")
        amostra = []
        for i in range(0, len(resultado["leituras"]), 15):
            amostra.append(resultado["leituras"][i])
        mostrar_tabela(amostra, [("minuto", "Minuto", 8), ("tensao_v", "Tensão V", 10),
                                 ("corrente_a", "Corrente A", 12), ("potencia_kw", "Potência kW", 13),
                                 ("energia_kwh", "Energia kWh", 12)])


def tela_simular_sessao(forcar_interrupcao: bool) -> None:
    opcoes = controle_sessao.opcoes_de_sessao()
    print("\nCARTÕES RFID")
    cartao = opcoes["cartoes"][escolher_opcao("Cartão aproximado do leitor...: ", opcoes["rotulos"])]
    rotulos = []
    for carregador in opcoes["carregadores"]:
        rotulos.append(f"{carregador['id']} | {carregador['model']} | {carregador['location']}")
    print("\nCARREGADORES")
    carregador = opcoes["carregadores"][escolher_opcao("Carregador...: ", rotulos)]
    duracao = ler_inteiro("Duração planejada em minutos...: ")
    resultado = controle_sessao.iniciar_sessao(cartao["uid"], carregador["id"], duracao, forcar_interrupcao)
    mostrar_resultado_da_sessao(resultado)


def tela_cartao_bloqueado() -> None:
    uid = controle_sessao.primeiro_cartao_bloqueado()
    if uid == "":
        print("\nNão há cartão bloqueado no momento.")
        return
    carregador = controle_sessao.opcoes_de_sessao()["carregadores"][0]["id"]
    mostrar_resultado_da_sessao(controle_sessao.iniciar_sessao(uid, carregador, 120, False))


def menu_simulacao() -> None:
    while True:
        print("""
    SIMULAÇÃO DO CARREGADOR GOODWE HCA G2
    0 - VOLTAR
    1 - Simular uma sessão de recarga completa
    2 - Simular uma sessão interrompida (queda de energia)
    3 - Tentar recarregar com um cartão bloqueado
    4 - Recriar a base de demonstração
        """)
        opcao = ler_inteiro("Opção desejada...: ")
        match opcao:
            case 0:
                break
            case 1:
                tela_simular_sessao(False)
            case 2:
                tela_simular_sessao(True)
            case 3:
                tela_cartao_bloqueado()
            case 4:
                if ler_sim_nao("Isso apaga os dados atuais. Continuar?"):
                    resumo = controle_sessao.recriar_base()
                    print(f"\nBase recriada: {resumo['unidades']} unidades, {resumo['cartoes']} cartões, "
                          f"{resumo['sessoes']} sessões e {resumo['faturas']} faturas.")
            case _:
                print("***** Opção inválida! *****")


# ----- TELAS DA INTELIGENCIA ARTIFICIAL
def mostrar_limite_dos_dados(previsao: dict) -> None:
    if "analise_do_limite" not in previsao:
        return
    limite = previsao["analise_do_limite"]
    meta = controle_ia.meta_de_precisao()
    print(f"\nDE ONDE VEM O ERRO (precisão no período de teste; meta da Sprint 1: {decimal(meta * 100, 0)}%)")
    print(f"Modelo, por dia...............: {decimal(limite['modelo_por_dia'] * 100, 1)}%")
    print(f"Teto do calendário............: {decimal(limite['teto_do_calendario'] * 100, 1)}% "
          f"(média real de cada dia da semana)")
    print(f"Sabendo as recargas do dia....: {decimal(limite['sabendo_as_recargas'] * 100, 1)}% "
          f"(por exemplo, com agendamento)")
    print(f"Modelo, por semana............: {decimal(limite['modelo_por_semana'] * 100, 1)}% "
          f"({limite['semanas_de_teste']} semanas de teste)")
    print("O modelo já está no teto do que o calendário explica. O erro restante é a variação")
    print("de quem recarrega e de quanto recarrega, que só dados da operação real reduzem.")


def mostrar_metricas(previsao: dict) -> None:
    print(f"\nHistórico usado.....: {previsao['dias_de_historico']} dias "
          f"({previsao['dias_treino']} de treino e {previsao['dias_teste']} de teste)")
    print("\nMODELO              MAE (kWh)   RMSE (kWh)   R²       Erro relativo")
    print(LINHA)
    linear = previsao["metricas_linear"]
    ridge = previsao["metricas_ridge"]
    print(f"Regressão Linear    {decimal(linear['mae'], 2).ljust(12)}{decimal(linear['rmse'], 2).ljust(13)}"
          f"{decimal(linear['r2'], 3).ljust(9)}{decimal(linear['erro_relativo'] * 100, 1)}%")
    print(f"Ridge (alpha={previsao['melhor_alpha']})".ljust(20)
          + f"{decimal(ridge['mae'], 2).ljust(12)}{decimal(ridge['rmse'], 2).ljust(13)}"
          f"{decimal(ridge['r2'], 3).ljust(9)}{decimal(ridge['erro_relativo'] * 100, 1)}%")
    print(LINHA)
    print(f"Modelo escolhido....: {previsao['modelo_escolhido']} (menor RMSE no período de teste)")
    print(f"Precisão estimada...: {decimal(previsao['precisao_estimada'] * 100, 1)}% (1 - erro relativo)")
    mostrar_limite_dos_dados(previsao)
    risco = previsao["risco"]
    if risco["treinado"]:
        print(f"\nCLASSIFICAÇÃO DO RISCO DE SOBRECARGA (limite de {decimal(previsao['limite_quadro_kw'], 0)} kW)")
        print(f"Dias com sobrecarga.: {risco['dias_com_sobrecarga']} de {risco['amostras']}")
        print(f"Acurácia............: {decimal(risco['acuracia'] * 100, 1)}%")
        print(f"Precisão............: {decimal(risco['precisao'] * 100, 1)}%")
        print(f"Recall..............: {decimal(risco['recall'] * 100, 1)}%")
        print(f"F1-score............: {decimal(risco['f1'], 3)}")
        print(f"Matriz de confusão..: {risco['matriz_confusao']}")


def mostrar_previsao_7_dias(previsao: dict) -> None:
    print("\nPREVISÃO PARA OS PRÓXIMOS 7 DIAS")
    linhas = []
    for dia in previsao["previsao_7_dias"]:
        risco = "normal"
        if dia["risco_alto"]:
            risco = "ALTO"
        linhas.append({"data": dia["data"], "dia": dia["dia_semana"], "kwh": dia["kwh_previsto"],
                       "prob": decimal(dia["prob_sobrecarga"] * 100, 0) + "%", "risco": risco})
    mostrar_tabela(linhas, [("data", "Data", 12), ("dia", "Dia", 10), ("kwh", "kWh previstos", 15),
                            ("prob", "Prob. sobrecarga", 18), ("risco", "Risco", 8)])


def menu_ia() -> None:
    while True:
        print(f"""
    INTELIGÊNCIA ARTIFICIAL [Síndico Virtual em modo: {controle_ia.modo_da_ia()}]
    0 - VOLTAR
    1 - Treinar e avaliar o modelo de previsão de demanda
    2 - Ver a previsão dos próximos 7 dias
    3 - Melhor horário para recarregar hoje
    4 - Conversar com o Síndico Virtual (visão do gestor)
        """)
        opcao = ler_inteiro("Opção desejada...: ")
        match opcao:
            case 0:
                break
            case 1:
                previsao = controle_ia.treinar()
                mostrar_metricas(previsao)
                mostrar_previsao_7_dias(previsao)
            case 2:
                previsao = controle_ia.previsao_atual()
                if previsao == {}:
                    print("***** O modelo ainda não foi treinado! Use a opção 1. *****")
                else:
                    mostrar_previsao_7_dias(previsao)
            case 3:
                tela_melhor_horario()
            case 4:
                tela_sindico_virtual(0)
            case _:
                print("***** Opção inválida! *****")


# ----- MENU PRINCIPAL
def menu_principal() -> None:
    controle_sessao.preparar_sistema()
    while True:
        print(f"""
{LINHA_DUPLA}
    EV CHARGEOPS - GOODWE + FIAP
    Gestão inteligente de recargas compartilhadas
{LINHA_DUPLA}
    0 - SAIR
    1 - PAINEL DO GESTOR
    2 - INTERFACE DO MORADOR
    3 - SIMULAÇÃO DO CARREGADOR (telemetria)
    4 - INTELIGÊNCIA ARTIFICIAL
        """)
        opcao = ler_inteiro("Opção desejada...: ")
        match opcao:
            case 0:
                break
            case 1:
                menu_gestor()
            case 2:
                menu_morador()
            case 3:
                menu_simulacao()
            case 4:
                menu_ia()
            case _:
                print("***** Opção inválida! *****")
    print("OK! O programa está encerrado...")
