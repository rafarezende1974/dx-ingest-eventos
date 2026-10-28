# DX Ingest Eventos v1.3.0 — cópias em outra unidade/pasta

- **Nova estrutura, numeração global:** primário fica em D:,
  cópias vão para outra unidade ou pasta a definir.
  - D: (primário): `01_Fotos_JPG`, `03_Videos`, `05_RAW`
  - Cópias: `02_Fotos_JPG_Copia`, `04_Videos_Copia`, `06_RAW_Copia`
  - Os nomes não têm mais "Sincronizar" nem "Backup".
  - Se a pasta de cópias estiver vazia na tela, as cópias
    continuam em D:, nos mesmos números 02, 04 e 06, para
    não perder a cópia por esquecimento.
  - Pastas de eventos antigos (01_Sincronizar etc.) não são
    migradas automaticamente — só os novos eventos usam a
    estrutura nova.
- O espaço livre agora é conferido separadamente: D: para o
  primário, pasta de cópias para as cópias.
- Novo checkbox "Cópia do RAW (06)", ao lado de JPG (02) e
  vídeo (04).

# DX Ingest Eventos v1.2.0 — "quero tudo"

- **Splash sem borda branca:** a janela do splash agora usa cor-chave
  transparente no Windows, então só o círculo do logo aparece,
  sem o quadrado branco em volta. Se o sistema não suportar
  transparência, cai para fundo preto.
- **Staging — pasta só pronta pro editor:** os arquivos vão
  primeiro para `.staging` dentro da pasta do evento, fora das
  pastas de sincronização. Só depois da conferência eles são
  movidos (renomeados, rápidos, na mesma unidade) para as pastas
  finais, e então copiados para as pastas de cópia. O editor/sync
  nunca vê arquivo incompleto.
- **Verificação por hash (opcional):** checkbox "Verificação
  completa por hash". Quando ligada, confere o conteúdo (SHA-256)
  das cópias novas e, se um arquivo já existente tiver o mesmo
  tamanho mas conteúdo diferente (corrompido), ele é recopiado.
  Mais lenta, use principalmente para RAW/backup.
- **Alerta de par RAW/JPG:** na análise, avisa quantos JPG estão
  sem RAW e quantos RAW estão sem JPG (mesmo nome base).
- **Fila de cartões + perfis:** adicione vários cartões
  (origem + profissional) à fila e descarregue um atrás do outro,
  no mesmo evento. Profissionais, evento, pasta base e backup
  externo ficam salvos em `dx-ingest-config.json` ao lado do .exe,
  para não digitar tudo de novo no próximo evento.
- **Backup externo opcional (só RAW):** informe uma pasta base
  externa (ex.: `E:\Backup`) e o RAW vai também para lá, além
  do backup em D:. A cópia em D: protege contra apagar sem
  querer, não contra falha do HD D:.
- **Som + ejetar com segurança:** som de conclusão diferente
  de som de falha (Windows), e botão "Ejetar com segurança"
  que só libera após descarga sem falhas — ele abre a janela
  de remoção segura do Windows para escolher o cartão.
- Extensão nova: vídeo Insta360 `.insv`.

# DX Ingest Eventos v1.1.0

## Novidade da v1.1: logo e ícone

- Ao abrir, o app mostra um splash com o logo audiovisual completo
  (`#digaxiiiss`), que some sozinho em cerca de 1,5 segundo, sem
  exigir clique.
- O ícone do .exe e da janela é derivado do logo: o diafragma do
  logo + uma seta de descarga, em preto e branco, legível em
  tamanho pequeno.
- Como a integração do GitHub só empurra texto, os arquivos binários
  (PNG/ICO) NÃO vão ao repo: o `generate_assets.py` guarda o logo
  em base64 (texto) e recria `assets/logo.png`, `assets/icon.png`
  e `assets/icon.ico` no runner, antes do PyInstaller. O workflow
  já inclui esse passo.

# DX Ingest Eventos v1.0.0 — protótipo (base)

Programa Windows para descarga de cartões em eventos. Copia, nunca move.
Não apaga nem formata o cartão. Não sobe nada para o Drive por conta própria.

