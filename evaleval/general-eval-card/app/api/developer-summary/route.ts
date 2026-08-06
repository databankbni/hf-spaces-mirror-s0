import { NextResponse } from "next/server"

import { getDeveloperSummaryById } from "@/lib/data-backend"

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const id = searchParams.get("id")

  if (!id) {
    return NextResponse.json({ error: "Missing developer id" }, { status: 400 })
  }

  const summary = await getDeveloperSummaryById(id)

  if (!summary) {
    return NextResponse.json({ error: "Developer not found" }, { status: 404 })
  }

  return NextResponse.json(summary)
}
