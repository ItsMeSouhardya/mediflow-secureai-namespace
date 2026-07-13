const MONO = { fontFamily: 'DM Mono, monospace' }

export default function HowItWorks({ title, steps }) {
  return (
    <section className="mt-8">
      <div className="mb-5 text-[11px] font-bold uppercase tracking-[0.2em] text-slate-400" style={MONO}>{title}</div>
      <div className="grid gap-5 md:grid-cols-3">
        {steps.map((step, index) => (
          <article key={step.title} className="rounded-2xl border border-blue-200 bg-white px-7 py-6 shadow-sm">
            <div className="mb-5 flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600 text-sm font-extrabold text-white" style={MONO}>{index + 1}</div>
            <h3 className="text-base font-extrabold text-slate-900">{step.title}</h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">{step.description}</p>
          </article>
        ))}
      </div>
    </section>
  )
}
