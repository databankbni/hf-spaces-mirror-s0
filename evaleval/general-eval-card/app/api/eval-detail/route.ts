import { NextResponse } from "next/server"

import { fetchEvalDetail } from "@/lib/hf-data"

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const id = searchParams.get("id")

  if (!id) {
    return NextResponse.json({ error: "Missing evaluation id" }, { status: 400 })
  }

  const detail = await fetchEvalDetail(id)

  if (!detail) {
    return NextResponse.json({ error: "Evaluation not found" }, { status: 404 })
  }

  return NextResponse.json(detail)
}
