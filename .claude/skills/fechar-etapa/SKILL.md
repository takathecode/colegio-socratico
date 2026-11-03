---
name: fechar-etapa
description: Use quando o usuário disser que uma etapa terminou ou pedir para "fechar a etapa", "finalizar", "revisar antes do commit". Verifica o projeto, atualiza o progresso no CLAUDE.md e sugere o commit.
---

# Fechar uma etapa do projeto

Execute na ordem e relate o resultado de cada item em uma lista curta.

1. **Verificação do Django**
   - `python manage.py check`
   - `python manage.py makemigrations --check --dry-run` (se houver migração pendente, crie-a e aplique com `migrate`)
   - `python manage.py test`
2. **Segurança**
   - Nenhuma senha, `DATABASE_URL`, `SECRET_KEY` ou chave do Supabase escrita no código.
   - `.env` continua no `.gitignore`; `.env.example` tem todas as variáveis novas (sem valores reais).
   - Nenhuma rota ou link de "cadastro/criar conta" foi criado.
   - Toda view nova tem `@login_required` e `@perfil_requerido`.
3. **Dependências**: se instalou algo novo, atualize o `requirements.txt` (`pip freeze > requirements.txt`).
4. **Progresso**: marque a etapa como concluída (`[x]`) na seção "Progresso" do `CLAUDE.md`
   e acrescente abaixo dela, em uma linha, qualquer decisão importante tomada.
5. **Resumo para a apresentação**: escreva 3 a 5 frases simples explicando o que foi feito
   e por quê, para os alunos usarem na documentação e na apresentação.
6. **Commit**: sugira uma mensagem no formato `feat(etapa-N): descrição curta` e os comandos
   `git add .` e `git commit -m "..."`. Não faça o commit sem o usuário confirmar.
