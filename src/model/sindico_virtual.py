"""
Autor.....: Equipe EV ChargeOps (RM573133, RM571998, RM568867, RM574003)
Assunto...: MODEL - IA frente 2: Sindico Virtual (agente conversacional)
Problema..: Responder em linguagem natural a perguntas sobre consumo, cobranca,
            anomalias e previsao, usando somente os dados reais do sistema.
            Cadeia de prompts: 1) classificar a intencao (few-shot + saida JSON)
                               2) executar a ferramenta local correspondente
                               3) redigir a resposta com o contexto obtido
            Sem chave da OpenAI, o mesmo fluxo roda em modo simulado.
"""
import json
import os
from datetime import datetime

from openai import OpenAI

import formato
from model import alertas
from model import dados
from model import ia_previsao
from model import rateio

# ----- CONSTANTES
MODELO_LLM = "gpt-4o-mini"
INTENCOES = ("consumo_unidade", "fatura_unidade", "comparar_meses", "anomalias",
             "previsao_demanda", "melhor_horario", "status_cartao", "resumo_gestor", "outro")
MESES = ("janeiro", "fevereiro", "marco", "abril", "maio", "junho",
         "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")
ACENTOS = (("á", "a"), ("à", "a"), ("ã", "a"), ("â", "a"), ("é", "e"), ("ê", "e"), ("í", "i"),
           ("ó", "o"), ("õ", "o"), ("ô", "o"), ("ú", "u"), ("ç", "c"))

# palavras-chave do modo simulado; a ordem define qual intencao vence
PALAVRAS_CHAVE = (
    ("comparar_meses", ("por que", "porque", "subiu", "aumentou", "comparar", "diferenca")),
    ("anomalias", ("anomalia", "problema", "alerta", "falha", "interromp", "divergen")),
    ("status_cartao", ("cartao", "rfid", "tag", "bloque")),
    ("fatura_unidade", ("fatura", "conta", "boleto", "cobranca", "pagar", "devo", "vencimento")),
    ("previsao_demanda", ("previs", "demanda", "proximos dias", "sobrecarga", "pico")),
    ("melhor_horario", ("horario", "que horas", "quando", "janela")),
    ("resumo_gestor", ("resumo", "condominio", "geral", "faturamento")),
    ("consumo_unidade", ("consumo", "consumi", "gastei", "gastou", "kwh", "recarga", "sessoes"))
)

# ----- PROMPTS
PROMPT_SISTEMA = """Você é o Síndico Virtual do EV ChargeOps, assistente de um condomínio com carregadores GoodWe para veículos elétricos.
Responda em português, de forma clara e direta, em no máximo 4 frases.
Use exclusivamente os dados do contexto fornecido. Se o dado não estiver no contexto, diga "Não tenho esse dado".
Informe energia em kWh e valores em R$ com duas casas decimais."""

# few-shot + saida estruturada em JSON
PROMPT_INTENCAO = """Classifique a pergunta em uma das intenções: consumo_unidade, fatura_unidade, comparar_meses, anomalias, previsao_demanda, melhor_horario, status_cartao, resumo_gestor, outro.
Retorne apenas um objeto JSON válido com os campos "intencao" (string), "unidade" (string ou null) e "mes" (string no formato MM-AAAA ou null).

Pergunta: "Quanto o apto 42 consumiu em junho de 2026?"
Resposta: {"intencao": "consumo_unidade", "unidade": "Apto 42", "mes": "06-2026"}

Pergunta: "Qual o valor da fatura do apartamento 21?"
Resposta: {"intencao": "fatura_unidade", "unidade": "Apto 21", "mes": null}

Pergunta: "Teve algum problema com os carregadores este mês?"
Resposta: {"intencao": "anomalias", "unidade": null, "mes": null}

Pergunta: "Qual o melhor horário para carregar hoje?"
Resposta: {"intencao": "melhor_horario", "unidade": null, "mes": null}

Pergunta: "PERGUNTA_DO_USUARIO"
Resposta:"""

