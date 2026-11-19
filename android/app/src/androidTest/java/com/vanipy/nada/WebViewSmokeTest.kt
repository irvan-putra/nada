package com.vanipy.nada

import android.provider.MediaStore
import androidx.test.ext.junit.rules.ActivityScenarioRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

@RunWith(AndroidJUnit4::class)
class WebViewSmokeTest {

    @get:Rule
    val rule = ActivityScenarioRule(MainActivity::class.java)

    private fun evalJs(js: String): String {
        val latch = CountDownLatch(1)
        var result = "null"
        rule.scenario.onActivity { activity ->
            activity.runOnUiThread {
                activity.webView.evaluateJavascript(js) { v ->
                    result = v ?: "null"
                    latch.countDown()
                }
            }
        }
        latch.await(15, TimeUnit.SECONDS)
        return result
    }

    @Test
    fun pageLoadsAndBridgeSavesToMediaStore() {
        // 1. The bundled web app loads and its JS runs on a real Android WebView.
        var title = ""
        for (i in 1..20) {
            title = evalJs("document.title")
            if (title.contains("nada")) break
            Thread.sleep(500)
        }
        assertTrue("page title did not load, got: $title", title.contains("nada"))

        // 2. Building the example recipe calls the real NadaBridge and the file
        //    lands in MediaStore (scoped storage), the same path a user save takes.
        evalJs("document.getElementById('build').click(); 'clicked'")
        val projection = arrayOf(MediaStore.MediaColumns._ID)
        val selection = "${MediaStore.MediaColumns.DISPLAY_NAME} = ?"
        val args = arrayOf("twinkle_twinkle.mid")
        var found = false
        for (i in 1..20) {
            rule.scenario.onActivity { activity ->
                activity.contentResolver.query(
                    MediaStore.Files.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY),
                    projection, selection, args, null
                )?.use { cursor ->
                    if (cursor.moveToFirst()) {
                        found = true
                        val id = cursor.getLong(0)
                        activity.contentResolver.delete(
                            MediaStore.Files.getContentUri(
                                MediaStore.VOLUME_EXTERNAL_PRIMARY),
                            "${MediaStore.MediaColumns._ID} = ?",
                            arrayOf(id.toString()))
                    }
                }
            }
            if (found) break
            Thread.sleep(500)
        }
        assertTrue("twinkle_twinkle.mid was not found in MediaStore", found)
    }
}
