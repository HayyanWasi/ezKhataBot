import Link from "next/link";

export default function Home() {
  return (
    <main className="flex-1 flex items-center justify-center px-4 py-16">
      <div className="max-w-lg text-center">
        <div className="text-5xl mb-4">📒</div>
        <h1 className="text-3xl font-bold mb-3">EzKhata</h1>
        <p className="text-muted mb-8">
          WhatsApp par apni dukaan ka hisaab rakhein: udhaar khata, cash book, stock aur bill. Bas message likhein.
        </p>
        <Link href="/signup" className="btn btn-brand inline-block px-6 py-3">Apna bot hasil karein</Link>
      </div>
    </main>
  );
}
