"""
Autor.....: Equipe EV ChargeOps (RM573133, RM571998, RM568867, RM574003)
Assunto...: MODEL - IA frente 1: previsao de demanda e deteccao de padroes
Problema..: Usar o historico de sessoes para prever a demanda diaria (regressao),
            estimar o risco de sobrecarga do quadro eletrico (regressao logistica)
            e sugerir janelas de recarga fora do pico
"""
import json
import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, LogisticRegression, Ridge
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score, mean_absolute_error,
                             mean_squared_error, precision_score, r2_score, recall_score)
from sklearn.model_selection import GridSearchCV, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from model import dados

# ----- CONSTANTES
ARQUIVO_CSV = "dados/sessoes_historico.csv"
ARQUIVO_PREVISAO = "dados/previsao_atual.json"
# uma coluna 0/1 para cada dia da semana; domingo e a referencia (todas zero)
COLUNAS_DIAS = ["seg", "ter", "qua", "qui", "sex", "sab"]
COLUNAS_DEMANDA = ["indice_dia"] + COLUNAS_DIAS + ["kwh_ontem", "kwh_media_7d"]
COLUNAS_RISCO = COLUNAS_DIAS + ["kwh_ontem", "kwh_media_7d"]
ALPHAS_RIDGE = [0.01, 0.1, 1, 10, 100]
LIMITE_PROBABILIDADE = 0.7           # acima disso o dia entra como risco alto
LIMITE_DE_LACUNA = 2                 # ate 2 dias seguidos sem sessao contam como consumo zero


# ----- SUBALGORITMOS DE PREPARACAO DOS DADOS
def exportar_sessoes_csv() -> pd.DataFrame:
    # tabela de sessoes em formato de planilha (uma linha por sessao)
    mapa = dados.mapa_cartao_unidade()
    colunas = {"session_id": [], "unit_id": [], "rfid_uid": [], "charger_id": [], "data": [],
               "hora_inicio": [], "dia_semana": [], "duracao_min": [], "kwh": [],
               "potencia_media_kw": [], "pico_kw": [], "interrompida": []}
    for sessao in dados.ordenar(dados.carregar_tabela("sessions"), "start_time", False):
        inicio = dados.texto_para_data(sessao["start_time"])
        fim = dados.texto_para_data(sessao["end_time"])
        unidade = 0
        if sessao["rfid_uid"] in mapa:
            unidade = mapa[sessao["rfid_uid"]]
        colunas["session_id"].append(sessao["id"])
        colunas["unit_id"].append(unidade)
        colunas["rfid_uid"].append(sessao["rfid_uid"])
        colunas["charger_id"].append(sessao["charger_id"])
        colunas["data"].append(inicio.strftime(dados.FORMATO_DATA))
        colunas["hora_inicio"].append(inicio.hour)
        colunas["dia_semana"].append(inicio.weekday())
        colunas["duracao_min"].append(int((fim - inicio).total_seconds() / 60))
        colunas["kwh"].append(sessao["kwh_delivered"])
        colunas["potencia_media_kw"].append(sessao["potencia_media_kw"])
        colunas["pico_kw"].append(sessao["pico_kw"])
        colunas["interrompida"].append(int(sessao["interrompida"]))
    tabela = pd.DataFrame(colunas)
    tabela.to_csv(ARQUIVO_CSV, index=False)
    return tabela


def energia_por_hora() -> dict:
    # {"AAAA-MM-DD": lista com 24 valores}. Cada valor e a energia entregue naquela
    # hora (kWh), que equivale a potencia media da hora (kW) somando os carregadores
    tabela = {}
    for sessao in dados.carregar_tabela("sessions"):
        inicio = dados.texto_para_data(sessao["start_time"])
        fim = dados.texto_para_data(sessao["end_time"])
        minutos = int((fim - inicio).total_seconds() / 60)
        if minutos <= 0:
            continue
        energia_por_minuto = sessao["kwh_delivered"] / minutos
        momento = inicio
        for m in range(minutos):
            dia = momento.strftime(dados.FORMATO_DATA)
            if dia not in tabela:
                tabela[dia] = [0.0] * 24
            tabela[dia][momento.hour] += energia_por_minuto
            momento = momento + timedelta(minutes=1)
    return tabela


