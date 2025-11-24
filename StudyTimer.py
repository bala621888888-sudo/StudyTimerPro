
        # 1) Prefer the new multi-exam helper so we pick the right exam immediately.
        try:
            prof = _load_profile() or {}
            current_exam = (prof.get("exam_name") or "").strip()
            dt = get_exam_date_for_exam(current_exam)
            if dt:
                return dt
        except Exception:
            pass

        # 2) Legacy single-date file shape: {"exam_date": "YYYY-MM-DD"}
                if isinstance(data, dict):
                    s = data.get("exam_date")
                    if s:
                        return datetime.strptime(s, "%Y-%m-%d").date()


        # Ensure date fields are always usable to avoid crashes during early boot
        from datetime import date as _date
        if not getattr(self, "progress_start_date", None):
            self.progress_start_date = _date.today()
        if not getattr(self, "progress_exam_date", None):
            self.progress_exam_date = self.progress_start_date
        if self.progress_exam_date < self.progress_start_date:
            self.progress_exam_date = self.progress_start_date

        if not hasattr(self, "progress_markers") or self.progress_markers is None:
            self.progress_markers = []

