---
name: md-to-docx
description: 'Export Markdown files to Microsoft Word (.docx) with headings, lists, tables, code, links and embedded images preserved - use whenever the user wants to turn a .md file (README, report, assignment write-up, notes) into a Word document, a .docx, or something they can upload to Google Docs / Drive, even if they just say "export to Word".'
---

# Markdown → Word (.docx) export

Use the bundled script `scripts/md2docx.py` (in this skill's folder). It uses only the standard library and picks the best converter available:

1. **pandoc**, if installed. This gives the highest fidelity.
2. Otherwise, a built-in Markdown → HTML step, then one of:
   - **macOS `textutil`** (built in), or
   - **LibreOffice `soffice --headless`**.

   textutil drops images when it writes `.docx`, so the script then embeds local PNG/JPEG images into the `.docx` package itself.

## Workflow

1. **Identify the input and output.**
   - Default output: the same path with a `.docx` extension.
   - Ask before overwriting an existing `.docx`.
   - Don't write the output into a git-tracked folder unless the user wants it committed.
2. **Run the converter** from any directory. Relative image paths are resolved against the Markdown file's folder.
   ```bash
   python3 <skill-dir>/scripts/md2docx.py path/to/FILE.md [path/to/OUT.docx] [--font-size 11] [--heading-size 16]
   ```
   - Body text defaults to 11 pt and all headings to 16 pt; inline and block code use the body size minus 1.5 pt. Change these with the flags if the user asks for other sizes.
   - With pandoc, these flags are ignored; use `--reference-doc` instead.
   - The script prints which engine it used and warns about any image it couldn't embed (missing, remote URL, or not PNG/JPEG).
3. **Verify the result.** Don't just trust the exit code.
   - Check that the text is readable: `textutil -convert txt OUT.docx -output /tmp/check.txt` (macOS), or `unzip -p OUT.docx word/document.xml | head -c 500`.
   - Check that the images were embedded: `unzip -l OUT.docx | grep media` should list one file per image.
   - On macOS, render a preview with `qlmanage -t -s 1000 -o /tmp/preview OUT.docx` and view the PNG.
4. **Report back** with the output path, the engine used, the number of embedded images, and any warnings. If there were warnings, suggest fixes: download remote images locally, convert GIF/SVG to PNG, or install pandoc.

## Supported Markdown in the fallback path

- Headings (`#`–`######`)
- Paragraphs, **bold**, *italic*, `inline code`
- Fenced code blocks
- Links, images, and nested bullet or numbered lists
- Pipe tables
- Blockquotes and horizontal rules

YAML front matter is skipped.

These are not supported in the fallback: footnotes, task-list checkboxes, HTML blocks, math, and Word styles such as a table of contents. If the document needs any of them, recommend `brew install pandoc` (or the platform equivalent). With pandoc, the user can also add `--reference-doc=template.docx` for corporate styling or `--toc` for a table of contents. In that case, run pandoc directly:

```bash
pandoc FILE.md -o OUT.docx --resource-path "$(dirname FILE.md)" --toc --reference-doc=template.docx
```

## Tips

- **Google Docs submission.** Upload the `.docx` to Google Drive, then use *Open with → Google Docs* (or enable auto-convert). Set sharing to "Anyone with the link can view" if a public link is required.
- **Page breaks.** Markdown has no page breaks. Insert them in Word afterwards, or use pandoc with a custom `--lua-filter`.
- **Images too large.** The fallback scales images to at most 6 inches wide. Pandoc respects `![alt](img.png){width=60%}`.
- Never put secrets or credentials into exported documents. Scan the Markdown first when exporting logs or configuration files.
