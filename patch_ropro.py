#!/usr/bin/env python3

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import struct
from typing import Optional
import urllib.parse
import urllib.request
import zipfile


EXPECTED_ID = "adbacgifemdbhdkfppmeilbgppmhaobf"
DESCRIPTION = "Patch RoPro client-side controls in place."
STORE_UPDATE_URL = "https://clients2.google.com/service/update2/crx"
EXPECTED_PUBLIC_KEY = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAhGmYsEtXY1/SIpSZINmGpx4ASwBIXSlU"
    "B9a/ngyUg3b2V2rXKo0QZvh/5x//PpgR85gFqFcvQzlK/b74QvyS8A1edMqkxwknmvNLdtBU1a6"
    "gJj6aYyj5DiPAWEUxizMC1F5uZ5o2i59ghAH+7yuT/YK4ggxYwd/1lIkP8oekvAxqJmCWL+rxX"
    "WNGqhSCpID8Mxjcbf3w8o6YefALD2vS/4wtTVHEa0ODm9g6cgEsz/1/GVgErJwYMzmIdhLni1W"
    "EyTNg+gQf66TcOhWYBO4c4tiCC00dlaae25rTQD/BNvRpQx/YGOZ7q4VB/j3gxJxRoP1jNA4N8q"
    "yHDD7FxtYc+QIDAQAB"
)
TEST_CONFIG_FILE = "ropro-local-test.json"
AUDITS_DIR = Path(__file__).resolve().parent / "audits"
MODIFIED_SOURCE_FILES = (
    "manifest.json",
    "background.js",
    "js/page/options.js",
    "js/page/friends.js",
    "js/shared/roproApiAdapter.js",
    "options.html",
)


SCENARIO_PRESETS = {
    "real": {
        "subscription": None,
        "restrict_settings": None,
        "roblox_premium": None,
        "discord_13_plus": None,
        "maintenance": "real",
        "settings": "real",
    },
    "free": {
        "subscription": "free_tier",
        "restrict_settings": False,
        "roblox_premium": True,
        "discord_13_plus": True,
        "maintenance": "none",
        "settings": "all-on",
    },
    "plus": {
        "subscription": "standard_tier",
        "restrict_settings": False,
        "roblox_premium": True,
        "discord_13_plus": True,
        "maintenance": "none",
        "settings": "all-on",
    },
    "rex": {
        "subscription": "pro_tier",
        "restrict_settings": False,
        "roblox_premium": True,
        "discord_13_plus": True,
        "maintenance": "none",
        "settings": "all-on",
    },
    "max-access": {
        "subscription": "pro_tier",
        "restrict_settings": False,
        "roblox_premium": True,
        "discord_13_plus": True,
        "maintenance": "none",
        "settings": "all-on",
        "verification": True,
        "egg_collection": "enabled",
        "free_trial_hours": 24.0,
        "route_checks": "allow",
        "sender_validation": "allow",
        "message_shape_validation": "allow",
        "url_validation": "allow-https",
        "api_payload_validation": "fallback-json",
        "setting_overrides": {},
    },
    "deny-all": {
        "subscription": "free_tier",
        "restrict_settings": True,
        "roblox_premium": False,
        "discord_13_plus": False,
        "maintenance": "all",
        "settings": "all-off",
    },
    "unknown-tier": {
        "subscription": "__unknown_subscription__",
        "restrict_settings": False,
        "roblox_premium": True,
        "discord_13_plus": True,
        "maintenance": "none",
        "settings": "all-on",
    },
}

CLIENT_CONTROL_DEFAULTS = {
    "verification": None,
    "egg_collection": "real",
    "free_trial_hours": None,
    "route_checks": "real",
    "sender_validation": "real",
    "message_shape_validation": "real",
    "url_validation": "real",
    "api_payload_validation": "real",
    "setting_overrides": {},
}
for preset_config in SCENARIO_PRESETS.values():
    for control_name, control_value in CLIENT_CONTROL_DEFAULTS.items():
        preset_config.setdefault(
            control_name,
            dict(control_value) if isinstance(control_value, dict) else control_value,
        )

def javascript_config(config: dict) -> str:
    return json.dumps(config, sort_keys=True, separators=(",", ":"))


