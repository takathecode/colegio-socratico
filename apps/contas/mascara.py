"""Máscara do e-mail mostrado em "Esqueci minha senha".

A tela confirma para qual endereço o link vai, sem revelar o endereço inteiro a quem só
sabe a matrícula. Fica visível: a primeira e a última letra do usuário, a primeira letra
do domínio e a terminação (tudo o que vem depois do primeiro ponto do domínio).

    fulana.souza@gmail.com          ->  f**********a@g****.com
    jose@escola.edu.br              ->  j**e@e*****.edu.br
    ana.lima9@turma.exemplo.br      ->  a*******9@t****.exemplo.br
"""


def _mascarar_usuario(usuario):
    if len(usuario) <= 1:
        return usuario
    if len(usuario) == 2:
        # Só duas letras: mostrar as duas seria mostrar tudo, então a última vira "*".
        return usuario[0] + "*"
    return usuario[0] + "*" * (len(usuario) - 2) + usuario[-1]


def mascarar_email(email):
    """Devolve o e-mail com asteriscos. Texto sem "@" volta vazio (não há o que mostrar).

    Tudo em minúsculas: e-mail não diferencia maiúsculas, e a máscara fica sempre igual.
    """
    email = (email or "").strip().lower()
    usuario, arroba, dominio = email.rpartition("@")
    if not arroba or not usuario or not dominio:
        return ""
    # "aluno.escola.br" -> nome "aluno" (mascarado) e terminação ".escola.br" (visível).
    nome, ponto, resto = dominio.partition(".")
    terminacao = ponto + resto
    return f"{_mascarar_usuario(usuario)}@{nome[:1]}{'*' * (len(nome) - 1)}{terminacao}"