def fim_do_historico(datas: list) -> datetime:
    # ultimo dia que entra na serie diaria. "datas" traz os dias com sessao, em ordem.
    # Duas regras de qualidade dos dados:
    # 1) o dia de hoje fica fora, porque ainda nao terminou;
    # 2) um intervalo maior que LIMITE_DE_LACUNA dias sem nenhuma sessao e falta de coleta,
    #    e nao consumo zero: a serie termina antes dele.
    hoje = dados.hoje_texto()
    ultimo = datetime.strptime(datas[0], dados.FORMATO_DATA)
    for texto in datas:
        dia = datetime.strptime(texto, dados.FORMATO_DATA)
        dias_vazios = (dia - ultimo).days - 1
        if texto >= hoje or dias_vazios > LIMITE_DE_LACUNA:
            break
        ultimo = dia
    return ultimo


def montar_tabela_diaria() -> pd.DataFrame:
    # serie temporal diaria: uma linha por dia, do primeiro dia com sessao ate o fim do historico
    config = dados.carregar_config()
    sessoes = pd.read_csv(ARQUIVO_CSV)
    horas = energia_por_hora()
    datas = sessoes["data"].values
    kwh = sessoes["kwh"].values

    kwh_do_dia = {}
    sessoes_do_dia = {}
    for i in range(len(sessoes)):
        if datas[i] not in kwh_do_dia:
            kwh_do_dia[datas[i]] = 0.0
            sessoes_do_dia[datas[i]] = 0
        kwh_do_dia[datas[i]] += kwh[i]
        sessoes_do_dia[datas[i]] += 1

    primeiro = datetime.strptime(datas[0], dados.FORMATO_DATA)
    ultimo = fim_do_historico(datas)
    total_dias = (ultimo - primeiro).days + 1

    colunas = {"data": [], "indice_dia": [], "dia_semana": [], "fim_de_semana": [],
               "kwh_total": [], "n_sessoes": [], "pico_kw": [], "sobrecarga": [],
               "kwh_ontem": [], "kwh_media_7d": []}
    for nome in COLUNAS_DIAS:
        colunas[nome] = []

    historico = []                      # kWh dos dias ja percorridos
    for indice in range(total_dias):
        dia = primeiro + timedelta(days=indice)
        texto = dia.strftime(dados.FORMATO_DATA)
        total = 0.0
        quantidade = 0
        if texto in kwh_do_dia:
            total = kwh_do_dia[texto]
            quantidade = sessoes_do_dia[texto]
        pico = 0.0
        if texto in horas:
            pico = max(horas[texto])

        colunas["data"].append(texto)
        colunas["indice_dia"].append(indice)
        colunas["dia_semana"].append(dia.weekday())
        colunas["fim_de_semana"].append(int(dia.weekday() >= 5))
        colunas["kwh_total"].append(round(total, 2))
        colunas["n_sessoes"].append(quantidade)
        colunas["pico_kw"].append(round(pico, 2))
        # alvo da classificacao: a potencia media de alguma hora passou do limite?
        colunas["sobrecarga"].append(int(pico > config["limite_quadro_kw"]))
        for d in range(len(COLUNAS_DIAS)):
            colunas[COLUNAS_DIAS[d]].append(int(dia.weekday() == d))

        # variaveis defasadas: o passado recente ajuda a explicar o dia
        if len(historico) >= 1:
            colunas["kwh_ontem"].append(historico[len(historico) - 1])
        else:
            colunas["kwh_ontem"].append(None)
        if len(historico) >= 7:
            soma = 0.0
            for k in range(1, 8):
                soma += historico[len(historico) - k]
            colunas["kwh_media_7d"].append(round(soma / 7, 2))
        else:
            colunas["kwh_media_7d"].append(None)
        historico.append(round(total, 2))
    return pd.DataFrame(colunas)


# ----- SUBALGORITMOS DO MODELO DE DEMANDA (REGRESSAO)
def calcular_metricas(y_real, y_previsto) -> dict:
    mae = mean_absolute_error(y_real, y_previsto)
    rmse = np.sqrt(mean_squared_error(y_real, y_previsto))
    r2 = r2_score(y_real, y_previsto)
    # erro relativo: erro absoluto medio dividido pela media do valor real
    erro_relativo = mae / np.mean(y_real)
    return {"mae": round(float(mae), 2), "rmse": round(float(rmse), 2),
            "r2": round(float(r2), 3), "erro_relativo": round(float(erro_relativo), 3)}


