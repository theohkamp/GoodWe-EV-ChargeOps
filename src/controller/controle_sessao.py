"""
Autor.....: Equipe EV ChargeOps (RM573133, RM571998, RM568867, RM574003)
Assunto...: CONTROLLER - sessoes de recarga e base de demonstracao
Problema..: Disparar a simulacao de uma sessao no carregador e (re)criar a base
"""
from model import carga_inicial
from model import dados
from model import ia_previsao
from model import rateio
from model import telemetria

# ----- CONSTANTES
DURACAO_MINIMA = 10
DURACAO_MAXIMA = 480


# ----- SUBALGORITMOS
def opcoes_de_sessao() -> dict:
    # cartoes e carregadores que as telas oferecem para iniciar uma sessao
    cartoes = dados.cartoes_detalhados()
    rotulos = []
    for cartao in cartoes:
        rotulos.append(f"{cartao['uid']} | {cartao['usuario']} | {cartao['unidade']} | {cartao['situacao']}")
    return {"cartoes": cartoes, "rotulos": rotulos, "carregadores": dados.carregar_tabela("chargers")}


def primeiro_cartao_bloqueado() -> str:
    for cartao in dados.carregar_tabela("rfid_cards"):
        if not cartao["status"]:
            return cartao["uid"]
    return ""


def iniciar_sessao(uid: str, charger_id: str, duracao_min: int, forcar_interrupcao: bool) -> dict:
    if duracao_min < DURACAO_MINIMA or duracao_min > DURACAO_MAXIMA:
        return {"valido": False,
                "mensagem": f"A duração deve ficar entre {DURACAO_MINIMA} e {DURACAO_MAXIMA} minutos."}
    # se o carregador ainda esta em uso, a nova sessao entra na fila e comeca quando ele liberar
    inicio = telemetria.proximo_horario_livre(charger_id)
    resultado = telemetria.simular_sessao(uid, charger_id, inicio, duracao_min, forcar_interrupcao)
    resultado["valido"] = True
    return resultado


def recriar_base() -> dict:
    # gera o condominio de exemplo e ja deixa o modelo de previsao treinado
    resumo = carga_inicial.gerar_base()
    ia_previsao.executar_previsao_completa()
    return resumo


def preparar_sistema() -> None:
    # chamada sempre que o sistema abre (console e web)
    # primeira execucao: cria a base de demonstracao
    if not dados.base_existe():
        recriar_base()
    # bloqueio automatico de inadimplentes (Sprint 1): os cartoes sao conferidos
    # contra as faturas vencidas sem depender de o gestor apertar um botao
    rateio.atualizar_bloqueios(dados.hoje_texto())
    # a previsao vale para o dia em que foi gerada: em um novo dia, o modelo e treinado de novo
    # (os 10 primeiros caracteres de "gerado_em" sao a data, AAAA-MM-DD)
    previsao = ia_previsao.carregar_previsao()
    if previsao == {} or previsao["gerado_em"][0:10] != dados.hoje_texto():
        ia_previsao.executar_previsao_completa()
