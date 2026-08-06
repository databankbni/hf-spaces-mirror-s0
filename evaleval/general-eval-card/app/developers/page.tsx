import { redirect } from "next/navigation"

export default function DevelopersRedirectPage() {
  redirect("/models?group=developer")
}