PROMPT_RESPOSTA = """Contexto (dados do sistema em JSON):
CONTEXTO_JSON

Pergunta:
PERGUNTA_DO_USUARIO"""

# chain-of-thought: pede o raciocinio passo a passo na comparacao entre meses
PROMPT_COMPARACAO = """Contexto (dados do sistema em JSON):
CONTEXTO_JSON

Pergunta:
PERGUNTA_DO_USUARIO

Vamos pensar passo a passo: compare o número de sessões, depois os kWh, depois o valor, e só então explique a diferença entre os dois meses."""


# ----- SUBALGORITMOS DE APOIO
def modo_llm_ativo() -> bool:
    return "OPENAI_API_KEY" in os.environ and os.environ["OPENAI_API_KEY"] != ""


def sem_acentos(texto: str) -> str:
    texto = texto.lower()
    for par in ACENTOS:
        texto = texto.replace(par[0], par[1])
    return texto


def chamar_llm(mensagens: list, temperatura: float, max_tokens: int) -> str:
    # chamada a API da OpenAI; em caso de falha de rede ou de chave devolve ""
    try:
        # sem novas tentativas e com limite de espera: se a API nao responder,
        # o assistente passa logo para o modo simulado em vez de travar a tela
        client = OpenAI(max_retries=0, timeout=20)
        completion = client.chat.completions.create(
            model=MODELO_LLM,
            messages=mensagens,
            temperature=temperatura,
            max_tokens=max_tokens
        )
        return completion.choices[0].message.content
    except Exception:
        return ""


def encontrar_unidade(pergunta: str) -> dict:
    # procura "apto 42", "apartamento 42" ou "unidade 42" na pergunta
    texto = sem_acentos(pergunta)
    for unidade in dados.carregar_tabela("units"):
        partes = unidade["name"].split(" ")
        numero = partes[len(partes) - 1]
        for prefixo in ("apto ", "apto. ", "apartamento ", "unidade ", "ap "):
            if prefixo + numero in texto:
                return unidade
    return {}


def encontrar_mes(pergunta: str, padrao: str) -> str:
    texto = sem_acentos(pergunta)
    ano = padrao.split("-")[1]
    for mes in dados.meses_com_sessoes():
        if mes in texto:
            return mes
    for i in range(len(MESES)):
        if MESES[i] in texto:
            return f"{i + 1:02d}-{ano}"
    return padrao


def mes_anterior(mes: str) -> str:
    meses = dados.meses_com_sessoes()
    for i in range(1, len(meses)):
        if meses[i] == mes:
            return meses[i - 1]
    return ""


def ultimo_mes_com_sessoes() -> str:
    meses = dados.meses_com_sessoes()
    if len(meses) == 0:
        return dados.mes_atual()
    return meses[len(meses) - 1]


def ultimo_mes_fechado() -> str:
    ultimo = ""
    for fatura in dados.carregar_tabela("invoices"):
        if ultimo == "" or dados.chave_do_mes(fatura["month"]) > dados.chave_do_mes(ultimo):
            ultimo = fatura["month"]
    if ultimo == "":
        return ultimo_mes_com_sessoes()
    return ultimo


# ----- ETAPA 1 DA CADEIA: CLASSIFICAR A INTENCAO
def classificar_por_palavras(pergunta: str) -> str:
    texto = sem_acentos(pergunta)
    for grupo in PALAVRAS_CHAVE:
        for palavra in grupo[1]:
            if palavra in texto:
                return grupo[0]
    return "outro"


def classificar_com_llm(pergunta: str) -> dict:
    prompt = PROMPT_INTENCAO.replace("PERGUNTA_DO_USUARIO", pergunta)
    texto = chamar_llm([{"role": "user", "content": prompt}], 0, 80)
    # a resposta deve ser um JSON; se nao for, o modo simulado assume
    try:
        resposta = json.loads(texto)
    except Exception:
        return {}
    if "intencao" not in resposta or resposta["intencao"] not in INTENCOES:
        return {}
    return resposta


