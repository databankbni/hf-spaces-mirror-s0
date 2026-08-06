import { NextResponse } from "next/server"

import { getDeveloperList } from "@/lib/data-backend"

export async function GET() {
  const developers = await getDeveloperList()
  return NextResponse.json(developers)
}
