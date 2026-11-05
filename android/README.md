# Editor Assistente Android — 0.1 alpha

Projeto separado da versão Windows oficial, na branch `codex/android-alpha`.

Fluxo-alvo confirmado: Galaxy Tab S9+, cartão da câmera no leitor USB do hub alimentado, destino primário no microSD inserido no tablet e cópia no SSD conectado ao mesmo hub.

## Esta primeira versão

- Kotlin + Jetpack Compose, tema escuro roxo/ciano, evento/data e profissional ou câmera.
- Seleção explícita das três pastas pelo Storage Access Framework. Só aceita o provedor local do Android, com três identificadores de volume diferentes; não aceita nuvem nem memória interna como destino.
- Origem com permissão somente de leitura. O app não possui operação de apagar, mover ou formatar a origem, nem permissão de acesso geral ao armazenamento ou à Internet.
- Análise recursiva e contagem de JPG, RAW, vídeo e áudio.
- Cópia microSD → conferência SHA-256 → cópia do arquivo verificado para SSD → conferência SHA-256. Verifica o arquivo temporário antes de renomeá-lo para o nome final.
- Progresso por bytes processados e contadores independentes de conferência nos dois destinos.
- Retomada **por arquivo inteiro**: a nova execução relê e compara hashes dos destinos. Conteúdo diferente recebe sufixo; nada é sobrescrito ou apagado. Temporários `.ea-*.part` são preservados se a operação falhar.
- Serviço em primeiro plano com notificação e bloqueio de suspensão da CPU durante a operação, respeitando limites do Android. Interrupção manual e tratamento de falhas/desconexão.
- Relatório por execução guardado no armazenamento privado do app, acessível pela tela Relatório. O histórico privado é apagado ao desinstalar o app; fotos e cópias externas não são apagadas.

## Primeiro teste no tablet

Use arquivos de teste e mantenha os originais. Esta é uma alpha, **não substitui a versão Windows em eventos reais**.

1. Extraia o APK do artefato `editor-assistente-android-alpha` e instale no tablet se desejar testar. O APK de desenvolvimento é assinado com chave debug, não é uma release Play Store.
2. Ligue a alimentação do hub e conecte leitor e SSD. Confirme primeiro no aplicativo Arquivos do Android que consegue abrir as três unidades.
3. Crie uma pasta `EventosTeste` no microSD e outra no SSD. O seletor Android pode impedir escolher a raiz; escolha essas pastas. Na origem, escolha `DCIM` ou a pasta com as mídias da câmera.
4. Selecione as três pastas no Editor Assistente, preencha evento/profissional, analise e descarregue.
5. Confira hashes/arquivos nos dois destinos e execute novamente: arquivos iguais devem ser reconferidos e pulados. Confira também o relatório.
6. Somente com material de teste: interrompa uma execução, reconecte as unidades e retome. Depois teste bloqueio de tela, rotação e desconexão do SSD.

O app não identifica fisicamente qual volume é o microSD ou SSD: o operador deve escolhê-los corretamente pelos nomes/IDs apresentados no seletor. IDs distintos não certificam dispositivos físicos distintos em discos com múltiplas partições.

## Limites desta alpha

- Compatibilidade do hub, leitor, alimentação, formato do SSD e permissões **ainda precisa ser comprovada no Tab S9+ real**. Não há garantia de gravação em NTFS; o volume precisa ser gravável pelo Android e permitir renomear documentos.
- O serviço reduz interrupções por suspensão, mas não garante continuidade após remoção do app, desconexão USB, encerramento pelo sistema ou limite de tempo do Android. A retomada é manual e não retoma bytes parciais.
- O SAF não garante transação atômica entre dispositivos. Há verificação antes de publicar e reconferência depois; não altere os destinos em outro aplicativo durante a descarga.
- Estrutura 01–08 por evento e participante, preservando subpastas da origem. Ainda não implementa as levas JPG `Cartao_N`, fila de múltiplos cartões, checklist de devolução, exportação do relatório ou detecção de contador zerado da versão Windows.
- Não prevê espaço livre total por unidade nesta etapa: falha de espaço interrompe a descarga e preserva a origem/temporários. O progresso mede bytes copiados ou já conferidos, não o tempo gasto calculando hash.
- Arquivos muito grandes demandam um sistema de arquivos que os suporte. Não troque/formate discos para testar; use unidades de teste já compatíveis.
- Os testes automatizados usam armazenamento em memória e não validam o provedor USB, desempenho, comportamento do hub ou integridade de codecs.

## Build

Android Studio com JDK 17, SDK 35 e Gradle 8.11.1. Abra a pasta `android/` como projeto. Sem wrapper nesta primeira etapa; o CI instala a versão fixada do Gradle:

```text
gradle -p android testDebugUnitTest lintDebug assembleDebug
```

O workflow `build-android.yml` gera o APK e o SHA-256 somente depois de passar testes e lint. Não modifica a release Windows nem publica release Android automaticamente.

Referências oficiais: [acesso a pastas com SAF](https://developer.android.com/training/data-storage/shared/documents-files) e [limites de serviços em primeiro plano](https://developer.android.com/develop/background-work/services/fgs/timeout).