def classificar_intencao(pergunta: str, unidade_padrao: dict) -> dict:
    intencao = classificar_por_palavras(pergunta)
    unidade = encontrar_unidade(pergunta)
    mes = ""
    modo = "simulado"
    if modo_llm_ativo():
        resposta = classificar_com_llm(pergunta)
        if resposta != {}:
            modo = "LLM " + MODELO_LLM
            intencao = resposta["intencao"]
            if "unidade" in resposta and resposta["unidade"] is not None:
                achada = dados.buscar_registro("units", "name", resposta["unidade"])
                if achada != {}:
                    unidade = achada
            if "mes" in resposta and resposta["mes"] in dados.meses_com_sessoes():
                mes = resposta["mes"]
    if unidade == {}:
        unidade = unidade_padrao
    # mes padrao: faturas olham o ultimo mes fechado; o resto, o mes mais recente
    if mes == "":
        if intencao in ("fatura_unidade", "comparar_meses"):
            mes = encontrar_mes(pergunta, ultimo_mes_fechado())
        else:
            mes = encontrar_mes(pergunta, ultimo_mes_com_sessoes())
    return {"intencao": intencao, "unidade": unidade, "mes": mes, "modo": modo}


# ----- ETAPA 2 DA CADEIA: FERRAMENTAS LOCAIS (consultam os dados do sistema)
def ferramenta_consumo(unidade: dict, mes: str) -> dict:
    config = dados.carregar_config()
    kwh = 0.0
    interrompidas = 0
    sessoes = dados.sessoes_da_unidade(unidade["id"], mes)
    for sessao in sessoes:
        kwh += sessao["kwh_delivered"]
        if sessao["interrompida"]:
            interrompidas += 1
    return {"unidade": unidade["name"], "mes": mes, "sessoes": len(sessoes),
            "kwh": round(kwh, 2), "tarifa": config["tarifa_kwh"],
            "consumo_rs": rateio.calcula_total(kwh, config["tarifa_kwh"], 0.0),
            "interrompidas": interrompidas}


def ferramenta_fatura(unidade: dict, mes: str) -> dict:
    fatura = dados.fatura_da_unidade(unidade["id"], mes)
    if fatura == {}:
        parcial = ferramenta_consumo(unidade, mes)
        return {"unidade": unidade["name"], "mes": mes, "fechado": False,
                "kwh_parcial": parcial["kwh"], "consumo_parcial_rs": parcial["consumo_rs"]}
    auditoria = rateio.auditar_fatura(fatura["id"])
    return {"unidade": unidade["name"], "mes": mes, "fechado": True, "fatura": fatura["id"],
            "kwh": fatura["total_kwh"], "tarifa": fatura["tarifa"], "taxa_admin": fatura["taxa_admin"],
            "valor": fatura["total_value"], "status": fatura["status"],
            "vencimento": fatura["vencimento"], "sessoes": fatura["sessoes"],
            "auditoria_confere": auditoria["confere"]}


def ferramenta_comparar(unidade: dict, mes: str) -> dict:
    anterior = mes_anterior(mes)
    if anterior == "":
        return {"unidade": unidade["name"], "mes": mes, "tem_anterior": False}
    atual = ferramenta_consumo(unidade, mes)
    antes = ferramenta_consumo(unidade, anterior)
    return {"unidade": unidade["name"], "tem_anterior": True,
            "mes_atual": mes, "sessoes_atual": atual["sessoes"], "kwh_atual": atual["kwh"],
            "valor_atual": atual["consumo_rs"],
            "mes_anterior": anterior, "sessoes_anterior": antes["sessoes"], "kwh_anterior": antes["kwh"],
            "valor_anterior": antes["consumo_rs"],
            "diferenca_kwh": round(atual["kwh"] - antes["kwh"], 2),
            "diferenca_rs": round(atual["consumo_rs"] - antes["consumo_rs"], 2)}


