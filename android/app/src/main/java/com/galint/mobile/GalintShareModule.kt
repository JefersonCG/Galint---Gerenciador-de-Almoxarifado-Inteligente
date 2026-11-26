package com.galint.mobile

import android.content.ClipData
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import androidx.core.content.FileProvider
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import com.facebook.react.bridge.ReadableArray
import com.facebook.react.bridge.UiThreadUtil
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL
import org.json.JSONObject

/**
 * Compartilhar uma saída ou devolução no WhatsApp com a FOTO do item e o texto como legenda
 * (pedido do usuário em 21/11/2026). O link whatsapp://send?text= e o Share do React Native só
 * levam texto no Android; aqui vai um ACTION_SEND com EXTRA_STREAM (foto) e EXTRA_TEXT (legenda).
 *
 * A foto do item vem do servidor em .webp; ela é convertida para JPEG (o WhatsApp pode tratar
 * .webp como figurinha) e reduzida para no máximo 1280 px. Sem WhatsApp instalado, abre o
 * compartilhar do Android. Sem foto (ou se o download falhar), vai só o texto.
 */
class GalintShareModule(private val context: ReactApplicationContext) : ReactContextBaseJavaModule(context) {

    override fun getName(): String = "GalintShare"

    @ReactMethod
    fun shareToWhatsApp(text: String, imageUrl: String?, promise: Promise) {
        Thread {
            try {
                val imageUri = if (imageUrl.isNullOrBlank()) null else downloadAsJpeg(imageUrl)
                val send = Intent(Intent.ACTION_SEND).apply {
                    putExtra(Intent.EXTRA_TEXT, text)
                    if (imageUri != null) {
                        type = "image/jpeg"
                        putExtra(Intent.EXTRA_STREAM, imageUri)
                        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    } else {
                        type = "text/plain"
                    }
                }
                val whatsapp = WHATSAPP_PACKAGES.firstOrNull { isInstalled(it) }
                val intent = if (whatsapp != null) {
                    if (imageUri != null) {
                        context.grantUriPermission(whatsapp, imageUri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    }
                    Intent(send).setPackage(whatsapp)
                } else {
                    Intent.createChooser(send, "Compartilhar")
                }
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                UiThreadUtil.runOnUiThread {
                    try {
                        // No RN 0.81 a tela atual fica no contexto (o módulo não tem mais currentActivity).
                        val activity = context.currentActivity
                        if (activity != null) activity.startActivity(intent) else context.startActivity(intent)
                        promise.resolve(imageUri != null)
                    } catch (error: Exception) {
                        promise.reject("share_failed", error.message, error)
                    }
                }
            } catch (error: Exception) {
                promise.reject("share_failed", error.message, error)
            }
        }.start()
    }

    /**
     * Saída de vários itens numa mensagem só, com a foto de cada um (2.5.0, pedido do usuário em 26/11/2026:
     * "que as saídas múltiplas sejam compartilhadas via WhatsApp com múltiplas fotos, em uma única mensagem").
     * ACTION_SEND_MULTIPLE com as fotos em JPEG e o texto como legenda; o WhatsApp manda como um álbum só.
     * Foto que não baixar fica de fora; sem nenhuma, vai só o texto.
     */
    @ReactMethod
    fun shareManyToWhatsApp(text: String, imageUrls: ReadableArray, promise: Promise) {
        Thread {
            try {
                val uris = ArrayList<Uri>()
                for (index in 0 until minOf(imageUrls.size(), MAX_FOTOS)) {
                    val url = imageUrls.getString(index)
                    if (url.isNullOrBlank()) continue
                    downloadAsJpeg(url, "item_$index.jpg")?.let { uris.add(it) }
                }
                if (uris.isEmpty()) {
                    UiThreadUtil.runOnUiThread { shareToWhatsApp(text, null, promise) }
                    return@Thread
                }
                val send = Intent(if (uris.size == 1) Intent.ACTION_SEND else Intent.ACTION_SEND_MULTIPLE).apply {
                    type = "image/jpeg"
                    putExtra(Intent.EXTRA_TEXT, text)
                    if (uris.size == 1) {
                        putExtra(Intent.EXTRA_STREAM, uris[0])
                    } else {
                        putParcelableArrayListExtra(Intent.EXTRA_STREAM, uris)
                    }
                    // Com várias fotos, a permissão de leitura vai pelo ClipData (EXTRA_STREAM em lista não basta).
                    clipData = ClipData.newRawUri("", uris[0]).also { clip -> uris.drop(1).forEach { clip.addItem(ClipData.Item(it)) } }
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                }
                val whatsapp = WHATSAPP_PACKAGES.firstOrNull { isInstalled(it) }
                val intent = if (whatsapp != null) {
                    uris.forEach { context.grantUriPermission(whatsapp, it, Intent.FLAG_GRANT_READ_URI_PERMISSION) }
                    Intent(send).setPackage(whatsapp)
                } else {
                    Intent.createChooser(send, "Compartilhar")
                }
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_GRANT_READ_URI_PERMISSION)
                UiThreadUtil.runOnUiThread {
                    try {
                        val activity = context.currentActivity
                        if (activity != null) activity.startActivity(intent) else context.startActivity(intent)
                        promise.resolve(uris.size)
                    } catch (error: Exception) {
                        promise.reject("share_failed", error.message, error)
                    }
                }
            } catch (error: Exception) {
                promise.reject("share_failed", error.message, error)
            }
        }.start()
    }

