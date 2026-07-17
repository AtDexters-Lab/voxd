import yaml


def test_gemma_transcription_defaults():
    from voxd.core.config import AppConfig

    cfg = AppConfig()
    assert cfg.gemma_server_url == "http://localhost:9292"
    assert cfg.gemma_model == "gemma-e4b"
    assert cfg.gemma_timeout == 300
    assert 0 < cfg.gemma_segment_seconds < 30
    assert cfg.gemma_segment_overlap_seconds < cfg.gemma_segment_seconds
    assert "gemma_transcription_prompt" not in cfg.data


def test_load_migrates_legacy_keys_out_of_config():
    from voxd.core.config import AppConfig, CONFIG_PATH

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        yaml.safe_dump(
            {
                "typing_delay": 3,
                "whisper_model_path": "/old/model.bin",
                "aipp_enabled": True,
                "flux_min_speech_ms": 200,
            }
        ),
        encoding="utf-8",
    )

    cfg = AppConfig()

    assert cfg.typing_delay == 3
    assert "whisper_model_path" not in cfg.data
    assert "aipp_enabled" not in cfg.data
    saved = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    assert set(saved) == set(cfg.data)


def test_invalid_values_fall_back_to_safe_defaults():
    from voxd.core.config import AppConfig, CONFIG_PATH, DEFAULT_CONFIG

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        yaml.safe_dump(
            {
                "typing_delay": "fast",
                "gemma_segment_seconds": 30,
                "gemma_segment_overlap_seconds": 28,
                "append_trailing_space": "yes",
            }
        ),
        encoding="utf-8",
    )

    cfg = AppConfig()

    assert cfg.typing_delay == DEFAULT_CONFIG["typing_delay"]
    assert cfg.gemma_segment_seconds == DEFAULT_CONFIG["gemma_segment_seconds"]
    assert cfg.gemma_segment_overlap_seconds < cfg.gemma_segment_seconds
    assert cfg.append_trailing_space is DEFAULT_CONFIG["append_trailing_space"]


def test_small_segment_always_gets_smaller_overlap():
    from voxd.core.config import AppConfig, CONFIG_PATH

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        yaml.safe_dump(
            {
                "gemma_segment_seconds": 0.5,
                "gemma_segment_overlap_seconds": 1,
            }
        ),
        encoding="utf-8",
    )

    cfg = AppConfig()

    assert 0 <= cfg.gemma_segment_overlap_seconds < cfg.gemma_segment_seconds
