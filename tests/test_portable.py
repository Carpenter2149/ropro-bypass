import os
from contextlib import ExitStack
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import patch_ropro


def scenario_args(**overrides):
    values = {
        "preset": "real",
        "subscription": None,
        "restrict_settings": None,
        "roblox_premium": None,
        "discord_13_plus": None,
        "maintenance": None,
        "settings": None,
        "verification": None,
        "egg_collection": None,
        "free_trial_hours": None,
        "route_checks": None,
        "sender_validation": None,
        "message_shape_validation": None,
        "url_validation": None,
        "api_payload_validation": None,
        "setting": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class PortableToolTests(unittest.TestCase):
    def make_minimal_patch_source(self, root):
        source = Path(root)
        for relative in (
            "background.js",
            "js/page/options.js",
            "js/page/friends.js",
            "js/shared/roproApiAdapter.js",
        ):
            path = source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("old", encoding="utf-8")
        return source

    def patch_in_place_context(self, verify_side_effect=None):
        metadata = {
            "extension_id": patch_ropro.EXPECTED_ID,
            "version": "1.0",
            "audited": False,
            "source_hashes": {},
        }
        return (
            patch("patch_ropro.validate_pristine", return_value=metadata),
            patch("patch_ropro.background_edits", return_value=(("old", "new"),)),
            patch("patch_ropro.options_edits", return_value=(("old", "new"),)),
            patch("patch_ropro.friends_edits", return_value=(("old", "new"),)),
            patch("patch_ropro.adapter_edits", return_value=(("old", "new"),)),
            patch("patch_ropro.verify_patched", side_effect=verify_side_effect, return_value="fingerprint"),
        )

    def test_patch_in_place_modifies_the_source_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_minimal_patch_source(temporary)
            contexts = self.patch_in_place_context()
            with contexts[0], contexts[1], contexts[2], contexts[3], contexts[4], contexts[5]:
                patch_ropro.patch_in_place(source, patch_ropro.SCENARIO_PRESETS["max-access"])
            self.assertEqual((source / "background.js").read_text(encoding="utf-8"), "new")
            self.assertTrue((source / patch_ropro.TEST_CONFIG_FILE).is_file())

    def test_patch_in_place_rolls_back_on_failed_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_minimal_patch_source(temporary)
            contexts = self.patch_in_place_context(SystemExit("verification failed"))
            with contexts[0], contexts[1], contexts[2], contexts[3], contexts[4], contexts[5]:
                with self.assertRaises(SystemExit):
                    patch_ropro.patch_in_place(source, patch_ropro.SCENARIO_PRESETS["max-access"])
            for relative in (
                "background.js",
                "js/page/options.js",
                "js/page/friends.js",
                "js/shared/roproApiAdapter.js",
            ):
                self.assertEqual((source / relative).read_text(encoding="utf-8"), "old")
            self.assertFalse((source / patch_ropro.TEST_CONFIG_FILE).exists())

    def test_update_replaces_only_an_already_patched_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            installed = Path(temporary) / "1.0_0"
            installed.mkdir()
            original_inode = installed.stat().st_ino
            original_parent_entries = {installed}
            (installed / patch_ropro.TEST_CONFIG_FILE).write_text("{}", encoding="utf-8")
            (installed / "old-file").write_text("old", encoding="utf-8")

            def extract_candidate(_package, destination):
                (destination / "manifest.json").write_text("{}", encoding="utf-8")

            def patch_candidate(source, _config, _policy):
                (source / "patched-file").write_text("new", encoding="utf-8")

            document = {
                "source": {"version": "1.0"},
                "config": patch_ropro.SCENARIO_PRESETS["max-access"],
            }
            candidate = {"version": "2.0", "audited": True}
            with ExitStack() as stack:
                stack.enter_context(patch("patch_ropro.choose_source", return_value=installed))
                stack.enter_context(patch("patch_ropro.read_test_document", return_value=document))
                stack.enter_context(patch("patch_ropro.verify_patched", return_value="fingerprint"))
                stack.enter_context(patch("patch_ropro.download_package", return_value=b"package"))
                stack.enter_context(patch("patch_ropro.extract_package", side_effect=extract_candidate))
                stack.enter_context(patch("patch_ropro.normalize_package_manifest", return_value={"version": "2.0"}))
                stack.enter_context(patch("patch_ropro.validate_pristine", return_value=candidate))
                stack.enter_context(patch("patch_ropro.patch_in_place", side_effect=patch_candidate))
                patch_ropro.update_in_place(installed)

            self.assertFalse((installed / "old-file").exists())
            self.assertEqual((installed / "patched-file").read_text(encoding="utf-8"), "new")
            self.assertEqual(installed.stat().st_ino, original_inode)
            self.assertEqual(set(Path(temporary).iterdir()), original_parent_entries)
            self.assertFalse(any(installed.glob(".ropro-bypass-update-*")))

    def test_update_rolls_back_inside_the_extension_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            installed = Path(temporary) / "1.0_0"
            installed.mkdir()
            original_inode = installed.stat().st_ino
            (installed / patch_ropro.TEST_CONFIG_FILE).write_text("{}", encoding="utf-8")
            (installed / "old-file").write_text("old", encoding="utf-8")

            def extract_candidate(_package, destination):
                (destination / "manifest.json").write_text("{}", encoding="utf-8")

            def patch_candidate(source, _config, _policy):
                (source / "patched-file").write_text("new", encoding="utf-8")

            document = {
                "source": {"version": "1.0"},
                "config": patch_ropro.SCENARIO_PRESETS["max-access"],
            }
            candidate = {"version": "2.0", "audited": True}
            original_copy = patch_ropro.copy_directory_contents
            copy_count = 0

            def fail_during_install(source, destination, excluded=None):
                nonlocal copy_count
                copy_count += 1
                if copy_count == 2:
                    (destination / "partial-file").write_text("partial", encoding="utf-8")
                    raise OSError("simulated install failure")
                return original_copy(source, destination, excluded)

            with ExitStack() as stack:
                stack.enter_context(patch("patch_ropro.choose_source", return_value=installed))
                stack.enter_context(patch("patch_ropro.read_test_document", return_value=document))
                stack.enter_context(patch("patch_ropro.verify_patched", return_value="fingerprint"))
                stack.enter_context(patch("patch_ropro.download_package", return_value=b"package"))
                stack.enter_context(patch("patch_ropro.extract_package", side_effect=extract_candidate))
                stack.enter_context(patch("patch_ropro.normalize_package_manifest", return_value={"version": "2.0"}))
                stack.enter_context(patch("patch_ropro.validate_pristine", return_value=candidate))
                stack.enter_context(patch("patch_ropro.patch_in_place", side_effect=patch_candidate))
                stack.enter_context(patch("patch_ropro.copy_directory_contents", side_effect=fail_during_install))
                with self.assertRaisesRegex(OSError, "simulated install failure"):
                    patch_ropro.update_in_place(installed)

            self.assertEqual(installed.stat().st_ino, original_inode)
            self.assertEqual((installed / "old-file").read_text(encoding="utf-8"), "old")
            self.assertFalse((installed / "partial-file").exists())
            self.assertFalse(any(installed.glob(".ropro-bypass-update-*")))
            self.assertEqual(set(Path(temporary).iterdir()), {installed})

    def test_update_leaves_an_unpatched_directory_untouched(self):
        with tempfile.TemporaryDirectory() as temporary:
            installed = Path(temporary) / "1.0_0"
            installed.mkdir()
            sentinel = installed / "unchanged"
            sentinel.write_text("same", encoding="utf-8")
            with patch("patch_ropro.choose_source", return_value=installed), patch(
                "patch_ropro.download_package"
            ) as download:
                patch_ropro.update_in_place(installed)
            download.assert_not_called()
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "same")

    def test_update_leaves_current_patch_when_upstream_is_unsupported(self):
        with tempfile.TemporaryDirectory() as temporary:
            installed = Path(temporary) / "1.0_0"
            installed.mkdir()
            (installed / patch_ropro.TEST_CONFIG_FILE).write_text("{}", encoding="utf-8")
            sentinel = installed / "unchanged"
            sentinel.write_text("same", encoding="utf-8")

            def extract_candidate(_package, destination):
                (destination / "manifest.json").write_text("{}", encoding="utf-8")

            document = {
                "source": {"version": "1.0"},
                "config": patch_ropro.SCENARIO_PRESETS["max-access"],
            }
            with ExitStack() as stack:
                stack.enter_context(patch("patch_ropro.choose_source", return_value=installed))
                stack.enter_context(patch("patch_ropro.read_test_document", return_value=document))
                stack.enter_context(patch("patch_ropro.verify_patched", return_value="fingerprint"))
                stack.enter_context(patch("patch_ropro.download_package", return_value=b"package"))
                stack.enter_context(patch("patch_ropro.extract_package", side_effect=extract_candidate))
                stack.enter_context(patch("patch_ropro.normalize_package_manifest", return_value={"version": "2.0"}))
                stack.enter_context(patch("patch_ropro.validate_pristine", side_effect=SystemExit("unsupported")))
                with self.assertRaises(SystemExit):
                    patch_ropro.update_in_place(installed)

            self.assertEqual(sentinel.read_text(encoding="utf-8"), "same")
            self.assertFalse(any(Path(temporary).glob(".*.update-*")))

    def test_audited_build_registry_is_complete(self):
        builds = patch_ropro.load_audited_builds()
        self.assertIn("1.7.1", builds)
        self.assertEqual(
            set(builds["1.7.1"]["hashes"]),
            set(patch_ropro.MODIFIED_SOURCE_FILES),
        )

    def test_content_fingerprint_ignores_metadata(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            for root in (Path(first), Path(second)):
                (root / "nested").mkdir()
                (root / "nested/file.txt").write_bytes(b"same bytes")
            os.utime(Path(first) / "nested/file.txt", (1_000_000_000, 1_000_000_000))
            os.utime(Path(second) / "nested/file.txt", (1_500_000_000, 1_500_000_000))
            self.assertEqual(
                patch_ropro.content_fingerprint(Path(first)),
                patch_ropro.content_fingerprint(Path(second)),
            )

    def test_replace_once_fails_closed(self):
        with self.assertRaises(RuntimeError):
            patch_ropro.replace_once("same same", "same", "new", "test")

    def test_supported_platform_roots_are_paths(self):
        self.assertTrue(patch_ropro.browser_data_roots())
        self.assertTrue(all(isinstance(path, Path) for path in patch_ropro.browser_data_roots()))

    def test_additional_chromium_browser_roots(self):
        with patch("patch_ropro.platform.system", return_value="Windows"), patch.dict(
            os.environ,
            {"LOCALAPPDATA": "C:/Local", "APPDATA": "C:/Roaming"},
        ):
            windows = "\n".join(map(str, patch_ropro.browser_data_roots()))
        with patch("patch_ropro.platform.system", return_value="Darwin"):
            macos = "\n".join(map(str, patch_ropro.browser_data_roots()))
        with patch("patch_ropro.platform.system", return_value="Linux"), patch.dict(
            os.environ,
            {"XDG_CONFIG_HOME": "/config"},
        ):
            linux = "\n".join(map(str, patch_ropro.browser_data_roots()))
        self.assertIn("Vivaldi", windows)
        self.assertIn("Brave-Origin", windows)
        self.assertIn("Opera GX", windows)
        self.assertIn("Arc", macos)
        self.assertIn("Brave-Origin", macos)
        self.assertIn("Thorium", macos)
        self.assertIn("Brave-Origin", linux)
        self.assertIn("ungoogled-chromium", linux)

    def test_extension_discovery_supports_root_and_named_profiles(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            direct = root / "Extensions" / patch_ropro.EXPECTED_ID / "1.0_0"
            named = root / "Profile 2" / "Extensions" / patch_ropro.EXPECTED_ID / "2.0_0"
            direct.mkdir(parents=True)
            named.mkdir(parents=True)
            self.assertEqual(
                set(patch_ropro.installed_extension_paths(root)),
                {direct.resolve(), named.resolve()},
            )

    def test_extension_discovery_supports_loaded_unpacked_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = root / "Default"
            source = root / "loaded-ropro"
            profile.mkdir()
            source.mkdir()
            preferences = {
                "extensions": {
                    "settings": {
                        patch_ropro.EXPECTED_ID: {"path": str(source)},
                    }
                }
            }
            (profile / "Preferences").write_text(json.dumps(preferences), encoding="utf-8")
            self.assertIn(source.resolve(), patch_ropro.installed_extension_paths(root))

    def test_legacy_bypass_is_detected(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            (source / "js/page").mkdir(parents=True)
            (source / "manifest.json").write_text(
                json.dumps({"key": patch_ropro.EXPECTED_PUBLIC_KEY}),
                encoding="utf-8",
            )
            marker = "const ROPRO_LOCAL_ENTITLEMENT_TEST_MODE = true;"
            (source / "background.js").write_text(marker, encoding="utf-8")
            (source / "js/page/options.js").write_text(marker, encoding="utf-8")
            self.assertTrue(patch_ropro.is_legacy_bypass(source))

    def test_all_presets_are_valid_and_independent(self):
        for name, preset in patch_ropro.SCENARIO_PRESETS.items():
            with self.subTest(name=name):
                patch_ropro.validate_test_config(preset)
        clone = dict(patch_ropro.SCENARIO_PRESETS["max-access"])
        clone["subscription"] = "changed"
        self.assertEqual(patch_ropro.SCENARIO_PRESETS["max-access"]["subscription"], "pro_tier")

    def test_scenario_overrides_are_composable(self):
        args = scenario_args(
            preset="real",
            subscription="ultra_tier",
            restrict_settings="true",
            roblox_premium="false",
            discord_13_plus="true",
            maintenance="all",
            settings="all-off",
        )
        config = patch_ropro.build_test_config(args)
        self.assertEqual(config["subscription"], "ultra_tier")
        self.assertTrue(config["restrict_settings"])
        self.assertFalse(config["roblox_premium"])
        self.assertTrue(config["discord_13_plus"])
        self.assertEqual(config["maintenance"], "all")
        self.assertEqual(config["settings"], "all-off")

    def test_subscription_supports_empty_and_arbitrary_values(self):
        common = dict(
            preset="real",
            restrict_settings=None,
            roblox_premium=None,
            discord_13_plus=None,
            maintenance=None,
            settings=None,
        )
        empty = patch_ropro.build_test_config(scenario_args(subscription="<empty>", **common))
        malformed = patch_ropro.build_test_config(scenario_args(subscription="malformed-tier", **common))
        self.assertEqual(empty["subscription"], "")
        self.assertEqual(malformed["subscription"], "malformed-tier")

    def test_max_access_preset_covers_all_controls(self):
        config = patch_ropro.build_test_config(scenario_args(preset="max-access"))
        self.assertTrue(config["verification"])
        self.assertEqual(config["egg_collection"], "enabled")
        self.assertEqual(config["route_checks"], "allow")
        self.assertEqual(config["sender_validation"], "allow")
        self.assertEqual(config["message_shape_validation"], "allow")
        self.assertEqual(config["url_validation"], "allow-https")
        self.assertEqual(config["api_payload_validation"], "fallback-json")

    def test_individual_setting_overrides_accept_json_scalars(self):
        config = patch_ropro.build_test_config(
            scenario_args(setting=["declineThreshold=100", 'lastOnlineTimezone="UTC"'])
        )
        self.assertEqual(config["setting_overrides"]["declineThreshold"], 100)
        self.assertEqual(config["setting_overrides"]["lastOnlineTimezone"], "UTC")


if __name__ == "__main__":
    unittest.main()
