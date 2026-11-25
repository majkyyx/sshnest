"""Keep bundled GTK state out of the real terminal/file-manager processes."""

import os
import sys
import unittest
from unittest.mock import patch

from sshnest.launcher import _host_environment


class HostEnvironmentTests(unittest.TestCase):
    def test_source_launch_preserves_environment(self):
        with patch.dict(os.environ, {"LD_LIBRARY_PATH": "/custom/lib"}, clear=True):
            self.assertEqual(_host_environment(), {"LD_LIBRARY_PATH": "/custom/lib"})

    def test_frozen_launch_restores_host_paths_without_changing_app_environment(self):
        env = {
            "LD_LIBRARY_PATH": "/bundle:/host/lib",
            "LD_LIBRARY_PATH_ORIG": "/host/lib",
            "GI_TYPELIB_PATH": "/bundle/gi_typelibs",
            "GIO_MODULE_DIR": "/bundle/gio_modules",
            "GTK_DATA_PREFIX": "/bundle",
            "XDG_DATA_DIRS": "/bundle/share:/usr/share",
            "DISPLAY": ":97",
            "SSH_AUTH_SOCK": "/test-agent",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "_MEIPASS", "/bundle", create=True),
        ):
            result = _host_environment()
            self.assertEqual(result["LD_LIBRARY_PATH"], "/host/lib")
            self.assertEqual(result["XDG_DATA_DIRS"], "/usr/share")
            self.assertEqual(result["SSH_AUTH_SOCK"], "/test-agent")
            self.assertNotIn("GI_TYPELIB_PATH", result)
            self.assertNotIn("GTK_DATA_PREFIX", result)
            self.assertNotIn("GIO_MODULE_DIR", result)
            self.assertEqual(os.environ["GI_TYPELIB_PATH"], "/bundle/gi_typelibs")

    def test_frozen_launch_removes_library_override_without_original(self):
        with (
            patch.dict(os.environ, {"LD_LIBRARY_PATH": "/bundle"}, clear=True),
            patch.object(sys, "frozen", True, create=True),
        ):
            self.assertNotIn("LD_LIBRARY_PATH", _host_environment())