def ferramenta_anomalias(mes: str) -> dict:
    lista = alertas.gerar_alertas(mes, dados.hoje_texto())
    mensagens = []
    for alerta in lista:
        if len(mensagens) < 5:
            mensagens.append(alerta["mensagem"])
    return {"mes": mes, "quantidade": len(lista), "principais": mensagens}


def ferramenta_previsao() -> dict:
    previsao = ia_previsao.carregar_previsao()
    if previsao == {}:
        return {"treinado": False}
    metricas = previsao["metricas"]
    dias = []
    dias_de_risco = []
    total = 0.0
    for dia in previsao["previsao_7_dias"]:
        dias.append({"data": dia["data"], "dia": dia["dia_semana"], "kwh": dia["kwh_previsto"]})
        total += dia["kwh_previsto"]
        if dia["risco_alto"]:
            dias_de_risco.append(dia["dia_semana"] + " " + dia["data"])
    return {"treinado": True, "modelo": previsao["modelo_escolhido"], "r2": metricas["r2"],
            "mae_kwh": metricas["mae"], "total_7_dias_kwh": round(total, 1),
            "previsao": dias, "dias_de_risco": dias_de_risco,
            "limite_quadro_kw": previsao["limite_quadro_kw"]}


def ferramenta_melhor_horario(pergunta: str) -> dict:
    previsao = ia_previsao.carregar_previsao()
    if previsao == {}:
        return {"treinado": False}
    # duracao pedida na pergunta ("3 horas", "4h"); sem isso, considera 3 horas
    texto = sem_acentos(pergunta)
    duracao = 3
    for n in range(1, 9):
        if f"{n} hora" in texto or f"{n}h" in texto:
            duracao = n
    janela = ia_previsao.sugerir_janela(previsao["curva_de_carga"], datetime.now().weekday(), duracao)
    janela["treinado"] = True
    return janela


def ferramenta_status_cartao(unidade: dict) -> dict:
    cartoes = []
    for cartao in dados.cartoes_da_unidade(unidade["id"]):
        if cartao["status"]:
            cartoes.append(cartao["uid"] + " (ativo)")
        else:
            cartoes.append(cartao["uid"] + " (bloqueado)")
    return {"unidade": unidade["name"], "cartoes": cartoes,
            "inadimplente": rateio.unidade_inadimplente(unidade["id"], dados.hoje_texto())}


def ferramenta_resumo(mes: str) -> dict:
    resumo = rateio.resumo_do_mes(mes)
    ranking = rateio.consumo_por_unidade(mes)
    maiores = []
    for i in range(len(ranking)):
        if i < 3:
            maiores.append(f"{ranking[i]['unidade']} ({formato.decimal(ranking[i]['kwh'], 1)} kWh)")
    return {"mes": mes, "sessoes": resumo["sessoes"], "total_kwh": resumo["total_kwh"],
            "fechado": resumo["fechado"], "valor_faturado": resumo["valor_faturado"],
            "valor_pendente": resumo["valor_pendente"], "interrompidas": resumo["interrompidas"],
            "maiores_consumos": maiores}


def executar_ferramenta(intencao: str, unidade: dict, mes: str, pergunta: str) -> dict:
    precisa_de_unidade = intencao in ("consumo_unidade", "fatura_unidade", "comparar_meses", "status_cartao")
    if precisa_de_unidade and unidade == {}:
        return {"erro": "unidade_nao_informada"}
    match intencao:
        case "consumo_unidade":
            return ferramenta_consumo(unidade, mes)
        case "fatura_unidade":
            return ferramenta_fatura(unidade, mes)
        case "comparar_meses":
            return ferramenta_comparar(unidade, mes)
        case "anomalias":
            return ferramenta_anomalias(mes)
        case "previsao_demanda":
            return ferramenta_previsao()
        case "melhor_horario":
            return ferramenta_melhor_horario(pergunta)
        case "status_cartao":
            return ferramenta_status_cartao(unidade)
        case "resumo_gestor":
            return ferramenta_resumo(mes)
        case _:
            return {}


