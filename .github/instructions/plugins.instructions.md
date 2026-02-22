# Plugin Development Instructions

Apply to files under src/plugins/.

- Every plugin must inherit from plugins.base.BasePlugin.
- Implement required methods: register(), handle_message().
- Keep plugin code isolated — no direct DB access unless via core interface.
- Make plugins easy to install (pip-installable in future).
- Add clear docstrings explaining how to extend.