# 🚀 Social Mídia Autônoma

App desktop local (Streamlit + SQLite) para pesquisa, roteirização, gestão e edição de conteúdo para Instagram/TikTok.

## Como rodar

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                # preencha as chaves que for usar
streamlit run app.py
```

O banco é criado automaticamente em `data/socialmidia.db`.

## Estrutura

```
app.py                  # entrada + menu lateral
database.py             # schema SQLite, migrações e acesso aos dados
modulos/                # uma página Streamlit por módulo (só interface)
  m0_dashboard.py       # Centro de Comando
  m1_cerebro.py         # Personas, Radar de Audiência, Assuntos Quentes, Histórico
  m2_maquina_conteudo.py
  m3_cofre_ideias.py    # Kanban
  m4_estudio.py         # Vídeo automático + carrosséis
  configuracoes.py      # provedor de IA, modelos e chaves de API
services/               # lógica sem Streamlit
  llm.py                # Ollama / OpenAI / Claude via LangChain + respostas em JSON
  scraper.py            # coleta de comentários (Apify) e importação manual (.txt/.csv)
  radar.py              # comentários -> IA -> Dores, Dicionário e Assuntos Quentes
  rastreador.py         # piloto automático: palavras-chave agendadas (APScheduler)
  maquina.py            # Termômetro de Validação, funil/formato e geração do roteiro
  cofre.py              # edição com registro no Dossiê e reciclagem de posts
  dashboard.py          # indicadores, alta performance e "Reciclar este tema"
  graficos.py           # gráficos do Dashboard (Plotly)
  video.py              # corte de silêncio, Whisper, legendas, zooms e motions
  motion.py             # motion graphics: stickers, tipografia cinética, CTA, transições, sons
  carrossel.py          # lâminas PNG sobre os templates + .zip
  estudio.py            # trabalhos do Estúdio (pastas, etapas, histórico)
assets/fontes/          # Source Sans Pro (licença SIL OFL) usada em legendas e carrosséis
worker.py               # roda o piloto automático com o app fechado
tests/                  # testes automatizados (IA simulada, sem custo)
data/                   # banco, uploads, templates e exportações (fora do git)
```

## Módulo 1 — Cérebro

1. **⚙️ Configurações**: escolha o provedor de IA. Para usar o **Ollama** (gratuito), instale em
   https://ollama.com e rode `ollama pull llama3.1`. Para OpenAI/Claude, informe a chave.
2. **👤 Personas**: cadastre cada perfil (público-alvo, tom de voz, palavras proibidas).
3. **📡 Radar de Audiência**: cole a URL de um post (coleta automática pela Apify, requer
   `APIFY_API_TOKEN`) ou cole/envie os comentários manualmente.
4. A IA gera **Dores**, **Dicionário do público** e **Alertas de Tendência**, que viram
   **🔥 Assuntos Quentes** e alimentam o Módulo 2.

### 🤖 Rastreador Automático (piloto automático)

Na aba **Rastreador Automático**, cadastre palavras-chave (ex.: `limpeza porcelanato manchado`).
No dia e horário configurados (padrão: **sexta às 08:00**), o app busca na Apify os vídeos mais
quentes de cada palavra, lê os comentários e envia **dores e tendências** para Assuntos Quentes.

- Funciona em segundo plano enquanto o app estiver aberto. Se o computador estiver desligado no
  horário, a rodada acontece assim que o app for aberto.
- Para rodar **com o app fechado**, use o worker:
  - `python worker.py` → fica rodando e respeita a agenda;
  - `python worker.py --agora` → roda só o que está pendente e encerra. Ideal para o
    **Agendador de Tarefas do Windows** (ou `cron` no Mac/Linux) toda sexta-feira.
- No Instagram, a busca usa a hashtag equivalente (`#limpezaporcelanatomanchado`).

## Módulo 2 — Máquina de Conteúdo

1. **Tema**: escolha um 🔥 Assunto Quente (ou escreva um tema livre), a persona e a plataforma.
2. **🌡️ Termômetro**: busca os vídeos concorrentes na Apify e calcula o **Score de Viralização**
   (50% números reais — views e engajamento — e 50% avaliação da IA), mostra os concorrentes e
   aponta a **Lacuna**. Validações dos últimos 7 dias são reaproveitadas para economizar créditos.
3. **Funil e Formato**: Topo, Meio ou Fundo; a IA sugere os 3 melhores formatos.
4. **Roteiro**: gancho de 3s, roteiro técnico (Áudio x Tela) ou lâminas do carrossel, legenda,
   CTA e hashtags — tudo editável. **Salvar no Cofre** envia para "Roteiros Prontos" (Módulo 3).

## Módulo 0 — Dashboard (Centro de Comando)

- **Indicadores** do período: posts publicados, views, média por post, taxa de salvamento e de
  compartilhamento — com filtro por persona e período.
- **🔔 Métricas pendentes**: 7 e 14 dias após a postagem, o post aparece com um formulário para
  lançar Views, Salvamentos, Compartilhamentos, Comentários e Curtidas.
- **🔥 Alta performance**: posts acima das metas (padrão 10.000 views ou 500 salvamentos,
  ajustáveis em ⚙️ Configurações) ou com 2x a mediana de views da persona ganham o botão
  **♻️ Reciclar este tema**, que cria um Assunto Quente e abre a Máquina de Conteúdo com ele.
- **📈 Gráficos**: top posts por views, taxa de salvamento por formato e views por data de
  postagem (com tabela dos dados).

