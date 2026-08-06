---
title: LPJ Universe
emoji: 🚀
colorFrom: green
colorTo: blue
sdk: docker
pinned: false
---

# LPJ Reader API

Backend service for parsing LPJ (Laporan Pertanggungjawaban) Excel files from Supabase Storage and extracting budget realisasi data.

## API Endpoints

### `POST /api/parse-lpj`

Parses all LPJ Excel files from the Supabase Storage bucket `lpj-documents`.

**Request Body:**
```json
{
  "supabaseUrl": "https://your-project.supabase.co",
  "supabaseKey": "your-service-role-key"
}
```

**Response:**
```json
{
  "error": false,
  "results": [
    {
      "letter": "173/KMD-AUDIT/V/2026",
      "branch_name": "ANYAR",
      "transportasi": 300000,
      "konsumsi": 300000,
      "lain_lain": 135000,
      "filename": "1779679618681_LPJ_ANYAR_173_KMD_AUDIT_V_2026_xlsx"
    }
  ],
  "summary": {
    "total_files": 5,
    "parsed": 4,
    "failed": 1
  }
}
```

### `GET /health`
Health check endpoint.
