import io
import re
import zipfile
from pathlib import Path

import fitz  # PyMuPDF
import streamlit as st

st.set_page_config(page_title="CDBL BOID Portfolio Separator", page_icon="📄", layout="wide")

st.title("CDBL BOID Portfolio Separator")
st.write(
    "Upload DPD1 account statements and/or DPA6 Daily BO-ISIN Holding Reports. "
    "The app separates pages by BOID, lists missing BOIDs, and creates TXT reports."
)

DPD1_DEFAULT = """1202950018995403
1201900021719463
1202900021719463"""

DPA6_DEFAULT = """1201530000002341
1604580000002341
1201530000003518
1201530000003534
1604580000003534
1201530061471934
1201530061471926
1201530000003577
1604580000003577
1201530062162908
1201530062162892
1201530000003569
1604580000003569
1201530062008338
1201530062008321
1201530000003542
1604580000003542
1201530061740096
1201530061740152
1605420073358281
1201530000003501
1301000000056063
1604580023518711
1605400047188717"""

st.subheader("1. BOID lists")
left, right = st.columns(2)
with left:
    dpd1_text = st.text_area("DPD1 BOIDs (one per line)", DPD1_DEFAULT, height=180)
with right:
    dpa6_text = st.text_area("DPA6 BOIDs (one per line)", DPA6_DEFAULT, height=360)

dpd1_targets = list(dict.fromkeys(re.findall(r"(?<!\d)\d{16}(?!\d)", dpd1_text)))
dpa6_targets = list(dict.fromkeys(re.findall(r"(?<!\d)\d{16}(?!\d)", dpa6_text)))
all_targets = list(dict.fromkeys(dpd1_targets + dpa6_targets))

st.caption(f"DPD1 targets: {len(dpd1_targets)} | DPA6 targets: {len(dpa6_targets)}")
report_choice = st.selectbox(
    "Report type of uploaded PDFs",
    ["Auto-detect each PDF", "DPD1 only", "DPA6 only"],
    help="Auto-detect is recommended. Each PDF is processed against the matching BOID list."
)

st.subheader("2. Upload PDF files")
uploads = st.file_uploader(
    "Select one or more DPD1 / DPA6 PDF files",
    type=["pdf"],
    accept_multiple_files=True,
)

def detect_boid(page_text):
    """Return a BOID from a page, supporting both DPD1 and DPA6 text layouts."""
    # DPD1-style: BO ID : 123... (same line or next line)
    patterns = [
        r"BO\s*ID\s*:\s*(?:\s*[\r\n]+\s*)?(\d{16})",
        r"BO\s*ID\s*:\s*[\r\n]+\s*(\d{16})",
    ]
    for pattern in patterns:
        match = re.search(pattern, page_text, flags=re.IGNORECASE)
        if match:
            return match.group(1)

    # DPA6 text extraction may place the BOID on a separate line,
    # while the BO ID label itself is elsewhere in the header.
    lines = [line.strip() for line in page_text.splitlines() if line.strip()]
    for i, line in enumerate(lines):
        if re.fullmatch(r"\d{16}", line):
            # DPA6 BOID is in the header, close to "BO ID" label.
            nearby = " ".join(lines[max(0, i - 5):min(len(lines), i + 4)]).lower()
            if "bo id" in nearby or "bo short name" in nearby:
                return line

    # Fallback: DPD1 / other CDBL page layouts sometimes expose BOID
    # without the label being in the extracted text.
    candidates = re.findall(r"(?<!\d)\d{16}(?!\d)", page_text)
    return candidates[0] if candidates else None


