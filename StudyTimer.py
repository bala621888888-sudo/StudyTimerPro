    def upload_daily_report_to_firebase(self, report_date: date | None = None):
        """Generate and upload the latest study report to Firebase for cloud delivery."""
        if report_date is None:
            report_date = date.today()
        firebase_sync = getattr(self, "_firebase_sync", None)
        if not firebase_sync or not getattr(firebase_sync, "enabled", False):
            print("[REPORT-UPLOAD] Firebase sync is disabled; skipping upload")
            return False
        try:
            if hasattr(self, 'runrate_graph') and self.runrate_graph:
                self.runrate_graph.save_snapshot_programmatic()
            pdf_buffer = self.generate_daily_pdf_auto(report_date)
            pdf_buffer.seek(0)
            pdf_base64 = base64.b64encode(pdf_buffer.read()).decode("utf-8")
            prof = _load_profile()
            chat_id = prof.get("telegram_chat_id")
            config = getattr(self, "config", {}) or {}

            payload = {
                "reportDate": report_date.isoformat(),
                "createdAt": datetime.utcnow().isoformat() + "Z",
                "telegramChatId": chat_id,
                "pdfBase64": pdf_base64,
                "appVersion": config.get("version", ""),
            }
            ref = firebase_sync.db.reference(
                f"studyReports/{firebase_sync.uid}/{report_date.isoformat()}"
            )
            ref.set(payload)
            print(
                f"[REPORT-UPLOAD] Uploaded report for {report_date} to Firebase (chat configured: {bool(chat_id)})"
            )
            return True
        except Exception as e:
            print(f"[REPORT-UPLOAD] Failed to upload report: {e}")
            return False
                messagebox.showinfo("Exported", f"PDF saved to:\n{file_path}\n\n(Auto-report will be sent automatically by the server around 11:59 PM IST)")

            try:
                self.upload_daily_report_to_firebase()
            except Exception as e:
                print(f"[CLOSE] Report upload skipped: {e}")

