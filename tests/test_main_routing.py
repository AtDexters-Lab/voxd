import sys


def test_default_invocation_routes_to_tray(monkeypatch):
    import voxd.__main__ as main_module
    import voxd.tray.tray_main as tray_module

    called = []
    monkeypatch.setattr(sys, "argv", ["voxd"])
    monkeypatch.setattr(main_module, "_mic_autoset_if_enabled", lambda _cfg: None)
    monkeypatch.setattr(tray_module, "main", lambda: called.append("tray"))

    main_module.main()

    assert called == ["tray"]


def test_trigger_exit_status_reflects_ipc_delivery(monkeypatch):
    import voxd.__main__ as main_module
    import voxd.utils.ipc_client as ipc_client

    monkeypatch.setattr(sys, "argv", ["voxd", "--trigger-record"])
    monkeypatch.setattr(ipc_client, "send_trigger", lambda: False)

    try:
        main_module.main()
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("trigger mode did not exit")
