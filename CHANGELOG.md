# Changelog

Anzen changes

## v1.0.1 - 2026-10-11

### Fixed
- `/configure`: the Finish button was disabled on the last page, now fixed.
- `/configure` now shows previously saved settings.
- Saving failures are now reported.
- Failing to log to a channel in one server no longer stops notifications to the other servers.

### Security
- Running `/configure` now requires having the Manage Server permission, only works in servers, and the panel is shown to everyone but editable only by the admin who opened it.
- Postgres no longer reachable from the network.

### Added
- Changelog
