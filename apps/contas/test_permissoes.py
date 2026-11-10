"""Varredura de permissões: percorre TODAS as rotas do sistema, não só os painéis.

Os outros testes conferem algumas telas de cada área. Este arquivo lê a lista de rotas do
Django e testa cada uma: o visitante vai para o login e cada perfil errado recebe 403.
Se alguém criar uma tela nova e esquecer o @perfil_requerido, um destes testes falha.

O perfil certo não é testado aqui (ele precisa de dados, e cada app já testa as suas telas).
Os números nas rotas (ex.: /turmas/999/) não existem: a permissão vem antes da busca no
banco, então o perfil errado recebe 403 mesmo assim.
"""

from django.test import TestCase
from django.urls import URLResolver, get_resolver, reverse

from .test_login import criar_usuarios

ALUNO, PROFESSOR, COORDENADOR = "ALUNO", "PROFESSOR", "COORDENADOR"
TODOS_DO_PORTAL = {ALUNO, PROFESSOR, COORDENADOR}

# Quem pode abrir cada área (namespace das rotas). O ADMIN não entra em nenhuma:
# ele usa só o Django Admin.
PERFIS_DA_AREA = {
    "aluno": {ALUNO},
    "professor": {PROFESSOR},
    "coordenacao": {COORDENADOR},
    "mensagens": TODOS_DO_PORTAL,
    "alertas": TODOS_DO_PORTAL,
    "videochamadas": {PROFESSOR, COORDENADOR},  # o aluno não participa das chamadas
}

# Em Relatórios cada rota tem o seu perfil.
PERFIS_DOS_RELATORIOS = {
    "inicio": {COORDENADOR},
    "meu_boletim": {ALUNO},
    "disciplina": {PROFESSOR},
    "boletim": {COORDENADOR},
    "turma": {COORDENADOR},
    "risco": {COORDENADOR},
    "alunos": {COORDENADOR},
}

# Rotas da API abertas a quem não entrou: o pedido do token e a documentação.
API_PUBLICA = {"token", "schema", "docs"}

# Áreas que não entram na varredura, e o motivo.
FORA_DA_VARREDURA = {
    "admin",  # o Django Admin tem a própria proteção (só is_staff)
    "contas",  # login, sair e redefinição de senha: públicas, testadas em test_login.py
}


def rotas_do_namespace(resolvedor, prefixo=""):
    """Lista (nome, parâmetros) de cada rota, descendo também nos include() sem namespace.

    Os parâmetros são os nomes que aparecem na rota, como "pk" em "turmas/<int:pk>/".
    Rotas com o mesmo nome (o DRF cria uma versão com ".json") aparecem uma vez só.
    """
    vistas = {}
    for item in resolvedor.url_patterns:
        if isinstance(item, URLResolver):
            vistas.update({n: p for n, p in rotas_do_namespace(item) if n not in vistas})
        elif item.name and item.name not in vistas:
            vistas[item.name] = list(item.pattern.regex.groupindex)
    return list(vistas.items())


def areas_do_sistema():
    """{namespace: [(nome, parâmetros), ...]} de todas as áreas ligadas em config/urls.py."""
    return {
        item.namespace: rotas_do_namespace(item)
        for item in get_resolver().url_patterns
        if isinstance(item, URLResolver) and item.namespace
    }


def endereco(namespace, nome, parametros):
    # 999 não existe no banco; "json" preenche o formato das rotas do DRF.
    valores = {p: "json" if p == "format" else 999 for p in parametros}
    return reverse(f"{namespace}:{nome}", kwargs=valores)


def rotas_das_telas(areas):
    """(namespace, nome, endereço, perfis permitidos, tem número na URL) de cada tela do portal."""
    for namespace, rotas in areas.items():
        if namespace in FORA_DA_VARREDURA or namespace == "api":
            continue
        for nome, parametros in rotas:
            if namespace == "relatorios":
                permitidos = PERFIS_DOS_RELATORIOS[nome]
            else:
                permitidos = PERFIS_DA_AREA[namespace]
            url = endereco(namespace, nome, parametros)
            yield namespace, nome, url, permitidos, bool(parametros)


class VarreduraTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuarios = criar_usuarios()
        cls.areas = areas_do_sistema()

    def rotas_das_telas(self):
        for namespace, nome, url, permitidos, _ in rotas_das_telas(self.areas):
            yield namespace, nome, url, permitidos

    def test_toda_area_tem_regra_de_permissao(self):
        """Área nova em config/urls.py precisa entrar no dicionário de perfis deste arquivo."""
        conhecidas = set(PERFIS_DA_AREA) | FORA_DA_VARREDURA | {"relatorios", "api"}
        self.assertEqual(set(self.areas) - conhecidas, set())
        rotas_dos_relatorios = {nome for nome, _ in self.areas["relatorios"]}
        self.assertEqual(rotas_dos_relatorios, set(PERFIS_DOS_RELATORIOS))

    def test_varredura_encontra_as_rotas(self):
        # Garante que a varredura não passa "vazia" por um erro na leitura das rotas.
        self.assertGreater(len(list(self.rotas_das_telas())), 50)

    def test_visitante_vai_para_o_login_em_todas_as_telas(self):
        login = reverse("contas:entrar")
        for namespace, nome, url, _ in self.rotas_das_telas():
            with self.subTest(rota=f"{namespace}:{nome}"):
                resposta = self.client.get(url)
                self.assertEqual(resposta.status_code, 302)
                self.assertTrue(resposta.url.startswith(f"{login}?next="))

    def test_perfil_errado_recebe_403_em_todas_as_telas(self):
        for perfil, usuario in self.usuarios.items():
            self.client.force_login(usuario)
            for namespace, nome, url, permitidos in self.rotas_das_telas():
                if perfil in permitidos:
                    continue
                with self.subTest(perfil=perfil, rota=f"{namespace}:{nome}"):
                    # GET e POST: as rotas que só aceitam POST também barram o perfil errado.
                    self.assertEqual(self.client.get(url).status_code, 403)
                    self.assertEqual(self.client.post(url).status_code, 403)

    def test_perfil_certo_nunca_recebe_403(self):
        # Com números que não existem, a resposta é 404, 405 ou um redirecionamento.
        for perfil, usuario in self.usuarios.items():
            self.client.force_login(usuario)
            for namespace, nome, url, permitidos in self.rotas_das_telas():
                if perfil not in permitidos:
                    continue
                with self.subTest(perfil=perfil, rota=f"{namespace}:{nome}"):
                    self.assertNotEqual(self.client.get(url).status_code, 403)

    def rotas_da_api(self):
        for nome, parametros in self.areas["api"]:
            if nome not in API_PUBLICA:
                yield nome, endereco("api", nome, parametros)

    def test_api_responde_401_para_quem_nao_se_identificou(self):
        for nome, url in self.rotas_da_api():
            with self.subTest(rota=f"api:{nome}"):
                self.assertEqual(self.client.get(url).status_code, 401)

    def test_api_responde_403_para_o_admin(self):
        self.client.force_login(self.usuarios["ADMIN"])
        for nome, url in self.rotas_da_api():
            with self.subTest(rota=f"api:{nome}"):
                self.assertEqual(self.client.get(url).status_code, 403)
