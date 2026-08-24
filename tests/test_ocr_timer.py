from web.app import _fmt_seconds, _ocr_timer_html


def test_ocr_timer_html_running_and_done():
    running = _ocr_timer_html(12.4, running=True)
    assert "OCR 进行中" in running
    assert _fmt_seconds(12.4) in running
    assert "ocr-clock-run" in running
    done = _ocr_timer_html(75.2, running=False)
    assert "OCR 总耗时" in done
    assert _fmt_seconds(75.2) in done
    assert "ocr-clock-done" in done
