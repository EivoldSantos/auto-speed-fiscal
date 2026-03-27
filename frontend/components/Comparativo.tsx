'use client'
import { useEffect, useState } from 'react'
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, Legend, CartesianGrid
} from 'recharts'

interface Props { cnpj: string }

export default function Comparativo({ cnpj }: Props) {
  const [dados, setDados] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!cnpj) return
    fetch(`/api/dashboard/comparativo?cnpj=${cnpj}&limite=12`)
      .then(r => r.json())
      .then(d => setDados([...d].reverse()))
      .finally(() => setLoading(false))
  }, [cnpj])

  if (loading) return <div className="text-gray-600 text-sm p-4">Carregando comparativo...</div>
  if (dados.length < 2) return (
    <div className="flex flex-col items-center justify-center h-64 gap-3 text-gray-600">
      <div className="text-4xl opacity-10">📊</div>
      <p className="text-sm">Processe pelo menos 2 meses do mesmo CNPJ para ver o comparativo</p>
      <p className="text-xs font-mono text-gray-700">{cnpj}</p>
    </div>
  )

  // Série para gráficos
  const serie = dados.map(d => ({
    periodo: d.dt_ini,
    erros:   d.total_erros,
    fixes:   d.total_fixes,
    flags:   d.total_flags,
    linhas:  d.total_linhas,
    // Alíquota média ponderada por BC
    aliqMedia: (() => {
      const entries = Object.values(d.aliq_map || {}) as any[]
      const totalBC   = entries.reduce((s, v) => s + v.bc,   0)
      const totalICMS = entries.reduce((s, v) => s + v.icms, 0)
      return totalBC > 0 ? Math.round(totalICMS / totalBC * 10000) / 100 : 0
    })(),
  }))

  // CFOPs mais relevantes (aparece em mais meses)
  const cfopFreq: Record<string, number> = {}
  dados.forEach(d => Object.keys(d.aliq_map || {}).forEach(cfop => {
    cfopFreq[cfop] = (cfopFreq[cfop] || 0) + 1
  }))
  const topCfops = Object.entries(cfopFreq).sort((a,b)=>b[1]-a[1]).slice(0,5).map(x=>x[0])

  const serieCfop = dados.map(d => ({
    periodo: d.dt_ini,
    ...Object.fromEntries(topCfops.map(cfop => [cfop, d.aliq_map?.[cfop]?.bc || 0]))
  }))

  const COLORS = ['#00d084','#4da6ff','#b088ff','#ffb347','#ff4757']
  const fmtN = (n: number) => n?.toLocaleString('pt-BR') ?? '0'

  const tooltip = {
    contentStyle: { background: '#1e2330', border: '1px solid #2a3040', borderRadius: 8, fontSize: 12 },
    labelStyle:   { color: '#8892a8', marginBottom: 4 },
  }

  return (
    <div className="space-y-6">
      <div className="text-xs uppercase tracking-widest text-gray-500">
        Comparativo — CNPJ {cnpj} · {dados.length} meses
      </div>

      {/* Linha: erros e fixes por mês */}
      <div className="bg-bg2 border border-border rounded-xl p-5">
        <div className="text-xs uppercase tracking-widest text-gray-500 mb-4">Erros × Correções por mês</div>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={serie}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2a3040" />
            <XAxis dataKey="periodo" tick={{ fontSize: 10, fill: '#4a5568', fontFamily: 'IBM Plex Mono' }} />
            <YAxis tick={{ fontSize: 10, fill: '#4a5568' }} />
            <Tooltip {...tooltip} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Line type="monotone" dataKey="erros" stroke="#ff4757" strokeWidth={2} dot={{ r: 4 }} name="Erros" />
            <Line type="monotone" dataKey="fixes" stroke="#b088ff" strokeWidth={2} dot={{ r: 4 }} name="Correções" />
            <Line type="monotone" dataKey="flags" stroke="#ffb347" strokeWidth={2} dot={{ r: 4 }} name="Flags" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Barra: alíquota média por mês */}
      <div className="bg-bg2 border border-border rounded-xl p-5">
        <div className="text-xs uppercase tracking-widest text-gray-500 mb-4">Alíquota efetiva média (ponderada por BC)</div>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={serie}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2a3040" />
            <XAxis dataKey="periodo" tick={{ fontSize: 10, fill: '#4a5568', fontFamily: 'IBM Plex Mono' }} />
            <YAxis tick={{ fontSize: 10, fill: '#4a5568' }} tickFormatter={v => `${v}%`} />
            <Tooltip {...tooltip} formatter={(v: any) => [`${v}%`, 'Alíq. média']} />
            <Bar dataKey="aliqMedia" fill="#4da6ff" radius={[4,4,0,0]} name="Alíq. efetiva %" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Barra empilhada: BC por CFOP */}
      {topCfops.length > 0 && (
        <div className="bg-bg2 border border-border rounded-xl p-5">
          <div className="text-xs uppercase tracking-widest text-gray-500 mb-4">Base de Cálculo por CFOP (top 5)</div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={serieCfop}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a3040" />
              <XAxis dataKey="periodo" tick={{ fontSize: 10, fill: '#4a5568', fontFamily: 'IBM Plex Mono' }} />
              <YAxis tick={{ fontSize: 10, fill: '#4a5568' }} tickFormatter={v => fmtN(v)} />
              <Tooltip {...tooltip} formatter={(v: any) => ['R$ ' + fmtN(v)]} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {topCfops.map((cfop, i) => (
                <Bar key={cfop} dataKey={cfop} stackId="a" fill={COLORS[i % COLORS.length]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Tabela resumo */}
      <div className="bg-bg2 border border-border rounded-xl overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border">
              {['Período','Erros','Correções','Flags','Linhas','Alíq. média'].map(h => (
                <th key={h} className="text-left px-4 py-3 text-gray-500 uppercase tracking-wide font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {serie.map((s, i) => (
              <tr key={i} className="border-b border-border hover:bg-bg3 transition-colors">
                <td className="px-4 py-2.5 font-mono text-gray-300">{s.periodo}</td>
                <td className="px-4 py-2.5 font-mono text-red-400">{s.erros}</td>
                <td className="px-4 py-2.5 font-mono text-purple-400">{s.fixes}</td>
                <td className="px-4 py-2.5 font-mono text-amber-400">{s.flags}</td>
                <td className="px-4 py-2.5 font-mono text-gray-400">{fmtN(s.linhas)}</td>
                <td className="px-4 py-2.5 font-mono text-blue-400">{s.aliqMedia.toFixed(2)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
