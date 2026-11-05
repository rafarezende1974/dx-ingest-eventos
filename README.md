# Editor Assistente 2.0 — prévia em desenvolvimento

Branch isolada: `codex/editor-assistente-v2`. Não é uma release de produção.

## Primeira etapa da interface

- Tema escuro inicial, menu lateral com navegação para seções e cartões CustomTkinter de JPG, RAW, vídeo e áudio com contagens e tamanhos reais da análise.
- Ações, discos, progresso por bytes e status no topo; fila, checklist, equipe/multicâmera e registro preservados.
- Migração incremental: controles de formulário e listas continuam em Tk/ttk. O mockup original não estava acessível; esta etapa segue os elementos descritos, ainda sem validação de fidelidade visual.
- Preferência de tema da v2 separada, mantendo as demais configurações existentes.

## Segurança e compatibilidade

Mantidos staging, pastas 01–08, levas JPG, backups opcionais, manifest, relatórios e checklist. O cartão nunca é apagado ou formatado.

Testes expuseram uma falha pré-existente na retomada com hash: o código verificava o hash salvo, mas não recalculava o hash dos destinos. Agora a retomada SHA-256 verifica os arquivos no disco. Conteúdos diferentes com mesmo nome/tamanho são preservados e recebem sufixo, inclusive na promoção do staging.

Cada descarga usa uma fotografia das opções, sem ler variáveis Tk na thread de cópia. Origem é reanalisada antes de descarregar; sobreposição com destinos é rejeitada. Fechamento durante cópia é bloqueado; erros inesperados voltam à interface e não liberam ejeção.

## Executar e testar

Python 3.12 para Windows com Tcl/Tk:

```powershell
python -m pip install -r requirements-build.txt
python -m unittest discover -s tests -v
python app.py
```

O workflow executa testes com pastas temporárias, gera assets, empacota e abre/fecha o executável em modo de teste. `--smoke-test` cria a interface sem carregar configurações do usuário ou copiar arquivos.

O artefato `editor-assistente-v2-preview` contém **a pasta completa**: extraia tudo e abra `EditorAssistente.exe`. Não copie apenas o executável. O build usa `--onedir` e inclui os dados do CustomTkinter, conforme sua [documentação de empacotamento](https://customtkinter.tomschimansky.com/documentation/packaging/). Não há etapa de publicação de release.

## Antes de aprovar merge

- Revisão visual com o mockup original e teste em diferentes escalas de tela/DPI.
- Teste manual em cartões e discos físicos, inclusive desconexão e pouco espaço.
- Testes automatizados usam conteúdo sintético: não validam codecs nem integridade fotográfica/audiovisual.
- A análise ainda é síncrona; cartões grandes podem deixar a interface ocupada durante a varredura/hash.
- A verificação sem SHA-256 continua comparando tamanho, como na versão anterior. A retomada de colisões com sufixo pode refazer staging; prioriza preservação sobre desempenho.

Nenhum merge ou release deve ser realizado sem aprovação do responsável.