# ----- ETAPA 3 DA CADEIA: REDIGIR A RESPOSTA
def resposta_simulada(intencao: str, c: dict) -> str:
    # respostas montadas com os mesmos dados que o LLM receberia como contexto
    if "erro" in c:
        return "Sobre qual unidade é a pergunta? Informe, por exemplo, \"Apto 42\"."
    match intencao:
        case "consumo_unidade":
            texto = (f"{c['unidade']} fez {c['sessoes']} recarga(s) em {c['mes']}, somando {formato.decimal(c['kwh'], 2)} kWh. "
                     f"Com a tarifa de {formato.reais(c['tarifa'])}/kWh, o consumo é de {formato.reais(c['consumo_rs'])}.")
            if c["interrompidas"] > 0:
                texto += f" {c['interrompidas']} sessão(ões) foi(ram) interrompida(s) e cobrada(s) só pelo kWh validado."
            return texto
        case "fatura_unidade":
            if not c["fechado"]:
                return (f"O mês {c['mes']} ainda não foi fechado. Até agora {c['unidade']} acumula "
                        f"{formato.decimal(c['kwh_parcial'], 2)} kWh, o que dá {formato.reais(c['consumo_parcial_rs'])} de consumo.")
            if c["status"] == "ISENTO":
                return f"{c['unidade']} não recarregou em {c['mes']} e ficou isento de cobrança."
            if c["taxa_admin"] > 0:
                taxa = f"mais taxa administrativa de {formato.reais(c['taxa_admin'])}"
            else:
                taxa = "sem taxa administrativa"
            situacao = "paga"
            if c["status"] == "PENDING":
                situacao = f"pendente, com vencimento em {c['vencimento']}"
            return (f"Fatura {c['fatura']} de {c['unidade']} em {c['mes']}: {formato.decimal(c['kwh'], 2)} kWh x "
                    f"{formato.reais(c['tarifa'])}, {taxa}, total de {formato.reais(c['valor'])}. Situação: {situacao}.")
        case "comparar_meses":
            if not c["tem_anterior"]:
                return "Não tenho um mês anterior para comparar."
            if c["diferenca_kwh"] > 0:
                sentido = "subiu"
            elif c["diferenca_kwh"] < 0:
                sentido = "caiu"
            else:
                sentido = "ficou igual"
            return (f"Em {c['mes_anterior']} {c['unidade']} fez {c['sessoes_anterior']} recarga(s) e consumiu "
                    f"{formato.decimal(c['kwh_anterior'], 2)} kWh ({formato.reais(c['valor_anterior'])}). Em {c['mes_atual']} foram "
                    f"{c['sessoes_atual']} recarga(s) e {formato.decimal(c['kwh_atual'], 2)} kWh ({formato.reais(c['valor_atual'])}). "
                    f"O consumo {sentido} {formato.decimal(abs(c['diferenca_kwh']), 2)} kWh, diferença de {formato.reais(abs(c['diferenca_rs']))}. "
                    f"Como a tarifa é a mesma, a variação vem da quantidade de energia recarregada.")
        case "anomalias":
            if c["quantidade"] == 0:
                return f"Nenhuma anomalia registrada em {c['mes']}."
            texto = f"Há {c['quantidade']} alerta(s). Os mais graves:"
            for mensagem in c["principais"]:
                texto += "\n- " + mensagem
            return texto
        case "previsao_demanda":
            if not c["treinado"]:
                return "O modelo de previsão ainda não foi treinado."
            texto = (f"Previsão para os próximos 7 dias: {formato.decimal(c['total_7_dias_kwh'], 1)} kWh no total "
                     f"(modelo {c['modelo']}, R² {formato.decimal(c['r2'], 2)}, erro médio de {formato.decimal(c['mae_kwh'], 1)} kWh por dia).")
            if len(c["dias_de_risco"]) > 0:
                texto += (f" Dias com risco de passar de {formato.decimal(c['limite_quadro_kw'], 0)} kW no quadro: "
                          + ", ".join(c["dias_de_risco"]) + ".")
            else:
                texto += " Nenhum dia com risco alto de sobrecarga."
            return texto
        case "melhor_horario":
            if not c["treinado"]:
                return "O modelo de previsão ainda não foi treinado."
            texto = (f"Para uma recarga de {c['duracao_h']} hora(s) hoje ({c['dia_semana']}): à noite, o melhor é "
                     f"começar às {c['noite_inicio']}h e terminar às {c['noite_fim']}h (demanda média de "
                     f"{formato.decimal(c['noite_demanda_kw'], 1)} kW); durante o dia, das {c['dia_inicio']}h às {c['dia_fim']}h. "
                     f"Evite por volta das {c['hora_pico']}h, o pico do dia.")
            if not c["dentro_do_limite"]:
                texto += " Mesmo na janela noturna a soma pode passar do limite do quadro."
            return texto
        case "status_cartao":
            texto = f"Cartões de {c['unidade']}: " + ", ".join(c["cartoes"]) + "."
            if c["inadimplente"]:
                texto += " Há fatura vencida; o desbloqueio ocorre após o pagamento."
            return texto
        case "resumo_gestor":
            texto = (f"Em {c['mes']} foram {c['sessoes']} sessões e {formato.decimal(c['total_kwh'], 2)} kWh. "
                     f"Maiores consumos: " + ", ".join(c["maiores_consumos"]) + ".")
            if c["fechado"]:
                texto += (f" Faturado: {formato.reais(c['valor_faturado'])}; pendente: {formato.reais(c['valor_pendente'])}.")
            else:
                texto += " O mês ainda não foi fechado."
            return texto
        case _:
            return ("Posso responder sobre consumo, faturas, anomalias, previsão de demanda, "
                    "melhor horário de recarga e situação dos cartões.")


