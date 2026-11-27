# CDBL BOID Portfolio Separator

A Streamlit application for separating DPD1 statements and DPA6 BO-ISIN holding report pages by BOID.

## Run locally

```bash
pip install -r requirements.txt
streamlit run cdbl_unified_boid_separator.py
```

## Deploy

Deploy `cdbl_unified_boid_separator.py` from this GitHub repository using Streamlit Community Cloud.

## Data handling and confidentiality

This repository should be private. Do not commit CDBL statements, customer portfolio PDFs, exported reports, BOID lists, or other confidential information. The app's default BOID lists are embedded in its source code; review and replace/remove them before making the repository public.

Before uploading real CDBL/customer documents to any hosted service, obtain the required organizational approval and confirm that the service is permitted for that data.
