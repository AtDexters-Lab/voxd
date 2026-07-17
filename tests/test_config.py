
def test_aipp_provider_validation_resets_invalid():
    from voxd.core.config import AppConfig
    cfg = AppConfig()
    cfg.data["aipp_provider"] = "invalid"
    cfg._validate_aipp_config()
    assert cfg.data["aipp_provider"] in (
        "ollama", "openai", "anthropic", "xai", "llamacpp_server"
    )


def test_llamacpp_status_flags_do_not_crash():
    from voxd.core.config import AppConfig
    cfg = AppConfig()
    status = cfg.validate_llamacpp_setup()
    assert {
        "server_available",
        "cli_available",
        "default_model_available",
    } <= set(status.keys())


def test_gemma_transcription_defaults():
    from voxd.core.config import AppConfig

    cfg = AppConfig()
    assert cfg.data["transcription_backend"] == "gemma"
    assert cfg.data["gemma_server_url"] == "http://localhost:9292"
    assert cfg.data["gemma_model"] == "gemma-e4b"
    assert cfg.data["gemma_timeout"] == 300
    assert 0 < cfg.data["gemma_segment_seconds"] < 30
    assert cfg.data["gemma_segment_overlap_seconds"] < cfg.data["gemma_segment_seconds"]
    prompt = cfg.data["gemma_transcription_prompt"]
    assert "natural punctuation" in prompt
    assert "question marks" in prompt
    assert "exact spellings" not in prompt
