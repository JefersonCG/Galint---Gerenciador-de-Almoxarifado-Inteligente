package com.galint.mobile

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import com.facebook.react.bridge.ActivityEventListener
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import com.facebook.react.modules.core.DeviceEventManagerModule
import kotlin.math.max

/**
 * Busca de material por voz (2.6.0, pedido do usuário em 27/11/2026: "aperto no microfone e falo 0265 e ele acha a
 * parafusadeira").
 *
 * `ouvir`: a janela de voz do próprio Android (Google), em português; devolve até 5 frases. Fecha sozinha com uns 2 s
 * de silêncio e não aceita esperar mais.
 *
 * `comecar` / `terminar` / `cancelar` (2.7.1): escuta contínua sem a janela do Google. Pedido do usuário em 27/11/2026:
 * "tem como aumentar o tempo de intervalo quando se fala, pois 2 segundos sem falar ele já fecha". O reconhecedor do
 * Android também fecha o trecho na pausa; aqui ele recomeça na hora e junta os trechos, até `silencio` ms sem fala
 * (8 s antes da primeira palavra) ou até o app pedir `terminar`. O texto vai para o app no evento "GalintVozEvento":
 * { tipo: "ouvindo" | "parcial" | "fim" | "erro", texto, codigo }. Precisa da permissão de microfone (o app pede).
 */
class GalintVozModule(private val context: ReactApplicationContext) : ReactContextBaseJavaModule(context), ActivityEventListener {

    private var pendente: Promise? = null

    init {
        context.addActivityEventListener(this)
    }

    override fun getName(): String = "GalintVoz"