def background_edits(config: dict):
    config_json = javascript_config(config)
    return (
    (
        "//RoPro v1.7\n\n",
        f"const ROPRO_LOCAL_TEST_CONFIG = Object.freeze({config_json});\n\n",
    ),
    (
        "async function isCurrentUserVerified() {\n"
        "  var verificationDict = normalizeVerificationDictionary(await getStorage(\"userVerification\"));",
        "async function isCurrentUserVerified() {\n"
        "  if (typeof ROPRO_LOCAL_TEST_CONFIG.verification === \"boolean\") {\n"
        "    return ROPRO_LOCAL_TEST_CONFIG.verification;\n"
        "  }\n"
        "  var verificationDict = normalizeVerificationDictionary(await getStorage(\"userVerification\"));",
    ),
    (
        "async function getSubscription() {\n"
        "  if (subscriptionPromise.length == 0) {",
        "async function getSubscription() {\n"
        "  if (ROPRO_LOCAL_TEST_CONFIG.subscription !== null) {\n"
        "    return ROPRO_LOCAL_TEST_CONFIG.subscription;\n"
        "  }\n"
        "  if (subscriptionPromise.length == 0) {",
    ),
    (
        "async function loadSettingValidityDetail(setting) {\n"
        "  var restrictSettings = await getStorage(\"restrictSettings\");\n"
        "  if (typeof restrictSettings !== \"boolean\") {",
        "async function loadSettingValidityDetail(setting) {\n"
        "  var restrictSettings = await getStorage(\"restrictSettings\");\n"
        "  if (typeof ROPRO_LOCAL_TEST_CONFIG.restrict_settings === \"boolean\") {\n"
        "    restrictSettings = ROPRO_LOCAL_TEST_CONFIG.restrict_settings;\n"
        "  }\n"
        "  if (typeof restrictSettings !== \"boolean\") {",
    ),
    (
        "  if (ROPRO_ROBLOX_PREMIUM_REQUIRED_SETTINGS.has(setting)) {\n"
        "    var premiumStatus = await getRobloxPremiumMembershipStatus();\n"
        "    hasRobloxPremium = premiumStatus.hasPremium === true;\n"
        "    if (!hasRobloxPremium) {",
        "  if (ROPRO_ROBLOX_PREMIUM_REQUIRED_SETTINGS.has(setting)) {\n"
        "    var premiumStatus = await getRobloxPremiumMembershipStatus();\n"
        "    hasRobloxPremium = premiumStatus.hasPremium === true;\n"
        "    if (typeof ROPRO_LOCAL_TEST_CONFIG.roblox_premium === \"boolean\") {\n"
        "      hasRobloxPremium = ROPRO_LOCAL_TEST_CONFIG.roblox_premium;\n"
        "    }\n"
        "    if (!hasRobloxPremium) {",
    ),
    (
        "    if (typeof discordVerified13Plus === \"boolean\" && discordVerified13Plus !== true) {",
        "    if (typeof ROPRO_LOCAL_TEST_CONFIG.discord_13_plus === \"boolean\") {\n"
        "      discordVerified13Plus = ROPRO_LOCAL_TEST_CONFIG.discord_13_plus;\n"
        "    }\n"
        "    if (typeof discordVerified13Plus === \"boolean\" && discordVerified13Plus !== true) {",
    ),
    (
        "  var disabled = false;\n"
        "  if (disabledFeatures?.includes(setting)) {",
        "  var disabled = false;\n"
        "  if (ROPRO_LOCAL_TEST_CONFIG.maintenance === \"all\") {\n"
        "    valid = false;\n"
        "    disabled = true;\n"
        "    setReason(\"disabled_feature\");\n"
        "  } else if (\n"
        "    ROPRO_LOCAL_TEST_CONFIG.maintenance === \"real\" &&\n"
        "    disabledFeatures?.includes(setting)\n"
        "  ) {",
    ),
    (
        "    if (typeof defaultSettings[gate.setting] === \"boolean\") {\n"
        "      settingEnabled =\n"
        "        normalizeBooleanSettingValue(gate.setting, await getRawSettingValue(gate.setting)) === true;\n"
        "    }\n"
        "  }\n\n"
        "  var allowed = settingEnabled && settingValid && tierAllowed;",
        "    if (typeof defaultSettings[gate.setting] === \"boolean\") {\n"
        "      settingEnabled =\n"
        "        normalizeBooleanSettingValue(gate.setting, await getRawSettingValue(gate.setting)) === true;\n"
        "    }\n"
        "    if (ROPRO_LOCAL_TEST_CONFIG.settings === \"all-on\") {\n"
        "      settingEnabled = true;\n"
        "    } else if (ROPRO_LOCAL_TEST_CONFIG.settings === \"all-off\") {\n"
        "      settingEnabled = false;\n"
        "    }\n"
        "  }\n\n"
        "  var allowed = settingEnabled && settingValid && tierAllowed;",
    ),
    (
        "    if (ROPRO_LOCAL_TEST_CONFIG.settings === \"all-on\") {\n"
        "      settingEnabled = true;\n"
        "    } else if (ROPRO_LOCAL_TEST_CONFIG.settings === \"all-off\") {\n"
        "      settingEnabled = false;\n"
        "    }",
        "    if (ROPRO_LOCAL_TEST_CONFIG.settings === \"all-on\") {\n"
        "      settingEnabled = true;\n"
        "    } else if (ROPRO_LOCAL_TEST_CONFIG.settings === \"all-off\") {\n"
        "      settingEnabled = false;\n"
        "    }\n"
        "    if (\n"
        "      Object.prototype.hasOwnProperty.call(\n"
        "        ROPRO_LOCAL_TEST_CONFIG.setting_overrides,\n"
        "        gate.setting\n"
        "      ) &&\n"
        "      typeof ROPRO_LOCAL_TEST_CONFIG.setting_overrides[gate.setting] === \"boolean\"\n"
        "    ) {\n"
        "      settingEnabled = ROPRO_LOCAL_TEST_CONFIG.setting_overrides[gate.setting];\n"
        "    }",
    ),
    (
        "  settingValue = normalizeBooleanSettingValue(setting, settingValue);\n"
        "  if (typeof defaultSettings[setting] === \"boolean\") {",
        "  if (\n"
        "    Object.prototype.hasOwnProperty.call(\n"
        "      ROPRO_LOCAL_TEST_CONFIG.setting_overrides,\n"
        "      setting\n"
        "    )\n"
        "  ) {\n"
        "    settingValue = ROPRO_LOCAL_TEST_CONFIG.setting_overrides[setting];\n"
        "  }\n"
        "  settingValue = normalizeBooleanSettingValue(setting, settingValue);\n"
        "  if (typeof defaultSettings[setting] === \"boolean\") {\n"
        "    if (ROPRO_LOCAL_TEST_CONFIG.settings === \"all-on\") {\n"
        "      settingValue = true;\n"
        "    } else if (ROPRO_LOCAL_TEST_CONFIG.settings === \"all-off\") {\n"
        "      settingValue = false;\n"
        "    }",
    ),
    (
        "  var requestConfig = operation.buildRequest(safePayload);\n"
        "  if (requestConfig == null || typeof requestConfig !== \"object\") {\n"
        "    return null;\n"
        "  }",
        "  var requestConfig = null;\n"
        "  if (ROPRO_LOCAL_TEST_CONFIG.api_payload_validation !== \"deny\") {\n"
        "    requestConfig = operation.buildRequest(safePayload);\n"
        "  }\n"
        "  if (\n"
        "    (requestConfig == null || typeof requestConfig !== \"object\") &&\n"
        "    ROPRO_LOCAL_TEST_CONFIG.api_payload_validation === \"fallback-json\"\n"
        "  ) {\n"
        "    requestConfig =\n"
        "      String(operation.method || \"POST\").toUpperCase() === \"GET\"\n"
        "        ? { query: safePayload }\n"
        "        : { query: null, bodyType: \"json\", body: safePayload };\n"
        "  }\n"
        "  if (requestConfig == null || typeof requestConfig !== \"object\") {\n"
        "    return null;\n"
        "  }",
    ),
    (
        "async function executeRoProApiOperation(operationName, payload) {\n"
        "  if (operationName === \"ropro_get_egg_collection\") {",
        "async function executeRoProApiOperation(operationName, payload) {\n"
        "  if (\n"
        "    operationName === \"ropro_free_trial_time\" &&\n"
        "    typeof ROPRO_LOCAL_TEST_CONFIG.free_trial_hours === \"number\"\n"
        "  ) {\n"
        "    return ROPRO_LOCAL_TEST_CONFIG.free_trial_hours;\n"
        "  }\n"
        "  if (\n"
        "    operationName === \"ropro_get_egg_collection\" &&\n"
        "    ROPRO_LOCAL_TEST_CONFIG.egg_collection !== \"enabled\"\n"
        "  ) {",
    ),
    (
        "function isAllowedBackgroundMessageSender(sender) {\n"
        "  if (sender == null || typeof sender !== \"object\") {",
        "function isAllowedBackgroundMessageSender(sender) {\n"
        "  if (ROPRO_LOCAL_TEST_CONFIG.sender_validation === \"allow\") {\n"
        "    return true;\n"
        "  }\n"
        "  if (ROPRO_LOCAL_TEST_CONFIG.sender_validation === \"deny\") {\n"
        "    return false;\n"
        "  }\n"
        "  if (sender == null || typeof sender !== \"object\") {",
    ),
    (
        "function isRoProUrl(url) {\n"
        "  return (",
        "function isRoProUrl(url) {\n"
        "  if (ROPRO_LOCAL_TEST_CONFIG.url_validation === \"allow-https\") {\n"
        "    return false;\n"
        "  }\n"
        "  return (",
    ),
    (
        "function normalizeMessageUrl(value, action) {\n"
        "  if (typeof value !== \"string\") {",
        "function normalizeMessageUrl(value, action) {\n"
        "  if (ROPRO_LOCAL_TEST_CONFIG.url_validation === \"deny\") {\n"
        "    return null;\n"
        "  }\n"
        "  if (ROPRO_LOCAL_TEST_CONFIG.url_validation === \"allow-https\") {\n"
        "    try {\n"
        "      var testUrl = new URL(String(value));\n"
        "      return testUrl.protocol === \"https:\" ? testUrl.toString() : null;\n"
        "    } catch (e) {\n"
        "      return null;\n"
        "    }\n"
        "  }\n"
        "  if (typeof value !== \"string\") {",
    ),
    (
        "function hasExactMessageKeys(request, allowedKeys, requiredKeys) {\n"
        "  if (request == null || typeof request !== \"object\" || Array.isArray(request)) {",
        "function hasExactMessageKeys(request, allowedKeys, requiredKeys) {\n"
        "  if (ROPRO_LOCAL_TEST_CONFIG.message_shape_validation === \"allow\") {\n"
        "    return true;\n"
        "  }\n"
        "  if (ROPRO_LOCAL_TEST_CONFIG.message_shape_validation === \"deny\") {\n"
        "    return false;\n"
        "  }\n"
        "  if (request == null || typeof request !== \"object\" || Array.isArray(request)) {",
    ),
    )


