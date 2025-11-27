import 'package:flutter/material.dart';
import 'main_patch.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // 🔥 DEBUG: prove this main() is actually running in the APK
  print('🔥 DART MAIN STARTED (flutter_bootstrap)');

  // Initialize FCM (this will print things like "🔔 Initializing Firebase...")
  await FCMInitializer.initialize();

  // Run the actual Flet host app
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    // Flet will take over this MaterialApp
    return MaterialApp(
      title: 'Chat App',
      home: Container(), // Flet root gets attached here
    );
  }
}
