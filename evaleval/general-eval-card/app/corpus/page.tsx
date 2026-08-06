import { redirect } from "next/navigation"

// Corpus signals were folded into the home page. Preserve any external links
// to /corpus by sending readers to the same content at the root.
export default function CorpusRedirect() {
  redirect("/")
}
