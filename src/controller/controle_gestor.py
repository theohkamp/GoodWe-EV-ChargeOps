"""
Autor.....: Equipe EV ChargeOps (RM573133, RM571998, RM568867, RM574003)
Assunto...: CONTROLLER - acoes do gestor (sindico / administradora)
Problema..: Receber os pedidos das telas (console e web), acionar os modelos
            e devolver os dados prontos para exibicao. Nenhum print ou input aqui.
"""
import formato
from model import alertas
from model import dados
from model import ia_previsao
from model import rateio
from model import telemetria


# ----- SUBALGORITMOS DE CONSULTA
def meses_disponiveis() -> list:
    return dados.meses_com_sessoes()


def configuracao() -> dict:
    return dados.carregar_config()


def nome_da_unidade(unit_id: int) -> str:
    unidade = dados.buscar_registro("units", "id", unit_id)
    if unidade == {}:
        return "?"
    return unidade["name"]


def consolidado_do_mes(mes: str) -> list:
    # mes fechado: as faturas gravadas, uma linha por unidade
    unidades = dados.carregar_tabela("units")
    linhas = []
    for fatura in dados.faturas_do_mes(mes):
        unidade = dados.buscar(unidades, "id", fatura["unit_id"])
        linhas.append({
            "fatura": fatura["id"],
            "unidade": unidade["name"],
            "bloco": unidade["block"],
            "sessoes": fatura["sessoes"],
            "kwh": fatura["total_kwh"],
            "tarifa": fatura["tarifa"],
            "taxa": fatura["taxa_admin"],
            "total": fatura["total_value"],
            "status": fatura["status"],
            "vencimento": fatura["vencimento"]
        })
    return linhas


def consolidado_em_csv(mes: str) -> str:
    # consolidado em texto CSV, para a administradora lancar os valores na cota condominial
    # ponto e virgula entre os campos e virgula decimal: abre direto em planilha em portugues
    linhas = ["fatura;unidade;bloco;mes;sessoes;kwh;tarifa;taxa_admin;total;status;vencimento"]
    for linha in consolidado_do_mes(mes):
        campos = [str(linha["fatura"]), linha["unidade"], linha["bloco"], mes, str(linha["sessoes"]),
                  formato.decimal(linha["kwh"], 2), formato.decimal(linha["tarifa"], 2),
                  formato.decimal(linha["taxa"], 2), formato.decimal(linha["total"], 2),
                  linha["status"], linha["vencimento"]]
        linhas.append(";".join(campos))
    return "\n".join(linhas) + "\n"


def exportar_consolidado(mes: str) -> dict:
    # grava o CSV do consolidado na pasta de dados (so para mes fechado)
    if len(dados.faturas_do_mes(mes)) == 0:
        return {"ok": False, "mensagem": f"O mês {mes} ainda não foi fechado.", "arquivo": ""}
    arquivo = dados.PASTA_DADOS + "/consolidado_" + mes + ".csv"
    # "utf-8-sig" marca o arquivo para a planilha reconhecer os acentos
    with open(arquivo, "w", encoding="utf-8-sig") as arq:
        arq.write(consolidado_em_csv(mes))
    return {"ok": True, "mensagem": f"Consolidado de {mes} gravado em {arquivo}.", "arquivo": arquivo}


def previa_do_mes(mes: str) -> list:
    # mes aberto: mostra as duas opcoes de fechamento, sem taxa e com taxa
    config = dados.carregar_config()
    linhas = []
    for unidade in dados.carregar_tabela("units"):
        sem_taxa = rateio.calcular_fatura(unidade["id"], mes, config["tarifa_kwh"], 0.0,
                                          config["cobrar_taxa_sem_uso"])
        com_taxa = rateio.calcular_fatura(unidade["id"], mes, config["tarifa_kwh"],
                                          config["taxa_admin"], config["cobrar_taxa_sem_uso"])
        linhas.append({
            "unidade": unidade["name"],
            "bloco": unidade["block"],
            "sessoes": sem_taxa["sessoes"],
            "kwh": sem_taxa["total_kwh"],
            "total_sem_taxa": sem_taxa["total_value"],
            "total_com_taxa": com_taxa["total_value"]
        })
    return linhas


def total_da_coluna(linhas: list, campo: str) -> float:
    soma = 0.0
    for linha in linhas:
        soma += linha[campo]
    return round(soma, 2)


def listar_alertas(mes: str) -> list:
    return alertas.gerar_alertas(mes, dados.hoje_texto())


def painel_do_mes(mes: str) -> dict:
    resumo = rateio.resumo_do_mes(mes)
    painel = {
        "mes": mes,
        "resumo": resumo,
        "ranking": rateio.consumo_por_unidade(mes),
        "alertas": listar_alertas(mes),
        "config": dados.carregar_config(),
        "unidades_inadimplentes": len(unidades_inadimplentes())
    }
    if resumo["fechado"]:
        painel["consolidado"] = consolidado_do_mes(mes)
        painel["previa"] = []
    else:
        painel["consolidado"] = []
        painel["previa"] = previa_do_mes(mes)
    return painel


def unidades_inadimplentes() -> list:
    resultado = []
    for unidade in dados.carregar_tabela("units"):
        if rateio.unidade_inadimplente(unidade["id"], dados.hoje_texto()):
            resultado.append(unidade)
    return resultado


def faturas_pendentes() -> list:
    unidades = dados.carregar_tabela("units")
    linhas = []
    for fatura in dados.filtrar_registros("invoices", "status", "PENDING"):
        unidade = dados.buscar(unidades, "id", fatura["unit_id"])
        linhas.append({"fatura": fatura["id"], "unidade": unidade["name"], "mes": fatura["month"],
                       "total": fatura["total_value"], "vencimento": fatura["vencimento"]})
    return linhas


