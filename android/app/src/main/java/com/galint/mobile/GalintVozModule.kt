package com.galint.mobile

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.speech.RecognizerIntent
import com.facebook.react.bridge.ActivityEventListener
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod

/**
 * Busca de material por voz (2.6.0, pedido do usuário em 27/11/2026: "aperto no microfone e falo 0265 e ele acha a
 * parafusadeira"). Abre a escuta de voz do próprio Android (Google), em português, e devolve até 5 frases entendidas,
 * da mais provável para a menos. Não precisa de biblioteca nem da permissão de microfone no app: quem grava é o
 * reconhecedor do sistema. Sem reconhecedor no aparelho, a promessa falha com "sem_voz".
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
            // 2.7.2: pede para a janela esperar 3,5 s na pausa ("2 segundos sem falar ele já fecha", 27/11/2026).
            // O Google costuma ignorar estes dois; a escuta própria da 2.7.1 foi desfeita a pedido do usuário.
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 3500L)
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, 3500L)
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

    companion object {
        private const val PEDIDO = 4521
    }
}
