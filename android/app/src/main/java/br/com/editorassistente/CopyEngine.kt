package br.com.editorassistente

import java.io.InputStream
import java.io.OutputStream
import java.security.MessageDigest
import java.util.UUID

enum class Media(val primary: String, val backup: String) {
    JPG("01_Fotos_JPG", "02_Fotos_JPG_Copia"),
    VIDEO("03_Videos", "04_Videos_Copia"),
    RAW("05_RAW", "06_RAW_Copia"),
    AUDIO("07_Audio", "08_Audio_Copia");
    companion object {
        fun classify(name: String): Media? {
            val ext = name.substringAfterLast('.', "").lowercase()
            return when (ext) {
                "jpg", "jpeg" -> JPG
                "cr2", "cr3", "nef", "arw", "raf", "dng", "rw2", "orf", "pef", "x3f", "3fr", "mos", "erf" -> RAW
                "mp4", "mov", "mxf", "mts", "m2ts", "avi", "wmv", "mkv", "mpg", "mpeg", "insv" -> VIDEO
                "wav", "mp3", "m4a", "flac", "aac", "aif", "aiff", "ogg", "opus" -> AUDIO
                else -> null
            }
        }
    }
}

data class Node(val id: String, val name: String, val directory: Boolean, val size: Long)
data class SourceFile(val node: Node, val relative: List<String>, val media: Media)
data class Digest(val bytes: Long, val sha256: String)
interface Storage {
    fun children(directory: Node): List<Node>
    fun mkdir(parent: Node, name: String): Node
    fun create(parent: Node, name: String): Node
    fun read(file: Node): InputStream
    fun writeNew(file: Node): OutputStream
    fun rename(file: Node, name: String): Node
}

fun safeName(name: String): String {
    val value = name.trim().replace(Regex("[<>:\"/\\\\|?*\\p{Cntrl}]"), "_").trim('.', ' ')
    require(value.isNotBlank() && value != "." && value != "..") { "Nome de pasta inválido" }
    require(value.length <= 120) { "Nome muito longo (máximo 120 caracteres)" }
    return value
}

/** Streaming, no deletion API, no writes to the source, no overwrite fallback. */
class CopyEngine(private val storage: Storage, private val check: () -> Unit = {}) {
    private fun checkActive() {
        check()
        if (Thread.currentThread().isInterrupted) throw InterruptedException("Operação interrompida")
    }

    fun scan(root: Node): List<SourceFile> {
        val result = mutableListOf<SourceFile>()
        val visited = mutableSetOf<String>()
        fun visit(dir: Node, prefix: List<String>) {
            checkActive()
            require(prefix.size < 64 && visited.add(dir.id)) { "Estrutura circular ou profunda demais" }
            for (node in storage.children(dir)) {
                checkActive()
                if (node.directory) visit(node, prefix + safeName(node.name))
                else Media.classify(node.name)?.let {
                    require(node.size >= 0) { "Tamanho indisponível: ${node.name}" }
                    result += SourceFile(node, prefix + safeName(node.name), it)
                }
            }
        }
        visit(root, emptyList())
        return result
    }

    fun hash(file: Node): Digest {
        val hash = MessageDigest.getInstance("SHA-256")
        var size = 0L
        val buffer = ByteArray(1024 * 1024)
        storage.read(file).use { input ->
            while (true) {
                checkActive()
                val n = input.read(buffer)
                if (n < 0) break
                if (n == 0) continue
                hash.update(buffer, 0, n)
                size += n
            }
        }
        return Digest(size, hash.digest().joinToString("") { "%02x".format(it) })
    }

    fun folder(root: Node, path: List<String>): Node = path.fold(root) { parent, name ->
        checkActive()
        val clean = safeName(name)
        val match = storage.children(parent).filter { it.name.equals(clean, ignoreCase = true) }
        require(match.size <= 1) { "Destino ambíguo: $clean" }
        match.firstOrNull()?.also { require(it.directory) { "Uma pasta é necessária: $clean" } }
            ?: storage.mkdir(parent, clean)
    }

    data class Verified(val file: Node, val skipped: Boolean)
    fun copyVerified(source: Node, parent: Node, name: String, expected: Digest,
                     onBytes: (Long) -> Unit = {}): Verified {
        checkActive()
        val clean = safeName(name)
        val dot = clean.lastIndexOf('.').takeIf { it > 0 } ?: clean.length
        var index = 0
        var selected: String
        // Rehash actual destinations: a saved status can never substitute for disk verification.
        while (true) {
            selected = if (index == 0) clean else clean.take(dot) + "_$index" + clean.drop(dot)
            val matches = storage.children(parent).filter { it.name.equals(selected, ignoreCase = true) }
            require(matches.size <= 1) { "Destino ambíguo: $selected" }
            val existing = matches.firstOrNull() ?: break
            if (!existing.directory && hash(existing) == expected) {
                onBytes(expected.bytes)
                return Verified(existing, true)
            }
            index++
        }
        val part = storage.create(parent, ".ea-${UUID.randomUUID()}.part")
        var copied = 0L
        val streamHash = MessageDigest.getInstance("SHA-256")
        storage.read(source).use { input ->
            storage.writeNew(part).use { output ->
                val buffer = ByteArray(1024 * 1024)
                while (true) {
                    checkActive()
                    val n = input.read(buffer)
                    if (n < 0) break
                    if (n == 0) continue
                    output.write(buffer, 0, n)
                    streamHash.update(buffer, 0, n)
                    copied += n
                    onBytes(n.toLong())
                }
                output.flush()
            }
        }
        val actual = Digest(copied, streamHash.digest().joinToString("") { "%02x".format(it) })
        require(actual == expected) { "A origem mudou ou a leitura foi interrompida: ${source.name}" }
        require(hash(part) == expected) { "SHA-256 divergente no destino; temporário preservado" }
        checkActive()
        require(storage.children(parent).none { it.name.equals(selected, ignoreCase = true) }) {
            "Destino apareceu durante a cópia; temporário preservado"
        }
        val published = storage.rename(part, selected)
        require(published.name == selected && hash(published) == expected) { "Falha na conferência final" }
        return Verified(published, false)
    }
}
