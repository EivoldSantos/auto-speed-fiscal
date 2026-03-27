'use client'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'

interface Props { sumario: any; tipo?: string }

const ALIQ_ICMS_OK = [0, 4, 7, 8, 10, 12, 17, 18, 20, 25]
const aliqIcmsOk = (a: number) => ALIQ_ICMS_OK.some(e => Math.abs(a - e) < 0.5)

const ALIQ_PIS_OK = [0, 0.65, 1.65]
const ALIQ_COFINS_OK = [0, 3, 7.6]
const aliqPisOk = (a: number) => ALIQ_PIS_OK.some(e => Math.abs(a - e) < 0.1)
const aliqCofOk = (a: number) => ALIQ_COFINS_OK.some(e => Math.abs(a - e) < 0.1)

const fmtN = (n: number) => n.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export default function Dashboard({ sumario, tipo = 'icms' }: Props) {
  if (tipo === 'contrib') return <DashboardContrib sumario={sumario} />
  return <DashboardICMS sumario={sumario} />
}

function DashboardICMS({ sumario }: { sumario: any }) {
  const aliqMap: Record<string, any> = sumario?.aliq_map || {}

  const entries = Object.entries(aliqMap)
    .map(([cfop, v]: [string, any]) => ({
      cfop,
      aliqEfet: v.bc > 0 ? Math.round(v.icms / v.bc * 10000) / 100 : 0,
      bc: v.bc, icms: v.icms, vlOpr: v.vl_opr, n: v.n,
    }))
    .sort((a, b) => b.vlOpr - a.vlOpr)
    .slice(0, 20)

  const maxVl = Math.max(...entries.map(e => e.vlOpr), 1)

  if (!entries.length) return (
    <div className="flex items-center justify-center h-64 text-gray-600 text-sm">
      Nenhum C190 com base de cálculo encontrado
    </div>
  )

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'CFOPs com tributação', val: entries.length },
          { label: 'Total BC ICMS', val: 'R$ ' + fmtN(entries.reduce((s,e)=>s+e.bc,0)) },
          { label: 'Total ICMS',    val: 'R$ ' + fmtN(entries.reduce((s,e)=>s+e.icms,0)) },
        ].map(c => (
          <div key={c.label} className="bg-bg2 border border-border rounded-xl p-4">
            <div className="text-2xl font-semibold font-mono text-blue-400 mb-1">{c.val}</div>
            <div className="text-xs uppercase tracking-wide text-gray-500">{c.label}</div>
          </div>
        ))}
      </div>

      <div className="bg-bg2 border border-border rounded-xl p-5">
        <div className="text-xs uppercase tracking-widest text-gray-500 mb-4">
          Alíquota efetiva por CFOP — top 20 por volume
        </div>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={entries} margin={{ top: 4, right: 8, bottom: 40, left: 8 }}>
            <XAxis dataKey="cfop" tick={{ fontSize: 10, fill: '#4a5568', fontFamily: 'IBM Plex Mono' }}
              angle={-45} textAnchor="end" interval={0} />
            <YAxis tick={{ fontSize: 10, fill: '#4a5568' }} tickFormatter={v => `${v}%`} />
            <Tooltip
              contentStyle={{ background: '#1e2330', border: '1px solid #2a3040', borderRadius: 8, fontSize: 12 }}
              formatter={(val: any) => [`${val}%`, 'Alíq. efetiva']} />
            <Bar dataKey="aliqEfet" radius={[4, 4, 0, 0]}>
              {entries.map((e, i) => (
                <Cell key={i} fill={aliqIcmsOk(e.aliqEfet) ? '#00d084' : '#ffb347'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="bg-bg2 border border-border rounded-xl overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border">
              {['CFOP','Alíq. efetiva','BC ICMS','ICMS','Vol. operações','Docs','Status'].map(h => (
                <th key={h} className="text-left px-4 py-3 text-gray-500 uppercase tracking-wide font-medium text-xs">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {entries.map((e, i) => {
              const ok = aliqIcmsOk(e.aliqEfet)
              const pct = maxVl > 0 ? Math.round(e.vlOpr / maxVl * 100) : 0
              return (
                <tr key={i} className="border-b border-border hover:bg-bg3 transition-colors">
                  <td className="px-4 py-2.5 font-mono font-medium">{e.cfop}</td>
                  <td className={`px-4 py-2.5 font-mono ${ok ? 'text-green' : 'text-amber-400'}`}>
                    {e.aliqEfet.toFixed(2)}%
                  </td>
                  <td className="px-4 py-2.5 font-mono text-gray-300">{fmtN(e.bc)}</td>
                  <td className="px-4 py-2.5 font-mono text-gray-300">{fmtN(e.icms)}</td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-2 bg-bg3 rounded overflow-hidden">
                        <div className="h-full bg-blue-500/60 rounded" style={{ width: `${pct}%` }} />
                      </div>
                      <span className="font-mono text-gray-400 w-20 text-right">{fmtN(e.vlOpr)}</span>
                    </div>
                  </td>
                  <td className="px-4 py-2.5 font-mono text-gray-500">{e.n}</td>
                  <td className="px-4 py-2.5">
                    <span className={`px-2 py-0.5 rounded text-xs font-mono
                      ${ok ? 'bg-green/10 text-green' : 'bg-amber-900/30 text-amber-400'}`}>
                      {ok ? '✓ OK' : '⚠ revisar'}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function DashboardContrib({ sumario }: { sumario: any }) {
  const aliqMap: Record<string, any> = sumario?.aliq_map || {}

  const entries = Object.entries(aliqMap)
    .map(([cfop, v]: [string, any]) => {
      const bcPis = v.bc_pis || 0
      const vlPis = v.vl_pis || 0
      const bcCof = v.bc_cofins || 0
      const vlCof = v.vl_cofins || 0
      const vlItem = v.vl_item || 0
      return {
        cfop,
        aliqPis: bcPis > 0 ? Math.round(vlPis / bcPis * 10000) / 100 : 0,
        aliqCof: bcCof > 0 ? Math.round(vlCof / bcCof * 10000) / 100 : 0,
        bcPis, vlPis, bcCof, vlCof, vlItem, n: v.n || 0,
      }
    })
    .sort((a, b) => b.vlItem - a.vlItem)
    .slice(0, 20)

  const maxVl = Math.max(...entries.map(e => e.vlItem), 1)

  if (!entries.length) return (
    <div className="flex items-center justify-center h-64 text-gray-600 text-sm">
      Nenhum C170 com base de cálculo PIS/COFINS encontrado
    </div>
  )

  const totBcPis = entries.reduce((s, e) => s + e.bcPis, 0)
  const totVlPis = entries.reduce((s, e) => s + e.vlPis, 0)
  const totBcCof = entries.reduce((s, e) => s + e.bcCof, 0)
  const totVlCof = entries.reduce((s, e) => s + e.vlCof, 0)

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'CFOPs tributados', val: String(entries.length), color: 'text-blue-400' },
          { label: 'Total BC PIS', val: 'R$ ' + fmtN(totBcPis), color: 'text-blue-400' },
          { label: 'Total PIS', val: 'R$ ' + fmtN(totVlPis), color: 'text-emerald-400' },
          { label: 'Total COFINS', val: 'R$ ' + fmtN(totVlCof), color: 'text-purple-400' },
        ].map(c => (
          <div key={c.label} className="bg-bg2 border border-border rounded-xl p-4">
            <div className={`text-2xl font-semibold font-mono mb-1 ${c.color}`}>{c.val}</div>
            <div className="text-xs uppercase tracking-wide text-gray-500">{c.label}</div>
          </div>
        ))}
      </div>

      <div className="bg-bg2 border border-border rounded-xl p-5">
        <div className="text-xs uppercase tracking-widest text-gray-500 mb-4">
          Alíquota PIS efetiva por CFOP — top 20 por volume
        </div>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={entries} margin={{ top: 4, right: 8, bottom: 40, left: 8 }}>
            <XAxis dataKey="cfop" tick={{ fontSize: 10, fill: '#4a5568', fontFamily: 'IBM Plex Mono' }}
              angle={-45} textAnchor="end" interval={0} />
            <YAxis tick={{ fontSize: 10, fill: '#4a5568' }} tickFormatter={v => `${v}%`} />
            <Tooltip
              contentStyle={{ background: '#1e2330', border: '1px solid #2a3040', borderRadius: 8, fontSize: 12 }}
              formatter={(val: any) => [`${val}%`, 'Alíq. PIS']} />
            <Bar dataKey="aliqPis" radius={[4, 4, 0, 0]}>
              {entries.map((e, i) => (
                <Cell key={i} fill={aliqPisOk(e.aliqPis) ? '#00d084' : '#ffb347'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="bg-bg2 border border-border rounded-xl overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border">
              {['CFOP','Alíq. PIS','BC PIS','VL PIS','Alíq. COFINS','BC COFINS','VL COFINS','Vol. itens','Docs'].map(h => (
                <th key={h} className="text-left px-3 py-3 text-gray-500 uppercase tracking-wide font-medium text-xs">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {entries.map((e, i) => {
              const okPis = aliqPisOk(e.aliqPis)
              const okCof = aliqCofOk(e.aliqCof)
              const pct = maxVl > 0 ? Math.round(e.vlItem / maxVl * 100) : 0
              return (
                <tr key={i} className="border-b border-border hover:bg-bg3 transition-colors">
                  <td className="px-3 py-2.5 font-mono font-medium">{e.cfop}</td>
                  <td className={`px-3 py-2.5 font-mono ${okPis ? 'text-green' : 'text-amber-400'}`}>
                    {e.aliqPis.toFixed(2)}%
                  </td>
                  <td className="px-3 py-2.5 font-mono text-gray-300">{fmtN(e.bcPis)}</td>
                  <td className="px-3 py-2.5 font-mono text-emerald-400">{fmtN(e.vlPis)}</td>
                  <td className={`px-3 py-2.5 font-mono ${okCof ? 'text-green' : 'text-amber-400'}`}>
                    {e.aliqCof.toFixed(2)}%
                  </td>
                  <td className="px-3 py-2.5 font-mono text-gray-300">{fmtN(e.bcCof)}</td>
                  <td className="px-3 py-2.5 font-mono text-purple-400">{fmtN(e.vlCof)}</td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-2 bg-bg3 rounded overflow-hidden">
                        <div className="h-full bg-blue-500/60 rounded" style={{ width: `${pct}%` }} />
                      </div>
                      <span className="font-mono text-gray-400 w-16 text-right">{fmtN(e.vlItem)}</span>
                    </div>
                  </td>
                  <td className="px-3 py-2.5 font-mono text-gray-500">{e.n}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
