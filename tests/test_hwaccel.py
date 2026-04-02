"""Tests for core.hwaccel — GPU diagnostics, encoder detection, quality params, benchmark."""
from unittest.mock import patch, MagicMock

import core.hwaccel as hwaccel_mod
from core.hwaccel import (
    EncoderInfo, _get_gpu_name, _get_nvenc_max_sessions,
    _quality_params_for, detect_best_encoder, diagnose_gpu,
    get_encoder_info, get_ffmpeg_params,
)


class TestGetGpuName:
    def test_nvidia_smi_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "NVIDIA GeForce RTX 3060\n"
        with patch("core.hwaccel.subprocess.run", return_value=mock_result):
            assert _get_gpu_name() == "NVIDIA GeForce RTX 3060"

    def test_nvidia_smi_not_found(self):
        with patch("core.hwaccel.subprocess.run", side_effect=FileNotFoundError):
            assert _get_gpu_name() is None

    def test_nvidia_smi_failure(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        with patch("core.hwaccel.subprocess.run", return_value=mock_result):
            assert _get_gpu_name() is None

    def test_multi_gpu_returns_first(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "NVIDIA GeForce RTX 4090\nNVIDIA GeForce RTX 3060\n"
        with patch("core.hwaccel.subprocess.run", return_value=mock_result):
            assert _get_gpu_name() == "NVIDIA GeForce RTX 4090"


class TestDiagnoseGpu:
    def test_nvenc_encoder(self):
        nvenc = EncoderInfo(
            codec="h264_nvenc", name="NVIDIA NVENC",
            is_hardware=True, extra_params=["-rc", "vbr"],
        )
        with (
            patch("core.hwaccel.get_encoder_info", return_value=nvenc),
            patch("core.hwaccel._get_gpu_name", return_value="NVIDIA GeForce RTX 3060"),
            patch("core.hwaccel._get_nvenc_max_sessions", return_value=3),
        ):
            info = diagnose_gpu()

        assert info["encoder_name"] == "NVIDIA NVENC"
        assert info["encoder_codec"] == "h264_nvenc"
        assert info["is_hardware"] is True
        assert info["gpu_model"] == "NVIDIA GeForce RTX 3060"
        assert info["nvenc_sessions"] == 3

    def test_software_encoder(self):
        libx264 = EncoderInfo(
            codec="libx264", name="Software x264",
            is_hardware=False, extra_params=["-preset", "medium"],
        )
        with patch("core.hwaccel.get_encoder_info", return_value=libx264):
            info = diagnose_gpu()

        assert info["encoder_name"] == "Software x264"
        assert info["is_hardware"] is False
        assert info["gpu_model"] is None
        assert info["nvenc_sessions"] is None

    def test_qsv_encoder_no_gpu_model(self):
        qsv = EncoderInfo(
            codec="h264_qsv", name="Intel QuickSync",
            is_hardware=True, extra_params=["-preset", "medium"],
        )
        with patch("core.hwaccel.get_encoder_info", return_value=qsv):
            info = diagnose_gpu()

        assert info["is_hardware"] is True
        assert info["gpu_model"] is None
        assert info["nvenc_sessions"] is None


# -- _quality_params_for ----------------------------------------------------


class TestQualityParams:
    def test_libx264_uses_crf(self):
        enc = EncoderInfo(codec="libx264", name="x264", is_hardware=False)
        params = _quality_params_for(enc, 23)
        assert params == ["-crf", "23"]

    def test_nvenc_uses_cq(self):
        enc = EncoderInfo(codec="h264_nvenc", name="NVENC", is_hardware=True)
        params = _quality_params_for(enc, 23)
        assert "-cq" in params
        assert "23" in params

    def test_qsv_uses_global_quality(self):
        enc = EncoderInfo(codec="h264_qsv", name="QSV", is_hardware=True)
        params = _quality_params_for(enc, 18)
        assert params == ["-global_quality", "18"]

    def test_amf_uses_qp(self):
        enc = EncoderInfo(codec="h264_amf", name="AMF", is_hardware=True)
        params = _quality_params_for(enc, 28)
        assert "-rc" in params
        assert "-qp_i" in params

    def test_videotoolbox_uses_q_v(self):
        enc = EncoderInfo(codec="h264_videotoolbox", name="VT", is_hardware=True)
        params = _quality_params_for(enc, 23)
        assert "-q:v" in params


# -- get_ffmpeg_params ------------------------------------------------------


class TestGetFfmpegParams:
    def test_returns_codec_and_quality(self):
        enc = EncoderInfo(codec="libx264", name="x264", is_hardware=False, extra_params=["-preset", "medium"])
        with patch("core.hwaccel.get_encoder_info", return_value=enc):
            params = get_ffmpeg_params("medium")
        assert params[0] == "-c:v"
        assert params[1] == "libx264"
        assert "-crf" in params

    def test_invalid_quality_raises(self):
        import pytest
        with pytest.raises(ValueError, match="Unknown quality"):
            get_ffmpeg_params("ultra")


# -- _get_nvenc_max_sessions ------------------------------------------------


class TestNvencMaxSessions:
    def test_consumer_gpu_returns_3(self):
        with patch("core.hwaccel._get_gpu_name", return_value="NVIDIA GeForce RTX 3090"):
            assert _get_nvenc_max_sessions() == 3

    def test_pro_gpu_returns_8(self):
        with patch("core.hwaccel._get_gpu_name", return_value="NVIDIA RTX A6000"):
            assert _get_nvenc_max_sessions() == 8

    def test_no_gpu_returns_3(self):
        with patch("core.hwaccel._get_gpu_name", return_value=None):
            assert _get_nvenc_max_sessions() == 3


# -- detect_best_encoder ---------------------------------------------------


class TestDetectBestEncoder:
    def test_caches_result(self):
        hwaccel_mod._cached_encoder = None
        with patch("core.hwaccel._pick_encoder") as mock_pick:
            mock_pick.return_value = EncoderInfo(
                codec="libx264", name="x264", is_hardware=False,
            )
            enc1 = detect_best_encoder()
            enc2 = detect_best_encoder()  # should use cache
        mock_pick.assert_called_once()
        assert enc1.codec == enc2.codec
        hwaccel_mod._cached_encoder = None  # cleanup

    def test_fallback_on_exception(self):
        hwaccel_mod._cached_encoder = None
        with patch("core.hwaccel._pick_encoder", side_effect=RuntimeError("boom")):
            enc = detect_best_encoder()
        assert enc.codec == "libx264"
        hwaccel_mod._cached_encoder = None
