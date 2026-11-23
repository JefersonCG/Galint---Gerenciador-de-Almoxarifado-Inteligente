package com.galint.mobile

import androidx.core.content.FileProvider
import com.facebook.react.ReactPackage
import com.facebook.react.bridge.NativeModule
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.uimanager.ViewManager

/** Registra os módulos do próprio app: GalintShare (foto + texto no WhatsApp) e GalintUpdate
 * (atualização sozinha do APK). Ver MainApplication.kt. */
class GalintSharePackage : ReactPackage {
    override fun createNativeModules(reactContext: ReactApplicationContext): List<NativeModule> =
        listOf(GalintShareModule(reactContext), GalintUpdateModule(reactContext))

    override fun createViewManagers(reactContext: ReactApplicationContext): List<ViewManager<*, *>> = emptyList()
}

/**
 * FileProvider próprio do app: outras bibliotecas (expo-sharing, expo-image-picker) declaram os
 * delas, e dois <provider> com a mesma classe colidiriam na fusão do manifesto.
 */
class GalintShareFileProvider : FileProvider()
