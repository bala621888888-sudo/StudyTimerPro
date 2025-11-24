        # Once onboarding is marked done, do not prompt again even if cached exam date is missing.
        need_wiz = not done_flag
                    self.progress_exam_date = _load_exam_date_only() or date.today()
                    self.progress_exam_date = date.today()
                self.progress_exam_date = _load_exam_date_only() or date.today()
                self.progress_exam_date = date.today()
        if self.progress_exam_date is None:
            self.progress_exam_date = date.today()
        if self.progress_start_date is None:
            self.progress_start_date = date.today()

