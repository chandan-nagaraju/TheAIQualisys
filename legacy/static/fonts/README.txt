Place Quali_1 font files here for the FIR report:
- Quali_1.woff2 (preferred)
- Quali_1.woff
- Quali_1.ttf (supported; used if woff2/woff not present)

The report will use this font for Actual Measured Values and Remarks.

For the font to show on all computers (including when accessed via ngrok or another host),
the app uses absolute URLs so the font is always loaded from the same server that served
the page. Ensure these font files exist in this folder on every deployment/server.
