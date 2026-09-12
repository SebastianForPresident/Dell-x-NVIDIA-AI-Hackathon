"""Local Streamlit interface for a crop insurance evidence assistant."""

from datetime import date, timedelta
import hashlib
import io
import json
from pathlib import Path
import tempfile

import streamlit as st
import pandas as pd
from pypdf import PdfReader

from forensics import (
    Finding, build_report, crop_finding, field_names, load_boundary,
    markdown_report, ndvi_mean, neighbors_finding, parse_weather,
    vegetation_finding, weather_finding,
)
from local_narrative import check_local_model, extract_claim_fields, write_narrative
from visuals import field_svg


st.set_page_config(page_title="Field Evidence | Crop Insurance Forensics", page_icon="🌾", layout="wide")
st.title("🌾 Crop Insurance Forensics")
st.caption("Local evidence assistant for adjusters · No claim decision")

mode = st.radio("Case source", ["Synthetic demo", "Upload case files"], horizontal=True)
demo = mode == "Synthetic demo"

with st.sidebar:
    st.header("Claim")
    claim_id = st.text_input("Claim ID", "DEMO-2026-001" if demo else "")
    cause = st.selectbox("Reported cause", ["Drought"] if demo else ["Drought", "Flood", "Other"])
    loss_date = st.date_input("Reported loss date", date(2026, 7, 18))
    expected_crop = st.selectbox("Claimed crop", ["Corn", "Soybeans", "Winter wheat", "Other"])
    st.caption("Thresholds are demo screening rules, not insurance standards.")
    st.divider()
    st.caption("OpenShell + Qwen readiness")
    if st.button("Test local model route"):
        try:
            reply = check_local_model()
            st.success(f"Local inference responded: {reply}")
        except Exception as exc:
            st.error(f"No OpenShell inference route: {exc}")

if demo:
    st.info("This case is synthetic. All weather, crop, and imagery values below are fabricated to demonstrate the workflow.")
    field_name = "North corn field"
    weather_rows = [
        {"date": loss_date - timedelta(days=29-i), "precipitation_mm": 1.0, "normal_mm": 3.0}
        for i in range(30)
    ]
    findings = [
        Finding("Crop type", "supported", "Dominant CDL class: Corn (91% of sampled pixels).",
                "Synthetic demo CDL sample", {"class": "Corn", "share": 0.91, "pixels": 450}),
        weather_finding(weather_rows, loss_date),
        vegetation_finding(0.72, 0.44, loss_date - timedelta(days=45),
                           loss_date + timedelta(days=25), loss_date, "Synthetic demo red/NIR pixels"),
        neighbors_finding([-0.19, -0.23, -0.04, -0.16]),
    ]
    findings[-1].source = "Synthetic demo neighboring fields"
    display_features = [
        {"geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
         "properties": {"name": "North corn field"}},
        {"geometry": {"type": "Polygon", "coordinates": [[[1.2, 0], [2.2, 0], [2.2, 1], [1.2, 1], [1.2, 0]]]},
         "properties": {"name": "Other field"}},
    ]
    display_selected = 0