    @ReactMethod
    fun ouvir(aviso: String?, promise: Promise) {
        val activity = context.currentActivity
        if (activity == null) {
            promise.reject("sem_tela", "Abra o app e tente de novo.")
            return
        }
        pendente?.reject("cancelado", "Outra escuta começou.")
        pendente = promise
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "pt-BR")
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, "pt-BR")
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 5)
            if (!aviso.isNullOrBlank()) putExtra(RecognizerIntent.EXTRA_PROMPT, aviso)
        }
        try {
            activity.startActivityForResult(intent, PEDIDO)
        } catch (erro: ActivityNotFoundException) {
            pendente = null
            promise.reject("sem_voz", "Este celular não tem o reconhecimento de voz do Google.", erro)
        }
    }

    override fun onActivityResult(activity: Activity, requestCode: Int, resultCode: Int, data: Intent?) {
        if (requestCode != PEDIDO) return
        val promise = pendente ?: return
        pendente = null
        val frases = Arguments.createArray()
        if (resultCode == Activity.RESULT_OK) {
            data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.forEach { frase ->
                if (!frase.isNullOrBlank()) frases.pushString(frase)
            }
        }
        promise.resolve(frases)
    }

    override fun onNewIntent(intent: Intent) = Unit

    // ---------- Escuta contínua (2.7.1) ----------

    private val principal = Handler(Looper.getMainLooper())
    private var reconhecedor: SpeechRecognizer? = null
    private var sessaoAtiva = false
    private val falado = StringBuilder()
    private var ultimoParcial = ""
    private var silencioMs = 4000L
    private var ultimaFala = 0L
    private var tentativas = 0
    private val fimPorSilencio = Runnable { encerrar(avisar = true) }

    @ReactMethod
    fun disponivel(promise: Promise) {
        promise.resolve(SpeechRecognizer.isRecognitionAvailable(context))
    }

    @ReactMethod
    fun comecar(silencio: Double) {
        principal.post {
            encerrar(avisar = false)
            silencioMs = silencio.toLong().coerceIn(1500L, 15000L)
            falado.setLength(0)
            ultimoParcial = ""
            tentativas = 0
            ultimaFala = SystemClock.elapsedRealtime()
            sessaoAtiva = true
            ouvirTrecho()
        }
    }

    // "Pronto": fecha já, com o que foi falado (o trecho em andamento entra pelo último parcial).
    @ReactMethod
    fun terminar() {
        principal.post { encerrar(avisar = true) }
    }

    @ReactMethod
    fun cancelar() {
        principal.post { encerrar(avisar = true, cancelado = true) }
    }

    // Exigidos pelo NativeEventEmitter do React Native.
    @ReactMethod
    fun addListener(eventName: String) = Unit

    @ReactMethod
    fun removeListeners(count: Double) = Unit

    private fun intencao() = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
        putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
        putExtra(RecognizerIntent.EXTRA_LANGUAGE, "pt-BR")
        putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, "pt-BR")
        putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
        putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
        putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, context.packageName)
        // Reconhecedores que respeitam o pedido esperam mais na pausa; os que não respeitam, o laço abaixo cobre.
        putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, silencioMs)
        putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, silencioMs)
    }

    private fun ouvirTrecho() {
        if (!sessaoAtiva) return
        val atual = reconhecedor ?: SpeechRecognizer.createSpeechRecognizer(context).also {
            it.setRecognitionListener(ouvinte)
            reconhecedor = it
        }
        try {
            atual.startListening(intencao())
        } catch (erro: Exception) {
            terminarComErro("falha", "Não foi possível ouvir agora.")
        }
    }

    private fun limiteDeSilencio(): Long = if (falado.isEmpty() && ultimoParcial.isBlank()) max(silencioMs, 8000L) else silencioMs

    private fun agendarFimPorSilencio() {
        principal.removeCallbacks(fimPorSilencio)
        val restante = limiteDeSilencio() - (SystemClock.elapsedRealtime() - ultimaFala)
        principal.postDelayed(fimPorSilencio, max(restante, 300L))
    }

    private fun textoAtual(): String {
        val parcial = ultimoParcial.trim()
        return when {
            falado.isEmpty() -> parcial
            parcial.isEmpty() -> falado.toString()
            else -> "$falado $parcial"
        }
    }

    private fun recomecarDepois(ms: Long) {
        principal.postDelayed({ ouvirTrecho() }, ms)
    }

    private val ouvinte = object : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) {
            tentativas = 0
            emitir("ouvindo", textoAtual())
            agendarFimPorSilencio()
        }

        override fun onBeginningOfSpeech() {
            ultimaFala = SystemClock.elapsedRealtime()
            principal.removeCallbacks(fimPorSilencio)
        }

        override fun onRmsChanged(rmsdB: Float) = Unit

        override fun onBufferReceived(buffer: ByteArray?) = Unit

        override fun onEndOfSpeech() {
            ultimaFala = SystemClock.elapsedRealtime()
        }

        override fun onPartialResults(partialResults: Bundle?) {
            if (!sessaoAtiva) return
            val parcial = partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull().orEmpty()
            if (parcial.isBlank()) return
            ultimoParcial = parcial
            ultimaFala = SystemClock.elapsedRealtime()
            principal.removeCallbacks(fimPorSilencio)
            emitir("parcial", textoAtual())
        }

        override fun onResults(results: Bundle?) {
            if (!sessaoAtiva) return
            val frase = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull().orEmpty().trim()
                .ifEmpty { ultimoParcial.trim() }
            ultimoParcial = ""
            if (frase.isNotEmpty()) {
                if (falado.isNotEmpty()) falado.append(' ')
                falado.append(frase)
                ultimaFala = SystemClock.elapsedRealtime()
                emitir("parcial", falado.toString())
            }
            recomecarDepois(100) // a pausa fechou o trecho: continua ouvindo
        }

        override fun onError(error: Int) {
            if (!sessaoAtiva) return
            when (error) {
                SpeechRecognizer.ERROR_NO_MATCH, SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> {
                    if (SystemClock.elapsedRealtime() - ultimaFala >= limiteDeSilencio()) encerrar(avisar = true) else recomecarDepois(150)
                }
                SpeechRecognizer.ERROR_RECOGNIZER_BUSY, SpeechRecognizer.ERROR_CLIENT -> {
                    tentativas += 1
                    if (tentativas > 4) {
                        if (textoAtual().isNotEmpty()) encerrar(avisar = true) else terminarComErro("falha", "Não foi possível ouvir agora.")
                    } else {
                        try {
                            reconhecedor?.cancel()
                        } catch (_: Exception) {
                        }
                        recomecarDepois(350)
                    }
                }
                SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> terminarComErro("sem_permissao", "Permita o microfone para falar.")
                else -> if (textoAtual().isNotEmpty()) encerrar(avisar = true) else terminarComErro("falha", "Sem resposta do reconhecimento de voz.")
            }
        }

        override fun onEvent(eventType: Int, params: Bundle?) = Unit
    }

    private fun terminarComErro(codigo: String, mensagem: String) {
        val tinha = sessaoAtiva
        encerrar(avisar = false)
        if (tinha) emitir("erro", mensagem, codigo)
    }

    private fun encerrar(avisar: Boolean, cancelado: Boolean = false) {
        val estava = sessaoAtiva
        val texto = textoAtual().trim()
        sessaoAtiva = false
        principal.removeCallbacksAndMessages(null)
        reconhecedor?.let {
            try {
                it.cancel()
            } catch (_: Exception) {
            }
            try {
                it.destroy()
            } catch (_: Exception) {
            }
        }
        reconhecedor = null
        falado.setLength(0)
        ultimoParcial = ""
        if (avisar && estava) emitir("fim", if (cancelado) "" else texto)
    }

    private fun emitir(tipo: String, texto: String = "", codigo: String? = null) {
        val dados = Arguments.createMap().apply {
            putString("tipo", tipo)
            putString("texto", texto)
            if (codigo != null) putString("codigo", codigo)
        }
        try {
            context.getJSModule(DeviceEventManagerModule.RCTDeviceEventEmitter::class.java).emit(EVENTO, dados)
        } catch (_: Exception) {
        }
    }

    override fun invalidate() {
        principal.post { encerrar(avisar = false) }
        super.invalidate()
    }

    companion object {
        private const val PEDIDO = 4521
        private const val EVENTO = "GalintVozEvento"
    }
}
