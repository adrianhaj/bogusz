# Mode G: UI

1. **Choose the target.** Use the UI dev server from the profile (start it in the background) or a URL the user gave in this request. A shared or deployed environment follows the Mode C rules. Credentials come only from environment variables the profile names; never type or print them. If you started a dev server, stop it when the checks are done.
2. **Hand the flow, base URL, a slug and the profile path to `bogusz:blazej-ui`.** It runs Playwright, preferring the project's existing specs, saves screenshots under `~/.bogusz/ui/<slug>/`, and returns per-step results with console errors, failed requests and a Playwright trace for each failed step. To compare a change with its base, pass two base URLs labelled before and after; it runs the same steps against both.
3. **Interactive checks.** If the user asks for their own browser (for example the Claude in Chrome extension) or the built-in browser, or the flow needs their logged-in session, drive those browser tools yourself instead: take screenshots, read the console and network, and never type passwords.
4. **Check its claims.** Open the key screenshots (Read the PNG) before you report a visual result.
5. **Report it.** Use the UI section of the test report, with screenshot paths. If a failure is a real bug, Mode F turns it into an issue and attaches the screenshots the user approved.
