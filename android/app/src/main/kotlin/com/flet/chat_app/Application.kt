package com.flet.chat_app

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import com.google.firebase.FirebaseApp
import com.google.firebase.messaging.FirebaseMessaging
import android.content.Context
import android.util.Log
import java.io.File

class MainActivity: FlutterActivity() {
    private val CHANNEL = "fcm_channel"
    
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        
        Log.d("MainActivity", "🔥 Initializing Firebase...")
        
        // Initialize Firebase
        try {
            FirebaseApp.initializeApp(this)
            Log.d("MainActivity", "✅ Firebase initialized")
            
            // Get FCM token
            FirebaseMessaging.getInstance().token.addOnCompleteListener { task ->
                if (task.isSuccessful) {
                    val token = task.result
                    Log.d("MainActivity", "📱 FCM Token: ${token.take(30)}...")
                    
                    // Save token to file for Python to read
                    saveTokenToFile(token)
                    
                } else {
                    Log.e("MainActivity", "❌ Failed to get FCM token", task.exception)
                }
            }
            
        } catch (e: Exception) {
            Log.e("MainActivity", "❌ Firebase init failed", e)
        }
        
        // Set up method channel for Python communication
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "getFCMToken" -> {
                        FirebaseMessaging.getInstance().token.addOnCompleteListener { task ->
                            if (task.isSuccessful) {
                                result.success(task.result)
                            } else {
                                result.error("ERROR", "Failed to get token", null)
                            }
                        }
                    }
                    else -> result.notImplemented()
                }
            }
    }
    
    private fun saveTokenToFile(token: String) {
        try {
            val dir = File(filesDir, ".chatapp")
            if (!dir.exists()) {
                dir.mkdirs()
            }
            val file = File(dir, "fcm_token.txt")
            file.writeText(token)
            Log.d("MainActivity", "✅ Token saved to: ${file.absolutePath}")
        } catch (e: Exception) {
            Log.e("MainActivity", "❌ Failed to save token", e)
        }
    }
}
