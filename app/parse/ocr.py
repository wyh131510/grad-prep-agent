# -*- coding: utf-8 -*-
"""OCR 引擎（RapidOCR，可选依赖）：文本图片 / 扫描版 PDF 的文字提取。"""
from __future__ import annotations

import io
import threading


class OcrEngine:
    _instance: "OcrEngine | None" = None
    _lock = threading.Lock()

    def __init__(self):
        self._engine = None
        self.error = ""
        self._tried = False

    @classmethod
    def get(cls) -> "OcrEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _ensure(self) -> bool:
        if self._tried:
            return self._engine is not None
        self._tried = True
        try:
            from rapidocr_onnxruntime import RapidOCR

            self._engine = RapidOCR()
        except Exception as exc:  # noqa: BLE001
            self.error = f"OCR 未安装或初始化失败：{exc}"
        return self._engine is not None

    @property
    def available(self) -> bool:
        return self._ensure()

    def recognize(self, image_bytes: bytes) -> str:
        """识别图片中的文字，返回按行拼接的文本。"""
        if not self._ensure():
            raise RuntimeError(self.error or "OCR 不可用")
        result, _ = self._engine(image_bytes)
        lines = []
        for item in result or []:
            text = str(item[1]).strip()
            if text:
                lines.append(text)
        return "\n".join(lines)

    def recognize_pdf_page(self, page) -> str:
        """渲染 PDF 页面为图片后识别。page: pymupdf Page。"""
        pix = page.get_pixmap(dpi=150)
        buf = io.BytesIO(pix.tobytes("png"))
        return self.recognize(buf.getvalue())


ocr = OcrEngine.get()
