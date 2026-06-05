import { NextResponse } from "next/server";

export async function POST(request: Request) {
  try {
    const { username, password } = await request.json();

    const expectedUser = process.env.ADMIN_USERNAME ?? "";
    const expectedPass = process.env.ADMIN_PASSWORD ?? "";
    const secret = process.env.AUTH_SECRET ?? "";

    if (!expectedUser || !expectedPass || !secret) {
      return NextResponse.json(
        { ok: false, error: "Auth nicht konfiguriert (ENV-Variablen fehlen)" },
        { status: 500 }
      );
    }

    if (username === expectedUser && password === expectedPass) {
      const response = NextResponse.json({ ok: true });
      response.cookies.set("bl_session", secret, {
        httpOnly: true,
        secure: process.env.NODE_ENV === "production",
        sameSite: "lax",
        maxAge: 60 * 60 * 24 * 30,
        path: "/",
      });
      return response;
    }

    return NextResponse.json(
      { ok: false, error: "Ungültiger Benutzername oder Passwort" },
      { status: 401 }
    );
  } catch {
    return NextResponse.json({ ok: false, error: "Ungültige Anfrage" }, { status: 400 });
  }
}
