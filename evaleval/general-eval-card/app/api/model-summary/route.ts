import { NextResponse } from "next/server"

import { getModelSummaryById } from "@/lib/data-backend"

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const id = searchParams.get("id")

  if (!id) {
    return NextResponse.json({ error: "Missing model id" }, { status: 400 })
  }

  const summary = await getModelSummaryById(id)

  if (!summary) {
    return NextResponse.json({ error: "Model not found" }, { status: 404 })
  }

  return NextResponse.json(summary)
}
