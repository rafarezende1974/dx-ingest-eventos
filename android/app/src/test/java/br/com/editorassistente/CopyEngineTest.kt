package br.com.editorassistente

import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.OutputStream

class CopyEngineTest {
    private class MemoryStorage : Storage {
        val nodes = linkedMapOf<String, Node>()
        val parents = mutableMapOf<String, String>()
        val data = mutableMapOf<String, ByteArray>()
        var writes = 0
        var corruptWrites = false
        var failRename = false
        fun root(name: String) = Node(name, name, true, 0).also { nodes[it.id] = it }
        fun source(parent: Node, name: String, bytes: ByteArray): Node = create(parent, name).also {
            data[it.id] = bytes.copyOf()
            nodes[it.id] = it.copy(size = bytes.size.toLong())
        }.let { nodes.getValue(it.id) }
        override fun children(directory: Node) = nodes.values.filter { parents[it.id] == directory.id }
        override fun mkdir(parent: Node, name: String) = create(parent, name).copy(directory = true).also { nodes[it.id] = it }
        override fun create(parent: Node, name: String): Node {
            require(children(parent).none { it.name == name })
            val node = Node("id${nodes.size}", name, false, 0)
            nodes[node.id] = node
            parents[node.id] = parent.id
            data[node.id] = byteArrayOf()
            return node
        }
        override fun read(file: Node) = ByteArrayInputStream(data.getValue(file.id))
        override fun writeNew(file: Node): OutputStream {
            writes++
            return object : ByteArrayOutputStream() {
                override fun close() {
                    super.close()
                    val bytes = toByteArray()
                    if (corruptWrites && bytes.isNotEmpty()) bytes[0] = (bytes[0].toInt() xor 1).toByte()
                    data[file.id] = bytes
                    nodes[file.id] = nodes.getValue(file.id).copy(size = bytes.size.toLong())
                }
            }
        }
        override fun rename(file: Node, name: String): Node {
            if (failRename) error("USB unavailable")
            return nodes.getValue(file.id).copy(name = name).also { nodes[file.id] = it }
        }
    }

    @Test fun twoDestinationsVerifiedAndSourcePreserved() {
        val s = MemoryStorage()
        val source = s.source(s.root("camera"), "photo.jpg", ByteArray(2100000) { (it % 251).toByte() })
        val original = s.data.getValue(source.id).copyOf()
        val engine = CopyEngine(s)
        val digest = engine.hash(source)
        var processed = 0L
        val primary = engine.copyVerified(source, s.root("sd"), source.name, digest) { processed += it }
        val backup = engine.copyVerified(primary.file, s.root("ssd"), source.name, digest) { processed += it }
        assertEquals(digest, engine.hash(primary.file))
        assertEquals(digest, engine.hash(backup.file))
        assertArrayEquals(original, s.data[source.id])
        assertEquals(original.size * 2L, processed)
    }

    @Test fun resumeReadsDestinationInsteadOfTrustingHistory() {
        val s = MemoryStorage()
        val source = s.source(s.root("camera"), "raw.cr3", byteArrayOf(1, 2, 3))
        val sd = s.root("sd")
        val e = CopyEngine(s)
        val hash = e.hash(source)
        val first = e.copyVerified(source, sd, source.name, hash)
        assertTrue(e.copyVerified(source, sd, source.name, hash).skipped)
        assertEquals(1, s.writes)
        s.data[first.file.id] = byteArrayOf(9, 9, 9)
        val repaired = e.copyVerified(source, sd, source.name, hash)
        assertFalse(repaired.skipped)
        assertEquals("raw_1.cr3", repaired.file.name)
        assertArrayEquals(byteArrayOf(9, 9, 9), s.data[first.file.id])
        assertEquals(hash, e.hash(repaired.file))
        assertTrue(e.copyVerified(source, sd, source.name, hash).skipped)
        assertEquals(2, s.writes)
    }

    @Test fun corruptDestinationNeverGetsFinalName() {
        val s = MemoryStorage()
        val source = s.source(s.root("camera"), "audio.wav", byteArrayOf(1, 2, 3))
        val sd = s.root("sd")
        val e = CopyEngine(s)
        s.corruptWrites = true
        assertThrows(IllegalArgumentException::class.java) { e.copyVerified(source, sd, source.name, e.hash(source)) }
        assertFalse(s.children(sd).any { it.name == source.name })
        assertTrue(s.children(sd).all { it.name.endsWith(".part") })
    }

    @Test fun renameFailureRetainsVerifiedTemporary() {
        val s = MemoryStorage()
        val source = s.source(s.root("camera"), "video.mov", byteArrayOf(1, 2, 3))
        val sd = s.root("sd")
        val e = CopyEngine(s)
        s.failRename = true
        assertThrows(IllegalStateException::class.java) { e.copyVerified(source, sd, source.name, e.hash(source)) }
        assertEquals(e.hash(source), e.hash(s.children(sd).single()))
        assertTrue(s.children(sd).single().name.endsWith(".part"))
    }

    @Test fun changedSourceCannotBePublishedWithOldHash() {
        val s = MemoryStorage()
        val source = s.source(s.root("camera"), "photo.jpg", byteArrayOf(1, 2, 3))
        val sd = s.root("sd")
        val e = CopyEngine(s)
        val digest = e.hash(source)
        s.data[source.id] = byteArrayOf(3, 2, 1)
        assertThrows(IllegalArgumentException::class.java) { e.copyVerified(source, sd, source.name, digest) }
        assertFalse(s.children(sd).any { it.name == source.name })
    }

    @Test fun cancellationBeforeCopyCreatesNothing() {
        val s = MemoryStorage()
        val source = s.source(s.root("camera"), "audio.wav", byteArrayOf(1))
        val sd = s.root("sd")
        val hash = CopyEngine(s).hash(source)
        val e = CopyEngine(s) { throw InterruptedException("cancelled") }
        assertThrows(InterruptedException::class.java) { e.copyVerified(source, sd, source.name, hash) }
        assertTrue(s.children(sd).isEmpty())
    }

    @Test fun recursiveScanClassifiesMediaAndIgnoresTemporaryFiles() {
        val s = MemoryStorage()
        val camera = s.root("camera")
        val dcim = s.mkdir(camera, "DCIM")
        listOf("A.JPG", "A.CR3", "B.MOV", "C.WAV", "ignored.part").forEach { s.source(dcim, it, byteArrayOf(1)) }
        val files = CopyEngine(s).scan(camera)
        assertEquals(4, files.size)
        assertEquals(Media.entries.toSet(), files.map { it.media }.toSet())
        assertTrue(files.all { it.relative.first() == "DCIM" })
    }

    @Test fun unsafeAndEmptyFolderNamesAreRejectedOrSanitized() {
        assertThrows(IllegalArgumentException::class.java) { safeName("..") }
        assertThrows(IllegalArgumentException::class.java) { safeName("   ") }
        assertEquals("Evento_2026", safeName("Evento/2026"))
    }
}
