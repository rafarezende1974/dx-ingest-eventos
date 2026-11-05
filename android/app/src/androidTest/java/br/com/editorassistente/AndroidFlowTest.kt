package br.com.editorassistente

import android.content.Intent
import android.net.Uri
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test

class AndroidFlowTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()

    @Test fun startsAndRejectsMissingSource() {
        compose.onNodeWithText("Editor Assistente").assertIsDisplayed()
        compose.onNodeWithText("Analisar cartão").performScrollTo().performClick()
        compose.onNodeWithText("Selecione a pasta do cartão da câmera").assertIsDisplayed()
        assertFalse(TransferStateHolder.state.value.running)
    }

    @Test fun opensAndroidFolderPicker() {
        val activity = compose.activity
        val providerPackage = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE)
            .resolveActivity(activity.packageManager)?.packageName
        assertNotNull(providerPackage)
        compose.onAllNodesWithText("Selecionar")[0].performScrollTo().performClick()
        val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
        assertTrue(device.wait(Until.hasObject(By.pkg(providerPackage!!)), 10000))
        device.pressBack()
    }

    @Test fun rejectsSameVolumesAndNonLocalProviders() {
        fun uri(id: String) = Uri.parse("content://${SafStorage.AUTHORITY}/tree/${Uri.encode(id)}")
        assertThrows(IllegalArgumentException::class.java) {
            SafStorage.validateDistinct(listOf(uri("CARD:DCIM"), uri("SD:Eventos"), uri("SD:Copias")))
        }
        assertThrows(IllegalArgumentException::class.java) {
            SafStorage.validateDistinct(listOf(uri("CARD:DCIM"), uri("primary:Eventos"), uri("SSD:Copias")))
        }
        assertThrows(IllegalArgumentException::class.java) {
            SafStorage.volume(Uri.parse("content://cloud.example/tree/root"))
        }
        SafStorage.validateDistinct(listOf(uri("CARD:DCIM"), uri("SD:Eventos"), uri("SSD:Copias")))
    }
}