def conciliacao(mes: str) -> list:
    return telemetria.conciliar_sems(mes)


def auditar(invoice_id: int) -> dict:
    return rateio.auditar_fatura(invoice_id)


def indicadores_da_sprint1() -> list:
    # os quatro KPIs definidos na Sprint 1, com o que o protótipo consegue medir
    faturas = rateio.conferir_faturas()
    previsao = ia_previsao.carregar_previsao()
    modelo = "modelo ainda não treinado"
    if previsao != {} and "analise_do_limite" in previsao:
        limite = previsao["analise_do_limite"]
        modelo = (f"{formato.percentual(limite['modelo_por_dia'], 1)} por dia e "
                  f"{formato.percentual(limite['modelo_por_semana'], 1)} por semana")
    return [
        {"indicador": "Precisão do faturamento", "meta": "100%",
         "resultado": formato.percentual(faturas["precisao"], 0),
         "como": f"auditoria: {faturas['conferem']} de {faturas['faturas']} faturas conferem com as sessões"},
        {"indicador": "Precisão do modelo preditivo", "meta": "> 85%",
         "resultado": modelo,
         "como": "período de teste com dados simulados; ver Previsão de Demanda"},
        {"indicador": "Disponibilidade da plataforma", "meta": "> 99%",
         "resultado": "não medido",
         "como": "exige operação contínua em produção"},
        {"indicador": "Margem de erro de leitura RFID", "meta": "< 1%",
         "resultado": "não medido",
         "como": "exige o leitor físico do carregador"}
    ]


# ----- SUBALGORITMOS DE ACAO
def fechar_mes(mes: str, com_taxa: bool) -> dict:
    return rateio.fechar_mes(mes, com_taxa)


def registrar_pagamento(invoice_id: int) -> dict:
    if not rateio.registrar_pagamento(invoice_id):
        return {"ok": False, "mensagem": "Fatura não encontrada ou não está pendente."}
    # pagamento em dia libera os cartoes da unidade na mesma hora
    bloqueios = rateio.atualizar_bloqueios(dados.hoje_texto())
    mensagem = f"Pagamento da fatura {invoice_id} registrado."
    if bloqueios["desbloqueados"] > 0:
        mensagem += f" {bloqueios['desbloqueados']} cartão(ões) desbloqueado(s)."
    return {"ok": True, "mensagem": mensagem}


def atualizar_bloqueios() -> dict:
    return rateio.atualizar_bloqueios(dados.hoje_texto())


def alterar_configuracao(tarifa: float, taxa: float, cobrar_taxa: bool) -> dict:
    if tarifa <= 0:
        return {"ok": False, "mensagem": "A tarifa precisa ser maior que zero."}
    if taxa < 0:
        return {"ok": False, "mensagem": "A taxa não pode ser negativa."}
    config = dados.carregar_config()
    config["tarifa_kwh"] = tarifa
    config["taxa_admin"] = taxa
    config["cobrar_taxa"] = cobrar_taxa
    dados.salvar_config(config)
    dados.registrar_evento("CONFIG_ALTERADA",
                           f"tarifa {formato.reais(tarifa)}/kWh, taxa {formato.reais(taxa)}, cobrar_taxa={cobrar_taxa}")
    return {"ok": True, "mensagem": "Configuração gravada."}


# ----- SUBALGORITMOS DO SIMULADOR DE RATEIO
def simular_rateio(kwh: float, tarifa: float, taxa: float) -> dict:
    return rateio.comparar_com_e_sem_taxa(kwh, tarifa, taxa)


def cenarios_de_rateio() -> list:
    # exemplos prontos: o registro do README da Sprint 1 e o exemplo do pitch
    return [
        {"nome": "Exemplo da Sprint 1 (fatura 9001)", "kwh": 120.0, "tarifa": 0.95, "taxa": 0.0},
        {"nome": "Exemplo do pitch (Apto 42)", "kwh": 12.4, "tarifa": 0.95, "taxa": 2.0}
    ]


# ----- SUBALGORITMOS DE CADASTRO
def listar_cadastros() -> dict:
    linhas_usuarios = []
    for usuario in dados.carregar_tabela("users"):
        linhas_usuarios.append({"id": usuario["id"], "nome": usuario["name"], "email": usuario["email"],
                                "unidade": nome_da_unidade(usuario["unit_id"])})
    return {"unidades": dados.carregar_tabela("units"), "usuarios": linhas_usuarios,
            "cartoes": dados.cartoes_detalhados(), "carregadores": dados.carregar_tabela("chargers")}


def cadastrar_unidade(nome: str, bloco: str) -> dict:
    if nome.strip() == "" or bloco.strip() == "":
        return {"ok": False, "mensagem": "Informe o nome e o bloco."}
    unidade = dados.cadastrar_unidade(nome.strip(), bloco.strip())
    return {"ok": True, "mensagem": f"Unidade {unidade['name']} cadastrada com id {unidade['id']}."}


def cadastrar_usuario(unit_id: int, nome: str, email: str) -> dict:
    if nome.strip() == "":
        return {"ok": False, "mensagem": "Informe o nome."}
    usuario = dados.cadastrar_usuario(unit_id, nome.strip(), email.strip())
    if usuario == {}:
        return {"ok": False, "mensagem": "Unidade não encontrada."}
    return {"ok": True, "mensagem": f"Usuário {usuario['name']} cadastrado com id {usuario['id']}."}


def cadastrar_cartao(uid: str, user_id: int) -> dict:
    if uid.strip() == "":
        return {"ok": False, "mensagem": "Informe o UID do cartão."}
    return dados.cadastrar_cartao(uid.strip().upper(), user_id)
