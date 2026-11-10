"""Paginação das listas da API: 20 itens por página, em ?pagina=2.

A resposta traz "count" (total de itens), "next" e "previous" (links das páginas vizinhas)
e "results" (os itens). ?tamanho=50 muda a quantidade por página, até 100.
"""

from rest_framework.pagination import PageNumberPagination


class Paginacao(PageNumberPagination):
    page_size = 20
    page_query_param = "pagina"
    page_size_query_param = "tamanho"
    max_page_size = 100