def options_edits(config: dict):
    config_json = javascript_config(config)
    return (
    (
        "function stripTags(s) {",
        f"const ROPRO_LOCAL_TEST_CONFIG = Object.freeze({config_json})\n\nfunction stripTags(s) {{",
    ),
    (
        "function getSubscription(userID) {\n\treturn new Promise(resolve => {",
        "function getSubscription(userID) {\n"
        "\tif (ROPRO_LOCAL_TEST_CONFIG.subscription !== null) {\n"
        "\t\treturn Promise.resolve(ROPRO_LOCAL_TEST_CONFIG.subscription)\n"
        "\t}\n"
        "\treturn new Promise(resolve => {",
    ),
    (
        "\trestrict = await getStorage(\"restrictSettings\")\n"
        "\tif (restrict == true) {",
        "\trestrict = await getStorage(\"restrictSettings\")\n"
        "\tif (typeof ROPRO_LOCAL_TEST_CONFIG.restrict_settings === \"boolean\") {\n"
        "\t\trestrict = ROPRO_LOCAL_TEST_CONFIG.restrict_settings\n"
        "\t}\n"
        "\tif (restrict == true) {",
    ),
    )


def adapter_edits(config: dict):
    config_json = javascript_config(config)
    return (
        (
            "(function (globalScope) {\n  if (globalScope.roproApiAdapter) {",
            "(function (globalScope) {\n"
            f"  var ROPRO_LOCAL_TEST_CONFIG = Object.freeze({config_json});\n"
            "  if (globalScope.roproApiAdapter) {",
        ),
        (
            "  function getSafeUrl(rawUrl, policy) {\n"
            "    var normalizedPolicy = resolveUrlPolicy(policy);",
            "  function getSafeUrl(rawUrl, policy) {\n"
            "    if (ROPRO_LOCAL_TEST_CONFIG.url_validation === \"deny\") {\n"
            "      return null;\n"
            "    }\n"
            "    if (ROPRO_LOCAL_TEST_CONFIG.url_validation === \"allow-https\") {\n"
            "      try {\n"
            "        var testUrl = new URL(rawUrl, window.location.href);\n"
            "        return testUrl.protocol === \"https:\" ? testUrl.href : null;\n"
            "      } catch (e) {\n"
            "        return null;\n"
            "      }\n"
            "    }\n"
            "    var normalizedPolicy = resolveUrlPolicy(policy);",
        ),
        (
            "  function verifyPath(matches) {\n"
            "    if (",
            "  function verifyPath(matches) {\n"
            "    if (ROPRO_LOCAL_TEST_CONFIG.route_checks === \"allow\") {\n"
            "      return true;\n"
            "    }\n"
            "    if (ROPRO_LOCAL_TEST_CONFIG.route_checks === \"deny\") {\n"
            "      return false;\n"
            "    }\n"
            "    if (",
        ),
    )


def friends_edits(config: dict):
    config_json = javascript_config(config)
    return (
        (
            "var url_matches = [",
            f"const ROPRO_LOCAL_TEST_CONFIG = Object.freeze({config_json});\n\nvar url_matches = [",
        ),
        (
            "function verifyPath(matches) {\n    if (!window.location.host.endsWith(\".roblox.com\")) return false;",
            "function verifyPath(matches) {\n"
            "    if (ROPRO_LOCAL_TEST_CONFIG.route_checks === \"allow\") return true;\n"
            "    if (ROPRO_LOCAL_TEST_CONFIG.route_checks === \"deny\") return false;\n"
            "    if (!window.location.host.endsWith(\".roblox.com\")) return false;",
        ),
    )


