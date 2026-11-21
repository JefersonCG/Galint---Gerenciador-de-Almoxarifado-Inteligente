package com.galint.mobile

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
import com.facebook.react.bridge.UiThreadUtil
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL

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

    private fun isInstalled(packageName: String): Boolean = try {
        context.packageManager.getPackageInfo(packageName, 0)
        true
    } catch (error: PackageManager.NameNotFoundException) {
        false
    }

    private fun downloadAsJpeg(imageUrl: String): Uri? {
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
            val file = File(dir, "item.jpg")
            FileOutputStream(file).use { bitmap.compress(Bitmap.CompressFormat.JPEG, 88, it) }
            FileProvider.getUriForFile(context, context.packageName + ".galintshare", file)
        } catch (error: Exception) {
            null
        }
    }

    companion object {
        private const val MAX_SIDE = 1280
        private val WHATSAPP_PACKAGES = listOf("com.whatsapp", "com.whatsapp.w4b")
    }
}