def montar_pipeline(modelo) -> Pipeline:
    # as mesmas tres etapas para qualquer modelo, sempre nesta ordem
    return Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="median")),     # preenche os primeiros dias
        ("scaler", StandardScaler()),                      # coloca as colunas na mesma escala
        ("model", modelo)
    ])


def treinar_modelo_demanda(tabela: pd.DataFrame) -> dict:
    X = tabela[COLUNAS_DEMANDA].values
    y = tabela["kwh_total"].values
    # divisao temporal: treina no passado (80%) e avalia no futuro (20%)
    corte = int(len(tabela) * 0.8)
    X_train = X[:corte]
    X_test = X[corte:]
    y_train = y[:corte]
    y_test = y[corte:]

    # modelo 1: regressao linear multipla
    linear = montar_pipeline(LinearRegression())
    linear.fit(X_train, y_train)
    previsto_linear = linear.predict(X_test)

    # modelo 2: Ridge, com busca do melhor alpha por validacao cruzada
    grid = GridSearchCV(estimator=montar_pipeline(Ridge()), param_grid={"model__alpha": ALPHAS_RIDGE},
                        cv=5, scoring="neg_mean_squared_error")
    grid.fit(X_train, y_train)
    previsto_ridge = grid.predict(X_test)

    metricas_linear = calcular_metricas(y_test, previsto_linear)
    metricas_ridge = calcular_metricas(y_test, previsto_ridge)

    # fica o modelo com menor erro (RMSE) no periodo de teste
    if metricas_ridge["rmse"] <= metricas_linear["rmse"]:
        escolhido = "Ridge"
        modelo = grid
        previsto = previsto_ridge
        metricas = metricas_ridge
    else:
        escolhido = "Regressão Linear"
        modelo = linear
        previsto = previsto_linear
        metricas = metricas_linear

    # listas simples (texto e float) para gravar em JSON e desenhar os graficos
    datas_teste = []
    y_teste = []
    y_previsto = []
    for i in range(len(y_test)):
        datas_teste.append(str(tabela["data"].values[corte + i]))
        y_teste.append(round(float(y_test[i]), 2))
        y_previsto.append(round(float(previsto[i]), 2))

    return {
        "modelo": modelo,
        "escolhido": escolhido,
        "melhor_alpha": grid.best_params_["model__alpha"],
        "metricas": metricas,
        "metricas_linear": metricas_linear,
        "metricas_ridge": metricas_ridge,
        "dias_treino": corte,
        "dias_teste": len(tabela) - corte,
        "datas_teste": datas_teste,
        "y_teste": y_teste,
        "y_previsto": y_previsto
    }


# ----- SUBALGORITMOS DO MODELO DE RISCO (CLASSIFICACAO)
def treinar_modelo_risco(tabela: pd.DataFrame) -> dict:
    # os 7 primeiros dias nao tem media movel; ficam fora do treino
    validos = tabela[7:]
    X = validos[COLUNAS_RISCO].values
    y = validos["sobrecarga"].values
    # com uma unica classe nao ha o que aprender
    if sum(y) == 0 or sum(y) == len(y):
        return {"treinado": False}

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)
    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_test = scaler.transform(X_test)
    modelo = LogisticRegression(max_iter=1000)
    modelo.fit(X_train, y_train)
    y_pred = modelo.predict(X_test)
    matriz = confusion_matrix(y_test, y_pred)
    return {
        "treinado": True,
        "modelo": modelo,
        "scaler": scaler,
        "amostras": len(validos),
        "dias_com_sobrecarga": int(sum(y)),
        "acuracia": round(float(accuracy_score(y_test, y_pred)), 3),
        "precisao": round(float(precision_score(y_test, y_pred, zero_division=0)), 3),
        "recall": round(float(recall_score(y_test, y_pred, zero_division=0)), 3),
        "f1": round(float(f1_score(y_test, y_pred, zero_division=0)), 3),
        "matriz_confusao": [[int(matriz[0][0]), int(matriz[0][1])],
                            [int(matriz[1][0]), int(matriz[1][1])]]
    }


