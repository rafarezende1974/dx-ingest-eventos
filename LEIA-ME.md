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
