import { NextResponse } from "next/server"

import { getOrganizationsData } from "@/lib/data-backend"

export async function GET() {
  const orgs = await getOrganizationsData()
  return NextResponse.json(orgs)
}
