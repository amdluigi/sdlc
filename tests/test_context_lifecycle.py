import unittest

from tests import test_bounded_runtime as bounded_tests
import execution_manager as manager
from tests.test_execution_contracts import result


class ContextLifecycleTests(unittest.TestCase):
    setUp = bounded_tests.BoundedRuntimeTests.setUp
    prepare = bounded_tests.BoundedRuntimeTests.prepare
    start = bounded_tests.BoundedRuntimeTests.start
    issue = bounded_tests.BoundedRuntimeTests.issue
    def update(self, content="Context B."):
        current = manager.inspect_execution(self.root, "feature-one")
        return manager.update_context(
            self.root, "feature-one", "shared", None, content,
            current["planDigest"], current["context"]["revision"],
        )

    def test_ac1_context_freeze_covers_blocked_and_unknown_native_work(self):
        self.update("Context A.")
        self.start()
        before = manager.inspect_execution(self.root, "feature-one")["context"]
        self.issue(lambda: self.update(), "E_EXECUTION_CONTEXT_ACTIVE")
        self.issue(lambda: self.update("Context A."), "E_EXECUTION_CONTEXT_ACTIVE")
        manager.record_task(self.root, "feature-one", "implement", "block", reason="Waiting.")
        self.issue(lambda: self.update(), "E_EXECUTION_CONTEXT_ACTIVE")
        manager.record_task(self.root, "feature-one", "implement", "unblock")
        self.api.stop(self.root, self.envelope)
        self.issue(lambda: self.update(), "E_EXECUTION_CONTEXT_ACTIVE")
        manager.record_task(self.root, "feature-one", "implement", "cancel", reason="Local stop declared.")
        self.issue(lambda: self.update(), "E_EXECUTION_CONTEXT_ACTIVE")
        self.assertEqual(before, manager.inspect_execution(self.root, "feature-one")["context"])

    def test_ac1_manual_terminal_state_releases_context_freeze(self):
        manager.record_task(self.root, "feature-one", "implement", "ready")
        manager.record_task(self.root, "feature-one", "implement", "start", "attempt-one")
        self.issue(lambda: self.update(), "E_EXECUTION_CONTEXT_ACTIVE")
        manager.record_task(self.root, "feature-one", "implement", "cancel", reason="Operator stopped work.")
        self.assertEqual("Context B.", self.update()["context"]["shared"]["content"])

    def test_ac1_worker_context_update_is_atomic_with_receipt(self):
        self.start()
        value = {**result(self.plan), "schemaVersion": 2, "contextUpdate": "Worker terminal note."}
        value["verification"][0]["result"] = "unavailable"
        self.api.receive(self.root, self.envelope, value)
        current = manager.inspect_execution(self.root, "feature-one")
        self.assertEqual("reported", current["state"]["tasks"]["implement"]["status"])
        self.assertEqual("Worker terminal note.", current["context"]["agents"]["developer"]["content"])
        self.assertEqual("Context B.", self.update()["context"]["shared"]["content"])


if __name__ == "__main__":
    unittest.main()