# ----- SUBALGORITMOS DA CURVA DE CARGA E DA JANELA DE RECARGA
def montar_curva_de_carga(tabela: pd.DataFrame) -> list:
    # matriz 7 x 24: potencia media (kW) por dia da semana e hora do dia
    horas = energia_por_hora()
    soma = []
    for d in range(7):
        soma.append([0.0] * 24)
    dias_contados = [0] * 7
    datas = tabela["data"].values
    dias_semana = tabela["dia_semana"].values
    for i in range(len(tabela)):
        d = int(dias_semana[i])
        dias_contados[d] += 1
        if datas[i] in horas:
            for h in range(24):
                soma[d][h] += horas[datas[i]][h]
    curva = []
    for d in range(7):
        linha = []
        for h in range(24):
            media = 0.0
            if dias_contados[d] > 0:
                media = soma[d][h] / dias_contados[d]
            linha.append(round(media, 2))
        curva.append(linha)
    return curva


def demanda_da_janela(curva: list, dia_semana: int, inicio: int, duracao_h: int) -> dict:
    # soma e maior valor da curva dentro da janela; se passar da meia-noite,
    # continua no dia seguinte (operador % faz a volta do relogio e da semana)
    soma = 0.0
    maior = 0.0
    for h in range(inicio, inicio + duracao_h):
        dia = dia_semana
        if h >= 24:
            dia = (dia_semana + 1) % 7
        valor = curva[dia][h % 24]
        soma += valor
        if valor > maior:
            maior = valor
    return {"soma": soma, "maior": maior}


def melhor_inicio(curva: list, dia_semana: int, duracao_h: int, horas_candidatas: list) -> int:
    # varredura: fica o inicio cuja janela tem a menor demanda media
    escolhido = horas_candidatas[0]
    menor_soma = -1.0
    for inicio in horas_candidatas:
        soma = demanda_da_janela(curva, dia_semana, inicio, duracao_h)["soma"]
        if menor_soma < 0 or soma < menor_soma:
            menor_soma = soma
            escolhido = inicio
    return escolhido


def sugerir_janela(curva: list, dia_semana: int, duracao_h: int) -> dict:
    config = dados.carregar_config()
    # janela do dia: comeca entre 6h e 17h; janela da noite: comeca entre 18h e 23h
    horas_dia = []
    for h in range(6, 18):
        horas_dia.append(h)
    horas_noite = []
    for h in range(18, 24):
        horas_noite.append(h)
    inicio_dia = melhor_inicio(curva, dia_semana, duracao_h, horas_dia)
    inicio_noite = melhor_inicio(curva, dia_semana, duracao_h, horas_noite)
    janela_dia = demanda_da_janela(curva, dia_semana, inicio_dia, duracao_h)
    janela_noite = demanda_da_janela(curva, dia_semana, inicio_noite, duracao_h)
    # maior demanda da janela noturna, somando mais um carregador ligado
    pico_com_recarga = janela_noite["maior"] + config["potencia_max_kw"]
    # hora de pico do dia, para o usuario saber o que evitar
    hora_pico = 0
    for h in range(24):
        if curva[dia_semana][h] > curva[dia_semana][hora_pico]:
            hora_pico = h
    return {
        "dia_semana": dados.NOMES_DOS_DIAS[dia_semana],
        "duracao_h": duracao_h,
        "dia_inicio": inicio_dia,
        "dia_fim": (inicio_dia + duracao_h) % 24,
        "dia_demanda_kw": round(janela_dia["soma"] / duracao_h, 2),
        "noite_inicio": inicio_noite,
        "noite_fim": (inicio_noite + duracao_h) % 24,
        "noite_demanda_kw": round(janela_noite["soma"] / duracao_h, 2),
        "pico_com_recarga_kw": round(pico_com_recarga, 2),
        "dentro_do_limite": pico_com_recarga <= config["limite_quadro_kw"],
        "hora_pico": hora_pico,
        "demanda_no_pico_kw": curva[dia_semana][hora_pico]
    }


