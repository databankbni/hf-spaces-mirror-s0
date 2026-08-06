import { NextResponse } from "next/server";

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const { token, chat_id, text, parse_mode } = body;

    if (!token || !chat_id || !text) {
      return NextResponse.json({ error: "Missing parameters" }, { status: 400 });
    }

    const cleanToken = token.trim().startsWith("bot") ? token.trim().slice(3) : token.trim();
    const telegramUrl = `https://api.telegram.org/bot${cleanToken}/sendMessage`;

    const response = await fetch(telegramUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chat_id,
        text,
        parse_mode: parse_mode || "HTML",
        disable_web_page_preview: true,
      }),
    });

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error: any) {
    return NextResponse.json({ error: error.message || "Relay error" }, { status: 500 });
  }
}
