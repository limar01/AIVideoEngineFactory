package com.autovideo.aivf

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONArray
import org.json.JSONObject
import java.net.URLEncoder
import java.util.concurrent.TimeUnit

/** Thin client for the AI Video Factory REST API (app/api/routes.py).
 *  Create/start/pause/resume/cancel are POSTs with QUERY params (server contract).
 *  Optional X-API-Key header when the server has one configured. */
data class AivfProject(
    val id: String,
    val name: String,
    val status: String,
    val niche: String = "",
    val topic: String = "",
    val targetSeconds: Int = 0,
)

class AivfApi(baseUrl: String, apiKey: String = "") {
    private val base = baseUrl.trim().trimEnd('/')
    private val key = apiKey.trim()
    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    private fun req(path: String, post: Boolean = false): Request {
        val url = (base + path).toHttpUrlOrNull()
            ?: throw IllegalArgumentException("Bad server URL: $base")
        val b = Request.Builder().url(url)
        if (post) b.post(okhttp3.RequestBody.create(null, ByteArray(0)))
        if (key.isNotEmpty()) b.header("X-API-Key", key)
        return b.build()
    }

    private suspend fun call(path: String, post: Boolean = false): String =
        withContext(Dispatchers.IO) {
            client.newCall(req(path, post)).execute().use { resp ->
                val body = resp.body?.string() ?: ""
                if (!resp.isSuccessful) throw ApiException(resp.code, body.ifBlank { resp.message })
                body
            }
        }

    suspend fun listProjects(): List<AivfProject> {
        val arr = JSONArray(call("/api/v1/projects"))
        return List(arr.length()) { i ->
            val o = arr.getJSONObject(i)
            AivfProject(
                id = o.optString("id"),
                name = o.optString("name"),
                status = o.optString("status"),
                niche = o.optString("niche"),
                topic = o.optString("topic"),
                targetSeconds = o.optInt("target_seconds"),
            )
        }
    }

    suspend fun createProject(name: String, niche: String, topic: String, seconds: Int): JSONObject {
        fun enc(s: String) = URLEncoder.encode(s, "UTF-8")
        val q = "name=${enc(name)}&niche=${enc(niche)}&topic=${enc(topic)}&target_seconds=$seconds"
        return JSONObject(call("/api/v1/projects?$q", post = true))
    }

    suspend fun projectStatus(id: String): JSONObject =
        JSONObject(call("/api/v1/projects/$id/status"))

    suspend fun queueStats(projectId: String? = null): JSONObject {
        val q = if (projectId != null) "?project_id=$projectId" else ""
        return JSONObject(call("/api/v1/queue/stats$q"))
    }

    suspend fun providerStatus(): JSONObject =
        JSONObject(call("/api/v1/provider/status"))

    suspend fun action(projectId: String, op: String): JSONObject {
        require(op in setOf("start", "pause", "resume", "cancel")) { "bad op: $op" }
        return JSONObject(call("/api/v1/projects/$projectId/$op", post = true))
    }
}

class ApiException(val code: Int, message: String) : Exception("HTTP $code: $message")
