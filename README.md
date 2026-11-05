# Editor Assistente 2.0.0

Versão oficial para Windows. Baixe o pacote completo em [Releases](https://github.com/rafarezende1974/dx-ingest-eventos/releases/tag/v2.0.0).

## Interface neon

- Tela principal reconstruída em CustomTkinter com base no mockup fornecido: identidade roxa/ciano, ícones, origem à esquerda, quatro cartões de mídia, progresso central, discos e fila visível. Não usa rolagem geral.
- Menu navega entre descarga, histórico, relatórios e configurações. O evento permanece visível e pode ser travado. Campos de caminhos e opções por tipo ficam nas configurações.
- Fila com seleção e estados reais de espera, cópia e conferência; edição da fila bloqueada durante execução.
- Arquivo atual e ritmo de processamento por bytes, com estimativa de tempo restante. O ritmo inclui bytes conferidos/pulados na retomada, portanto não equivale à velocidade física do disco. Nenhum dado de progresso demonstrativo é usado.
- Discos mostram espaço livre real; barras representam a proporção livre. Dados indisponíveis são indicados sem inventar capacidade.
- Tema neon escuro; preferências e dados antigos continuam compatíveis. A interface clássica permanece no código como base do controlador, mas o executável abre a nova interface.

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

O artefato `editor-assistente-2.0.0-windows` contém **a pasta completa**: extraia tudo e abra `EditorAssistente.exe`. Não copie apenas o executável. O build usa `--onedir` e inclui os dados do CustomTkinter, conforme sua [documentação de empacotamento](https://customtkinter.tomschimansky.com/documentation/packaging/). A tag `v2.0.0` publica ZIP e SHA-256 somente após testes, build e verificação de que o commit pertence à main.

## Limites e validação em campo

- Revisão do acabamento com o usuário e teste em diferentes escalas de tela/DPI. A implementação segue a composição do mockup, sem prometer reprodução pixel a pixel dos brilhos e gradientes da imagem.
- Teste manual em cartões e discos físicos, inclusive desconexão e pouco espaço.
- Testes automatizados usam conteúdo sintético: não validam codecs nem integridade fotográfica/audiovisual.
- A análise ainda é síncrona; cartões grandes podem deixar a interface ocupada durante a varredura.
- A verificação sem SHA-256 continua comparando tamanho, como na versão anterior. A retomada de colisões com sufixo pode refazer staging; prioriza preservação sobre desempenho.

Consulte [as notas da versão](RELEASE-NOTES.md) para atualização e compatibilidade.
