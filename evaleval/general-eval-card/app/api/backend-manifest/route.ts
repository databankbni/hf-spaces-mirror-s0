import { NextResponse } from "next/server"

import { getBackendManifestStatusData } from "@/lib/data-backend"

export async function GET() {
  const manifestStatus = await getBackendManifestStatusData()
  return NextResponse.json(manifestStatus)
}