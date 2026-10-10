"""
Autor.....: Equipe EV ChargeOps (RM573133, RM571998, RM571913, RM568867, RM574003)
Assunto...: EV ChargeOps - modo console
Problema..: Ponto de entrada do protótipo em menu de terminal.
            Executar a partir da raiz do repositorio:  python src/main.py

            Arquitetura MVC:
              view/        telas (console e web) e graficos
              controller/  recebe os pedidos das telas e aciona os modelos
              model/       dados, regras de rateio, telemetria, alertas e IA
"""
from view import view_console

# ----- PROGRAMA PRINCIPAL
view_console.menu_principal()