## O que ele faz

1. Você escolhe o cartão/pasta de origem, o evento (data + nome) e o profissional
   (ex.: `Fotografo_01`, `Cinegrafista_01`).
2. Clica em **Analisar cartão**: ele mostra quantos JPG, RAW e vídeos achou,
   quanto vai copiar (JPG e vídeo contam 2x, por causa da cópia) e quanto
   espaço livre há no destino.
3. Clica em **Descarregar**: ele copia para a estrutura abaixo e confere
   por tamanho ao final, gerando `relatorio-descarga.txt` dentro da pasta
   do evento.

```
D:\Eventos\<AAAA-MM-DD>_<Nome do evento>\
  01_Fotos_JPG_Sincronizar\<Profissional>\
  02_Fotos_JPG_Copia\<Profissional>\
  03_Videos_Sincronizar\<Profissional>\
  04_Videos_Copia\<Profissional>\
  05_RAW_Backup\<Profissional>\
  relatorio-descarga.txt
```

- JPG -> 01 + 02 (a 02 pode ser desligada na tela, se não quiser a cópia)
- Vídeo (MP4, MOV, MXF, MTS, M2TS, AVI, WMV, MKV) -> 03 + 04
- RAW (CR2, CR3, NEF, ARW, RAF, DNG, RW2, ORF e outros) -> só 05
- Arquivos de outro tipo são ignorados e contados como "Outros".
- Mesmo nome de arquivo de profissionais diferentes não se sobrescreve:
  fica em subpasta por profissional, e dentro da mesma pasta um nome
  repetido com conteúdo diferente ganha sufixo `_1`, `_2`...
- Se o arquivo já existir no destino com o mesmo tamanho, ele é pulado
  e registrado no relatório (a 2ª descarga do mesmo cartão não duplica).
- Só depois de conferir as pastas, ejete o cartão. Formatar é manual,
  fora do programa, de propósito.

## Como gerar o .exe (mesmo esquema do DX Downloader)

A integração do Muse não consegue criar repositórios no GitHub (erro 403),
então o passo 1 é manual, igual ao dos outros apps:

1. No GitHub, crie o repositório (sugestão: `dx-ingest-eventos`).
   Pode ser público ou privado, como preferir.
2. Me avise que criou. Eu subo o `app.py` e este LEIA-ME para a `main`.
3. No GitHub, crie o arquivo `.github/workflows/build-windows.yml`
   colando o conteúdo de `WORKFLOW-BUILD-WINDOWS.yml.txt` deste projeto.
   Esse commit dispara o build.
4. Quando o build ficar verde, baixe o artefato `dx-ingest-eventos`
   (arquivo `DXIngestEventos.exe`, portátil, sem instalar).
5. Na 1ª execução o Windows pode avisar "editor desconhecido"
   (SmartScreen, porque o .exe não é assinado). É o mesmo aviso do
   DX Downloader.
6. Se for testar uma versão nova, apague o .exe antigo antes — os
   artefatos têm sempre o mesmo nome.

## Teste recomendado antes de usar num evento real

1. Crie uma pasta de teste imitando um cartão, com 2 ou 3 JPG, 1 RAW
   e 1 vídeo pequeno.
2. No programa, mude a pasta base de destino para uma pasta de teste
   (não D: ainda) e faça a descarga.
3. Confira: pastas 01 a 05, subpasta do profissional, relatório,
   e rode de novo para ver que a 2ª vez só pula arquivos.
4. Só depois use com D: e com um cartão real — e confira o relatório
   antes de ejetar o cartão.

## Limites da v1 (de propósito)

- Verificação por tamanho, não por hash completo (rápido para vídeos
  grandes; um arquivo com mesmo nome e mesmo tamanho é tratado como
  já copiado).
- Sem renomeação, sem apagar foto ruim e sem upload para o Drive —
  isso continua com o editor.
- Sem detecção automática de cartão: você escolhe a pasta de origem.
- Windows apenas; a pasta base padrão é `D:\Eventos`, mas pode ser
  alterada na tela.