# ----- SUBALGORITMO DE PREVISAO DOS PROXIMOS DIAS
def prever_proximos_dias(tabela: pd.DataFrame, demanda: dict, risco: dict, curva: list,
                         n_dias: int) -> list:
    config = dados.carregar_config()
    datas = tabela["data"].values
    ultimo_dia = datetime.strptime(datas[len(datas) - 1], dados.FORMATO_DATA)
    ultimo_indice = int(tabela["indice_dia"].values[len(tabela) - 1])
    historico = list(tabela["kwh_total"].values)
    # a previsao mostrada comeca hoje. Se o historico terminou ha mais dias (base parada),
    # os dias do intervalo tambem sao previstos, mas so para alimentar os dias seguintes
    hoje = datetime.strptime(dados.hoje_texto(), dados.FORMATO_DATA)
    dias_pulados = (hoje - ultimo_dia).days - 1
    if dias_pulados < 0:
        dias_pulados = 0
    previsoes = []
    for k in range(1, dias_pulados + n_dias + 1):
        dia = ultimo_dia + timedelta(days=k)
        ontem = historico[len(historico) - 1]
        soma = 0.0
        for j in range(1, 8):
            soma += historico[len(historico) - j]
        media_7d = soma / 7
        dias = []
        for d in range(len(COLUNAS_DIAS)):
            dias.append(int(dia.weekday() == d))

        linha_demanda = [ultimo_indice + k] + dias + [ontem, media_7d]
        kwh_previsto = float(demanda["modelo"].predict(np.array([linha_demanda]))[0])
        if kwh_previsto < 0:
            kwh_previsto = 0.0

        probabilidade = 0.0
        if risco["treinado"]:
            linha_risco = np.array([dias + [ontem, media_7d]])
            linha_risco = risco["scaler"].transform(linha_risco)
            # predict_proba devolve [P(sem sobrecarga), P(sobrecarga)]
            probabilidade = float(risco["modelo"].predict_proba(linha_risco)[0][1])

        pico_tipico = max(curva[dia.weekday()])
        if k > dias_pulados:
            previsoes.append({
                "data": dia.strftime(dados.FORMATO_DATA),
                "dia_semana": dados.NOMES_DOS_DIAS[dia.weekday()],
                "kwh_previsto": round(kwh_previsto, 1),
                "prob_sobrecarga": round(probabilidade, 3),
                "pico_tipico_kw": round(pico_tipico, 2),
                # SOBRECARGA_PREVISTA = (PICO_TIPICO > LIMITE) OR (PROBABILIDADE >= 0,7)
                "risco_alto": pico_tipico > config["limite_quadro_kw"] or probabilidade >= LIMITE_PROBABILIDADE
            })
        # a previsao de um dia vira o "ontem" do dia seguinte
        historico.append(kwh_previsto)
    return previsoes


# ----- SUBALGORITMOS DA ANALISE DO LIMITE DOS DADOS
def precisao_das_previsoes(real: list, previsto: list) -> float:
    # 1 - erro relativo: soma dos erros absolutos dividida pela soma dos valores reais
    soma_erro = 0.0
    soma_real = 0.0
    for i in range(len(real)):
        soma_erro += abs(real[i] - previsto[i])
        soma_real += real[i]
    if soma_real == 0:
        return 0.0
    return 1 - soma_erro / soma_real