def redigir_resposta(pergunta: str, intencao: str, contexto: dict, historico: list,
                     usar_llm: bool) -> dict:
    # devolve o texto e o modo em que ele foi realmente escrito
    simulada = {"texto": resposta_simulada(intencao, contexto), "modo": "simulado"}
    if not usar_llm or "erro" in contexto or intencao == "outro":
        return simulada
    if intencao == "comparar_meses":
        modelo_de_prompt = PROMPT_COMPARACAO
    else:
        modelo_de_prompt = PROMPT_RESPOSTA
    prompt = modelo_de_prompt.replace("CONTEXTO_JSON", json.dumps(contexto, ensure_ascii=False))
    prompt = prompt.replace("PERGUNTA_DO_USUARIO", pergunta)
    # memoria da conversa: as ultimas mensagens vao junto com a pergunta atual
    mensagens = [{"role": "system", "content": PROMPT_SISTEMA}]
    for i in range(len(historico)):
        if i >= len(historico) - 6:
            mensagens.append({"role": historico[i]["role"], "content": historico[i]["content"]})
    mensagens.append({"role": "user", "content": prompt})
    resposta = chamar_llm(mensagens, 0.2, 300)
    if resposta == "":
        return simulada
    return {"texto": resposta, "modo": "LLM " + MODELO_LLM}


# ----- SUBALGORITMO PRINCIPAL
def responder(pergunta: str, unidade_padrao: dict, historico: list) -> dict:
    classificacao = classificar_intencao(pergunta, unidade_padrao)
    contexto = executar_ferramenta(classificacao["intencao"], classificacao["unidade"],
                                   classificacao["mes"], pergunta)
    # se o modelo nao conseguiu classificar, a pergunta inteira segue em modo simulado
    usar_llm = classificacao["modo"] != "simulado"
    redacao = redigir_resposta(pergunta, classificacao["intencao"], contexto, historico, usar_llm)
    dados.registrar_evento("SINDICO_VIRTUAL", f"{classificacao['intencao']} [{redacao['modo']}]")
    return {"resposta": redacao["texto"], "intencao": classificacao["intencao"],
            "modo": redacao["modo"], "contexto": contexto}