## Módulo 3 — Cofre de Ideias (Kanban)

- Colunas: **💡 Ideias no Radar → 📝 Roteiros Prontos → 🎬 Em Edição → ✅ Postado**. Use ◀ ▶ nos cards.
- Ao mover para **Postado**, informe a data (e o link): o Dashboard pede as métricas 7 e 14 dias depois.
- Filtros por persona, plataforma, funil e busca por texto.
- **💡 Nova ideia** cria um card simples; o botão **⚙️** leva a ideia para a Máquina de Conteúdo e,
  ao salvar o roteiro lá, o próprio card avança para "Roteiros Prontos" (sem duplicar).
- **📂 Dossiê**: roteiro editável, referências (Assunto Quente, validação, lacuna, links), linha do
  tempo de tudo o que aconteceu com o card e métricas.
- **♻️ Reciclar** (cards postados): a IA reescreve o conteúdo em outro formato, usando o original e
  as métricas dele; a nova versão vira um card em "Roteiros Prontos", ligada ao post de origem.

## Módulo 4 — Estúdio de Produção

### 🎬 Vídeo Automático
1. **Etapa 1**: envie o vídeo bruto (pode vincular a um conteúdo do Cofre). O app **corta os
   silêncios** (sensibilidade ajustável) e **transcreve** com o Whisper, palavra por palavra.
2. Revise: veja o vídeo cortado e **corrija palavras** da transcrição, se precisar.
3. **Etapa 2**: escolha o estilo e renderize:
   - **Legendas sincronizadas** (2–4 palavras por vez, palavra falada em destaque por cor ou pílula,
     entrada em "pop" e saída rápida, dentro da área segura do Reels/TikTok);
   - **Zooms dinâmicos**: zoom alternado a cada corte (disfarça os cortes) e punch-in nas palavras
     de ênfase (números, exclamações, palavras longas ou em CAIXA ALTA);
   - **Motions**: movimento suave de câmera (Ken Burns), título do gancho animado nos primeiros
     segundos e barra de progresso;
   - Formato original ou **vertical 9:16**; exportação pela GPU (NVENC) com volta automática à CPU.
   - **🎨 Motion graphics** (tudo automático a partir da fala):
     - **Legenda estilo Hormozi**: 1–2 palavras gigantes, pop a cada palavra, cores alternando;
     - **Stickers flat 2D** (✔ ✖ ⚠ 💡 💰 ⏰ 📈 ❤ ⭐ 🔥 👇) quando você fala "erro", "dica",
       "dinheiro", "tempo", "resultado"… — desenhados pelo app, iguais em qualquer computador;
     - **Tipografia cinética** para números e frases de impacto ("3 ERROS", "72 HORAS");
     - **Selo de abertura** com seu @ e **CTA final** animado com toque no botão
       (Salvar / Seguir / Comentar / Link na bio);
     - **Transições** nos cortes (flash, zoom com desfoque, glitch ou alternando);
     - **Efeitos sonoros** sintetizados e sincronizados (whoosh, pop, clique, ding);
     - **Acabamento de cinema**: contraste, saturação, vinheta e granulado.
   A **prévia de um quadro** mostra o resultado antes de renderizar o vídeo todo.

#### Usando a placa NVIDIA (recomendado)
O `pip install -r requirements.txt` instala o PyTorch **sem** CUDA no Windows. Para o Whisper
usar a GPU, reinstale o PyTorch com CUDA usando o comando que o site https://pytorch.org gera
para o seu sistema, por exemplo:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu126
```

**Erro "no kernel image is available for execution on the device"?** O PyTorch instalado não tem
suporte ao modelo da sua placa (comum em placas mais antigas, como a série GTX 10xx, com o PyTorch
para CUDA 12.8). O app passa a usar a CPU sozinho e mostra o aviso no Estúdio. Para usar a placa,
descubra o modelo e a "capacidade" dela:

```bash
python -c "import torch; print(torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0))"
```

Se aparecer `(6, 1)`, `(6, 0)`, `(5, x)` ou `(7, 0)`, reinstale o PyTorch para **CUDA 12.6**:

```bash
python -m pip uninstall -y torch
python -m pip install torch --index-url https://download.pytorch.org/whl/cu126
```

Com a GPU detectada, o Estúdio usa o modelo **medium** (ótimo em português). Sem GPU, usa o
**small**. Dá para trocar em ⚙️ Configurações. Na primeira transcrição o Whisper baixa o modelo
(~1,5 GB para o medium). Não é preciso instalar o FFmpeg: o app usa o que vem com o moviepy.

### 🖼️ Fábrica de Carrosséis
- Cadastre **templates** (imagem de fundo, cores, posição do texto, escurecimento).
- Escolha um conteúdo do Cofre (as lâminas do roteiro entram automaticamente) ou cole um texto
  (linha em branco separa as lâminas; `*asteriscos*` destacam palavras na cor de destaque).
- O texto se ajusta sozinho ao espaço; capa maior, contador (2/8), assinatura e "arraste →".
- Gere e baixe o **.zip** com as lâminas em PNG (4:5, 1:1 ou 9:16).

> Os nomes e formatos dos coletores da Apify ficam em `services/scraper.py`
> (`ATORES_APIFY`, `ATORES_BUSCA_APIFY`, `_input_apify`, `_input_busca`).

## Testes

```bash
pip install pytest
python -m pytest -q
```
