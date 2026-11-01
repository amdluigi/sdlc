"""Optional SDK seam coverage, not evidence of real worker qualification."""

import asyncio
import copy
import hashlib
import importlib
import importlib.metadata
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.test_execution_contracts import ROOT
from artifact_contracts import ContractIssue

ADAPTER = ROOT / "integrations" / "copilot-sdk"

class SDKError(Exception):
    pass


class CopilotSDKAdapterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.assertTrue((ADAPTER / "copilot_adapter.py").is_file(),
                        "Isolated optional SDK qualification is not provided")
        if str(ADAPTER) not in sys.path:
            sys.path.insert(0, str(ADAPTER))
        self.api = importlib.import_module("copilot_adapter")
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in ("copilot-runtime.exe", "runtime.node"):
            (self.root / name).write_bytes(b"synthetic SDK-seam fixture")
        files = [{
            "path": path.name, "bytes": path.stat().st_size,
            "sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
        } for path in sorted(self.root.iterdir())]
        self.config = {
            "schemaVersion": 1, "sdkVersion": "1.0.28", "timeoutSeconds": 5,
            "runtime": {"root": str(self.root), "version": "1.0.105",
                        "entrypoint": "copilot-runtime.exe", "files": files},
        }
        self.client = SimpleNamespace(
            start=mock.AsyncMock(return_value=None), stop=mock.AsyncMock(return_value=None),
            force_stop=mock.AsyncMock(return_value=None),
            get_status=mock.AsyncMock(return_value=SimpleNamespace(version="1.0.105", protocol_version=3)),
            ping=mock.AsyncMock(side_effect=lambda message: SimpleNamespace(
                message="pong: " + message, protocol_version=3)),
        )
        self.connection = SimpleNamespace(env=None)
        self.sdk = SimpleNamespace(
            RuntimeConnection=SimpleNamespace(for_stdio=mock.Mock(return_value=self.connection)),
            CopilotClient=mock.Mock(return_value=self.client),
            StopError=SDKError,
            _jsonrpc=SimpleNamespace(JsonRpcError=SDKError, ProcessExitedError=SDKError),
        )

    async def qualify(self):
        with mock.patch.object(self.api, "_sdk", return_value=self.sdk):
            return await self.api.qualify(self.config)

    async def test_exact_shape_qualifies_transport_not_workers_or_models(self):
        original = copy.deepcopy(self.config)
        output = await self.qualify()
        self.assertEqual("passed", output["connectionQualification"])
        self.assertEqual("not-run", output["workerQualification"])
        self.assertEqual("not-assessed", output["modelRouting"])
        self.assertEqual("not-assessed", output["cancellation"])
        self.assertFalse(output["telemetryRequested"])
        self.assertEqual(2, output["runtimeFileCount"])
        self.assertEqual({
            "schemaVersion", "adapter", "sdkVersion", "runtimeVersion", "protocolVersion",
            "transport", "runtimeDigest", "runtimeFileCount", "runtimeBytes",
            "connectionQualification", "workerQualification", "modelRouting",
            "cancellation", "telemetryRequested", "contractValid", "semanticApproval", "notice",
        }, set(output))
        self.assertEqual(original, self.config)
        self.client.stop.assert_awaited_once()
        self.client.force_stop.assert_not_awaited()
        self.assertNotIn(str(self.root), json.dumps(output))

    async def test_empty_isolated_native_client_disables_ambient_features(self):
        await self.qualify()
        kwargs = self.sdk.CopilotClient.call_args.kwargs
        self.assertEqual("empty", kwargs["mode"])
        self.assertFalse(kwargs["use_logged_in_user"])
        self.assertEqual([], kwargs["builtin_plugin_directories"])
        self.assertEqual(kwargs["working_directory"], kwargs["base_directory"])
        self.assertNotEqual(str(self.root), kwargs["base_directory"])
        self.assertEqual("1", self.connection.env["COPILOT_SKIP_CLI_DOWNLOAD"])
        self.assertEqual("true", self.connection.env["COPILOT_GITHUB_TELEMETRY_DISABLED"])
        self.assertEqual("true", self.connection.env["OTEL_SDK_DISABLED"])
        self.assertNotIn("telemetry", kwargs)
        self.assertEqual(str(self.root / "copilot-runtime.exe"),
                         self.sdk.RuntimeConnection.for_stdio.call_args.kwargs["path"])

    async def test_altered_missing_or_extra_artifact_fails_before_sdk_load(self):
        for mutation in ("altered", "missing", "extra"):
            with self.subTest(mutation=mutation):
                target = self.root / "runtime.node"
                target.write_bytes(b"synthetic SDK-seam fixture")
                extra = self.root / "unlisted.txt"
                if extra.exists():
                    extra.unlink()
                if mutation == "altered":
                    target.write_bytes(b"changed")
                elif mutation == "missing":
                    target.unlink()
                else:
                    extra.write_text("extra", encoding="utf-8")
                with mock.patch.object(self.api, "_sdk") as loader:
                    with self.assertRaises(ContractIssue):
                        await self.api.qualify(self.config)
                    loader.assert_not_called()

    async def test_traversal_case_alias_and_missing_companion_are_rejected(self):
        for mutation in ("traversal", "alias", "companion"):
            bad = copy.deepcopy(self.config)
            if mutation == "traversal":
                bad["runtime"]["files"][0]["path"] = "../outside"
            elif mutation == "alias":
                bad["runtime"]["files"].append({
                    **bad["runtime"]["files"][0], "path": "COPILOT-RUNTIME.EXE",
                })
            else:
                bad["runtime"]["files"] = bad["runtime"]["files"][:1]
            with self.assertRaises(ContractIssue):
                self.api.validate_config(bad)

    async def test_unapproved_sdk_runtime_and_versions_fail_closed(self):
        for field, replacement in (("sdkVersion", "1.0.29"), ("schemaVersion", 2),
                                   ("timeoutSeconds", True), ("timeoutSeconds", 0),
                                   ("timeoutSeconds", 301)):
            bad = copy.deepcopy(self.config)
            bad[field] = replacement
            with self.assertRaises(ContractIssue):
                self.api.validate_config(bad)
        bad = copy.deepcopy(self.config)
        bad["runtime"]["version"] = "1.0.86"
        with self.assertRaises(ContractIssue):
            self.api.validate_config(bad)

    async def test_sdk_absence_has_explicit_error_without_import_or_download(self):
        with mock.patch.object(importlib.metadata, "version",
                               side_effect=importlib.metadata.PackageNotFoundError("github-copilot-sdk")):
            with self.assertRaises(ContractIssue) as caught:
                self.api._sdk()
        self.assertEqual("E_SDK_MISSING", caught.exception.code)
        with mock.patch.object(importlib.metadata, "version", return_value="1.0.29"):
            with self.assertRaises(ContractIssue) as caught:
                self.api._sdk()
        self.assertEqual("E_SDK_VERSION", caught.exception.code)

    async def test_invalid_sdk_response_still_stops_owned_client(self):
        for mutation in ("version", "protocol", "message"):
            self.client.stop.reset_mock()
            self.client.get_status.return_value = SimpleNamespace(version="1.0.105", protocol_version=3)
            self.client.ping.side_effect = lambda message: SimpleNamespace(message="pong: " + message, protocol_version=3)
            if mutation == "version":
                self.client.get_status.return_value.version = "wrong-version"
            elif mutation == "protocol":
                self.client.get_status.return_value.protocol_version = 3.0
            else:
                self.client.ping.side_effect = lambda message: SimpleNamespace(message="unrelated", protocol_version=3)
            with self.assertRaises(ContractIssue):
                await self.qualify()
            self.client.stop.assert_awaited_once()

    async def test_failed_start_and_shutdown_cannot_return_success(self):
        self.client.start.side_effect = RuntimeError("synthetic start failure")
        with self.assertRaises(ContractIssue):
            await self.qualify()
        self.client.stop.assert_awaited_once()
        self.client.start.side_effect = None
        self.client.stop.side_effect = RuntimeError("synthetic stop failure")
        with self.assertRaises(ContractIssue) as caught:
            await self.qualify()
        self.assertEqual("E_SDK_SHUTDOWN", caught.exception.code)
        self.client.force_stop.assert_awaited_once()

    async def test_complete_inventory_is_bounded(self):
        bad = copy.deepcopy(self.config)
        bad["runtime"]["files"] *= 129
        with self.assertRaises(ContractIssue):
            self.api.validate_config(bad)
        bad = copy.deepcopy(self.config)
        bad["runtime"]["files"][0]["bytes"] = 512 * 1024 * 1024 + 1
        with self.assertRaises(ContractIssue):
            self.api.validate_config(bad)

    async def test_unreadable_directory_is_not_silently_skipped(self):
        def unavailable(root, **kwargs):
            kwargs["onerror"](PermissionError("synthetic inaccessible directory"))
            return iter(())
        with mock.patch.object(self.api.os, "walk", side_effect=unavailable):
            with mock.patch.object(self.api, "_sdk") as loader:
                with self.assertRaises(ContractIssue):
                    await self.api.qualify(self.config)
                loader.assert_not_called()

    async def test_inventory_requires_exact_entrypoint_spelling(self):
        self.config["runtime"]["entrypoint"] = "COPILOT-RUNTIME.EXE"
        with mock.patch.object(self.api, "_sdk") as loader:
            with self.assertRaises(ContractIssue):
                await self.api.qualify(self.config)
            loader.assert_not_called()

    async def test_root_link_or_junction_is_rejected(self):
        import subprocess
        alias = self.root / "alias"
        target = self.root / "target"
        target.mkdir()
        try:
            alias.symlink_to(target, target_is_directory=True)
        except OSError:
            if sys.platform != "win32":
                raise
            subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(alias), str(target)],
                           check=True, capture_output=True)
        self.addCleanup(alias.rmdir if sys.platform == "win32" else alias.unlink)
        nested = target / "nested"
        nested.mkdir()
        for name in ("copilot-runtime.exe", "runtime.node"):
            (nested / name).write_bytes(b"synthetic SDK-seam fixture")
        for root in (alias, alias / "nested"):
            self.config["runtime"]["root"] = str(root)
            with mock.patch.object(self.api, "_sdk") as loader:
                with self.assertRaises(ContractIssue) as caught:
                    await self.api.qualify(self.config)
                self.assertEqual("E_SDK_PATH", caught.exception.code)
                loader.assert_not_called()

    async def test_timeout_and_caller_cancellation_stop_the_owned_client(self):
        async def slow_start():
            await asyncio.sleep(60)
        self.client.start.side_effect = slow_start
        self.config["timeoutSeconds"] = 1
        with self.assertRaises(ContractIssue) as caught:
            await self.qualify()
        self.assertEqual("E_SDK_TIMEOUT", caught.exception.code)
        self.client.stop.assert_awaited_once()
        self.client.stop.reset_mock()
        self.client.start.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.qualify()
        self.client.stop.assert_awaited_once()

    async def test_sdk_rpc_and_documented_cleanup_errors_are_neutral(self):
        self.client.get_status.side_effect = SDKError("synthetic RPC diagnostic")
        with self.assertRaises(ContractIssue) as caught:
            await self.qualify()
        self.assertEqual("E_SDK_TRANSPORT", caught.exception.code)
        self.client.get_status.side_effect = None
        self.client.stop.side_effect = ExceptionGroup("SDK cleanup", [SDKError("synthetic cleanup")])
        with self.assertRaises(ContractIssue) as caught:
            await self.qualify()
        self.assertEqual("E_SDK_SHUTDOWN", caught.exception.code)

    async def test_client_construction_and_shutdown_timeout_fail_explicitly(self):
        self.sdk.CopilotClient.side_effect = ValueError("synthetic SDK constructor failure")
        with self.assertRaises(ContractIssue) as caught:
            await self.qualify()
        self.assertEqual("E_SDK_TRANSPORT", caught.exception.code)
        self.client.start.assert_not_awaited()
        self.sdk.CopilotClient.side_effect = None
        async def slow_stop():
            await asyncio.sleep(60)
        self.client.stop.side_effect = slow_stop
        self.config["timeoutSeconds"] = 1
        with self.assertRaises(ContractIssue) as caught:
            await self.qualify()
        self.assertEqual("E_SDK_SHUTDOWN", caught.exception.code)
        self.client.force_stop.assert_awaited_once()

    async def test_sdk_parser_failures_are_neutral_and_still_stop(self):
        for method in (self.client.get_status, self.client.ping):
            for error in (ValueError, AssertionError):
                method.side_effect = error("synthetic private parser diagnostic")
                with self.assertRaises(ContractIssue) as caught:
                    await self.qualify()
                self.assertEqual("E_SDK_RESPONSE", caught.exception.code)
                self.assertNotIn("private", caught.exception.cli_message())
                method.side_effect = None
        self.assertEqual(4, self.client.stop.await_count)

    async def test_forced_cleanup_failure_is_not_a_success_fallback(self):
        self.client.stop.side_effect = RuntimeError("synthetic failed graceful stop")
        self.client.force_stop.side_effect = OSError("synthetic failed forced stop")
        with self.assertRaises(ContractIssue) as caught:
            await self.qualify()
        self.assertEqual("E_SDK_SHUTDOWN", caught.exception.code)
        self.client.force_stop.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
