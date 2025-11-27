import 'dart:io';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:path_provider/path_provider.dart';

/// Background message handler - must be top-level function
Future<void> _firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp();
  print('📨 Background message: ${message.notification?.title}');
}

class FCMHandler {
  static final FirebaseMessaging _messaging = FirebaseMessaging.instance;
  static final FlutterLocalNotificationsPlugin _notifications =
      FlutterLocalNotificationsPlugin();

  /// Initialize FCM and request permissions
  static Future<void> initialize() async {
    print('🔔 Initializing FCM...');

    // Request notification permissions
    NotificationSettings settings = await _messaging.requestPermission(
      alert: true,
      badge: true,
      sound: true,
      provisional: false,
    );

    print('📱 Notification permission: ${settings.authorizationStatus}');

    if (settings.authorizationStatus == AuthorizationStatus.authorized ||
        settings.authorizationStatus == AuthorizationStatus.provisional) {
      // Get FCM token
      String? token = await _messaging.getToken();
      if (token != null) {
        print('📱 FCM Token obtained: ${token.length > 20 ? token.substring(0, 20) + "..." : token}');
        print('   Full token length: ${token.length}');

        // Save token to SharedPreferences
        final prefs = await SharedPreferences.getInstance();
        await prefs.setString('fcm_token', token);

        // ALSO write token to a file for Python runtime to read
        await _writeTokenToFile(token);

        print('✅ FCM token saved to SharedPreferences and written to file');
      } else {
        print('⚠️ Failed to get FCM token');
      }

      // Token refresh listener
      _messaging.onTokenRefresh.listen((newToken) async {
        print('🔄 FCM token refreshed');
        await _saveTokenAsync(newToken);
        await _writeTokenToFile(newToken);
      });

      // Initialize local notifications
      await _initializeLocalNotifications();

      // Set up message handlers
      _setupMessageHandlers();

      print('✅ FCM fully initialized');
    } else {
      print('⚠️ Notification permission denied');
    }
  }

  /// Save token asynchronously (SharedPreferences)
  static Future<void> _saveTokenAsync(String token) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('fcm_token', token);
    } catch (e) {
      print('❌ Error saving token to SharedPreferences: $e');
    }
  }

  /// Write token to a file so Python/Flet runtime can read it
  static Future<void> _writeTokenToFile(String token) async {
    try {
      final dir = await getApplicationDocumentsDirectory();
      // use a hidden folder to avoid casual visibility
      final appDir = Directory('${dir.path}/.chatapp');
      if (!await appDir.exists()) {
        await appDir.create(recursive: true);
      }
      final file = File('${appDir.path}/fcm_token.txt');
      await file.writeAsString(token);
      print('✅ Token written to file: ${file.path}');
    } catch (e) {
      print('❌ Error writing token file: $e');
    }
  }

  /// Initialize local notifications for foreground messages
  static Future<void> _initializeLocalNotifications() async {
    const AndroidInitializationSettings androidSettings =
        AndroidInitializationSettings('@mipmap/ic_launcher');

    const InitializationSettings settings = InitializationSettings(
      android: androidSettings,
    );

    await _notifications.initialize(settings,
        onDidReceiveNotificationResponse: (NotificationResponse response) {
      print('📱 Notification tapped');
    });

    // Create notification channel
    const AndroidNotificationChannel channel = AndroidNotificationChannel(
      'chat_messages',
      'Chat Messages',
      description: 'Notifications for new chat messages',
      importance: Importance.high,
      playSound: true,
      enableVibration: true,
    );

    final androidPlugin = _notifications.resolvePlatformSpecificImplementation<
        AndroidFlutterLocalNotificationsPlugin>();

    if (androidPlugin != null) {
      await androidPlugin.createNotificationChannel(channel);
    }
  }

  /// Set up message handlers
  static void _setupMessageHandlers() {
    // Foreground messages
    FirebaseMessaging.onMessage.listen((RemoteMessage message) {
      print('📨 Foreground message: ${message.notification?.title}');
      _showLocalNotification(message);
    });

    // Background messages
    FirebaseMessaging.onBackgroundMessage(_firebaseMessagingBackgroundHandler);

    // Notification tap
    FirebaseMessaging.onMessageOpenedApp.listen((RemoteMessage message) {
      print('👆 Notification tapped');
    });

    // Check initial message
    _checkInitialMessage();
  }

  /// Check if app was opened from notification
  static Future<void> _checkInitialMessage() async {
    try {
      RemoteMessage? initialMessage = await _messaging.getInitialMessage();
      if (initialMessage != null) {
        print('🚀 App opened from notification');
      }
    } catch (e) {
      print('❌ Error checking initial message: $e');
    }
  }

  /// Show local notification
  static Future<void> _showLocalNotification(RemoteMessage message) async {
    RemoteNotification? notification = message.notification;
    if (notification != null) {
      const AndroidNotificationDetails androidDetails =
          AndroidNotificationDetails(
        'chat_messages',
        'Chat Messages',
        channelDescription: 'Notifications for new chat messages',
        importance: Importance.high,
        priority: Priority.high,
        playSound: true,
        icon: '@mipmap/ic_launcher',
      );

      const NotificationDetails details =
          NotificationDetails(android: androidDetails);

      await _notifications.show(
        notification.hashCode,
        notification.title,
        notification.body,
        details,
      );
    }
  }

  /// Get current FCM token
  static Future<String?> getToken() async {
    try {
      return await _messaging.getToken();
    } catch (e) {
      print('Error getting FCM token: $e');
      return null;
    }
  }

  /// Delete FCM token
  static Future<void> deleteToken() async {
    try {
      await _messaging.deleteToken();
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove('fcm_token');

      // delete file copy as well
      try {
        final dir = await getApplicationDocumentsDirectory();
        final file = File('${dir.path}/.chatapp/fcm_token.txt');
        if (await file.exists()) {
          await file.delete();
          print('✅ Token file deleted: ${file.path}');
        }
      } catch (e) {
        print('⚠️ Error deleting token file: $e');
      }

      print('✅ FCM token deleted');
    } catch (e) {
      print('Error deleting token: $e');
    }
  }
}
