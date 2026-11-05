package br.com.editorassistente

import android.app.*
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.Uri
import android.os.*
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.update
import java.io.File
import java.time.LocalDateTime
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

data class TransferState(
    val running: Boolean = false, val status: String = "Selecione o cartão, o microSD e o SSD.",
    val current: String = "", val doneBytes: Long = 0, val totalBytes: Long = 0,
    val primary: Int = 0, val backup: Int = 0, val files: Int = 0,
    val counts: Map<Media, Int> = emptyMap(), val report: String = ""
)
object TransferStateHolder { val state = MutableStateFlow(TransferState()) }

class IngestService : Service() {
    private val executor = Executors.newSingleThreadExecutor()
    private val cancelled = AtomicBoolean(false)
    private var busy = false
    private var wakeLock: PowerManager.WakeLock? = null
    private val state get() = TransferStateHolder.state
    override fun onBind(intent: Intent?) = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == "CANCEL") {
            cancelled.set(true)
            state.update { it.copy(status = "Interrompendo; aguarde a liberação das gravações…") }
            return START_NOT_STICKY
        }
        if (intent == null || busy) return START_NOT_STICKY
        busy = true
        cancelled.set(false)
        val notifications = getSystemService(NotificationManager::class.java)
        notifications.createNotificationChannel(NotificationChannel("ingest", "Descarga de cartões", NotificationManager.IMPORTANCE_LOW))
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        val notification = NotificationCompat.Builder(this, "ingest")
            .setSmallIcon(android.R.drawable.stat_sys_upload).setContentTitle("Editor Assistente")
            .setContentText("Análise / cópia em andamento. Abra para acompanhar.").setOngoing(true)
            .setContentIntent(open).build()
        ServiceCompat.startForeground(this, 1, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        state.value = TransferState(running = true, status = "Lendo o cartão…")
        getSharedPreferences("config", MODE_PRIVATE).edit().putBoolean("unfinished", true).commit()
        executor.execute { runTransfer(intent, startId) }
        return START_NOT_STICKY
    }

    private fun runTransfer(intent: Intent, startId: Int) {
        val log = File(filesDir, "descarga-${System.currentTimeMillis()}.txt")
        val prefs = getSharedPreferences("config", MODE_PRIVATE)
        prefs.edit().putString("lastReport", log.name).apply()
        fun record(line: String) {
            val entry = "${LocalDateTime.now()} | $line\n"
            log.appendText(entry, Charsets.UTF_8)
            state.update { it.copy(report = (it.report + entry).takeLast(24000)) }
        }
        try {
            wakeLock = (getSystemService(POWER_SERVICE) as PowerManager)
                .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "EditorAssistente:Ingest")
                .apply { acquire(6 * 60 * 60 * 1000L) }
            val store = SafStorage(contentResolver)
            val check = { if (cancelled.get()) throw InterruptedException("Interrompido pelo usuário ou pelo Android") }
            val engine = CopyEngine(store, check)
            val sourceUri = Uri.parse(requireNotNull(intent.getStringExtra("source")))
            val source = store.root(sourceUri)
            val analyze = intent.action == "ANALYZE"
            val destinations = if (analyze) emptyList() else {
                val uris = listOf(sourceUri, Uri.parse(requireNotNull(intent.getStringExtra("primary"))),
                    Uri.parse(requireNotNull(intent.getStringExtra("backup"))))
                SafStorage.validateDistinct(uris)
                uris.drop(1).map(store::root)
            }
            val files = engine.scan(source)
            require(files.isNotEmpty()) { "Nenhum JPG, RAW, vídeo ou áudio encontrado nesta pasta." }
            val total = Math.multiplyExact(files.sumOf { it.node.size }, 2L)
            state.update { it.copy(files = files.size, counts = files.groupingBy { f -> f.media }.eachCount(), totalBytes = total) }
            record("Arquivos: ${files.size}. SHA-256 obrigatório. Origem somente leitura.")
            if (analyze) {
                state.update { it.copy(status = "Análise pronta. Confira os destinos antes de descarregar.") }
            } else {
                val event = safeName(requireNotNull(intent.getStringExtra("event")))
                val participant = safeName(requireNotNull(intent.getStringExtra("participant")))
                val mode = intent.getStringExtra("mode") ?: "Equipe"
                record("Evento: $event | $mode: $participant")
                state.update { it.copy(status = "Copiando e conferindo os dois destinos…") }
                var done = 0L
                var lastUpdate = 0L
                val progress: (Long) -> Unit = { n ->
                    done += n
                    val now = SystemClock.elapsedRealtime()
                    if (now - lastUpdate >= 150 || done >= total) {
                        state.update { it.copy(doneBytes = done) }
                        lastUpdate = now
                    }
                }
                for (file in files) {
                    check()
                    state.update { it.copy(current = "SHA-256 da origem: ${file.relative.joinToString("/")}") }
                    val digest = engine.hash(file.node)
                    require(digest.bytes == file.node.size) { "Arquivo mudou desde a análise: ${file.node.name}" }
                    if (digest.bytes == 0L) record("ALERTA: arquivo vazio ${file.node.name}; conferir no cartão.")
                    val relativeParent = file.relative.dropLast(1)
                    val primaryParent = engine.folder(destinations[0], listOf(event, file.media.primary, participant) + relativeParent)
                    state.update { it.copy(current = "microSD: ${file.node.name}") }
                    val primary = engine.copyVerified(file.node, primaryParent, file.relative.last(), digest, progress)
                    state.update { it.copy(primary = it.primary + 1) }
                    record("microSD CONFERIDO | ${file.relative.joinToString("/")} | ${digest.sha256} | retomada=${primary.skipped}")
                    val backupParent = engine.folder(destinations[1], listOf(event, file.media.backup, participant) + relativeParent)
                    state.update { it.copy(current = "SSD: ${file.node.name}") }
                    val backup = engine.copyVerified(primary.file, backupParent, file.relative.last(), digest, progress)
                    state.update { it.copy(backup = it.backup + 1) }
                    record("SSD CONFERIDO | ${file.relative.joinToString("/")} | ${digest.sha256} | retomada=${backup.skipped}")
                }
                check()
                record("CONCLUÍDO: ambos os destinos conferidos. Origem preservada.")
                state.update { it.copy(doneBytes = total, current = "", status = "microSD e SSD conferidos. Confira os arquivos antes de remover as unidades pelo Android.") }
            }
        } catch (error: Exception) {
            val message = "INTERROMPIDO: ${error.message ?: error.javaClass.simpleName}. Mantenha o cartão; reconecte as unidades e execute novamente para conferir/retomar."
            runCatching { record(message) }
            state.update { it.copy(status = message) }
        } finally {
            wakeLock?.let { if (it.isHeld) it.release() }
            prefs.edit().putBoolean("unfinished", false).commit()
            state.update { it.copy(running = false) }
            busy = false
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf(startId)
        }
    }

    override fun onTimeout(startId: Int, fgsType: Int) {
        cancelled.set(true)
        executor.shutdownNow()
        state.update { it.copy(status = "Limite de execução do Android atingido. Aguarde a interrupção e retome com o app aberto.") }
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf(startId)
    }
    override fun onDestroy() {
        cancelled.set(true)
        executor.shutdownNow()
        super.onDestroy()
    }
}
