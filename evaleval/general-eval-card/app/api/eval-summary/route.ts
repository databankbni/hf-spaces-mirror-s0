import { NextResponse } from "next/server"

import { getEvalSummaryById } from "@/lib/data-backend"

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const id = searchParams.get("id")

  if (!id) {
    return NextResponse.json({ error: "Missing evaluation id" }, { status: 400 })
  }

  const summary = await getEvalSummaryById(id)

  if (!summary) {
    return NextResponse.json({ error: "Evaluation not found" }, { status: 404 })
  }

  return NextResponse.json(summary)
}