else:
    st.subheader("Upload case evidence")
    st.write("GeoJSON coordinates must be WGS84 (EPSG:4326). Before and after GeoTIFFs must each contain red and near-infrared bands. Weather CSV needs `date,precipitation`; add `normal_precipitation` for a rainfall-deficit check.")
    claim_pdf = st.file_uploader("Claim PDF (optional)", type=["pdf"])
    if claim_pdf:
        try:
            reader = PdfReader(io.BytesIO(claim_pdf.getvalue()))
            claim_text = "\n".join(page.extract_text() or "" for page in reader.pages)
            with st.expander("Extracted claim text — verify dates and crop manually"):
                st.text(claim_text[:12000] or "No selectable text found. This PDF may need OCR.")
            if claim_text and st.button("Suggest claim fields with local model"):
                try:
                    st.code(extract_claim_fields(claim_text), language="json")
                    st.caption("Verify these suggestions against the PDF, then enter them in the Claim panel.")
                except Exception as exc:
                    st.error(f"Local inference unavailable: {exc}")
        except Exception as exc:
            st.warning(f"Could not read PDF: {exc}")
    boundary_file = st.file_uploader("Field boundary GeoJSON", type=["geojson", "json"])
    weather_file = st.file_uploader("Weather CSV", type=["csv"])
    crop_file = st.file_uploader("USDA CDL GeoTIFF", type=["tif", "tiff"], key="crop")
    before_file = st.file_uploader("Before image GeoTIFF", type=["tif", "tiff"], key="before")
    after_file = st.file_uploader("After image GeoTIFF", type=["tif", "tiff"], key="after")
    col1, col2, col3, col4 = st.columns(4)
    before_date = col1.date_input("Before image date", loss_date - timedelta(days=45))
    after_date = col2.date_input("After image date", loss_date + timedelta(days=25))
    red_band = col3.number_input("Red band index", min_value=1, value=1)
    nir_band = col4.number_input("NIR band index", min_value=1, value=2)
    unit = st.radio("Weather precipitation unit", ["mm", "inches"], horizontal=True)
    features = None
    if boundary_file:
        try:
            features = load_boundary(boundary_file.getvalue())
            names = field_names(features)
            field_name = st.selectbox("Claimed field", names)
            target_index = names.index(field_name)
            display_features = features
            display_selected = target_index
            st.caption(f"{len(features)} field polygon(s) supplied. Other polygons are treated as neighboring fields.")
        except Exception as exc:
            st.error(f"Boundary error: {exc}")
    case_signature = hashlib.sha256()
    case_signature.update(repr((claim_id, cause, loss_date, expected_crop, before_date,
                                after_date, red_band, nir_band, unit,
                                field_name if features else None)).encode())
    for upload in (boundary_file, weather_file, crop_file, before_file, after_file):
        case_signature.update((upload.name if upload else "<missing>").encode())
        case_signature.update(upload.getvalue() if upload else b"<missing>")
    current_signature = case_signature.hexdigest()
    run = st.button("Investigate case", type="primary", disabled=not (claim_id and features))
    if run:
        findings = []
        geometry = features[target_index]["geometry"]
        with tempfile.TemporaryDirectory() as temp_dir:
            def save_uploaded(upload, name):
                if upload is None:
                    return None
                path = Path(temp_dir) / name
                path.write_bytes(upload.getvalue())
                return path

            crop_path = save_uploaded(crop_file, "crop.tif")
            before_path = save_uploaded(before_file, "before.tif")
            after_path = save_uploaded(after_file, "after.tif")
            if crop_path:
                try:
                    findings.append(crop_finding(crop_path, geometry, expected_crop))
                    findings[-1].source = crop_file.name
                except Exception as exc:
                    findings.append(Finding("Crop type", "unavailable", str(exc), crop_file.name, {}))
            else:
                findings.append(Finding("Crop type", "unavailable", "No crop layer supplied.", "No source", {}))

            if weather_file:
                try:
                    findings.append(weather_finding(parse_weather(weather_file.getvalue(), unit), loss_date, cause=cause))
                    findings[-1].source = weather_file.name
                except Exception as exc:
                    findings.append(Finding("Precipitation", "unavailable", str(exc), weather_file.name, {}))
            else:
                findings.append(Finding("Precipitation", "unavailable", "No weather CSV supplied.", "No source", {}))

            changes = []
            if before_path and after_path and red_band != nir_band:
                try:
                    before = ndvi_mean(before_path, geometry, red_band, nir_band)
                    after = ndvi_mean(after_path, geometry, red_band, nir_band)
                    findings.append(vegetation_finding(before, after, before_date, after_date,
                                                       loss_date, f"{before_file.name}; {after_file.name}"))
                    for i, feature in enumerate(features):
                        if i == target_index:
                            continue
                        try:
                            old = ndvi_mean(before_path, feature["geometry"], red_band, nir_band)
                            new = ndvi_mean(after_path, feature["geometry"], red_band, nir_band)
                            if old is not None and new is not None:
                                changes.append(new - old)
                        except ValueError:
                            continue
                except Exception as exc:
                    findings.append(Finding("Vegetation change", "unavailable", str(exc),
                                            f"{before_file.name}; {after_file.name}", {}))
            else:
                reason = "Red and NIR band indices must differ." if red_band == nir_band else "Both before and after imagery are required."
                findings.append(Finding("Vegetation change", "unavailable", reason, "No valid image pair", {}))
            findings.append(neighbors_finding(changes))
        st.session_state["report"] = build_report(claim_id, cause, loss_date, field_name, findings)
        st.session_state["report_signature"] = current_signature

if demo:
    report = build_report(claim_id, cause, loss_date, field_name, findings, demo=True)
else:
    report = (st.session_state.get("report")
              if st.session_state.get("report_signature") == current_signature else None)

if report:
    st.divider()
    st.subheader("Evidence package")
    counts = report["evidence_summary"]
    cols = st.columns(4)
    for col, label, key in zip(cols, ["Supported", "Contradicted", "Inconclusive", "Unavailable"], counts):
        col.metric(label, counts[key])
    view_left, view_right = st.columns(2)
    with view_left:
        st.markdown("**Field boundary**")
        if demo or (features and field_name == report["field"]):
            st.html(field_svg(display_features, display_selected))
        else:
            st.caption("Re-run the investigation to update the field view.")
    with view_right:
        st.markdown("**Vegetation timeline**")
        vegetation = next((f for f in report["findings"] if f["check"] == "Vegetation change"), None)
        if vegetation and {"before_ndvi", "after_ndvi", "before_date", "after_date"} <= vegetation["values"].keys():
            values = vegetation["values"]
            series = pd.DataFrame({"Date": [values["before_date"], values["after_date"]],
                                   "Mean NDVI": [values["before_ndvi"], values["after_ndvi"]]})
            st.line_chart(series, x="Date", y="Mean NDVI", y_label="Mean NDVI", height=280)
        else:
            st.caption("Valid before and after imagery are needed for a timeline.")
    for finding in report["findings"]:
        icon = {"supported": "✅", "contradicted": "⚠️", "inconclusive": "❔", "unavailable": "—"}[finding["status"]]
        with st.expander(f"{icon} {finding['check']} · {finding['status'].title()}", expanded=True):
            st.write(finding["detail"])
            st.caption(f"Source: {finding['source']}")
            st.json(finding["values"])
    st.caption(report["assessment"])
    st.download_button("Download evidence report (.md)", markdown_report(report),
                       file_name=f"{report['claim_id'] or 'claim'}-evidence.md", mime="text/markdown")
    st.download_button("Download structured evidence (.json)", json.dumps(report, indent=2),
                       file_name=f"{report['claim_id'] or 'claim'}-evidence.json", mime="application/json")
    with st.expander("Optional local AI narrative (OpenShell)"):
        st.write("Uses only `https://inference.local` inside an OpenShell sandbox. The evidence above remains the source of record.")
        if st.button("Draft narrative with local model"):
            try:
                st.write(write_narrative(report))
            except Exception as exc:
                st.error(f"Local inference unavailable: {exc}")
