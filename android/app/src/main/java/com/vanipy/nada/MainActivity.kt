package com.vanipy.nada

import android.app.Activity
import android.content.ContentValues
import android.os.Bundle
import android.provider.MediaStore
import android.webkit.JavascriptInterface
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import android.util.Base64
import android.util.Log
import androidx.webkit.WebViewAssetLoader

class MainActivity : Activity() {

    internal lateinit var webView: WebView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val webView = WebView(this)
        this.webView = webView
        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        // Serve the bundled web assets over the reserved appassets domain instead
        // of file:///android_asset, which WebView restricts for targetSdk 30+.
        val assetLoader = WebViewAssetLoader.Builder()
            .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(this))
            .build()
        // Launch with --ez autosave true to build the example recipe once the
        // page has loaded (used by CI to exercise the save path hands-free).
        val autosave = intent.getBooleanExtra("autosave", false)
        var autosaved = false
        webView.webViewClient = object : WebViewClient() {
            override fun shouldInterceptRequest(
                view: WebView,
                request: WebResourceRequest
            ): WebResourceResponse? = assetLoader.shouldInterceptRequest(request.url)

            override fun onPageFinished(view: WebView, url: String) {
                if (autosave && !autosaved) {
                    autosaved = true
                    view.evaluateJavascript("document.getElementById('build').click(); 'clicked'", null)
                }
            }

            override fun onReceivedError(
                view: WebView,
                request: WebResourceRequest,
                error: android.webkit.WebResourceError
            ) {
                Log.e("nada", "WebView error ${error.errorCode} ${error.description} for ${request.url}")
            }
        }
        webView.addJavascriptInterface(object {
            @JavascriptInterface
            fun saveMidi(base64Data: String, filename: String) {
                val safeName = filename.replace(Regex("[^A-Za-z0-9._-]"), "_")
                Log.i("nada", "saveMidi called: $safeName")
                val bytes = try {
                    Base64.decode(base64Data, Base64.DEFAULT)
                } catch (e: Exception) {
                    Log.e("nada", "saveMidi base64 decode failed", e)
                    return
                }
                val values = ContentValues().apply {
                    put(MediaStore.MediaColumns.DISPLAY_NAME, safeName)
                    put(MediaStore.MediaColumns.MIME_TYPE, "audio/midi")
                    put(MediaStore.MediaColumns.RELATIVE_PATH, "Music/nada")
                }
                // MediaStore.Files only allows Download/ and Documents/ as primary
                // directories; audio (incl. MIDI) must go through the Audio collection
                // for Music/ to be accepted.
                val uri = contentResolver.insert(
                    MediaStore.Audio.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY),
                    values
                )
                Log.i("nada", "saveMidi insert uri=$uri bytes=${bytes.size}")
                val ok = uri?.let { contentResolver.openOutputStream(it) }?.use {
                    it.write(bytes)
                    true
                } ?: false
                Log.i("nada", "saveMidi write ok=$ok")
                runOnUiThread {
                    val msg = if (ok) "saved to Music/nada/$safeName" else "save failed"
                    Toast.makeText(this@MainActivity, msg, Toast.LENGTH_LONG).show()
                }
            }
        }, "NadaBridge")
        webView.loadUrl("https://appassets.androidplatform.net/assets/web/index.html")
        setContentView(webView)
    }
}
