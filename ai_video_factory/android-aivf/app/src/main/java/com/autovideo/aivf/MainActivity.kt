package com.autovideo.aivf

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** v1 UI: server config + project list + create form. Detail lives in DetailActivity. */
class MainActivity : AppCompatActivity() {
    private val scope = CoroutineScope(Dispatchers.Main + Job())
    private lateinit var prefs: android.content.SharedPreferences
    private lateinit var urlField: EditText
    private lateinit var keyField: EditText
    private lateinit var statusLine: TextView
    private lateinit var listBox: LinearLayout

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = getSharedPreferences("aivf", Context.MODE_PRIVATE)

        val root = ScrollView(this).apply {
            addView(LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(32, 32, 32, 64)
                urlField = EditText(this@MainActivity).apply {
                    hint = "Server URL"
                    setText(prefs.getString("base_url", "http://192.168.100.200:8890"))
                }
                addView(urlField)
                keyField = EditText(this@MainActivity).apply {
                    hint = "API key (optional)"
                    setText(prefs.getString("api_key", ""))
                }
                addView(keyField)
                val testBtn = Button(this@MainActivity).apply { text = "Test + Refresh" }
                testBtn.setOnClickListener { saveAndRefresh() }
                addView(testBtn)
                statusLine = TextView(this@MainActivity).apply { text = "Idle." }
                addView(statusLine)
                val createBtn = Button(this@MainActivity).apply { text = "Create project…" }
                createBtn.setOnClickListener { showCreateForm(this) }
                addView(createBtn)
                listBox = LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.VERTICAL
                }
                addView(listBox)
            })
        }
        setContentView(root)
        saveAndRefresh()
    }

    private fun api() = AivfApi(
        urlField.text.toString(),
        keyField.text.toString(),
    )

    private fun saveAndRefresh() {
        prefs.edit()
            .putString("base_url", urlField.text.toString().trim())
            .putString("api_key", keyField.text.toString().trim())
            .apply()
        statusLine.text = "Connecting…"
        listBox.removeAllViews()
        scope.launch {
            try {
                val projects = withContext(Dispatchers.IO) { api().listProjects() }
                val prov = try {
                    withContext(Dispatchers.IO) { api().providerStatus() }
                } catch (e: Exception) { null }
                statusLine.text = "OK — ${projects.size} project(s)" +
                    (prov?.let { " · provider=${it.optString("provider")}" } ?: " · provider n/a")
                if (projects.isEmpty()) {
                    listBox.addView(TextView(this@MainActivity).apply {
                        text = "No projects yet — create one below."
                    })
                }
                for (p in projects) {
                    val btn = Button(this@MainActivity).apply {
                        text = "${p.name} [${p.status}]"
                    }
                    btn.setOnClickListener {
                        startActivity(Intent(this@MainActivity, DetailActivity::class.java).apply {
                            putExtra("project_id", p.id)
                            putExtra("project_name", p.name)
                        })
                    }
                    listBox.addView(btn)
                }
            } catch (e: Exception) {
                statusLine.text = "Error: ${e.message}"
            }
        }
    }

    private fun showCreateForm(parent: LinearLayout) {
        val name = EditText(this).apply { hint = "Name (required)" }
        val topic = EditText(this).apply { hint = "Topic" }
        val niche = EditText(this).apply { hint = "Niche"; setText("horror") }
        val secs = EditText(this).apply { hint = "Seconds"; setText("64") }
        val go = Button(this).apply { text = "Create" }
        go.setOnClickListener {
            val n = name.text.toString().trim()
            if (n.isEmpty()) {
                Toast.makeText(this, "Name required", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            scope.launch {
                try {
                    val res = withContext(Dispatchers.IO) {
                        api().createProject(
                            n,
                            niche.text.toString().trim().ifEmpty { "horror" },
                            topic.text.toString().trim(),
                            secs.text.toString().toIntOrNull() ?: 64,
                        )
                    }
                    Toast.makeText(this@MainActivity,
                        "Created ${res.optString("id")}", Toast.LENGTH_SHORT).show()
                    saveAndRefresh()
                } catch (e: Exception) {
                    Toast.makeText(this@MainActivity,
                        "Create failed: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
        }
        parent.addView(name)
        parent.addView(topic)
        parent.addView(niche)
        parent.addView(secs)
        parent.addView(go)
    }
}
