package com.autovideo.aivf

import android.content.Context
import android.os.Bundle
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Project detail: status + queue stats + start/pause/resume/cancel. */
class DetailActivity : AppCompatActivity() {
    private val scope = CoroutineScope(Dispatchers.Main + Job())
    private lateinit var info: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val pid = intent.getStringExtra("project_id") ?: run { finish(); return }
        val prefs = getSharedPreferences("aivf", Context.MODE_PRIVATE)
        val api = AivfApi(
            prefs.getString("base_url", "http://192.168.100.200:8890") ?: "",
            prefs.getString("api_key", "") ?: "",
        )
        title = intent.getStringExtra("project_name") ?: pid

        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 32, 32, 64)
        }
        info = TextView(this).apply { text = "Loading…" }
        box.addView(info)
        for (op in listOf("start", "pause", "resume", "cancel")) {
            val b = Button(this).apply { text = op.replaceFirstChar { it.uppercase() } }
            b.setOnClickListener {
                scope.launch {
                    try {
                        withContext(Dispatchers.IO) { api.action(pid, op) }
                        refresh(api, pid)
                    } catch (e: Exception) {
                        info.text = "Action failed: ${e.message}"
                    }
                }
            }
            box.addView(b)
        }
        val back = Button(this).apply { text = "Refresh" }
        back.setOnClickListener { refresh(api, pid) }
        box.addView(back)
        setContentView(ScrollView(this).apply { addView(box) })
        refresh(api, pid)
    }

    private fun refresh(api: AivfApi, pid: String) {
        info.text = "Loading…"
        scope.launch {
            try {
                val st = withContext(Dispatchers.IO) { api.projectStatus(pid) }
                val q = withContext(Dispatchers.IO) { api.queueStats(pid) }
                val sb = StringBuilder()
                sb.append("STATUS\n").append(st.toString(2)).append("\n\n")
                sb.append("QUEUE\n").append(q.toString(2))
                info.text = sb.toString()
            } catch (e: Exception) {
                info.text = "Error: ${e.message}"
            }
        }
    }
}
