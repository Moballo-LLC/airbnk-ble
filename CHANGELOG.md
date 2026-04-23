# Changelog

## Unreleased

## 1.0.1 - 2026-04-23

- Fixed the Bluetooth auto-discovery setup dialog so the `Cloud` and `Manual` setup options render correctly instead of showing a blank menu
- Improved Bluetooth discovery naming so newly discovered locks show a more specific lock title during setup
- Normalized local brand assets for current Home Assistant custom-integration packaging and added brand-asset regression tests

## 1.0.0 - 2026-04-23

- Initial standalone `Airbnk BLE` custom integration scaffold
- Local BLE runtime ported from the original private Home Assistant component
- Cloud-assisted bootstrap flow, manual bootstrap flow, diagnostics, tests, and CI scaffolding
- Bluetooth auto-discovery and rediscovery support for connectable Airbnk locks
- Plus-address cloud login compatibility
- Public docs, branding, HACS packaging, and CI validation for first release
