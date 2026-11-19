package com.vanipy.nada

import android.app.Activity
import android.content.ContentValues
import android.os.Bundle
import android.provider.MediaStore
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.widget.Toast
import android.util.Base64

class MainActivity : Activity() {

    internal lateinit var webView: WebView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val webView = WebView(this)
        this.webView = webView
        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        webView.addJavascriptInterface(object {
            @JavascriptInterface
            fun saveMidi(base64Data: String, filename: String) {
                val safeName = filename.replace(Regex("[^A-Za-z0-9._-]"), "_")
                val bytes = Base64.decode(base64Data, Base64.DEFAULT)
                val values = ContentValues().apply {
                    put(MediaStore.MediaColumns.DISPLAY_NAME, safeName)
                    put(MediaStore.MediaColumns.MIME_TYPE, "audio/midi")
                    put(MediaStore.MediaColumns.RELATIVE_PATH, "Music/nada")
                }
                val uri = contentResolver.insert(
                    MediaStore.Files.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY),
                    values
                )
                val ok = uri?.let { contentResolver.openOutputStream(it) }?.use {
                    it.write(bytes)
                    true
                } ?: false
                runOnUiThread {
                    val msg = if (ok) "saved to Music/nada/$safeName" else "save failed"
                    Toast.makeText(this@MainActivity, msg, Toast.LENGTH_LONG).show()
                }
            }
        }, "NadaBridge")
        webView.loadUrl("file:///android_asset/web/index.html")
        setContentView(webView)
    }
}
