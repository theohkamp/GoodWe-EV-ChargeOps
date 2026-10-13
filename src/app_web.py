"""
Autor.....: Equipe EV ChargeOps (RM573133, RM571998, RM568867, RM574003)
Assunto...: EV ChargeOps - interface web
Problema..: Ponto de entrada do painel web (gestor e morador).
            Executar a partir da raiz do repositorio:  streamlit run src/app_web.py

            O Streamlit executa este arquivo de novo, do inicio ao fim, a cada clique.
            Por isso as telas apenas chamam os controllers, que consultam o banco de dados.
"""
from view import view_web

# ----- PROGRAMA PRINCIPAL
view_web.mostrar_aplicacao()