def analisar_limite_dos_dados(tabela: pd.DataFrame, corte: int, previsto_modelo: list) -> dict:
    # compara o modelo com duas referencias para mostrar de onde vem o erro
    kwh = list(tabela["kwh_total"].values)
    dias = list(tabela["dia_semana"].values)
    recargas = list(tabela["n_sessoes"].values)
    real = kwh[corte:]

    # referencia 1 (teto do calendario): a media real de cada dia da semana,
    # calculada com o historico inteiro, inclusive o periodo de teste.
    # Nenhum modelo que so conhece o calendario consegue fazer melhor que isso.
    soma = [0.0] * 7
    quantidade = [0] * 7
    for i in range(len(kwh)):
        d = int(dias[i])
        soma[d] += kwh[i]
        quantidade[d] += 1
    gabarito = []
    for i in range(corte, len(kwh)):
        d = int(dias[i])
        gabarito.append(soma[d] / quantidade[d])

    # referencia 2: se o numero de recargas do dia fosse conhecido de antemao
    # (por exemplo, com agendamento), bastaria multiplicar pela media por recarga
    total_kwh = 0.0
    total_recargas = 0
    for i in range(corte):
        total_kwh += kwh[i]
        total_recargas += recargas[i]
    media_por_recarga = total_kwh / total_recargas
    com_contagem = []
    for i in range(corte, len(kwh)):
        com_contagem.append(recargas[i] * media_por_recarga)

    # mesma previsao do modelo, somada em blocos de 7 dias (visao semanal)
    erros_semana = []
    for inicio in range(0, len(real) - 6, 7):
        soma_real = 0.0
        soma_prevista = 0.0
        for i in range(inicio, inicio + 7):
            soma_real += real[i]
            soma_prevista += previsto_modelo[i]
        if soma_real > 0:
            erros_semana.append(abs(soma_prevista - soma_real) / soma_real)
    precisao_semanal = 0.0
    if len(erros_semana) > 0:
        precisao_semanal = 1 - sum(erros_semana) / len(erros_semana)

    return {
        "modelo_por_dia": round(float(precisao_das_previsoes(real, previsto_modelo)), 3),
        "teto_do_calendario": round(float(precisao_das_previsoes(real, gabarito)), 3),
        "sabendo_as_recargas": round(float(precisao_das_previsoes(real, com_contagem)), 3),
        "modelo_por_semana": round(float(precisao_semanal), 3),
        "semanas_de_teste": len(erros_semana),
        "media_kwh_por_recarga": round(float(media_por_recarga), 1)
    }


# ----- SUBALGORITMO PRINCIPAL
def executar_previsao_completa() -> dict:
    # pipeline completo: dados -> treino -> avaliacao -> previsao -> arquivo JSON
    config = dados.carregar_config()
    exportar_sessoes_csv()
    tabela = montar_tabela_diaria()
    demanda = treinar_modelo_demanda(tabela)
    risco = treinar_modelo_risco(tabela)
    curva = montar_curva_de_carga(tabela)
    previsoes = prever_proximos_dias(tabela, demanda, risco, curva, 7)

    metricas = demanda["metricas"]

    resultado = {
        "gerado_em": dados.agora_texto(),
        "historico_ate": tabela["data"].values[len(tabela) - 1],
        "dias_de_historico": len(tabela),
        "dias_treino": demanda["dias_treino"],
        "dias_teste": demanda["dias_teste"],
        "modelo_escolhido": demanda["escolhido"],
        "melhor_alpha": demanda["melhor_alpha"],
        "metricas": metricas,
        "metricas_linear": demanda["metricas_linear"],
        "metricas_ridge": demanda["metricas_ridge"],
        # "precisao" do KPI da Sprint 1 medida como 1 - erro relativo no periodo de teste
        "precisao_estimada": round(1 - metricas["erro_relativo"], 3),
        "datas_teste": demanda["datas_teste"],
        "y_teste": demanda["y_teste"],
        "y_previsto": demanda["y_previsto"],
        "limite_quadro_kw": config["limite_quadro_kw"],
        "curva_de_carga": curva,
        "previsao_7_dias": previsoes,
        "risco": {"treinado": risco["treinado"]}
    }
    # de onde vem o erro: o modelo comparado com o teto dos dados
    resultado["analise_do_limite"] = analisar_limite_dos_dados(tabela, demanda["dias_treino"],
                                                               demanda["y_previsto"])
    if risco["treinado"]:
        for chave in ("amostras", "dias_com_sobrecarga", "acuracia", "precisao", "recall",
                      "f1", "matriz_confusao"):
            resultado["risco"][chave] = risco[chave]

    with open(ARQUIVO_PREVISAO, "w", encoding="utf-8") as arq:
        arq.write(json.dumps(resultado, indent=4, ensure_ascii=False))
    dados.registrar_evento("MODELO_TREINADO",
                           f"{resultado['modelo_escolhido']} (R2 {metricas['r2']}, MAE {metricas['mae']} kWh)")
    return resultado


def carregar_previsao() -> dict:
    # as telas leem o ultimo resultado gravado, sem treinar de novo
    if not os.path.exists(ARQUIVO_PREVISAO):
        return {}
    with open(ARQUIVO_PREVISAO, "r", encoding="utf-8") as arq:
        return json.loads(arq.read())
