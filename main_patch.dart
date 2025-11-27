import 'dart:io';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:path_provider/path_provider.dart';

// Background message handler
@pragma('vm:entry-point')
Future<void> _firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp();
  print('📨 Background message: ${message.notification?.title}');
}

class FCMInitializer {
  static final FirebaseMessaging _messaging = FirebaseMessaging.instance;
  static final FlutterLocalNotificationsPlugin _notifications =
      FlutterLocalNotificationsPlugin();

  /// Write token to a file so the embedded Python runtime can read it.
  /// We use the app documents directory so it works regardless of package name.
  static Future<void> _writeTokenToFile(String token) async {
    try {
      // Typically: /data/user/0/<package>/app_flutter
      final dir = await getApplicationDocumentsDirectory();

      final appDir = Directory('${dir.path}/.chatapp');
      if (!await appDir.exists()) {
        await appDir.create(recursive: true);
      }

      final file = File('${appDir.path}/fcm_token.txt');
      await file.writeAsString(token);
      print('✅ [FCMInitializer] Token written to file: ${file.path}');
    } catch (e) {
      print('❌ [FCMInitializer] Error writing token file: $e');
    }
  }

  static Future<void> initialize() async {
    try {
      print('🔔 Initializing Firebase...');

      // Initialize Firebase
      await Firebase.initializeApp();
      print('✅ Firebase initialized');

      // Request notification permission (Android 13+)
      await Permission.notification.request();
      print('✅ Permission requested');

      // Request FCM permission
      NotificationSettings settings = await _messaging.requestPermission(
        alert: true,
        badge: true,
        sound: true,
        provisional: false,
      );

      print('📱 Notification permission: ${settings.authorizationStatus}');

      if (settings.authorizationStatus == AuthorizationStatus.authorized ||
          settings.authorizationStatus == AuthorizationStatus.provisional) {
        // Initialize local notifications FIRST
        await _initializeLocalNotifications();

        // Get FCM token
        String? token = await _messaging.getToken();
        if (token != null) {
          print('📱 FCM Token: ${token.substring(0, 20)}...');

          // Save to SharedPreferences
          final prefs = await SharedPreferences.getInstance();
          await prefs.setString('fcm_token', token);
          print('✅ Token saved to SharedPreferences');

          // Also write token to file for Python side
          await _writeTokenToFile(token);
        } else {
          print('⚠️ Failed to get FCM token');
        }

        // Keep file updated on token refresh
        _messaging.onTokenRefresh.listen((newToken) async {
          print('🔄 FCM token refreshed');
          final prefs = await SharedPreferences.getInstance();
          await prefs.setString('fcm_token', newToken);
          await _writeTokenToFile(newToken);
        });

        // Set up message handlers
        _setupMessageHandlers();

        print('✅ FCM fully initialized');
      } else {
        print('⚠️ Notification permission denied');
      }
    } catch (e) {
      print('❌ FCM initialization error: $e');
    }
  }

  static Future<void> _initializeLocalNotifications() async {
    const AndroidInitializationSettings androidSettings =
        AndroidInitializationSettings('@mipmap/ic_launcher');

    const InitializationSettings settings = InitializationSettings(
      android: androidSettings,
    );

    await _notifications.initialize(settings);

    // Create notification channel
    const AndroidNotificationChannel channel = AndroidNotificationChannel(
      'chat_messages',
      'Chat Messages',
      description: 'Notifications for new chat messages',
      importance: Importance.high,
      playSound: true,
      enableVibration: true,
    );

    final androidPlugin = _notifications
        .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>();

    if (androidPlugin != null) {
      await androidPlugin.createNotificationChannel(channel);
      print('✅ Notification channel created');
    }
  }

  static void _setupMessageHandlers() {
    // Foreground messages
    FirebaseMessaging.onMessage.listen((RemoteMessage message) {
      print('📨 Foreground message: ${message.notification?.title}');
      _showLocalNotification(message);
    });

    // Background messages
    FirebaseMessaging.onBackgroundMessage(_firebaseMessagingBackgroundHandler);

    // Message opened app
    FirebaseMessaging.onMessageOpenedApp.listen((RemoteMessage message) {
      print('👆 Notification tapped');
    });
  }

  static Future<void> _showLocalNotification(RemoteMessage message) async {
    RemoteNotification? notification = message.notification;

    if (notification != null) {
      await _notifications.show(
        notification.hashCode,
        notification.title,
        notification.body,
        const NotificationDetails(
          android: AndroidNotificationDetails(
            'chat_messages',
            'Chat Messages',
            channelDescription: 'Notifications for new chat messages',
            importance: Importance.high,
            priority: Priority.high,
            playSound: true,
            icon: '@mipmap/ic_launcher',
          ),
        ),
      );
    }
  }
}