    /**
     * Relatório em PDF ou Excel (pedido do usuário em 23/11/2026: "compartilhar os relatórios via
     * WhatsApp tanto em PDF e em XLS"). Baixa o arquivo com o token do app, confere a resposta (a
     * mensagem de erro do servidor vira o erro da promessa) e manda o arquivo no WhatsApp; sem
     * WhatsApp, abre o compartilhar do Android. Com openOnly = true só abre o arquivo no celular.
     *
     * Substitui o expo-file-system + expo-sharing das telas antigas: o app tinha o expo-file-system
     * 17 com o Expo 54 (que pede o 19) e o compartilhar genérico do Android, sem ir ao WhatsApp.
     */
    @ReactMethod
    fun shareFile(url: String, token: String, fileName: String, mimeType: String, openOnly: Boolean, promise: Promise) {
        Thread {
            try {
                val dir = File(context.cacheDir, "compartilhar/relatorios").apply { mkdirs() }
                val oneHourAgo = System.currentTimeMillis() - 60 * 60 * 1000
                dir.listFiles()?.filter { it.lastModified() < oneHourAgo }?.forEach { it.delete() }
                val file = File(dir, fileName.replace(Regex("[^A-Za-z0-9._-]"), "_"))
                val connection = (URL(url).openConnection() as HttpURLConnection).apply {
                    connectTimeout = 15000
                    readTimeout = 90000
                    setRequestProperty("Authorization", "Bearer $token")
                }
                try {
                    val code = connection.responseCode
                    if (code !in 200..299) {
                        val body = try {
                            connection.errorStream?.bufferedReader()?.use { it.readText() }
                        } catch (error: Exception) {
                            null
                        }
                        promise.reject("http_$code", serverMessage(body) ?: "O servidor não gerou o relatório (erro $code).")
                        return@Thread
                    }
                    connection.inputStream.use { input -> FileOutputStream(file).use { input.copyTo(it) } }
                } finally {
                    connection.disconnect()
                }
                val uri = FileProvider.getUriForFile(context, context.packageName + ".galintshare", file)
                var whatsapp: String? = null
                val intent = if (openOnly) {
                    Intent(Intent.ACTION_VIEW).setDataAndType(uri, mimeType)
                } else {
                    val send = Intent(Intent.ACTION_SEND).apply {
                        type = mimeType
                        putExtra(Intent.EXTRA_STREAM, uri)
                    }
                    whatsapp = WHATSAPP_PACKAGES.firstOrNull { isInstalled(it) }
                    if (whatsapp != null) {
                        context.grantUriPermission(whatsapp, uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
                        Intent(send).setPackage(whatsapp)
                    } else {
                        Intent.createChooser(send, "Compartilhar")
                    }
                }
                intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
                UiThreadUtil.runOnUiThread {
                    try {
                        val activity = context.currentActivity
                        if (activity != null) activity.startActivity(intent) else context.startActivity(intent)
                        promise.resolve(whatsapp != null)
                    } catch (error: android.content.ActivityNotFoundException) {
                        promise.reject("no_app", "Nenhum app neste celular abre este arquivo.", error)
                    } catch (error: Exception) {
                        promise.reject("share_failed", error.message, error)
                    }
                }
            } catch (error: Exception) {
                promise.reject("download_failed", error.message ?: "Falha ao baixar o relatório.", error)
            }
        }.start()
    }

    private fun serverMessage(body: String?): String? {
        if (body.isNullOrBlank()) return null
        return try {
            val json = JSONObject(body)
            json.optString("message").ifBlank { json.optString("error") }.ifBlank { null }
        } catch (error: Exception) {
            null
        }
    }

    private fun isInstalled(packageName: String): Boolean = try {
        context.packageManager.getPackageInfo(packageName, 0)
        true
    } catch (error: PackageManager.NameNotFoundException) {
        false
    }

    private fun downloadAsJpeg(imageUrl: String, fileName: String = "item.jpg"): Uri? {
        return try {
            val connection = (URL(imageUrl).openConnection() as HttpURLConnection).apply {
                connectTimeout = 8000
                readTimeout = 15000
            }
            val bytes = try {
                connection.inputStream.use { it.readBytes() }
            } finally {
                connection.disconnect()
            }
            val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
            var sample = 1
            while (bounds.outWidth / sample > MAX_SIDE * 2 || bounds.outHeight / sample > MAX_SIDE * 2) sample *= 2
            val decoded = BitmapFactory.decodeByteArray(bytes, 0, bytes.size, BitmapFactory.Options().apply { inSampleSize = sample })
                ?: return null
            val scale = minOf(1f, MAX_SIDE.toFloat() / maxOf(decoded.width, decoded.height))
            val bitmap = if (scale < 1f) {
                Bitmap.createScaledBitmap(decoded, (decoded.width * scale).toInt(), (decoded.height * scale).toInt(), true)
            } else {
                decoded
            }
            val dir = File(context.cacheDir, "compartilhar").apply { mkdirs() }
            val file = File(dir, fileName)
            FileOutputStream(file).use { bitmap.compress(Bitmap.CompressFormat.JPEG, 88, it) }
            FileProvider.getUriForFile(context, context.packageName + ".galintshare", file)
        } catch (error: Exception) {
            null
        }
    }

    companion object {
        private const val MAX_SIDE = 1280
        private const val MAX_FOTOS = 30 // o WhatsApp aceita até 30 de uma vez
        private val WHATSAPP_PACKAGES = listOf("com.whatsapp", "com.whatsapp.w4b")
    }
}
