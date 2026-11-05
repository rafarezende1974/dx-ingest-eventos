package br.com.editorassistente

import android.content.ContentResolver
import android.net.Uri
import android.provider.DocumentsContract as DC
import java.io.InputStream
import java.io.OutputStream

/** Only the local external-storage provider is accepted for this hardware-focused alpha. */
class SafStorage(private val resolver: ContentResolver) : Storage {
    private val columns = arrayOf(DC.Document.COLUMN_DOCUMENT_ID, DC.Document.COLUMN_DISPLAY_NAME,
        DC.Document.COLUMN_MIME_TYPE, DC.Document.COLUMN_SIZE)

    companion object {
        const val AUTHORITY = "com.android.externalstorage.documents"
        fun volume(uri: Uri): String {
            require(uri.scheme == "content" && uri.authority == AUTHORITY && DC.isTreeUri(uri)) {
                "Selecione uma pasta em armazenamento local (cartão, microSD ou SSD), não na nuvem."
            }
            return DC.getTreeDocumentId(uri).substringBefore(':').also { require(it.isNotBlank()) }
        }
        fun validateDistinct(uris: List<Uri>) {
            require(uris.size == 3 && uris.map(::volume).distinct().size == 3) {
                "Origem, microSD e SSD precisam estar em três volumes diferentes."
            }
            require(uris.drop(1).none { volume(it) == "primary" }) {
                "Escolha microSD e SSD externos, não a memória interna do tablet."
            }
        }
    }

    fun root(uri: Uri): Node {
        volume(uri)
        return info(DC.buildDocumentUriUsingTree(uri, DC.getTreeDocumentId(uri))).also {
            require(it.directory) { "Selecione uma pasta" }
        }
    }
    private fun info(uri: Uri): Node = resolver.query(uri, columns, null, null, null)?.use { c ->
        require(c.moveToFirst()) { "Pasta ou arquivo indisponível: $uri" }
        Node(uri.toString(), c.getString(1), c.getString(2) == DC.Document.MIME_TYPE_DIR,
            if (c.isNull(3)) -1 else c.getLong(3))
    } ?: error("Não foi possível consultar $uri")

    override fun children(directory: Node): List<Node> {
        val uri = Uri.parse(directory.id)
        val children = DC.buildChildDocumentsUriUsingTree(uri, DC.getDocumentId(uri))
        return resolver.query(children, columns, null, null, null)?.use { c ->
            buildList {
                while (c.moveToNext()) add(Node(DC.buildDocumentUriUsingTree(uri, c.getString(0)).toString(),
                    c.getString(1), c.getString(2) == DC.Document.MIME_TYPE_DIR,
                    if (c.isNull(3)) -1 else c.getLong(3)))
            }
        } ?: error("Leitura indisponível. Confira conexão e permissão da pasta.")
    }
    override fun mkdir(parent: Node, name: String) = info(
        DC.createDocument(resolver, Uri.parse(parent.id), DC.Document.MIME_TYPE_DIR, name)
            ?: error("Não foi possível criar a pasta $name"))
    override fun create(parent: Node, name: String): Node {
        require(children(parent).none { it.name.equals(name, true) }) { "Nome já existe" }
        return info(DC.createDocument(resolver, Uri.parse(parent.id), "application/octet-stream", name)
            ?: error("Gravação indisponível. Confira espaço, conexão e permissão."))
    }
    override fun read(file: Node): InputStream = resolver.openInputStream(Uri.parse(file.id))
        ?: error("Arquivo não pode ser lido: ${file.name}")
    override fun writeNew(file: Node): OutputStream = resolver.openOutputStream(Uri.parse(file.id), "wt")
        ?: error("Destino não pode ser gravado: ${file.name}")
    override fun rename(file: Node, name: String): Node = info(
        DC.renameDocument(resolver, Uri.parse(file.id), name)
            ?: error("Este volume não permitiu finalizar o temporário. Não remova o cartão."))
}
