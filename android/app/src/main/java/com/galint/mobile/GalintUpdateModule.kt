package com.galint.mobile

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import com.facebook.react.bridge.UiThreadUtil
import com.facebook.react.modules.core.DeviceEventManagerModule
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/**
 * Atualização sozinha do app (23/11/2026), como no Pipocas: o GALINT distribui o APK
 * (/api/mobile/app/apk/<código>); este módulo baixa o arquivo, confere o SHA-256 e abre o instalador
 * do Android. Na primeira vez o Android pede a permissão "instalar apps desconhecidos" para o GALINT.
 * O progresso do download vai para o JavaScript no evento GalintUpdateProgress (0 a 100).
 */
class GalintUpdateModule(private val context: ReactApplicationContext) : ReactContextBaseJavaModule(context) {

    override fun getName(): String = "GalintUpdate"

    @ReactMethod
    fun canInstall(promise: Promise) {
        val allowed = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.packageManager.canRequestPackageInstalls()
        } else {
            true
        }
        promise.resolve(allowed)
    }

    @ReactMethod
    fun openInstallPermission(promise: Promise) {
        UiThreadUtil.runOnUiThread {
            try {
                val intent = Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + context.packageName))
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                val activity = context.currentActivity
                if (activity != null) activity.startActivity(intent) else context.startActivity(intent)
                promise.resolve(true)
            } catch (error: Exception) {
                promise.reject("permission_failed", error.message, error)
            }
        }
    }

    @ReactMethod
    fun downloadAndInstall(url: String, fileName: String, expectedSha256: String?, promise: Promise) {
        Thread {
            try {
                val dir = File(context.cacheDir, "atualizacao").apply { mkdirs() }
                dir.listFiles()?.forEach { it.delete() }
                val file = File(dir, fileName.replace(Regex("[^A-Za-z0-9._-]"), "_"))
                val digest = MessageDigest.getInstance("SHA-256")
                val connection = (URL(url).openConnection() as HttpURLConnection).apply {
                    connectTimeout = 15000
                    readTimeout = 60000
                }
                try {
                    val total = connection.contentLengthLong
                    connection.inputStream.use { input ->
                        FileOutputStream(file).use { output ->
                            val buffer = ByteArray(64 * 1024)
                            var done = 0L
                            var lastPercent = -1
                            while (true) {
                                val read = input.read(buffer)
                                if (read < 0) break
                                output.write(buffer, 0, read)
                                digest.update(buffer, 0, read)
                                done += read
                                if (total > 0) {
                                    val percent = ((done * 100) / total).toInt()
                                    if (percent != lastPercent) {
                                        lastPercent = percent
                                        emitProgress(percent)
                                    }
                                }
                            }
                        }
                    }
                } finally {
                    connection.disconnect()
                }
                val sha = digest.digest().joinToString("") { "%02x".format(it) }
                if (!expectedSha256.isNullOrBlank() && !sha.equals(expectedSha256, ignoreCase = true)) {
                    file.delete()
                    promise.reject("checksum", "O arquivo baixado veio diferente do publicado. Tente de novo.")
                    return@Thread
                }
                val uri = FileProvider.getUriForFile(context, context.packageName + ".galintshare", file)
                val intent = Intent(Intent.ACTION_VIEW)
                    .setDataAndType(uri, "application/vnd.android.package-archive")
                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
                UiThreadUtil.runOnUiThread {
                    try {
                        val activity = context.currentActivity
                        if (activity != null) activity.startActivity(intent) else context.startActivity(intent)
                        promise.resolve(true)
                    } catch (error: Exception) {
                        promise.reject("install_failed", error.message, error)
                    }
                }
            } catch (error: Exception) {
                promise.reject("download_failed", error.message ?: "Falha ao baixar a atualização.", error)
            }
        }.start()
    }

    private fun emitProgress(percent: Int) {
        try {
            context
                .getJSModule(DeviceEventManagerModule.RCTDeviceEventEmitter::class.java)
                .emit("GalintUpdateProgress", Arguments.createMap().apply { putInt("percent", percent) })
        } catch (error: Exception) {
            // sem tela ouvindo: segue o download
        }
    }

    // Exigidos pelo NativeEventEmitter do JavaScript.
    @ReactMethod
    fun addListener(eventName: String) = Unit

    @ReactMethod
    fun removeListeners(count: Int) = Unit
}
