"""Run actual pinned SDK parser/cleanup regressions without launching a process."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import copilot_adapter as adapter


async def verify():
    sdk = adapter._sdk()
    root = Path(__file__).resolve().parent
    config = {
        "schemaVersion": 1, "sdkVersion": adapter.SDK_VERSION, "timeoutSeconds": 1,
        "runtime": {
            "root": str(root), "version": adapter.RUNTIME_VERSION,
            "entrypoint": "copilot-runtime.exe",
            "files": [{"path": name, "bytes": 0, "sha256": "sha256:" + "0" * 64}
                      for name in ("copilot-runtime.exe", "runtime.node")],
        },
    }

    def client():
        connection = sdk.RuntimeConnection.for_stdio(path=str(root / "copilot-runtime.exe"))
        connection.env = {"COPILOT_SKIP_CLI_DOWNLOAD": "1"}
        return sdk.CopilotClient(connection=connection, mode="empty", use_logged_in_user=False,
                                 base_directory=str(root), working_directory=str(root),
                                 builtin_plugin_directories=[])

    async def invoke(instance):
        with (
            mock.patch.object(adapter, "_verify_runtime", return_value=root / "copilot-runtime.exe"),
            mock.patch.object(sdk, "CopilotClient", return_value=instance),
            mock.patch("subprocess.Popen", side_effect=AssertionError("process launch forbidden")),
        ):
            return await adapter.qualify(config)

    instance = client()
    instance.start = mock.AsyncMock(return_value=None)
    instance.get_status = mock.AsyncMock(
        return_value=SimpleNamespace(version=adapter.RUNTIME_VERSION, protocol_version=3))
    instance.ping = mock.AsyncMock(
        side_effect=lambda nonce: SimpleNamespace(message="pong: " + nonce, protocol_version=3))
    process = mock.Mock()
    process.poll.return_value = None
    process.wait.return_value = 0
    instance._process = instance._cli_process = process

    async def stalled_shutdown(**kwargs):
        await asyncio.sleep(60)
    instance._rpc = SimpleNamespace(runtime=SimpleNamespace(shutdown=stalled_shutdown))
    try:
        await invoke(instance)
    except adapter.ContractIssue as error:
        assert error.code == "E_SDK_SHUTDOWN"
    else:
        raise AssertionError("graceful timeout must remain a failed qualification")
    process.kill.assert_called_once()
    process.wait.assert_called_once_with(timeout=5)
    assert instance._cli_process is None and instance._process is None

    for method, response in (
        ("status.get", {"version": "PRIVATE_SDK_DIAGNOSTIC"}),
        ("ping", {"message": "PRIVATE_SDK_DIAGNOSTIC"}),
        ("status.get", None), ("status.get", []),
        ("ping", None), ("ping", []),
    ):
        instance = client()
        instance.start = mock.AsyncMock(return_value=None)
        instance.stop = mock.AsyncMock(return_value=None)
        if method == "ping":
            instance.get_status = mock.AsyncMock(
                return_value=SimpleNamespace(version=adapter.RUNTIME_VERSION, protocol_version=3))
        instance._client = SimpleNamespace(request=mock.AsyncMock(return_value=response))
        try:
            await invoke(instance)
        except adapter.ContractIssue as error:
            assert error.code == "E_SDK_RESPONSE"
            assert "PRIVATE_SDK_DIAGNOSTIC" not in error.cli_message()
        else:
            raise AssertionError("malformed SDK response must fail neutrally")
        assert instance._client.request.call_args.args[0] == method
        instance.stop.assert_awaited_once()
        instance._client = None
    print("Actual SDK parser and forced-cleanup regressions passed; no process or inference was launched")


if __name__ == "__main__":
    asyncio.run(verify())
