import { NextResponse } from "next/server"

import { getModelCards } from "@/lib/data-backend"

export async function GET() {
  const models = await getModelCards()
  return NextResponse.json(models)
}
