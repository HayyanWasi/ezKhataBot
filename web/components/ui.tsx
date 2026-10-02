export function PageTitle({ title, sub, right }: { title: string; sub?: string; right?: React.ReactNode }) {
  return (
    <div className="flex items-end justify-between gap-4 mb-5 flex-wrap">
      <div>
        <h1 className="text-2xl font-bold">{title}</h1>
        {sub && <p className="text-muted text-sm mt-1">{sub}</p>}
      </div>
      {right}
    </div>
  );
}

export function Loading({ error, loading }: { error: string; loading: boolean }) {
  if (error) return <div className="card p-4 text-danger">{error}</div>;
  if (loading) return <div className="text-muted">Load ho raha hai… (server so raha ho tou ~1 minute)</div>;
  return null;
}

export function OnOff({ off }: { off: string | null | undefined }) {
  return off
    ? <span className="badge bg-danger-soft text-danger">Band</span>
    : <span className="badge bg-brand-soft text-brand">Chalu</span>;
}

export function Empty({ text }: { text: string }) {
  return <div className="card p-8 text-center text-muted">{text}</div>;
}