def parse_nullable_boolean(value: Optional[str], fallback):
    if value is None:
        return fallback
    if value == "real":
        return None
    return value == "true"


def build_test_config(args) -> dict:
    config = dict(SCENARIO_PRESETS[args.preset])
    if args.subscription is not None:
        if args.subscription == "real":
            config["subscription"] = None
        elif args.subscription == "<empty>":
            config["subscription"] = ""
        else:
            config["subscription"] = args.subscription
    config["restrict_settings"] = parse_nullable_boolean(
        args.restrict_settings, config["restrict_settings"]
    )
    config["roblox_premium"] = parse_nullable_boolean(
        args.roblox_premium, config["roblox_premium"]
    )
    config["discord_13_plus"] = parse_nullable_boolean(
        args.discord_13_plus, config["discord_13_plus"]
    )
    if args.maintenance is not None:
        config["maintenance"] = args.maintenance
    if args.settings is not None:
        config["settings"] = args.settings
    config["verification"] = parse_nullable_boolean(
        args.verification, config["verification"]
    )
    if args.egg_collection is not None:
        config["egg_collection"] = args.egg_collection
    if args.free_trial_hours is not None:
        try:
            config["free_trial_hours"] = (
                None if args.free_trial_hours == "real" else float(args.free_trial_hours)
            )
        except ValueError as error:
            raise SystemExit("--free-trial-hours must be 'real' or a number") from error
    for argument_name in (
        "route_checks",
        "sender_validation",
        "message_shape_validation",
        "url_validation",
        "api_payload_validation",
    ):
        argument_value = getattr(args, argument_name)
        if argument_value is not None:
            config[argument_name] = argument_value
    config["setting_overrides"] = dict(config["setting_overrides"])
    for setting_override in args.setting or []:
        if "=" not in setting_override:
            raise SystemExit("--setting must use NAME=JSON syntax")
        setting_name, raw_value = setting_override.split("=", 1)
        if not setting_name or not setting_name.replace("_", "").isalnum():
            raise SystemExit(f"Invalid setting name: {setting_name}")
        try:
            setting_value = json.loads(raw_value)
        except json.JSONDecodeError as error:
            raise SystemExit(f"Invalid JSON for --setting {setting_name}: {error}") from error
        if isinstance(setting_value, (dict, list)):
            raise SystemExit("--setting values must be JSON scalars")
        config["setting_overrides"][setting_name] = setting_value
    validate_test_config(config)
    return config


def validate_test_config(config: dict) -> None:
    expected_keys = {
        "subscription",
        "restrict_settings",
        "roblox_premium",
        "discord_13_plus",
        "maintenance",
        "settings",
        "verification",
        "egg_collection",
        "free_trial_hours",
        "route_checks",
        "sender_validation",
        "message_shape_validation",
        "url_validation",
        "api_payload_validation",
        "setting_overrides",
    }
    if set(config) != expected_keys:
        raise SystemExit("Invalid test configuration keys")
    if config["subscription"] is not None and not isinstance(config["subscription"], str):
        raise SystemExit("subscription must be a string or null")
    for key in ("restrict_settings", "roblox_premium", "discord_13_plus"):
        if config[key] is not None and not isinstance(config[key], bool):
            raise SystemExit(f"{key} must be true, false, or null")
    if config["maintenance"] not in ("real", "none", "all"):
        raise SystemExit("maintenance must be real, none, or all")
    if config["settings"] not in ("real", "all-on", "all-off"):
        raise SystemExit("settings must be real, all-on, or all-off")
    if config["verification"] is not None and not isinstance(config["verification"], bool):
        raise SystemExit("verification must be true, false, or null")
    if config["egg_collection"] not in ("real", "enabled", "disabled"):
        raise SystemExit("egg_collection must be real, enabled, or disabled")
    if config["free_trial_hours"] is not None:
        if not isinstance(config["free_trial_hours"], (int, float)):
            raise SystemExit("free_trial_hours must be numeric or null")
        if not -1 <= config["free_trial_hours"] <= 8760:
            raise SystemExit("free_trial_hours must be between -1 and 8760")
    enum_controls = {
        "route_checks": ("real", "allow", "deny"),
        "sender_validation": ("real", "allow", "deny"),
        "message_shape_validation": ("real", "allow", "deny"),
        "url_validation": ("real", "allow-https", "deny"),
        "api_payload_validation": ("real", "fallback-json", "deny"),
    }
    for key, choices in enum_controls.items():
        if config[key] not in choices:
            raise SystemExit(f"{key} must be one of: {', '.join(choices)}")
    if not isinstance(config["setting_overrides"], dict) or len(config["setting_overrides"]) > 200:
        raise SystemExit("setting_overrides must be an object with at most 200 entries")
    for key, value in config["setting_overrides"].items():
        if not isinstance(key, str) or not key or isinstance(value, (dict, list)):
            raise SystemExit("setting_overrides must contain named JSON scalar values")


