# Editor Assistente 2.0.0

Versão oficial com a interface neon aprovada: menu lateral, painel de origem, cartões JPG/RAW/vídeo/áudio, progresso, discos e fila no painel principal. Histórico, relatórios e configurações têm páginas próprias.

Mantidos staging, retomada, backups, SHA-256, relatórios, levas e modos equipe/multicâmera. A retomada com SHA-256 confere os destinos no disco; colisões de conteúdo preservam os arquivos existentes. O aplicativo copia, nunca apaga ou formata o cartão.

## Como usar

1. Baixe `EditorAssistente-2.0.0-Windows.zip` e extraia **a pasta inteira**.
2. Abra `EditorAssistente.exe` pelo Explorador de Arquivos, em sua sessão normal do Windows.
3. Confira a origem, o evento e os destinos antes de descarregar.

Não substitua apenas o executável: mantenha a pasta `_internal` que acompanha o pacote. Para conservar suas preferências, copie `dx-ingest-config.json` da versão anterior para junto do novo executável, com ambos fechados. Não é necessário mover os eventos ou cartões.

O arquivo `SHA256SUMS.txt` permite conferir o ZIP baixado.

## Validação e limites

O build Windows executa a suíte automatizada de regressão e da interface, além de testar a inicialização do executável antes de publicar. Os testes usam pastas e arquivos sintéticos; não certificam cartões, discos físicos ou codecs.

A análise de cartões ainda é síncrona. O ritmo exibido inclui bytes processados por retomada e não equivale à velocidade física de escrita; o tempo restante é uma estimativa. Sem SHA-256, a comparação continua por tamanho. A retomada de colisões com sufixo pode refazer staging.
