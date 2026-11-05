package br.com.editorassistente

import android.Manifest
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.DocumentsContract
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import java.io.File
import java.time.LocalDate

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val prefs = getSharedPreferences("config", MODE_PRIVATE)
        if (!TransferStateHolder.state.value.running && prefs.getBoolean("unfinished", false)) {
            TransferStateHolder.state.value = TransferState(status = "A última descarga foi interrompida. Reconecte as três unidades e execute novamente; os destinos serão reconferidos.")
        }
        setContent {
            MaterialTheme(colorScheme = darkColorScheme(primary = Color(0xFFB465FF), secondary = Color(0xFF15E6D3),
                background = Color(0xFF0E101B), surface = Color(0xFF1A1C2B))) {
                Screen()
            }
        }
    }

    @Composable private fun Screen() {
        val state by TransferStateHolder.state.collectAsStateWithLifecycle()
        var source by rememberSaveable { mutableStateOf(prefs().getString("source", "") ?: "") }
        var primary by rememberSaveable { mutableStateOf(prefs().getString("primary", "") ?: "") }
        var backup by rememberSaveable { mutableStateOf(prefs().getString("backup", "") ?: "") }
        var event by rememberSaveable { mutableStateOf(prefs().getString("event", "") ?: "") }
        var date by rememberSaveable { mutableStateOf(LocalDate.now().toString()) }
        var person by rememberSaveable { mutableStateOf(prefs().getString("participant", "Fotografo_01") ?: "Fotografo_01") }
        var mode by rememberSaveable { mutableStateOf(prefs().getString("mode", "Equipe") ?: "Equipe") }
        var selecting by rememberSaveable { mutableStateOf("source") }
        var error by rememberSaveable { mutableStateOf("") }
        var showReport by rememberSaveable { mutableStateOf(false) }
        val notifications = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { }
        val picker = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            if (result.resultCode == RESULT_OK) result.data?.data?.let { uri ->
                runCatching {
                    SafStorage.volume(uri)
                    val requested = Intent.FLAG_GRANT_READ_URI_PERMISSION or
                        if (selecting == "source") 0 else Intent.FLAG_GRANT_WRITE_URI_PERMISSION
                    val granted = (result.data?.flags ?: 0) and requested
                    require(granted == requested) { "É necessário autorizar leitura e, nos destinos, gravação." }
                    contentResolver.takePersistableUriPermission(uri, granted)
                    prefs().edit().putString(selecting, uri.toString()).apply()
                    when (selecting) {
                        "source" -> source = uri.toString()
                        "primary" -> primary = uri.toString()
                        else -> backup = uri.toString()
                    }
                    error = ""
                }.onFailure { error = it.message ?: "Falha ao autorizar a pasta" }
            }
        }
        fun choose(key: String) {
            selecting = key
            val grants = Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION or
                Intent.FLAG_GRANT_PREFIX_URI_PERMISSION or if (key == "source") 0 else Intent.FLAG_GRANT_WRITE_URI_PERMISSION
            picker.launch(Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).addFlags(grants))
        }
        fun start(analyze: Boolean) {
            runCatching {
                require(source.isNotBlank()) { "Selecione a pasta do cartão da câmera" }
                if (!analyze) {
                    require(primary.isNotBlank() && backup.isNotBlank()) { "Selecione as pastas no microSD e no SSD" }
                    SafStorage.validateDistinct(listOf(source, primary, backup).map(Uri::parse))
                    LocalDate.parse(date)
                    safeName(event)
                    safeName(person)
                }
                prefs().edit().putString("event", event).putString("participant", person).putString("mode", mode).apply()
                if (Build.VERSION.SDK_INT >= 33) notifications.launch(Manifest.permission.POST_NOTIFICATIONS)
                ContextCompat.startForegroundService(this@MainActivity, Intent(this@MainActivity, IngestService::class.java)
                    .setAction(if (analyze) "ANALYZE" else "COPY").putExtra("source", source)
                    .putExtra("primary", primary).putExtra("backup", backup)
                    .putExtra("event", "${date}_${event}").putExtra("participant", person).putExtra("mode", mode))
                error = ""
            }.onFailure { error = it.message ?: "Não foi possível iniciar" }
        }
        Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).safeDrawingPadding()
            .verticalScroll(rememberScrollState()).padding(24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Text("Editor Assistente", style = MaterialTheme.typography.headlineLarge)
            Text("ANDROID · 0.1 ALPHA   |   Cartão → microSD → SSD", color = MaterialTheme.colorScheme.secondary)
            Text("Primeira versão para testar o acesso às unidades no Galaxy Tab S9+. Use arquivos de teste.")
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(date, { date = it }, label = { Text("Data (AAAA-MM-DD)") }, enabled = !state.running, modifier = Modifier.weight(1f))
                OutlinedTextField(event, { event = it }, label = { Text("Evento") }, enabled = !state.running, modifier = Modifier.weight(2f))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedButton(onClick = { mode = if (mode == "Equipe") "Multicâmera" else "Equipe" }, enabled = !state.running) { Text(mode) }
                OutlinedTextField(person, { person = it }, label = { Text(if (mode == "Equipe") "Profissional" else "Câmera") }, enabled = !state.running, modifier = Modifier.weight(1f))
            }
            Location("1 · Cartão da câmera / leitor USB", source, !state.running) { choose("source") }
            Location("2 · Principal / microSD do tablet", primary, !state.running) { choose("primary") }
            Location("3 · Cópia / SSD externo no hub", backup, !state.running) { choose("backup") }
            Text("Escolha pastas, como DCIM na origem e Eventos nos destinos. O Android pode impedir selecionar a raiz de um volume.", style = MaterialTheme.typography.bodySmall)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Media.entries.forEach { media ->
                    Card(Modifier.weight(1f)) { Column(Modifier.padding(12.dp)) {
                        Text(media.name, color = MaterialTheme.colorScheme.secondary)
                        Text((state.counts[media] ?: 0).toString(), style = MaterialTheme.typography.headlineMedium)
                    } }
                }
            }
            Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(state.status, style = MaterialTheme.typography.titleMedium)
                Text(state.current)
                LinearProgressIndicator(progress = { if (state.totalBytes == 0L) 0f else (state.doneBytes.toFloat() / state.totalBytes).coerceIn(0f, 1f) }, modifier = Modifier.fillMaxWidth())
                Text("microSD: ${state.primary}/${state.files} conferidos   ·   SSD: ${state.backup}/${state.files} conferidos")
                Text("SHA-256 obrigatório nos dois destinos. O cartão nunca é apagado.")
            } }
            if (error.isNotBlank()) Text(error, color = MaterialTheme.colorScheme.error)
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedButton(onClick = { start(true) }, enabled = !state.running) { Text("Analisar cartão") }
                Button(onClick = { start(false) }, enabled = !state.running) { Text("Descarregar / retomar") }
                OutlinedButton(onClick = { showReport = !showReport }) { Text("Relatório") }
                if (state.running) OutlinedButton(onClick = {
                    startService(Intent(this@MainActivity, IngestService::class.java).setAction("CANCEL"))
                }) { Text("Interromper") }
            }
            if (showReport) {
                val report = state.report.ifBlank {
                    prefs().getString("lastReport", null)?.let { runCatching { File(filesDir, it).readText().takeLast(24000) }.getOrNull() }
                        ?: "Nenhuma descarga registrada."
                }
                Text(report, style = MaterialTheme.typography.bodySmall)
            }
        }
    }

    @Composable private fun Location(title: String, value: String, enabled: Boolean, select: () -> Unit) {
        Card(Modifier.fillMaxWidth()) {
            Row(Modifier.padding(16.dp), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                Column(Modifier.weight(1f)) {
                    Text(title, style = MaterialTheme.typography.titleMedium)
                    Text(if (value.isBlank()) "Nenhuma pasta selecionada" else
                        runCatching { DocumentsContract.getTreeDocumentId(Uri.parse(value)) }.getOrDefault(value))
                }
                OutlinedButton(onClick = select, enabled = enabled) { Text("Selecionar") }
            }
        }
    }
    private fun prefs() = getSharedPreferences("config", MODE_PRIVATE)
}