def add_scenario_arguments(parser) -> None:
    parser.add_argument(
        "--preset",
        choices=tuple(SCENARIO_PRESETS),
        default="max-access",
        help="starting scenario (default: max-access)",
    )
    parser.add_argument(
        "--subscription",
        metavar="VALUE",
        help="literal tier/alias to return; use real or <empty> for special cases",
    )
    parser.add_argument(
        "--restrict-settings",
        choices=("real", "true", "false"),
        help="override age/restricted-settings state",
    )
    parser.add_argument(
        "--roblox-premium",
        choices=("real", "true", "false"),
        help="override Roblox Premium membership state",
    )
    parser.add_argument(
        "--discord-13-plus",
        choices=("real", "true", "false"),
        help="override the Discord 13+ policy input",
    )
    parser.add_argument(
        "--maintenance",
        choices=("real", "none", "all"),
        help="use the real disabled-feature list, disable none, or disable all",
    )
    parser.add_argument(
        "--settings",
        choices=("real", "all-on", "all-off"),
        help="use stored setting values or force all Boolean settings on/off",
    )
    parser.add_argument(
        "--verification",
        choices=("real", "true", "false"),
        help="override the local verification result",
    )
    parser.add_argument(
        "--egg-collection",
        choices=("real", "enabled", "disabled"),
        help="retain, remove, or force the local Egg Collection kill switch",
    )
    parser.add_argument(
        "--free-trial-hours",
        metavar="REAL_OR_NUMBER",
        help="override the locally displayed free-trial time (-1 through 8760)",
    )
    parser.add_argument(
        "--route-checks",
        choices=("real", "allow", "deny"),
        help="retain or force content-script route checks",
    )
    parser.add_argument(
        "--sender-validation",
        choices=("real", "allow", "deny"),
        help="retain or force background message-sender validation",
    )
    parser.add_argument(
        "--message-shape-validation",
        choices=("real", "allow", "deny"),
        help="retain or force exact runtime-message shape checks",
    )
    parser.add_argument(
        "--url-validation",
        choices=("real", "allow-https", "deny"),
        help="retain host/path policies, allow any HTTPS host, or deny URLs",
    )
    parser.add_argument(
        "--api-payload-validation",
        choices=("real", "fallback-json", "deny"),
        help="retain builders, serialize rejected payloads for registered operations, or deny all",
    )
    parser.add_argument(
        "--setting",
        action="append",
        metavar="NAME=JSON",
        help="override any individual setting; repeat as needed",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_digest(path: Path, relative: str) -> str:
    if relative != "manifest.json":
        return sha256(path)
    document = json.loads(path.read_text(encoding="utf-8"))
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def extension_id(manifest: dict) -> str:
    public_key = base64.b64decode(manifest["key"])
    prefix = hashlib.sha256(public_key).digest()[:16].hex()
    return "".join(chr(ord("a") + int(nibble, 16)) for nibble in prefix)


def web_store_download_url(extension_identifier: str) -> str:
    query = urllib.parse.urlencode(
        {
            "response": "redirect",
            "prodversion": "131.0.0.0",
            "acceptformat": "crx2,crx3",
            "x": f"id={extension_identifier}&installsource=ondemand&uc",
        }
    )
    return f"{STORE_UPDATE_URL}?{query}"


def download_package(extension_identifier: str = EXPECTED_ID) -> bytes:
    request = urllib.request.Request(
        web_store_download_url(extension_identifier),
        headers={"User-Agent": "Mozilla/5.0 ropro-bypass-updater/1.0"},
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        data = response.read(100 * 1024 * 1024 + 1)
    if len(data) > 100 * 1024 * 1024:
        raise RuntimeError("Downloaded package exceeds 100 MiB")
    return data


def zip_payload(package: bytes) -> bytes:
    if package.startswith(b"PK\x03\x04"):
        return package
    if not package.startswith(b"Cr24") or len(package) < 12:
        raise RuntimeError("Store response is not a ZIP, CRX2, or CRX3 package")
    version = struct.unpack_from("<I", package, 4)[0]
    if version == 2:
        if len(package) < 16:
            raise RuntimeError("Truncated CRX2 header")
        public_key_size, signature_size = struct.unpack_from("<II", package, 8)
        offset = 16 + public_key_size + signature_size
    elif version == 3:
        header_size = struct.unpack_from("<I", package, 8)[0]
        offset = 12 + header_size
    else:
        raise RuntimeError(f"Unsupported CRX version: {version}")
    payload = package[offset:]
    if not payload.startswith(b"PK\x03\x04"):
        raise RuntimeError("CRX ZIP payload is missing or truncated")
    return payload


def extract_package(package: bytes, destination: Path) -> None:
    with zipfile.ZipFile(io.BytesIO(zip_payload(package))) as archive:
        destination_root = destination.resolve()
        for info in archive.infolist():
            target = (destination / info.filename).resolve()
            try:
                target.relative_to(destination_root)
            except ValueError as error:
                raise RuntimeError(f"Unsafe archive path: {info.filename}") from error
        archive.extractall(destination)


def normalize_package_manifest(source: Path) -> dict:
    manifest_path = source / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if "key" not in manifest:
        manifest["key"] = EXPECTED_PUBLIC_KEY
        with manifest_path.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    if extension_id(manifest) != EXPECTED_ID:
        raise RuntimeError("Downloaded package has an unexpected extension ID")
    return manifest


def load_audited_builds() -> dict:
    builds = {}
    if not AUDITS_DIR.is_dir():
        return builds
    for path in sorted(AUDITS_DIR.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema") != 1:
            raise SystemExit(f"Unsupported audit profile schema: {path}")
        version = document.get("version")
        hashes = document.get("hashes")
        if (
            document.get("extension_id") != EXPECTED_ID
            or not isinstance(version, str)
            or not version
            or not isinstance(hashes, dict)
            or set(hashes) != set(MODIFIED_SOURCE_FILES)
        ):
            raise SystemExit(f"Invalid audit profile: {path}")
        if version in builds:
            raise SystemExit(f"Duplicate audit profile for version {version}")
        builds[version] = document
    return builds


def validate_anchor_compatibility(source: Path) -> None:
    config = dict(SCENARIO_PRESETS["real"])
    edit_groups = (
        (source / "background.js", background_edits(config), "background.js"),
        (source / "js/page/options.js", options_edits(config), "options.js"),
        (source / "js/shared/roproApiAdapter.js", adapter_edits(config), "roproApiAdapter.js"),
        (source / "js/page/friends.js", friends_edits(config), "friends.js"),
    )
    for path, edits, label in edit_groups:
        if not path.is_file():
            raise RuntimeError(f"Missing required compatible source file: {path}")
        text_value = path.read_text(encoding="utf-8")
        for index, (old, new) in enumerate(edits, start=1):
            text_value = replace_once(text_value, old, new, f"{label} edit {index}")


def validate_pristine(source: Path, version_policy: str = "audited") -> dict:
    if version_policy not in ("audited", "compatible"):
        raise SystemExit("version policy must be audited or compatible")
    manifest_path = source / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"Missing manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual_id = extension_id(manifest)
    if actual_id != EXPECTED_ID:
        raise SystemExit(f"Unsupported extension ID: {actual_id}")
    version = manifest.get("version")
    if not isinstance(version, str) or not version:
        raise SystemExit("Source manifest has no valid version")
    builds = load_audited_builds()
    profile = builds.get(version)
    if profile is None and version_policy == "audited":
        supported = ", ".join(sorted(builds)) or "none"
        raise SystemExit(f"RoPro {version} is not audited; supported versions: {supported}")
    expected_hashes = profile["hashes"] if profile is not None else {}
    mismatches = []
    actual_hashes = {}
    for relative in MODIFIED_SOURCE_FILES:
        path = source / relative
        actual = source_digest(path, relative) if path.is_file() else "missing"
        actual_hashes[relative] = actual
        expected = expected_hashes.get(relative)
        if expected is not None and actual != expected:
            mismatches.append(f"{relative}: expected {expected}, got {actual}")
        if expected is None and actual == "missing":
            mismatches.append(f"{relative}: missing")
    if mismatches:
        raise SystemExit(f"Source does not match RoPro {version}:\n" + "\n".join(mismatches))
    if profile is None:
        validate_anchor_compatibility(source)
    return {
        "extension_id": actual_id,
        "version": version,
        "audited": profile is not None,
        "source_hashes": actual_hashes,
    }


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one {label} anchor; found {count}")
    return text.replace(old, new, 1)


def render_edits(path: Path, edits, label: str) -> str:
    text = path.read_text(encoding="utf-8")
    for index, (old, new) in enumerate(edits, start=1):
        text = replace_once(text, old, new, f"{label} edit {index}")
    return text


def content_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(bytes.fromhex(sha256(path)))
    return digest.hexdigest()


def read_test_document(source: Path) -> dict:
    config_path = source / TEST_CONFIG_FILE
    if not config_path.is_file():
        raise SystemExit(f"Missing test configuration: {config_path}")
    document = json.loads(config_path.read_text(encoding="utf-8"))
    if (
        document.get("schema") != 2
        or not isinstance(document.get("config"), dict)
        or not isinstance(document.get("source"), dict)
    ):
        raise SystemExit("Unsupported test configuration schema")
    config = document["config"]
    validate_test_config(config)
    source = document["source"]
    if (
        source.get("extension_id") != EXPECTED_ID
        or not isinstance(source.get("version"), str)
        or not isinstance(source.get("audited"), bool)
        or not isinstance(source.get("source_hashes"), dict)
    ):
        raise SystemExit("Invalid source metadata in test configuration")
    return document


def verify_patched(source: Path, expected_config: Optional[dict] = None, quiet: bool = False) -> str:
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    if extension_id(manifest) != EXPECTED_ID or not isinstance(manifest.get("version"), str):
        raise SystemExit("Patched manifest identity/version is incorrect")
    document = read_test_document(source)
    config = document["config"]
    source_metadata = document["source"]
    if source_metadata["version"] != manifest["version"]:
        raise SystemExit("Patched manifest does not match recorded source version")
    if source_metadata["audited"]:
        profile = load_audited_builds().get(source_metadata["version"])
        if profile is None:
            raise SystemExit("Patched source refers to an unavailable audit profile")
        if source_metadata["source_hashes"] != profile["hashes"]:
            raise SystemExit("Patched source hashes do not match its audit profile")
    if expected_config is not None and config != expected_config:
        raise SystemExit("RoPro is already patched with a different scenario; restore the original files first")
    config_marker = f"const ROPRO_LOCAL_TEST_CONFIG = Object.freeze({javascript_config(config)})"
    adapter_config_marker = f"var ROPRO_LOCAL_TEST_CONFIG = Object.freeze({javascript_config(config)})"
    background = (source / "background.js").read_text(encoding="utf-8")
    options = (source / "js/page/options.js").read_text(encoding="utf-8")
    adapter = (source / "js/shared/roproApiAdapter.js").read_text(encoding="utf-8")
    friends = (source / "js/page/friends.js").read_text(encoding="utf-8")
    required = {
        "background scenario": config_marker + ";" in background,
        "options scenario": config_marker in options,
        "adapter scenario": adapter_config_marker in adapter,
        "friends scenario": config_marker + ";" in friends,
        "subscription override": "return ROPRO_LOCAL_TEST_CONFIG.subscription;" in background,
        "options subscription override": "Promise.resolve(ROPRO_LOCAL_TEST_CONFIG.subscription)" in options,
        "restriction override": "restrict_settings" in background and "restrict_settings" in options,
        "Roblox Premium override": "ROPRO_LOCAL_TEST_CONFIG.roblox_premium" in background,
        "Discord policy override": "ROPRO_LOCAL_TEST_CONFIG.discord_13_plus" in background,
        "maintenance override": "ROPRO_LOCAL_TEST_CONFIG.maintenance" in background,
        "setting-state override": "ROPRO_LOCAL_TEST_CONFIG.settings" in background,
        "individual setting overrides": "ROPRO_LOCAL_TEST_CONFIG.setting_overrides" in background,
        "verification override": "ROPRO_LOCAL_TEST_CONFIG.verification" in background,
        "Egg Collection override": "ROPRO_LOCAL_TEST_CONFIG.egg_collection" in background,
        "free-trial override": "ROPRO_LOCAL_TEST_CONFIG.free_trial_hours" in background,
        "route override": "ROPRO_LOCAL_TEST_CONFIG.route_checks" in adapter,
        "standalone friends route override": "ROPRO_LOCAL_TEST_CONFIG.route_checks" in friends,
        "sender validation override": "ROPRO_LOCAL_TEST_CONFIG.sender_validation" in background,
        "message shape override": "ROPRO_LOCAL_TEST_CONFIG.message_shape_validation" in background,
        "background URL override": "ROPRO_LOCAL_TEST_CONFIG.url_validation" in background,
        "adapter URL override": "ROPRO_LOCAL_TEST_CONFIG.url_validation" in adapter,
        "API payload override": "ROPRO_LOCAL_TEST_CONFIG.api_payload_validation" in background,
        "no API blocklist": "ROPRO_LOCAL_TEST_ALLOW_AUTHENTICATED_APIS" not in background,
        "no settings blocklist": "ROPRO_LOCAL_TEST_BLOCKED_SETTINGS" not in background,
        "no PoC banner": "roproLocalSecurityTestBanner" not in (source / "options.html").read_text(encoding="utf-8"),
    }
    failures = [name for name, passed in required.items() if not passed]
    if failures:
        raise SystemExit("Verification failed: " + ", ".join(failures))
    fingerprint = content_fingerprint(source)
    if not quiet:
        print(f"Verified patched RoPro: {source}")
        print(
            f"Source version: {source_metadata['version']} "
            f"({'audited' if source_metadata['audited'] else 'anchor-compatible'})"
        )
        print(f"Scenario: {json.dumps(config, sort_keys=True)}")
        print(f"Content fingerprint: {fingerprint}")
    return fingerprint


def patch_in_place(
    source: Path,
    config: dict,
    version_policy: str = "compatible",
) -> None:
    source = source.resolve()
    config_path = source / TEST_CONFIG_FILE
    if config_path.is_file():
        verify_patched(source, config)
        print(f"Already patched: {source}")
        return
    source_metadata = validate_pristine(source, version_policy)
    edit_groups = (
        (source / "background.js", background_edits(config), "background.js"),
        (source / "js/page/options.js", options_edits(config), "options.js"),
        (source / "js/shared/roproApiAdapter.js", adapter_edits(config), "roproApiAdapter.js"),
        (source / "js/page/friends.js", friends_edits(config), "friends.js"),
    )
    originals = {path: path.read_bytes() for path, _, _ in edit_groups}
    rendered = {
        path: render_edits(path, edits, label)
        for path, edits, label in edit_groups
    }
    try:
        for path, text_value in rendered.items():
            with path.open("w", encoding="utf-8", newline="\n") as stream:
                stream.write(text_value)
        with config_path.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(
                json.dumps(
                    {"schema": 2, "source": source_metadata, "config": config},
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )
        verify_patched(source, config)
    except BaseException:
        for path, original_bytes in originals.items():
            path.write_bytes(original_bytes)
        config_path.unlink(missing_ok=True)
        raise
    print(f"Patched in place: {source}")


def browser_data_roots() -> list[Path]:
    home = Path.home()
    system = platform.system()
    if system == "Windows":
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local"))
        roaming = Path(os.environ.get("APPDATA", home / "AppData/Roaming"))
        return [
            local / "BraveSoftware/Brave-Browser/User Data",
            local / "BraveSoftware/Brave-Origin/User Data",
            local / "Google/Chrome/User Data",
            local / "Chromium/User Data",
            local / "Microsoft/Edge/User Data",
            local / "Vivaldi/User Data",
            local / "TheBrowserCompany/Arc/User Data",
            local / "Thorium/User Data",
            roaming / "Opera Software/Opera Stable",
            roaming / "Opera Software/Opera GX Stable",
        ]
    if system == "Darwin":
        support = home / "Library/Application Support"
        return [
            support / "BraveSoftware/Brave-Browser",
            support / "BraveSoftware/Brave-Origin",
            support / "Google/Chrome",
            support / "Chromium",
            support / "Microsoft Edge",
            support / "Vivaldi",
            support / "com.operasoftware.Opera",
            support / "com.operasoftware.OperaGX",
            support / "Arc/User Data",
            support / "Thorium",
        ]
    config = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
    return [
        config / "BraveSoftware/Brave-Browser",
        config / "BraveSoftware/Brave-Origin",
        config / "google-chrome",
        config / "chromium",
        config / "microsoft-edge",
        config / "vivaldi",
        config / "opera",
        config / "opera-gx",
        config / "thorium",
        config / "ungoogled-chromium",
    ]


def installed_extension_paths(root: Path) -> list[Path]:
    patterns = (
        f"Extensions/{EXPECTED_ID}/*_*",
        f"*/Extensions/{EXPECTED_ID}/*_*",
    )
    candidates = {path.resolve() for pattern in patterns for path in root.glob(pattern)}
    preference_files = [root / "Preferences", *root.glob("*/Preferences")]
    for preferences in preference_files:
        if not preferences.is_file():
            continue
        try:
            document = json.loads(preferences.read_text(encoding="utf-8"))
            configured_path = document["extensions"]["settings"][EXPECTED_ID]["path"]
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError):
            continue
        if not isinstance(configured_path, str) or not configured_path:
            continue
        candidate = Path(configured_path).expanduser()
        if not candidate.is_absolute():
            candidate = preferences.parent / candidate
        if candidate.is_dir():
            candidates.add(candidate.resolve())
    return sorted(
        candidates,
        key=lambda item: str(item).lower(),
    )


def is_legacy_bypass(source: Path) -> bool:
    try:
        manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
        if extension_id(manifest) != EXPECTED_ID:
            return False
        background = (source / "background.js").read_text(encoding="utf-8")
        options = (source / "js/page/options.js").read_text(encoding="utf-8")
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, ValueError):
        return False
    marker = "ROPRO_LOCAL_ENTITLEMENT_TEST_MODE = true"
    return marker in background and marker in options


def validate_patchable(source: Path, version_policy: str = "compatible") -> None:
    if (source / TEST_CONFIG_FILE).is_file():
        verify_patched(source, quiet=True)
    elif is_legacy_bypass(source):
        return
    else:
        validate_pristine(source, version_policy)


def discover_sources(version_policy: str = "compatible") -> list[Path]:
    candidates = []
    explicit_environment = os.environ.get("ROPRO_SOURCE")
    local_candidates = []
    for root in (Path.cwd(), Path(__file__).resolve().parent):
        local_candidates.extend(root.glob("*_*"))
    for source_parent in (Path.cwd() / "source", Path(__file__).resolve().parent / "source"):
        if source_parent.is_dir():
            local_candidates.extend(source_parent.glob("*_*"))
    if explicit_environment:
        local_candidates.insert(0, Path(explicit_environment).expanduser())
    for path in local_candidates:
        try:
            validate_patchable(path, version_policy)
        except (SystemExit, RuntimeError, OSError, ValueError, KeyError):
            continue
        candidates.append(path.resolve())
    for root in browser_data_roots():
        if not root.is_dir():
            continue
        for path in installed_extension_paths(root):
            try:
                validate_patchable(path, version_policy)
            except (SystemExit, RuntimeError, OSError, ValueError, KeyError):
                continue
            candidates.append(path.resolve())
    return sorted(set(candidates), key=lambda item: str(item).lower())


def choose_source(explicit: Optional[Path], version_policy: str = "compatible") -> Path:
    if explicit is not None:
        validate_patchable(explicit.resolve(), version_policy)
        return explicit.resolve()
    sources = discover_sources(version_policy)
    if not sources:
        raise SystemExit("No compatible pristine RoPro installation was found; pass --source PATH")
    if len(sources) > 1:
        choices = "\n".join(f"  {path}" for path in sources)
        raise SystemExit(f"Multiple compatible sources found; pass --source PATH:\n{choices}")
    return sources[0]


def quickstart(
    source: Optional[Path],
    config: dict,
    version_policy: str,
) -> None:
    selected = choose_source(source, version_policy)
    if is_legacy_bypass(selected):
        print(f"Already bypassed by a legacy build: {selected}")
        return
    patch_in_place(
        selected,
        config,
        version_policy,
    )


def reject_symlinks(root: Path) -> None:
    if root.is_symlink():
        raise SystemExit(f"Refusing to modify a symlinked extension directory: {root}")
    for path in root.rglob("*"):
        if path.is_symlink():
            raise SystemExit(f"Refusing to modify an extension containing a symlink: {path}")


def copy_directory_contents(
    source: Path,
    destination: Path,
    excluded: Optional[set[Path]] = None,
) -> None:
    excluded = excluded or set()
    for child in source.iterdir():
        if child in excluded:
            continue
        if child.is_symlink():
            raise SystemExit(f"Refusing to copy a symlink: {child}")
        target = destination / child.name
        if child.is_dir():
            shutil.copytree(child, target)
        elif child.is_file():
            shutil.copy2(child, target)
        else:
            raise SystemExit(f"Refusing to copy an unsupported filesystem entry: {child}")


def clear_directory_contents(root: Path, preserved: Optional[set[Path]] = None) -> None:
    preserved = preserved or set()
    for child in root.iterdir():
        if child in preserved:
            continue
        if child.is_symlink() or child.is_file():
            child.unlink()
        elif child.is_dir():
            shutil.rmtree(child)
        else:
            raise SystemExit(f"Refusing to remove an unsupported filesystem entry: {child}")


def update_in_place(source: Optional[Path], version_policy: str = "compatible") -> None:
    installed = choose_source(source, version_policy)
    reject_symlinks(installed)
    if not (installed / TEST_CONFIG_FILE).is_file():
        print(f"Not patched: {installed}")
        return
    document = read_test_document(installed)
    config = document["config"]
    previous_version = document["source"]["version"]
    verify_patched(installed, config, quiet=True)

    package = download_package()
    workspace = installed / f".ropro-bypass-update-{secrets.token_hex(6)}"
    candidate_root = workspace / "candidate"
    backup_root = workspace / "backup"
    candidate_root.mkdir(parents=True)
    backup_root.mkdir()
    replacement_started = False
    try:
        extract_package(package, candidate_root)
        manifest = normalize_package_manifest(candidate_root)
        candidate = validate_pristine(candidate_root, version_policy)
        print(
            f"Upstream RoPro {manifest['version']} is supported "
            f"({'audited' if candidate['audited'] else 'anchor-compatible'})"
        )
        patch_in_place(candidate_root, config, version_policy)
        verify_patched(candidate_root, config, quiet=True)

        copy_directory_contents(installed, backup_root, {workspace})
        replacement_started = True
        clear_directory_contents(installed, {workspace})
        copy_directory_contents(candidate_root, installed)
        verify_patched(installed, config, quiet=True)
    except BaseException:
        if replacement_started:
            clear_directory_contents(installed, {workspace})
            copy_directory_contents(backup_root, installed)
            verify_patched(installed, config, quiet=True)
        raise
    finally:
        if workspace.exists():
            shutil.rmtree(workspace)
    print(f"Replaced patched RoPro {previous_version} with {manifest['version']}: {installed}")


def main() -> None:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    subparsers = parser.add_subparsers(dest="command", required=True)
    apply_parser = subparsers.add_parser("apply", help="patch a specified RoPro directory in place")
    apply_parser.add_argument("source", type=Path)
    apply_parser.add_argument(
        "--version-policy",
        choices=("audited", "compatible"),
        default="compatible",
        help="require a stored hash profile or allow exact-anchor-compatible versions",
    )
    add_scenario_arguments(apply_parser)
    verify_parser = subparsers.add_parser("verify", help="verify a patched RoPro directory")
    verify_parser.add_argument("source", type=Path)
    discover_parser = subparsers.add_parser("discover", help="find compatible installed RoPro sources")
    discover_parser.add_argument(
        "--version-policy",
        choices=("audited", "compatible"),
        default="compatible",
    )
    subparsers.add_parser("scenarios", help="print presets and spoofable client inputs")
    update_parser = subparsers.add_parser("update", help="replace patched RoPro with the latest supported release")
    update_parser.add_argument("--source", type=Path)
    update_parser.add_argument(
        "--version-policy",
        choices=("audited", "compatible"),
        default="compatible",
        help="require a stored hash profile or allow exact-anchor-compatible versions",
    )
    quick_parser = subparsers.add_parser("quickstart", help="discover and patch RoPro in place")
    quick_parser.add_argument("--source", type=Path)
    quick_parser.add_argument(
        "--version-policy",
        choices=("audited", "compatible"),
        default="compatible",
        help="require a stored hash profile or allow exact-anchor-compatible versions",
    )
    add_scenario_arguments(quick_parser)
    args = parser.parse_args()
    if args.command == "apply":
        patch_in_place(
            args.source,
            build_test_config(args),
            args.version_policy,
        )
    elif args.command == "verify":
        verify_patched(args.source.resolve())
    elif args.command == "discover":
        sources = discover_sources(args.version_policy)
        if not sources:
            raise SystemExit("No compatible pristine RoPro installation found")
        print("\n".join(str(path) for path in sources))
    elif args.command == "scenarios":
        print(json.dumps(SCENARIO_PRESETS, indent=2, sort_keys=True))
    elif args.command == "update":
        update_in_place(args.source, args.version_policy)
    else:
        quickstart(
            args.source,
            build_test_config(args),
            args.version_policy,
        )


if __name__ == "__main__":
    main()