if uploads and all_targets:
    if st.button("Separate portfolios and generate reports", type="primary"):
        output_files = {}
        summary_rows = []
        missing_by_file = {}
        unidentified_by_file = {}
        detected_by_file = {}

        progress = st.progress(0)
        status = st.empty()

        for file_index, uploaded in enumerate(uploads):
            source_name = Path(uploaded.name).name
            try:
                source_bytes = uploaded.getvalue()
                source_doc = fitz.open(stream=source_bytes, filetype="pdf")
            except Exception as exc:
                st.error(f"Could not open {source_name}: {exc}")
                continue

            sample_text = "\\n".join(source_doc[i].get_text("text") for i in range(min(2, len(source_doc))))
            if report_choice == "DPD1 only":
                file_targets = dpd1_targets
                report_type = "DPD1"
            elif report_choice == "DPA6 only":
                file_targets = dpa6_targets
                report_type = "DPA6"
            elif "DPA6" in sample_text.upper() or "DAILY BO-ISIN HOLDING REPORT" in sample_text.upper():
                file_targets = dpa6_targets
                report_type = "DPA6 (auto-detected)"
            else:
                file_targets = dpd1_targets
                report_type = "DPD1 (auto-detected)"

            pages_by_boid = {}
            page_map = []
            unidentified_pages = []
            last_boid = None

            for page_index, page in enumerate(source_doc):
                page_no = page_index + 1
                text = page.get_text("text")
                detected = detect_boid(text)

                # Carry forward the previous BOID only when a continuation page
                # has no readable BOID. Mark it as carried in the audit report.
                carried = False
                if detected:
                    last_boid = detected
                elif last_boid:
                    detected = last_boid
                    carried = True
                else:
                    unidentified_pages.append(page_no)

                if detected:
                    pages_by_boid.setdefault(detected, []).append(page_index)
                    page_map.append((page_no, detected, "Carried forward" if carried else "Detected"))

            detected_by_file[source_name] = sorted(pages_by_boid.keys())
            target_set = set(file_targets)
            missing = [boid for boid in file_targets if boid not in pages_by_boid]
            missing_by_file[source_name] = missing
            unidentified_by_file[source_name] = unidentified_pages

            # Generate one PDF for each requested BOID that is present.
            for boid in file_targets:
                page_indices = pages_by_boid.get(boid, [])
                if not page_indices:
                    continue
                out_doc = fitz.open()
                for page_index in page_indices:
                    out_doc.insert_pdf(source_doc, from_page=page_index, to_page=page_index)
                safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(source_name).stem)
                output_files[f"{safe_stem}_{boid}.pdf"] = out_doc.tobytes()
                out_doc.close()

            for boid in file_targets:
                page_indices = pages_by_boid.get(boid, [])
                summary_rows.append({
                    "Source PDF": source_name,
                    "BOID": boid,
                    "Status": "FOUND" if page_indices else "MISSING",
                    "Pages": ", ".join(str(i + 1) for i in page_indices) if page_indices else "-",
                    "Page count": len(page_indices),
                })

            # Per-source audit text
            report_lines = [
                "CDBL BOID PORTFOLIO SEPARATION REPORT",
                f"Source PDF: {source_name}",
                f"Report type: {report_type}",
                f"Total pages: {len(source_doc)}",
                "",
                "TARGET BOID STATUS",
                "------------------",
            ]
            for boid in file_targets:
                page_indices = pages_by_boid.get(boid, [])
                if page_indices:
                    report_lines.append(
                        f"FOUND   | {boid} | Pages: " + ", ".join(str(i + 1) for i in page_indices)
                    )
                else:
                    report_lines.append(f"MISSING | {boid}")

            report_lines += ["", "PAGE-BY-PAGE BOID DETECTION", "---------------------------"]
            for page_no, boid, method in page_map:
                report_lines.append(f"Page {page_no}: {boid} ({method})")

            report_lines += ["", "UNIDENTIFIED PAGES", "------------------"]
            if unidentified_pages:
                report_lines.extend(f"Page {p}: BOID could not be detected" for p in unidentified_pages)
            else:
                report_lines.append("None")

            report_lines += ["", "DETECTED BOIDs NOT IN TARGET LIST", "---------------------------------"]
            extras = [b for b in pages_by_boid if b not in target_set]
            if extras:
                report_lines.extend(f"{b}: pages " + ", ".join(str(i + 1) for i in pages_by_boid[b]) for b in extras)
            else:
                report_lines.append("None")

            output_files[f"{Path(source_name).stem}_BOID_report.txt"] = "\n".join(report_lines).encode("utf-8")
            source_doc.close()
            status.write(f"Processed {source_name}")
            progress.progress((file_index + 1) / len(uploads))

        st.session_state["cdbl_output_files"] = output_files
        st.session_state["cdbl_summary_rows"] = summary_rows
        st.session_state["cdbl_missing_by_file"] = missing_by_file
        st.session_state["cdbl_unidentified_by_file"] = unidentified_by_file

        # Combined missing BOID TXT
        combined = ["CDBL COMBINED MISSING BOID REPORT", "================================="]
        for source_name, missing in missing_by_file.items():
            combined += ["", f"Source PDF: {source_name}", f"Missing BOID count: {len(missing)}"]
            combined.extend(missing if missing else ["No missing BOIDs"])
        combined += ["", "UNIDENTIFIED PAGES", "=================="]
        for source_name, pages in unidentified_by_file.items():
            combined.append(f"{source_name}: " + (", ".join(map(str, pages)) if pages else "None"))
        st.session_state["cdbl_output_files"]["COMBINED_MISSING_BOID_REPORT.txt"] = "\n".join(combined).encode("utf-8")

if "cdbl_summary_rows" in st.session_state:
    st.subheader("3. Separation results")
    st.dataframe(st.session_state["cdbl_summary_rows"], use_container_width=True, hide_index=True)

    for source_name, missing in st.session_state["cdbl_missing_by_file"].items():
        found_count = len([r for r in st.session_state["cdbl_summary_rows"] if r["Source PDF"] == source_name and r["Status"] == "FOUND"])
        st.write(f"**{source_name}:** {found_count} found, {len(missing)} missing")
        if missing:
            st.warning("Missing BOIDs: " + ", ".join(missing))
        else:
            st.success("All target BOIDs were found.")

    st.subheader("4. Download files")
    output_files = st.session_state["cdbl_output_files"]

    # Individual downloads
    with st.expander("Download individual portfolio PDFs and TXT reports", expanded=False):
        for filename, data in output_files.items():
            st.download_button(
                label=f"Download {filename}",
                data=data,
                file_name=filename,
                mime="application/pdf" if filename.lower().endswith(".pdf") else "text/plain",
                key=f"dl_{filename}",
            )

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, data in output_files.items():
            zf.writestr(filename, data)
    st.download_button(
        "Download ALL separated PDFs + TXT reports (ZIP)",
        data=zip_buffer.getvalue(),
        file_name="CDBL_BOID_Separated_Portfolios.zip",
        mime="application/zip",
        type="primary",
    )

elif uploads and not all_targets:
    st.warning("Please enter at least one valid 16-digit BOID in the selected report type list.")
else:
    st.info("Enter your BOID lists and upload one or more PDF files to begin.")

st.divider()
st.caption(
    "Note: The app reads selectable PDF text. If a PDF is scanned as images, OCR is required. "
    "Pages without a detectable BOID are listed for manual review. Continuation pages without "
    "a BOID are assigned the previous detected BOID and marked 'Carried forward' in the TXT report."
)
