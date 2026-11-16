## Documentação técnica — Instituto Socrático

N ov 16, 2026

O Instituto Socrático é um sistema de gestão acadêmica em Django, projeto final do curso de Desenvolvimento de Sistemas do SENAI Morvan Figueiredo. Cada perfil (aluno, professor, coordenação) tem a sua área, e um módulo de aprendizado de máquina estima a chance de cada aluno desistir do curso.

Esta documentação descreve o repositório takathecode/colegio-socratico no commit f6f80eb . Ela foi escrita a partir da leitura do código, da execução dos testes e do treino do modelo em uma cópia local. [URL 🔗](https://github.com/takathecode/colegio-socratico)

·

@Felippe

## Visão geral

- Aluno: painel com gráfico de notas, boletim (com PDF), frequência, justificativa de faltas com anexo, calendário, mensagens e financeiro simulado.

- Professor: turmas, lançamento de notas, chamada com biometria simulada, avaliação de justificativas, gráfico de desempenho, relatórios da disciplina e videochamada com a coordenação.

- Coordenação: visão geral, alunos em risco de evasão, cadastro de alunos, professores, turmas e disciplinas, criação de contas, relatórios em PDF e Excel, central de alertas e videochamada com os professores.

- Automação: alertas gerados todo dia às 6h (Celery + Redis), sino de notificações no portal e e-mails para os casos graves.

- Integração: API REST somente de consulta, documentada em /api/docs/ (Swagger).

Não existe tela de cadastro: as contas são criadas pela coordenação ou pelo Django Admin.

| Item Valor Etapas concluídas 13 de 14 (falta a publicação na Vercel) |
| --- |
| Apps Django 12 Código Python (sem migrações) cerca de 13.400 linhas Testes automatizados 348 Banco de dados PostgreSQL no Supabase (SQLite em memória nos testes) |


## Stack e arquitetura

O sistema é um monolito Django com páginas renderizadas no servidor, sem React nem Vue. A stack foi exigida pelo professor e o CLAUDE.md do projeto proíbe trocá-la.

| Camada | Tecnologia | Papel |
| --- | --- | --- |
| Web | Django 5.2 LTS, Python 3.12 ou mais | páginas, formulários, Admin, |
|   | novo | autenticação |
| Banco | PostgreSQL no Supabase (Session | dados; schema só pelas |
|   | pooler, porta 5432) | migrações do Django |
| API | Django REST Framework, django- | consulta REST e |
|   | filter, drf-spectacular | documentação Swagger |
| Aprendizado de | scikit-learn (RandomForest), joblib, | risco de evasão |
| máquina | pandas, numpy |   |
| Gráficos | matplotlib | PNG gerado no servidor, |
|   |   | enviado em base64 |
| Relatórios | reportlab (PDF), pandas + | boletins e listas |
|   | openpyxl (Excel) |   |
| Tarefas | Celery + Redis (Upstash ou | alertas automáticos e e-mails |
|   | Docker) |   |
| Front-end | templates Django, Tailwind CSS, | interface |
|   | JavaScript puro, ícones Lucide |   |
| Videochamada | Jitsi Meet (serviço externo) | chamadas entre coordenação |
|   |   | e professores |


## Tudo pelo Django; banco, fila e e-mail são serviços externos passa

arquitetura · Django, Supabase, Redis, Celery e e-mail

Navegador e integrações falam só com o Django, e os apps de área, os relatórios, os alertas e o módulo de evasão usam calculos.py para os números. A fila e o worker cuidam dos alertas e dos e-mails. O vídeo das videochamadas vai direto do navegador ao Jitsi Meet, sem passar pelo Django.

As dependências estão fixadas em requirements.txt . O Node.js só é preciso para recompilar o CSS: o static/css/app.css compilado já vai no Git.

## Decisões de projeto que explicam o código

- 1. Uma única fonte para os cálculos. Média, frequência e selo de situação não ficam salvos no banco. São calculados em apps/academico/calculos.py , e telas, relatórios, alertas, API e modelo de evasão usam as mesmas funções. Por isso nunca há dois números diferentes para o mesmo aluno.

- 2. Histórico protegido. As chaves estrangeiras acadêmicas usam PROTECT : apagar uma turma ou aluno que já tem notas gera erro, em vez de apagar o histórico em silêncio.

- 3. Poucas consultas ao banco. Como cada ida ao Supabase demora, os cálculos usam consultas agrupadas. resumo_das_matriculas faz 2 consultas para qualquer número de alunos, e variaveis_dos_alunos faz 4.

- 4. Anexos no banco. O conteúdo dos anexos fica na tabela ArquivoAnexo , e não na pasta media/ , para chegar a quem usa outro computador ou a Vercel.

- 5. Fila que nunca derruba a tela. Se o Redis cair, a tarefa roda na hora, depois de cerca de 2 s. Com CELERY_SEM_REDIS=True tudo roda sem fila.

- 6. Sem rota pública para arquivos. Anexos só saem por views que conferem a permissão.


- 7. Testes isolados. Em manage.py test o banco é um SQLite em memória e o Celery roda sem fila, então os testes não tocam no Supabase.

Em cada app, as views.py cuidam da requisição e dos formulários, e as regras ficam em servicos.py , calculos.py ou regras.py . Os templates usam peças reutilizáveis de

templates/componentes/ .

## Estrutura do repositório

O código está dividido em 12 apps Django dentro de apps/ , mais a configuração em config/ . Os apps de área (aluno, professor, coordenação) não têm modelos próprios: eles leem e gravam os dados de academico .

| App | Rota |   | O que faz |
| --- | --- | --- | --- |
| contas | / , | /entrar/ , | usuário customizado (login por matrícula), |
|   | /senha/... |   | bloqueio de senhas erradas, menu lateral, |
|   |   |   | decorator @perfil_requerido |
| academico | (sem rotas) |   | modelos acadêmicos, regras de cálculo |
|   |   |   | ( calculos.py ), armazenamento de anexos, |
|   |   |   | Django Admin, comando popular_demo |
| aluno | /aluno/ |   | painel, notas e boletim, frequência, |
|   |   |   | justificativas, calendário, financeiro |
| professor | /professor/ |   | turmas, notas, chamada, desempenho, |
|   |   |   | avaliação de justificativas |
| coordenacao | /coordenacao/ |   | visão geral, alunos em risco, cadastros, |
|   |   |   | contas, central de alertas |
| analytics | (sem rotas) |   | módulo de evasão ( evasao.py ), modelo |
|   |   |   | RiscoEvasao , gráficos matplotlib |
| alertas | /alertas/ |   | modelo Alerta , regras, tarefas Celery, sino |
|   |   |   | de notificações |
| relatorios | /relatorios/ |   | PDF e Excel, filtros |
| mensagens | /mensagens/ |   | caixa de mensagens entre aluno e professor |
|   |   |   | ou secretaria |
| videochamadas | /videochamadas/ |   | salas do Jitsi Meet entre coordenador e |
|   |   |   | professor |
| financeiro | (tela em aluno ) |   | modelo Mensalidade , simulado |


| App | Rota | O que faz |
| --- | --- | --- |
| api | /api/ , /api/docs/ | viewsets de consulta, token, Swagger |

## Fora de apps/ :

- config/ : settings.py , urls.py , celery.py , wsgi.py , asgi.py .

- (sidebar, selo, cartão de indicador, gráfico, modal, paginação, campos de formulário). templates/ : esqueleto.html , base.html , 403.html e as peças de componentes/

- imagens, e a entrada tailwind.css . static/ e assets/ : CSS compilado, portal.js (biometria simulada e interações),

- docs/ : documentos por tema ( DER.md , MODELO_EVASAO.md , ALERTAS.md , RELATORIOS.md , API.md , SEGURANCA.md , VIDEOCHAMADA.md ), o enunciado TEMA_8.pdf e o protótipo em imagem.

- ml/ : guarda modelo_evasao.joblib . A pasta não vai para o Git: cada computador treina o seu.

- instruções usadas para desenvolver o projeto com o Claude Code, incluindo o registro de progresso por etapa. CLAUDE.md , PROMPT_INICIAL.md , ROTEIRO_PROMPTS.md e .claude/skills/ :

## Perfis, login e permissões

O login é por matrícula e senha, e o perfil da conta decide a área que a pessoa vê. O

modelo contas.Usuario herda de AbstractUser , remove o campo username e usa matricula como USERNAME_FIELD .

| Perfil | Para onde vai após o | O que enxerga |
| --- | --- | --- |
|   | login |   |
| ALUNO | /aluno/ | só os próprios dados |
| PROFESSOR | /professor/ | só as disciplinas que leciona (ofertas ligadas a |
|   |   | ele) |
| COORDENADOR | /coordenacao/ | a instituição inteira |
| ADMIN | /admin/ | Django Admin; não usa as áreas do portal nem a |
|   |   | API |

Todo pedido passa por três conferências, nesta ordem:

- 1. A pessoa entrou? @login_required manda quem não entrou para o login.


- 2. O perfil pode abrir esta tela? @perfil_requerido(...) (em apps/contas/decorators.py ) responde 403 com página amigável. Mesmo sem @login_required , o visitante anônimo não tem perfil e continua bloqueado.

- 3. O registro é dela? A consulta já filtra pelo usuário ( Conversa.objects.do_usuario , ofertas_do_professor , escopo.py na API). Registro de outra pessoa responde 404, como se não existisse, para ninguém descobrir números válidos trocando o endereço.

## Outros pontos do login:

- A tela tem "Manter conectado" (sem marcar, a sessão termina ao fechar o navegador) e "Esqueci minha senha", com link válido por 1 hora.

- Depois de 5 senhas erradas seguidas, a matrícula fica bloqueada por 15 minutos ( apps/contas/bloqueio.py , tabela BloqueioDeLogin ).

- Contas são criadas pela coordenação (com senha provisória aleatória mostrada uma vez) ou pelo Admin, e nunca são apagadas, só desativadas.

- O menu lateral de cada perfil vem de apps/contas/menu.py . Um item sem rota aparece desativado, para nunca existir link quebrado.

## Modelo de dados e regras de cálculo

O núcleo é a cadeia Curso, Turma, Oferta, Matrícula. A oferta é uma disciplina dada em uma turma por um professor, e é a base da permissão do professor. Notas e presenças pendem da matrícula e da oferta. O DER completo está em docs/DER.md .

| Modelo | App | Papel e restrições principais |   |
| --- | --- | --- | --- |
| Usuario | contas | matrícula única, perfil , tratamento | ("Prof.", |
|   |   | "Profa.") |   |
| BloqueioDeLogin | contas | erros de senha por matrícula digitada |   |
| Curso | academico | nome único, total de créditos |   |
| Disciplina | academico | código único, créditos, carga horária; pertence a |   |
|   |   | um curso |   |
| Turma | academico | código + semestre ( 2026.2 ) únicos |   |
| Oferta | academico | turma + disciplina + professor; disciplina única |   |
|   |   | por turma, e do mesmo curso da turma |   |
| Matricula | academico | aluno + turma únicos; situação ATIVA , |   |
|   |   | TRANCADA , EVADIDA ou CONCLUIDA |   |
| Avaliacao | academico | prova ou entrega de uma oferta, com data e local |   |


| Modelo | App | Papel e restrições principais |
| --- | --- | --- |
| Nota | academico | uma por avaliação e matrícula; valor de 0 a 10 |
|   |   | (validador e CheckConstraint no banco) |
| Aula | academico | uma por oferta e dia, com horas-aula (padrão 2) |
| Frequencia | academico | presença de uma matrícula em uma aula; método |
|   |   | manual ou biometria simulada |
| Justificativa | academico | pedido do aluno para uma falta; PENDENTE , |
|   |   | APROVADA ou REJEITADA ; anexo opcional de até |
|   |   | 5 MB (PDF, JPG, PNG) |
| Evento | academico | calendário (institucional, feriado ou atividade da |
|   |   | disciplina) |
| ArquivoAnexo | academico | conteúdo dos anexos, guardado no banco |
| RiscoEvasao | analytics | uma linha por matrícula ativa com dados, |
|   |   | regravada a cada cálculo |
| Alerta | alertas | aviso para uma pessoa, com gravidade, link e |
|   |   | chave de assunto |
| Conversa , | mensagens | conversa entre um aluno e um professor ou |
| Mensagem |   | coordenador |
| Chamada | videochamadas sala do Jitsi entre coordenador e professor, com |   |
|   |   | histórico |
| Mensalidade | financeiro | parcela simulada; a situação é calculada pela data |

As chaves estrangeiras acadêmicas usam PROTECT . Alertas usam CASCADE (não fazem sentido sem a pessoa), e RiscoEvasao também, porque é refeito no próximo cálculo.

## Regras de média, frequência e selo

Ficam em apps/academico/calculos.py e não são gravadas no banco.

- Média da disciplina: média simples das notas lançadas, com duas casas. Sem nota, o valor é vazio ( None ), e isso não conta contra o aluno.

- Frequência: horas de presença sobre horas de aula dadas, em %. A frequência global soma as horas de todas as disciplinas.

- Justificativa aprovada não muda a frequência, como informa o protótipo.

- Visão da coordenação: a média geral é a média das médias das disciplinas, e a situação é a pior entre as disciplinas.


| Selo | Condição |
| --- | --- |
| Em risco | frequência abaixo de 75% ou média abaixo de 6 |
| Em atenção frequência abaixo de 80% ou média abaixo de 7 |   |
| Regular | nenhuma das anteriores |

Esses mesmos limites (constantes FREQUENCIA_MINIMA , FREQUENCIA_ATENCAO , MEDIA_RISCO , MEDIA_MINIMA ) são reutilizados nos motivos do modelo de evasão, nos alertas e nos relatórios.

## Módulo de evasão

O módulo estima, para cada aluno com matrícula ativa, a probabilidade de desistir do curso, para a coordenação conversar com ele antes que isso aconteça. Um RandomForest treinado com 2.000 alunos simulados olha quatro números do aluno e devolve a chance de evasão, que vira um nível (baixo, médio, alto) e até três motivos em frases. O código está em apps/analytics/evasao.py , e o resultado fica salvo em RiscoEvasao .

## O modelo é treinado uma vez e consultado a cada cálculo de risco

fluxo do módulo de evasão · treino e previsão

O treino acontece uma vez por ambiente. A previsão roda todo dia às 6h, no botão "Recalcular agora" e ao fim de treinar_modelo , sempre lendo o mesmo arquivo.


## As quatro variáveis

| Variável | Como é calculada | Observação |
| --- | --- | --- |
| frequencia | frequência global do | mesma de |
|   | aluno, em % | resumo_das_matriculas , a das |
|   |   | telas |
| media | média das médias das | só disciplinas com nota |
|   | disciplinas |   |
| tendencia | última nota menos a | negativo = notas em queda; |
|   | primeira, por disciplina, | disciplina com uma nota só não |
|   | com média entre as | conta; sem nenhuma, vale 0 |
|   | disciplinas |   |
| justificativas_pendentes | justificativas de falta | contagem simples |
|   | ainda sem resposta do |   |
|   | professor |   |

Quem ainda não tem nota ou não tem chamada fica fora do cálculo, porque sem dados o modelo só chutaria. A tela mostra quantos alunos estão nessa situação. O cálculo das variáveis faz 4 consultas ao banco, qualquer que seja o número de alunos.

## Treino com dados simulados

A escola não tem histórico real de quem desistiu. Por isso treinar_modelo gera alunos fictícios (semente fixa 42, resultado sempre igual) e uma regra escrita pelos autores decide quem "evadiu". Os valores sorteiam-se assim: frequência normal com média 82 e desvio 12 (entre 30 e 100); média normal 6,8 e desvio 1,6 (entre 0 e 10); tendência normal 0 e desvio 1,2 (entre -5 e 5); justificativas pendentes por Poisson de média 0,6 (entre 0 e 6). A regra escondida é:

```
z = -1{,}0 + 0{,}15\,(80 - \text{frequência}) + 0{,}9\,(6{,}5 - \text{média})
- 0{,}6\,\text{tendência} + 0{,}4\,\text{pendentes}
\qquad
P(\text{evadir}) = \frac{1}{1 + e^{-z}}
```

Um sorteio com essa probabilidade decide cada caso, então existem exceções, como na vida real. O modelo não conhece a regra: ele descobre o padrão pelos exemplos.

O treino separa 20% dos alunos (estratificado pela proporção de evadidos) para a prova e treina com os outros 80%. O modelo é um RandomForestClassifier com 200 árvores, profundidade máxima 6 e pelo menos 10 alunos por folha, o que evita decorar os exemplos.

O arquivo sai em ml/modelo_evasao.joblib .


Resultado do treino, conferido em uma execução feita para esta documentação:

| Métrica | Valor |
| --- | --- |
| Alunos simulados | 2.000 |
| Evadiram na simulação | 33,9% |
| Acurácia nos 20% de prova | 81% |
| Acurácia de quem chuta "ninguém evade" 66% |   |
| Peso da frequência | 49,8% |
| Peso da média | 35,1% |
| Peso da tendência | 13,5% |
| Peso das justificativas pendentes | 1,6% |

A frequência e a média dominam a decisão. As justificativas pendentes pesam só 1,6%, embora a regra que gera os dados as use.

Previsão: calcular_riscos()

- 1. Carrega o modelo. Se o arquivo não existe, levanta ModeloNaoTreinado com a instrução de rodar treinar_modelo .

- 2. Busca as matrículas com situação ATIVA e calcula as quatro variáveis de cada uma.

- 3. Monta uma tabela do pandas e chama predict_proba , que devolve a chance de ficar e a de evadir. A de evadir, multiplicada por 100 e arredondada para duas casas, é a probabilidade.

- 4. Em uma transação única, apaga todos os registros de RiscoEvasao e grava os novos. Se algo falhar no meio, o banco mantém o cálculo anterior inteiro.

Cada RiscoEvasao guarda a probabilidade, o nível, os motivos (JSON) e as quatro variáveis usadas, para a tela mostrar de onde veio o resultado. Há um registro por

matrícula ( OneToOneField ).

## Níveis e motivos

| Nível | Probabilidade |
| --- | --- |
| Baixo | abaixo de 30% |
| Médio de 30% até menos de 60% |   |


| Nível | Probabilidade |
| --- | --- |
| Alto | 60% ou mais |

Os motivos não vêm do modelo: a floresta não explica cada decisão de forma simples. A função explicar() monta frases a partir dos números do aluno, com os mesmos limites do selo de situação. Aparecem no máximo três, nesta ordem de gravidade:

- 1. Frequência abaixo de 75%: "Frequência de X%, abaixo do mínimo de 75%".

- 2. Média abaixo de 6: "Média X, abaixo de 6".

- 3. Tendência de -0,5 ponto ou menos: "Notas em queda", com a diferença entre a primeira e a última avaliação.

- 4. Frequência de 75% a menos de 80%: "perto do mínimo de 75%".

- 5. Média de 6 a menos de 7: "Média X, abaixo de 7".

- 6. Uma ou mais justificativas pendentes: "N justificativa(s) de falta aguardando o professor".

Os números do texto são cortados em uma casa em vez de arredondados ( numero_br ): 74,96% aparece como 74,9%, e não como 75%, que pareceria estar no limite e não abaixo dele.

## Onde o resultado aparece

- Coordenação, Alunos em risco ( /coordenacao/risco/ ): cartões com a quantidade em cada nível, filtros por busca, turma e nível, lista paginada ordenada pela maior probabilidade, horário do último cálculo, quantos alunos ficaram sem dados e os botões de PDF e Excel, que levam os filtros da tela. Sem modelo treinado, a tela explica como treinar.

- Botão "Recalcular agora" (POST em /coordenacao/risco/recalcular/ ): roda calcular_riscos() na hora.

- Coordenação, Visão geral: cartão com os até 8 alunos de maior probabilidade, sem os de nível baixo.

- Alertas: risco alto gera um alerta "Em risco" para cada coordenador ativo, também por e-mail.

- API: GET /api/riscos/ e /api/relatorios/risco/ , só para a coordenação.

| Comando | O que faz |
| --- | --- |
| python manage.py treinar_modelo | gera os dados simulados, treina, salva o .joblib |
|   | e recalcula os riscos ( --sem-calcular só treina) |


| Comando | O que faz |
| --- | --- |
| python manage.py calcular_riscos | recalcula com o modelo já treinado |
| python manage.py gerar_alertas | roda a rotina diária completa, que começa |
|   | recalculando o risco |
| Tarefa rotina_diaria (Celery beat, | recalcula o risco e gera os alertas do dia |
| 6h) |   |

## Limitações

- O modelo aprende a regra dos autores, não evasão real. As probabilidades servem para demonstrar o método e ordenar os alunos, e não como medida de uma taxa real. Os 81% de acurácia valem para os dados simulados.

- Não há caminho pronto para dados reais. treinar() sempre chama gerar_dados_simulados() . Como existe a situação EVADIDA em Matricula , uma continuação natural seria montar a tabela de treino com as mesmas quatro colunas mais o rótulo evadiu a partir do histórico (sugestão desta análise, não está no código).

- O arquivo do modelo não vai para o Git. Cada ambiente precisa rodar treinar_modelo , inclusive o servidor publicado. Sem ele, a rotina diária ainda gera os outros alertas, mas pula o de evasão.

- A tela trata o resultado como um sinal para conversar com o aluno, e não como uma sentença: o modelo acerta cerca de 8 em cada 10 casos simulados.

## Alertas automáticos

O sistema avisa sozinho quem precisa agir. Uma rotina diária às 6h recalcula o risco de evasão e aplica as regras abaixo. Outros avisos saem na hora, quando alguém publica uma nota ou envia uma mensagem. As regras estão em apps/alertas/regras.py , as tarefas em tasks.py , e a explicação para a apresentação em docs/ALERTAS.md .

| Alerta | Quem recebe | Gravidade | E- | Quando |
| --- | --- | --- | --- | --- |
|   |   |   | mail |   |
| Frequência abaixo | o aluno | Em risco | sim frequência global |   |
| do mínimo |   |   |   | abaixo de 75% |
| Média abaixo de 6 o aluno |   | Em risco | sim média geral abaixo de |   |
|   |   |   |   | 6 |


| Alerta | Quem recebe | Gravidade | E- | Quando |
| --- | --- | --- | --- | --- |
|   |   |   | mail |   |
| Risco de evasão | todos os | Em risco | sim nível ALTO no |   |
| alto | coordenadores |   |   | modelo, com os |
|   | ativos |   |   | motivos no texto |
| Justificativas sem | o professor | Em atenção | não pendentes há mais de |   |
| resposta |   |   |   | 3 dias; um lembrete |
|   |   |   |   | com o total |
| Nota publicada | cada aluno com | Informativo | não | o professor publica as |
|   | nota |   |   | notas de uma |
|   |   |   |   | avaliação (o texto não |
|   |   |   |   | traz a nota) |
| Justificativa | o aluno | Informativo ou | não | o professor aprova ou |
| avaliada |   | Em atenção |   | rejeita |
| Mensagem nova | quem recebe | Informativo | não | um aviso por |
|   |   |   |   | conversa, até ser |
|   |   |   |   | aberta |
| Convite de | o convidado | Informativo | não quando a chamada é |   |
| videochamada |   |   |   | criada |

## Como funciona

- Sem repetição: a mesma pessoa com a mesma chave de assunto (por exemplo frequencia-12 ) não recebe outro alerta antes de 7 dias. Mensagens e videochamadas ficam fora dessa janela, com regras próprias.

- Fila: os avisos de ação entram na fila do Celery logo depois de a transação gravar ( transaction.on_commit ), e quem salvou não espera. As tarefas recebem só o número dos registros, e o worker lê o dado atualizado.

- Redis fora do ar: apps/alertas/fila.py desiste da fila em cerca de 2 segundos e roda a tarefa na hora, então a tela nunca quebra.

- Sem Redis: com CELERY_SEM_REDIS=True tudo roda dentro do próprio Django. Nesse modo a rotina das 6h não dispara sozinha, e se usa o botão "Rodar rotina agora" ou python manage.py gerar_alertas .

- E-mail: só os alertas "Em risco" vão por e-mail, com link para o portal. Se o servidor de e-mail falhar, o worker tenta de novo até 3 vezes, com 1 minuto entre as tentativas. Em desenvolvimento, o e-mail aparece no terminal.


- Sem modelo treinado: a rotina registra um aviso no log e gera os outros alertas, deixando só o de evasão de fora.

O sino no topo de qualquer tela mostra o contador de não lidos e os últimos avisos. A tela /alertas/ lista os alertas da pessoa para os três perfis, e cada um só enxerga os próprios (alerta de outra pessoa responde 404). A Central de alertas da coordenação ( /coordenacao/alertas/ ) mostra tudo que o sistema enviou, com filtros, indicadores da semana e o botão "Rodar rotina agora".

## Áreas do portal e módulos de apoio

Cada área segue o mesmo layout (barra lateral, breadcrumb, sino, avatar), baseado no protótipo do Figma, com selos verde "Regular", âmbar "Em atenção" e vermelho "Em risco". O protótipo só cobria o aluno, então as telas do professor e da coordenação seguem o visual da área do aluno.

## Área do aluno ( /aluno/ )

- Painel: indicadores, gráfico de barras das notas por disciplina, próximas avaliações e pendências.

- Notas e boletim ( notas/ ): média por disciplina, com o nome de cada avaliação (A1, A2) e a mais recente em destaque, e boletim em PDF.

- Frequência ( frequencia/ ): calendário de presenças e faltas e formulário de justificativa com anexo. Várias faltas sem justificativa contam como uma só pendência. Quem avalia é o professor da disciplina.

- Calendário acadêmico ( calendario/ ): avaliações criadas pelos professores e eventos institucionais, em visões por período.

- Financeiro ( financeiro/ ): mensalidades simuladas, com boleto e comprovante desativados.

- Mensagens e notificações.

Sem matrícula ativa, as telas mostram um aviso em vez de erro.

## Área do professor ( /professor/ )

- Minhas turmas ( turmas/ ): só as disciplinas que leciona. Disciplina de outro professor responde 404.

- Lançar notas ( notas/ ): o professor cria as avaliações aqui, e elas aparecem no calendário do aluno. Campo de nota vazio apaga a nota. Ao publicar, os alunos recebem um alerta.


- Chamada ( chamada/ ): não aceita data futura e exige marcar todos os alunos. A biometria é simulada no navegador ( static/js/portal.js ), com cerca de 9 em 10 leituras reconhecidas, e a falta é sempre gravada como manual. Falta que já tem justificativa fica travada.

- Justificativas ( justificativas/ ): aprova ou rejeita (rejeitar exige uma resposta), e o aluno recebe o aviso. O anexo só abre para quem tem permissão.

- Desempenho ( desempenho/ ): distribuição das médias da turma por faixa, em gráfico e em tabela.

- Mensagens e videochamada com a coordenação.

## Área da coordenação ( /coordenacao/ )

- Visão geral: indicadores da instituição no semestre atual, justificativas pendentes, frequência mensal por turma (até 8 turmas no gráfico) e os alunos de maior risco de evasão.

- Alunos em risco: o módulo descrito na seção anterior.

- Alunos, professores, turmas e disciplinas: cadastro e edição. O aluno é criado junto com a matrícula na turma, que só pode mudar enquanto não há notas nem presenças. Disciplinas e professores entram na turma pela tela da turma (as ofertas). Turma, disciplina e oferta só são excluídas se não tiverem registros ligados.

- Contas: criação de coordenadores, senha provisória aleatória (mostrada uma vez) e ativação ou desativação. Ninguém desativa a própria conta, e o perfil ADMIN fica só no Django Admin.

- Relatórios, Alertas (central) e Videochamadas.

## Módulos de apoio

- Mensagens ( /mensagens/ ): conversas entre um aluno e um professor ou a secretaria. O coordenador atende como "Secretaria acadêmica". O professor só inicia conversa com alunos ativos das suas turmas, e a secretaria com qualquer aluno ativo. Anexos de até 5 MB (PDF, JPG, PNG). Um aviso por conversa aparece no sino até a pessoa abri-la.

- Videochamadas ( /videochamadas/ ): a chamada é sempre entre um coordenador e um professor, nos dois sentidos. O portal cria uma sala no Jitsi Meet com nome sorteado ( InstitutoSocratico- mais 24 caracteres hexadecimais), avisa o convidado pelo sino e guarda o histórico. O vídeo não passa pelo portal e abre em outra aba. A chamada esquecida deixa de aparecer como em andamento depois de 3 horas. O servidor do Jitsi pode ser trocado em JITSI_SERVIDOR . Detalhes em docs/VIDEOCHAMADA.md .


- Financeiro ( apps/financeiro ): só o modelo Mensalidade , com valor líquido, bolsa em % e situação calculada (paga, a vencer, em atraso). O sistema não processa pagamentos.

- Anexos: justificativas e mensagens usam FileField , mas o armazenamento ( apps/academico/armazenamento.py ) grava o conteúdo na tabela ArquivoAnexo . Anexos antigos ainda são lidos da pasta media/ , e python manage.py migrar_anexos os copia para o banco.

- Gráficos: matplotlib sem pyplot, gerados no servidor e enviados como PNG em base64, com uma descrição em texto no atributo alt . As cores foram testadas para daltonismo.

## Relatórios e API REST

Os relatórios e a API entregam os mesmos números das telas, porque chamam as mesmas funções de calculos.py . Os dois respeitam o perfil: aluno vê o próprio, professor as disciplinas que leciona, coordenação tudo.

## Relatórios em PDF e Excel ( /relatorios/ )

| Relatório | Quem baixa | PDF Excel |
| --- | --- | --- |
| Boletim do semestre | o aluno (o próprio) e a coordenação (qualquer | sim não |
|   | matrícula) |   |
| Desempenho da | o professor (só as dele) | sim sim |
| disciplina |   |   |
| Desempenho da turma | coordenação | sim sim |
| Alunos em risco de | coordenação | sim sim |
| evasão |   |   |
| Lista de alunos | coordenação | não sim |

O formato vem em ?formato=pdf ou ?formato=xlsx (outro valor responde 404). Os relatórios são gerados na hora, sem Celery.

- dados.py monta o conteúdo uma vez (classes Relatorio , Tabela , Coluna ), e pdf.py (reportlab) e excel.py (pandas + openpyxl) apenas desenham. Assim o PDF e o Excel de um relatório nunca divergem.

- filtros.py usa django-filter (turma, nível de risco, situação, busca), os mesmos filtros da tela "Alunos em risco", e os botões PDF e Excel levam os filtros da lista.


- No PDF, os números saem com uma casa, cortando a segunda. No Excel, a nota e o percentual vêm como número exato, e nota não lançada fica em branco. Há uma aba por tabela e uma aba "Sobre o relatório".

- O relatório de risco traz a probabilidade, o nível e os motivos de cada aluno.

## API REST ( /api/ )

A API só consulta: gravar pela API responde 405, porque as validações de nota, chamada e conta ficam nas telas. A documentação navegável (Swagger) fica em /api/docs/ e o esquema OpenAPI em /api/schema/ .

- Entrada: pela sessão do portal ou por token. O token vem de POST /api/token/ (máximo de 10 pedidos por minuto) e segue no cabeçalho Authorization: Token <token> . DELETE /api/token/ o apaga. Trocar a senha também apaga o token, e contas ADMIN não recebem token.

- Permissão e escopo: perfil sem acesso ao endpoint recebe 403 ( permissoes.py ). Registro fora do que a pessoa vê responde 404 ( escopo.py ).

- Listas: páginas de 20 itens, com ?pagina= e ?tamanho= (até 100). Notas e percentuais saem como número, e o que não existe sai como null .

| Endpoint | Aluno | Professor | Coordenação |
| --- | --- | --- | --- |
| /api/eu/ , /api/cursos/ , | sim | sim | sim |
| /api/disciplinas/ |   |   |   |
| /api/turmas/ | as suas | as suas | todas |
| /api/turmas/{id}/desempenho/ | 403 | 403 | sim |
| /api/ofertas/ | as da sua | as que | todas |
|   | turma | leciona |   |
| /api/ofertas/{id}/desempenho/ | 403 | só as suas | sim |
| /api/matriculas/ e | a própria | 403 | todas |
| /api/matriculas/{id}/boletim/ |   |   |   |
| /api/riscos/ e /api/riscos/{matrícula}/ | 403 | 403 | sim |
| /api/relatorios/boletim/{matrícula}/ | a própria | 403 | sim |
| /api/relatorios/disciplina/{oferta}/ | 403 | só as suas | sim |
| /api/relatorios/turma/{turma}/ , risco/ , | 403 | 403 | sim |
| alunos/ |   |   |   |


O professor não usa /api/matriculas/ porque a média geral mistura as notas de outros professores. Ele vê os seus alunos no desempenho de cada oferta. O endereço de risco usa o número da matrícula, e não o do registro, porque o risco é regravado a cada cálculo. O detalhamento está em docs/API.md e docs/RELATORIOS.md .

## Segurança

A segurança é conferida no servidor em todas as telas, e não só escondendo botões. O documento completo está em docs/SEGURANCA.md . Os pontos principais:

| Proteção | Como é feita |
| --- | --- |
| Acesso por perfil | @login_required + @perfil_requerido ; perfil |
|   | errado recebe 403, e o pedido de um registro alheio |
|   | recebe 404 |
| Senhas | só o hash (PBKDF2, padrão do Django) é guardado; |
|   | os validadores do Django recusam senhas fracas |
| Mensagem de login igual matrícula inexistente, senha errada e conta |   |
|   | desativada mostram a mesma mensagem |
| Força bruta | 5 erros seguidos bloqueiam a matrícula por 15 |
|   | minutos; o bloqueio fica no banco e no backend de |
|   | autenticação, então vale para o portal, a API e o |
|   | Admin |
| Troca de senha | encerra as sessões, apaga o token da API e |
|   | desbloqueia o login |
| Contas | criadas pela coordenação com senha provisória de |
|   | secrets , mostrada uma vez; nunca apagadas, só |
|   | desativadas |
| Anexos | sem URL pública ( ArmazenamentoNoBanco.url |
|   | levanta erro); só saem por views que conferem a |
|   | permissão; tipos PDF, JPG e PNG, até 5 MB |
| Redirecionamentos | o sino só redireciona para endereços do próprio |
|   | site ( url_has_allowed_host_and_scheme ) |
| Segredos | SECRET_KEY e DATABASE_URL vêm do .env , que |
|   | está no .gitignore ; o sistema não inicia sem eles |
| HTTPS | USAR_HTTPS=True liga redirecionamento, cookies |
|   | seguros, o cabeçalho do proxy da Vercel e HSTS de |
|   | 1 dia, sem subdomínios nem preload |


| Proteção | Como é feita |
| --- | --- |
| API | exige login, tem token com limite de 10 pedidos por |
|   | minuto e só aceita GET nos dados |
| Banco | o Django usa a role postgres ; a Data API do |
|   | Supabase fica desligada, pois as tabelas do Django |
|   | não têm RLS |

Nesta análise, uma busca no código das telas não encontrou |safe , mark_safe , csrf_exempt , .raw() nem SQL cru. As views de área têm controle de perfil, e as exceções são funções auxiliares e as duas páginas que devem ser públicas ou de redirecionamento ( inicio e atendimento ). O teste apps/contas/test_permissoes.py percorre todas as rotas e falha se uma tela nova ficar sem proteção.

Um detalhe sobre o modelo de evasão: o arquivo .joblib é carregado com joblib.load , que executa código se o arquivo for malicioso. Isso é aceitável aqui porque o arquivo é gerado pelo próprio sistema, e nunca enviado por usuários, mas ele não deve vir de uma fonte externa.

## Instalação, configuração e testes

O passo a passo completo para Windows está no README.md . Em resumo, o sistema precisa de Python 3.12 ou mais novo, Git e uma conta no Supabase. Redis e Node.js são opcionais.

```
git clone https://github.com/takathecode/colegio-socratico.git
cd colegio-socratico
py -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
Copy-Item .env.example .env # preencha o .env
python manage.py migrate
python manage.py createsuperuser # conta ADMIN
python manage.py popular_demo # dados fictícios (só com DEBUG=True)
python manage.py treinar_modelo # treina o modelo de evasão
python manage.py runserver
```


## Variáveis do .env

| Variável | Obrigatória | Para quê |
| --- | --- | --- |
| SECRET_KEY | sim | chave do Django; sem ela o sistema |
|   |   | não inicia |
| DATABASE_URL | sim (fora dos | URL do Supabase pelo Session pooler, |
|   | testes) | com ?sslmode=require |
| DEBUG | não | True no computador de |
|   |   | desenvolvimento |
| ALLOWED_HOSTS | não | endereços permitidos, separados por |
|   |   | vírgula |
| USAR_HTTPS | não | True só no servidor publicado; no |
|   |   | computador deve ficar False |
| REDIS_URL | não | fila do Celery (Docker ou Upstash |
|   |   | rediss:// ) |
| CELERY_SEM_REDIS | não | True roda as tarefas na hora, sem fila |
| EMAIL_BACKEND , | não | e-mail; por padrão a mensagem |
| DEFAULT_FROM_EMAIL |   | aparece no terminal |
| ENDERECO_DO_SITE | não | base dos links nos e-mails de alerta |
| JITSI_SERVIDOR | não | servidor das videochamadas (padrão |
|   |   | https://meet.jit.si ) |

## Endereços e contas de demonstração

Portal em http://127.0.0.1:8000/ , Admin em /admin/ e Swagger em /api/docs/ . O

popular_demo cria 1 coordenador, 6 professores, 2 turmas (CC-6A e CC-6B) e 40 alunos fictícios, e a senha de cada conta é igual à matrícula.

| Perfil | Matrículas |
| --- | --- |
| Coordenador | coord01 |
| Professores | prof01 a prof06 |
| Alunos | aluno01 a aluno40 (a aluno01 reproduz o |
|   | protótipo) |


| Perfil | Matrículas |
| --- | --- |
| Alunos com dados de risco | aluno05 , aluno09 , aluno14 , aluno18 , aluno23 , |
|   | aluno27 , aluno32 , aluno38 |

O ADMIN ( admin01 , por exemplo) é criado por você com createsuperuser . Use estas contas só em desenvolvimento.

## Comandos do dia a dia

| Comando | Para quê |
| --- | --- |
| python manage.py check | valida a configuração |
| python manage.py test | roda os testes |
| python manage.py makemigrations e | migrações (o schema só nasce delas) |
| migrate |   |
| python manage.py popular_demo | recria os dados de demonstração, com as |
|   | datas ajustadas para hoje |
| python manage.py treinar_modelo | / modelo de evasão |
| calcular_riscos |   |
| python manage.py gerar_alertas | rotina diária na hora |
| python manage.py migrar_anexos | copia anexos antigos da pasta media/ para |
|   | o banco |
| celery -A config worker --pool=solo -l | worker (no Windows, --pool=solo é |
| info | obrigatório) |
| celery -A config beat -l info | agenda a rotina das 6h |
| npm install , npm run css , npm run | só para recompilar o Tailwind |
| css:dev |   |

## Testes

python manage.py test usa SQLite em memória e o Celery sem fila, então não precisa de internet, Redis nem Supabase. Em uma execução feita para esta documentação, foram 348 testes em cerca de 37 segundos. Eles cobrem, por app: cálculos acadêmicos, áreas de aluno, professor e coordenação, alertas, mensagens, videochamadas, relatórios, API e o módulo preditivo (treino, cálculo do risco, motivos e o fato de piorar uma variável nunca baixar o risco). Três suítes merecem destaque:


- apps/contas/test_login.py : login por matrícula, "Manter conectado", redefinição de senha e o bloqueio por 5 erros.

- apps/contas/test_permissoes.py : percorre todas as rotas e confere que o visitante vai ao login e que cada perfil errado recebe 403.

- e abre todas as telas de cada perfil. Este teste depende de um problema descrito na próxima seção. apps/contas/test_telas_demo.py : roda o popular_demo , o modelo e a rotina diária,

O registro de progresso em CLAUDE.md informa que python manage.py check --deploy com USAR_HTTPS=True sai limpo. Essa verificação não foi refeita nesta análise, porque o banco real não estava disponível.

## Pontos de atenção e próximos passos

O projeto está coerente e bem documentado. A análise encontrou um problema real nos testes e algumas lacunas, listados do mais importante para o menos.

## 1. Dois testes falham em um clone limpo

Com python manage.py test em uma cópia nova do repositório (sem ml/modelo_evasao.joblib ), 2 dos 348 testes falham:

test_a_demonstracao_tem_riscos_e_alertas e test_modelo_encontra_os_alunos_montados_em_risco , ambos em

apps/contas/test_telas_demo.py . Com o arquivo do modelo já treinado na máquina, eles passam, e por isso o problema não aparece para quem desenvolve.

Causa: em ModeloTreinadoMixin ( apps/analytics/tests.py ), super().setUpClass()

roda primeiro. Ele executa setUpTestData , que chama popular_demo e rotina_diaria . Nesse momento o modelo temporário do teste ainda não existe, então a rotina procura o

arquivo real em ml/ , não o encontra e não grava nenhum risco.

Correção testada: treinar o modelo temporário antes de chamar super().setUpClass() . Aplicada em uma cópia, os 348 testes passaram sem o arquivo ml/ .


```
@classmethod
def setUpClass(cls):
pasta = tempfile.TemporaryDirectory()
cls.addClassCleanup(pasta.cleanup)
configuracao = override_settings(MODELO_EVASAO=Path(pasta.name) /
"modelo.joblib")
configuracao.enable()
cls.addClassCleanup(configuracao.disable)
cls.resultado = evasao.treinar(quantidade=400, arvores=25)
super().setUpClass() # agora vem por último
```

## 2. Publicação na Vercel (etapa 14) ainda não feita

O settings.py não define STATIC_ROOT e o projeto não usa WhiteNoise, então os arquivos estáticos precisam de uma solução ( collectstatic mais WhiteNoise ou a configuração da Vercel). O CLAUDE.md lista as decisões em aberto:

- como o modelo .joblib chega ao servidor (versionar ou treinar no build), já que a pasta ml/ fica fora do Git;

- Celery sem worker: CELERY_SEM_REDIS=True mais um Cron da Vercel para a rotina das 6h;

- Transaction pooler do Supabase (porta 6543) e o limite de cerca de 500 MB do pacote;

- bibliotecas novas precisam de aprovação, conforme as regras do projeto.

## 3. Evasão treinada só com dados simulados

Descrito na seção do módulo de evasão. Para usar dados reais, treinar() precisaria ler o histórico da escola no lugar de gerar_dados_simulados() , com as mesmas quatro colunas mais o rótulo evadiu .

## 4. Pequenos ajustes de documentação

- O README.md manda fazer cd projeto-escolar depois do git clone , mas a pasta se chama colegio-socratico , e o endereço do repositório fica como <endereço do repositório> .

- O repositório se chama colegio-socratico , enquanto o sistema se chama Instituto Socrático em todas as telas, por decisão registrada no CLAUDE.md .

- As datas da demonstração são calculadas a partir do dia em que o popular_demo roda, então vale rodá-lo pouco antes de apresentar.


## O que não foi verificado

O sistema não foi aberto no navegador e não foi ligado ao Supabase, ao Redis nem a um servidor de e-mail. A leitura do código, os 348 testes e o treino do modelo foram feitos em uma cópia local com SQLite. As telas e os PDFs não foram inspecionados visualmente.

## Fontes

- Repositório takathecode/colegio-socratico, commit f6f80eb , incluindo README.md , CLAUDE.md e a pasta docs/ . [URL 🔗](https://github.com/takathecode/colegio-socratico)
